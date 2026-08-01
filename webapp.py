#!/usr/bin/env python3
"""
pywebview desktop shell for Very Thoughtful Normalisation (but in a good way).

    pip install pywebview
    python3 webapp.py [/path/to/vtdn_app.html]

`vtdn_app.html` is a self-contained design that also runs standalone in a
browser on mock data. When it runs *inside* this shell, the bridge below
feature-detects `window.pywebview` and swaps the mock seams for real engine
calls:

    pickSource() -> Api.pick_source()   native dialog + background scan
    pickDest()   -> Api.pick_dest()     native dialog
    startRun()   -> Api.run()           normalizer.normalize_audio streamed back

`normalizer.py` is the engine and stays UI-agnostic — this is its third
front-end, alongside the manual CLI and the autowatch daemon.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import normalizer

APP_NAME = "Very Thoughtful Normalisation (but in a good way)"

log = logging.getLogger("vtn.app")


# ── logging ──────────────────────────────────────────────────────────────────
# A packaged app has no console, so anything worth seeing goes to a file the
# user can hand back. The path is printed and logged on startup.
def _log_path() -> Path:
    if sys.platform == "darwin":
        d = Path.home() / "Library" / "Logs"
    elif os.name == "nt":
        d = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "VTNormalisation"
    else:
        d = Path.home() / ".local" / "state" / "vtnormalisation"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        d = Path(tempfile.gettempdir())
    return d / "VTNormalisation.log"


def _setup_logging() -> Path:
    path = _log_path()
    if not log.handlers:
        log.setLevel(logging.DEBUG)
        try:
            fh = logging.FileHandler(path, encoding="utf-8")
            fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)-5s %(message)s"))
            log.addHandler(fh)
        except OSError:
            log.addHandler(logging.NullHandler())
    return path


def _install_crash_handlers() -> None:
    """Without these a crash just ends the log with no reason."""
    def _main_hook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        log.critical("UNCAUGHT (main thread)", exc_info=(exc_type, exc, tb))
    sys.excepthook = _main_hook

    def _thread_hook(args):
        if issubclass(args.exc_type, SystemExit):
            return
        log.critical("UNCAUGHT (thread %s)", getattr(args.thread, "name", "?"),
                     exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
    try:
        threading.excepthook = _thread_hook
    except Exception:  # noqa: BLE001
        pass


def _resource_base() -> Path:
    """Bundled resources live beside the executable in a frozen app, beside this
    file when run from source."""
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) if base else Path(__file__).resolve().parent


_FFMPEG_VERSION: str | None = None


def _ffmpeg_version() -> str:
    """
    Short version for the brow readout, e.g. '8.1.2'. Best effort, cached.

    The timeout is deliberately generous. When the bundled ffmpeg is x86_64 and
    the Mac is Apple Silicon, the very FIRST exec pays for Rosetta translating a
    77 MB binary — measured at over 5 seconds, after which it runs in ~0.05s.
    A short timeout here meant the brow permanently read "ffmpeg —" on first
    launch, which looked like a broken install rather than a one-off warm-up.
    """
    global _FFMPEG_VERSION
    if _FFMPEG_VERSION is not None:
        return _FFMPEG_VERSION
    version = "?"
    try:
        out = subprocess.run([normalizer.resolve_ffmpeg(), "-version"],
                             capture_output=True, text=True,
                             stdin=subprocess.DEVNULL, timeout=60).stdout
        m = re.search(r"ffmpeg version (\S+)", out)
        if m:
            version = m.group(1).split("-")[0]
    except Exception:  # noqa: BLE001
        pass
    _FFMPEG_VERSION = version
    return version


# ── the JS bridge, injected once the page has loaded ─────────────────────────
_BRIDGE_JS = r"""
(function(){
  if(!window.pywebview || !window.pywebview.api){ return; }   // standalone: keep the mock
  const api = window.pywebview.api;

  // Take the format registry from the ENGINE rather than the copy baked into the
  // page, so the two can never drift apart.
  api.formats().then(f => {
    if(f && f.formats){ FORMATS = f.formats; BITRATES = f.bitrates; S.rate = f.default_bitrate; }
    if(f && f.ffmpeg){ document.getElementById('ffv').textContent = f.ffmpeg; }
    drawSegs(); drawRate(); drawGuarantee(); gate();
  }).catch(()=>{});

  // Folder pick returns the path immediately; the scan (which probes every file
  // to count what's lossless) runs in the background so the button never freezes.
  window.pickSource = async () => {
    const r = await api.pick_source();
    if(!r || !r.dir) return;                       // cancelled
    S.src = r.dir; setPath('src', S.src);
    S.scan = null; S.scanning = true;
    drawGuarantee(); gate();
  };
  window.pickDest = async () => {
    const r = await api.pick_dest();
    if(!r || !r.dir) return;
    S.dst = r.dir; setPath('dst', S.dst); gate();
  };

  // Scan callbacks: the file count lands first (fast), then the lossless
  // breakdown refines as files are probed.
  window.__vtdnScan = (info) => {
    if(!S.src || info.dir !== S.src) return;       // a newer pick superseded it
    S.scan = info; S.scanning = !info.final;
    drawGuarantee(); gate();
  };

  // Run callbacks.
  window.__vtdnStart  = (total, est, files) => { pgStart(total, est, files); };
  window.__vtdnETA    = (sec)  => pgSetETA(sec);
  window.__vtdnFile   = (name, note) => pgFile(name, 0, {note: note||''});
  window.__vtdnResult = (row)  => pgDone1(row);
  window.__vtdnDone   = (sum)  => pgFinish(sum);

  window.startRun = () => {
    S.running = true; gate(); setState('Working','busy');
    api.run(S.fmt, S.rate);
  };
  window.cancelRun = () => { try { api.cancel_run(); } catch(e){} };
})();
"""


class Api:
    """Exposed to JS as `window.pywebview.api.*`. Everything returns JSON-able data."""

    def __init__(self) -> None:
        self.window = None
        self._src: Path | None = None
        self._dst: Path | None = None
        self._files: list[Path] = []
        self._scan_gen = 0
        # Set by cancel_run(); the run loop checks it BETWEEN tracks so the
        # ffmpeg currently encoding is always allowed to finish. Killing it
        # mid-write would leave a truncated file in the user's destination
        # folder that looks like a real output.
        self._cancel = threading.Event()

    # -- bridge helpers ------------------------------------------------------
    def _emit(self, fn: str, *args) -> None:
        if not self.window:
            return
        payload = ", ".join(json.dumps(a) for a in args)
        try:
            self.window.evaluate_js(f"window.{fn} && window.{fn}({payload})")
        except Exception:  # noqa: BLE001 — a closing window must not kill the worker
            pass

    # -- static data ---------------------------------------------------------
    def formats(self):
        """The engine's own format registry, reshaped for the UI."""
        log.info("formats(): bridge connected")
        return {
            "formats": {
                key: {
                    "label": "AAC" if key == "aac" else key.upper(),
                    "lossy": spec["lossy"],
                    "preserves": spec["preserves"],
                    "gear": spec["gear"],
                    "blurb": spec["blurb"],
                }
                for key, spec in normalizer.OUTPUT_FORMATS.items()
            },
            "bitrates": list(normalizer.BITRATES),
            "default_bitrate": normalizer.DEFAULT_BITRATE,
            "ffmpeg": _ffmpeg_version(),
        }

    # -- folder pickers ------------------------------------------------------
    def _show_folder_dialog(self):
        """
        Open the native folder picker and return pywebview's raw result.

        On Windows this MUST run on pywebview's GUI thread. That thread is
        created STA (webview/platforms/winforms.py — SetApartmentState(STA)),
        while our js_api methods run on a separate, MTA, thread. The Windows
        folder picker is the Vista COM IFileDialog, and showing a COM dialog
        from an MTA thread hangs outright — which is exactly what happened:
        the app launched fine, then froze the moment a folder was chosen.

        pywebview's Window.create_file_dialog does no marshalling of its own, so
        we do it here, the same way pywebview does internally for secondary
        windows: hand the call to the form's Invoke so it executes on the
        owning GUI thread.

        macOS and Linux have no such requirement and call straight through.
        """
        import webview

        if sys.platform != "win32":
            return self.window.create_file_dialog(webview.FOLDER_DIALOG)

        try:
            from System import Func, Type                          # pythonnet
            from webview.platforms.winforms import BrowserView
        except Exception as e:  # noqa: BLE001
            log.warning("windows: cannot reach the WinForms host (%s); "
                        "calling the dialog directly", e)
            return self.window.create_file_dialog(webview.FOLDER_DIALOG)

        form = BrowserView.instances.get(self.window.uid)
        if form is None:
            log.warning("windows: no form for uid %s; calling the dialog directly",
                        self.window.uid)
            return self.window.create_file_dialog(webview.FOLDER_DIALOG)

        box = {}

        def _on_gui_thread():
            try:
                box["result"] = self.window.create_file_dialog(webview.FOLDER_DIALOG)
            except Exception:  # noqa: BLE001 — must not kill the GUI thread
                log.exception("windows: folder dialog raised on the GUI thread")
                box["result"] = None
            return None

        log.info("windows: showing the folder dialog on the GUI thread")
        form.Invoke(Func[Type](_on_gui_thread))
        log.info("windows: folder dialog closed")
        return box.get("result")

    def _pick(self):
        picked = self._show_folder_dialog()
        if not picked:
            return None
        return Path(picked[0] if isinstance(picked, (list, tuple)) else picked)

    def pick_source(self):
        d = self._pick()
        if d is None:
            return None
        self._src = d
        self._scan_gen += 1
        threading.Thread(target=self._scan, args=(d, self._scan_gen), daemon=True).start()
        log.info("source: %s", d)
        return {"dir": str(d)}

    def pick_dest(self):
        d = self._pick()
        if d is None:
            return None
        self._dst = d
        log.info("destination: %s", d)
        return {"dir": str(d)}

    def _scan(self, src: Path, gen: int) -> None:
        """
        Classify the folder, fast.

        The first version probed EVERY file with `ffmpeg -i` before the app
        became usable. On a real library that is thousands of process spawns —
        minutes of "Reading your tracks…" with NORMALIZE held disabled the whole
        time. Worse on Apple Silicon, where a bundled x86_64 ffmpeg pays Rosetta
        on every one.

        The extension already answers it (normalizer.lossless_by_extension) with
        no subprocess at all, so the counts appear instantly. Only two things
        still want a probe, and neither blocks anything:

          - '.m4a', which is ALAC (lossless) or AAC (lossy)
          - the >48 kHz count, a detail the guarantee line can add late

        Both are refined in the background; the scan is final as soon as the
        instant pass is done.
        """
        files = normalizer.find_audio_files(src)
        if self._src != src or gen != self._scan_gen:
            return
        self._files = files
        total = len(files)
        if not total:
            self._emit("__vtdnScan", {"dir": str(src), "total": 0, "lossless": 0,
                                      "lossy": 0, "hires": 0, "final": True})
            log.info("scan: %s -> no supported audio files", src)
            return

        lossless = lossy = 0
        unknown = []
        for f in files:
            known = normalizer.lossless_by_extension(f)
            if known is True:
                lossless += 1
            elif known is False:
                lossy += 1
            else:
                unknown.append(f)               # .m4a — needs a probe

        # Publish immediately. Anything still unknown counts as lossy for now:
        # understating how much is lossless is the safe direction to be wrong
        # in, because it never promises a guarantee we can't keep.
        self._emit("__vtdnScan", {"dir": str(src), "total": total,
                                  "lossless": lossless, "lossy": lossy + len(unknown),
                                  "hires": 0, "final": True})
        log.info("scan: %s -> %d files (%d lossless, %d lossy, %d to probe), one pass",
                 src, total, lossless, lossy, len(unknown))

        threading.Thread(target=self._refine,
                         args=(src, gen, total, lossless, lossy, unknown),
                         daemon=True).start()

    def _refine(self, src: Path, gen: int, total: int,
                lossless: int, lossy: int, unknown: list) -> None:
        """
        Background detail pass: resolve .m4a, then count sources above 48 kHz.

        Purely additive — the UI is already usable and the run can already be
        started. Bails the moment a newer folder pick supersedes it.
        """
        def stale():
            return self._src != src or gen != self._scan_gen

        for f in unknown:
            if stale():
                return
            if normalizer.probe_source(str(f)).get("lossless"):
                lossless += 1
            else:
                lossy += 1
        if unknown and not stale():
            self._emit("__vtdnScan", {"dir": str(src), "total": total, "lossless": lossless,
                                      "lossy": lossy, "hires": 0, "final": True})

        # The >48 kHz count needs a real probe of each lossless file. Only worth
        # doing for a library small enough to finish while the user is still
        # looking at the screen; beyond that the guarantee line omits it rather
        # than churning for minutes on a detail.
        HIRES_PROBE_LIMIT = 400
        candidates = [f for f in self._files
                      if normalizer.lossless_by_extension(f) is not False]
        if len(candidates) > HIRES_PROBE_LIMIT:
            log.info("scan: skipping >48k probe (%d lossless files, limit %d)",
                     len(candidates), HIRES_PROBE_LIMIT)
            return

        hires = 0
        for f in candidates:
            if stale():
                return
            rate = normalizer.probe_source(str(f)).get("sample_rate")
            if rate and rate > normalizer.MAX_GEAR_SAMPLE_RATE:
                hires += 1
        if not stale():
            self._emit("__vtdnScan", {"dir": str(src), "total": total, "lossless": lossless,
                                      "lossy": lossy, "hires": hires, "final": True})
            log.info("scan: refined -> %d lossless, %d lossy, %d above 48k",
                     lossless, lossy, hires)

    # -- the run -------------------------------------------------------------
    def run(self, output_format: str, bitrate: int):
        if self._src is None or self._dst is None:
            return {"error": "source and destination are both required"}
        self._cancel.clear()               # drop any stop left over from a prior run
        threading.Thread(target=self._run_worker,
                         args=(str(output_format), int(bitrate)), daemon=True).start()
        return {"started": True}

    def cancel_run(self):
        """
        Ask the run to stop after the track currently being encoded.

        Deliberately graceful rather than killing ffmpeg: a half-written AIFF
        sitting in the destination alongside the real outputs is worse than
        waiting a few seconds for one track to land cleanly.
        """
        self._cancel.set()
        log.info("cancel requested")
        return {"stopping": True}

    def _run_worker(self, output_format: str, bitrate: int) -> None:
        src, dst = self._src, self._dst
        files = self._files or normalizer.find_audio_files(src)
        total = len(files)
        log.info("run: %d file(s) %s -> %s as %s%s", total, src, dst, output_format,
                 f" @{bitrate}k" if normalizer.OUTPUT_FORMATS[output_format]["lossy"] else "")

        try:
            Path(dst).mkdir(parents=True, exist_ok=True)
        except OSError as e:
            log.error("cannot create destination: %s", e)
            self._emit("__vtdnDone", {"ok": 0, "fail": total,
                                      "note": f"could not create the destination folder: {e}"})
            return

        # Seed the clock with a rough per-file cost, then replace it with the
        # measured average as soon as a few files have actually finished — two
        # ffmpeg passes over a track vary far too much to predict up front.
        SEED_SECONDS_PER_FILE = 9.0
        self._emit("__vtdnStart", total, int(total * SEED_SECONDS_PER_FILE),
                   [f.name for f in files[:2000]])

        t0 = time.monotonic()
        ok = fail = 0
        cancelled = False
        # Output names are stem + new extension, so two sources sharing a stem
        # ("set01.flac" and "set01.mp3") both map to "set01.aiff" and the second
        # would silently overwrite the first — losing a track while still
        # reporting two successes. Refuse the collision instead: nothing is lost
        # and the user is told which pair clashed.
        written: dict[str, str] = {}
        for i, f in enumerate(files, 1):
            if self._cancel.is_set():
                cancelled = True
                log.info("run cancelled after %d of %d", i - 1, total)
                break
            self._emit("__vtdnFile", f.name, "analyzing…")
            out = normalizer.get_output_filename(str(f), str(dst), output_format)
            clash = written.get(out)
            if clash is not None:
                fail += 1
                msg = (f"would overwrite the output already written from "
                       f"{clash} — both files are named "
                       f"\"{Path(f).stem}\". Rename one and run again.")
                log.error("  SKIP %s: %s", f.name, msg)
                self._emit("__vtdnResult", {"f": f.name, "t": "fail", "msg": msg})
                continue
            try:
                success, message = normalizer.normalize_audio(
                    str(f), out, output_format=output_format, bitrate=bitrate)
            except Exception as e:  # noqa: BLE001 — one bad file must not end the run
                log.exception("unexpected failure on %s", f.name)
                success, message = False, f"unexpected error: {e}"

            if success:
                ok += 1
                written[out] = f.name
            else:
                fail += 1
                log.error("  FAIL %s: %s", f.name, message)
            self._emit("__vtdnResult", {"f": f.name, "t": "ok" if success else "fail",
                                        "msg": "" if success else message})

            elapsed = time.monotonic() - t0
            if i >= 3:
                self._emit("__vtdnETA", round((total - i) * (elapsed / i)))

        mins = max(1, round((time.monotonic() - t0) / 60))
        if cancelled:
            note = (f"Stopped after {ok + fail} of {total} tracks. "
                    f"The {ok} already written {'is' if ok == 1 else 'are'} complete "
                    f"and safe to use; the rest were not touched.")
        else:
            note = (f"{ok} track{'' if ok == 1 else 's'} levelled to −12 LUFS "
                    f"in about {mins} minute{'' if mins == 1 else 's'}.")
        if fail:
            note += f" {fail} could not be processed — see below."
        log.info("run done: %d ok, %d failed, %d min%s",
                 ok, fail, mins, " (cancelled)" if cancelled else "")
        self._emit("__vtdnDone", {"ok": ok, "fail": fail, "note": note,
                                  "cancelled": cancelled})


# ── window geometry ──────────────────────────────────────────────────────────
# pywebview's create_window supports width/height/min_size/resizable — but it has
# NO max_size and no aspect-ratio lock. Those exist only on the native window, so
# they are applied below, best-effort, once the window is up.
WIN_W, WIN_H = 980, 880
MIN_W, MIN_H = 720, 640
MAX_W, MAX_H = 1400, 1260

# Fixed window. The interface is a single centred card of fixed max width with a
# progress sheet over it — there is nothing here that benefits from being
# resized, and a fixed window means the layout can never be dragged into a shape
# nobody checked. Set False to allow resizing between MIN_* and MAX_*.
FIXED_SIZE = True
LOCK_ASPECT = False          # only consulted when FIXED_SIZE is False


def _constrain_window(window) -> None:
    """
    Apply a maximum size and (optionally) an aspect-ratio lock.

    macOS only, and entirely optional: pywebview exposes the underlying NSWindow
    as `window.native`, which understands both. Wrapped in a broad try/except
    because the attribute and its type vary across pywebview versions and
    backends — failing to pin a maximum size must never stop the app opening.
    """
    if FIXED_SIZE or sys.platform != "darwin":
        return                       # resizable=False already fixes size AND ratio
    try:
        native = getattr(window, "native", None)
        if native is None:
            return
        # A BrowserView-ish wrapper may hold the real NSWindow.
        nswindow = getattr(native, "window", None) or native
        setter = getattr(nswindow, "setContentMaxSize_", None)
        if setter is None:
            log.info("window: native has no setContentMaxSize_, leaving unconstrained")
            return
        from Foundation import NSMakeSize  # type: ignore
        setter(NSMakeSize(MAX_W, MAX_H))
        if LOCK_ASPECT:
            ratio = getattr(nswindow, "setContentAspectRatio_", None)
            if ratio is not None:
                ratio(NSMakeSize(WIN_W, WIN_H))
        log.info("window: max %dx%d, aspect_lock=%s", MAX_W, MAX_H, LOCK_ASPECT)
    except Exception as e:  # noqa: BLE001 — cosmetic only
        log.info("window: could not constrain natively (%s)", e)


def main(argv: list[str] | None = None) -> int:
    log_path = _setup_logging()
    _install_crash_handlers()
    try:
        import webview
    except ModuleNotFoundError:
        print("pywebview is required:  pip install pywebview", file=sys.stderr)
        return 1

    argv = sys.argv[1:] if argv is None else argv
    html = Path(argv[0]) if argv else _resource_base() / "vtdn_app.html"
    if not html.is_file():
        print(f"HTML not found: {html}", file=sys.stderr)
        return 2

    log.info("=== %s starting ===", APP_NAME)
    log.info("python %s on %s (%s)", platform.python_version(),
             platform.platform(), platform.machine())
    log.info("frozen=%s  resources=%s", bool(getattr(sys, "_MEIPASS", None)), _resource_base())
    # Path only — deliberately NOT the version. Probing it here would run ffmpeg
    # on the critical path to showing a window, and on a first Rosetta launch
    # that stalls the app for seconds with nothing on screen. The version is
    # fetched later by formats(), once the page is already up.
    log.info("ffmpeg -> %s", normalizer.resolve_ffmpeg())
    print(f"{APP_NAME} — debug log: {log_path}")

    # Warm the version cache off the critical path so the brow fills in as soon
    # as the page asks for it, even on a cold Rosetta start.
    threading.Thread(target=_ffmpeg_version, daemon=True).start()

    # The page loads over file:// and pulls gui_assets/background.png as a
    # sibling, so it has to be served from a directory containing both. In a
    # frozen app they already sit together; from source they do too.
    api = Api()
    window = webview.create_window(APP_NAME, str(html), js_api=api,
                                   width=WIN_W, height=WIN_H,
                                   min_size=(WIN_W, WIN_H) if FIXED_SIZE else (MIN_W, MIN_H),
                                   resizable=not FIXED_SIZE,
                                   background_color="#0E1217")
    api.window = window
    window.events.loaded += lambda: (log.info("window loaded"),
                                     window.evaluate_js(_BRIDGE_JS),
                                     _constrain_window(window))

    # Record which GUI backend pywebview resolved BEFORE handing control to it.
    # On Windows the host is webview.platforms.winforms running on pythonnet; if
    # that cannot load, the app shows a window and then hangs with no error
    # anywhere. A hang is not a crash, so the exception handler below never
    # fires and the log would otherwise just stop — leaving nothing to go on.
    try:
        import webview.guilib as _guilib
        log.info("pywebview backend: %s", getattr(_guilib, "guilib", None) or "not yet resolved")
    except Exception as e:  # noqa: BLE001
        log.warning("could not determine pywebview backend: %s", e)
    log.info("calling webview.start() — anything after this is the GUI loop")

    try:
        webview.start()
    except Exception:
        log.critical("webview.start() crashed", exc_info=True)
        raise
    log.info("=== app exited normally ===")
    return 0


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    raise SystemExit(main())
