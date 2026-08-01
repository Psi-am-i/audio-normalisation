#!/usr/bin/env python3
"""
GUI smoke test — exercises the real shell code without opening a window.

The interface is HTML in a webview, so there are no widgets to poke. What CAN
break silently is the seam between the two halves, and that is what this covers:

  - webapp imports, and the interface file is present and well-formed
  - Api.formats() matches the engine registry exactly (the HTML has its own
    literal copy for standalone use; the shell overwrites it on load, and this
    asserts the shape the bridge relies on)
  - every JS callback the bridge invokes actually exists in the HTML
  - the background is referenced as a RELATIVE sibling — an absolute or
    file:// path here is the classic "black window in the packaged app" bug
  - the scan classifies lossless/lossy/hi-res correctly on generated audio

Needs ffmpeg. Does NOT need a display, pywebview, or tkinter.
Run:  python3 tests/test_gui_smoke.py
"""

import re
import subprocess
import time
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import normalizer  # noqa: E402
import webapp      # noqa: E402

REPO = Path(__file__).resolve().parent.parent
HTML = REPO / "vtdn_app.html"
FFMPEG = normalizer.resolve_ffmpeg()

PASS = 0
FAIL = 0


def check(label, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}  {detail}")


def main():
    print("[interface file]")
    check("vtdn_app.html exists", HTML.is_file(), str(HTML))
    if not HTML.is_file():
        print("\nFAILURES: cannot continue without the interface")
        sys.exit(1)
    html = HTML.read_text(encoding="utf-8")

    check("fonts are bundled (not fetched from a CDN)",
          "@font-face" in html and "data:font" in html)
    # A strict check: no http(s) asset can be referenced, because the packaged
    # app has no network guarantee and WKWebView would just leave a blank slot.
    remote = re.findall(r'(?:src|href)\s*=\s*["\']https?://', html)
    check("no remote assets referenced", not remote, f"found {len(remote)}")

    # The background must resolve NEXT TO the html inside the bundle.
    bg = re.search(r"url\(['\"]([^'\"]*background\.png)['\"]\)", html)
    check("background referenced", bg is not None)
    if bg:
        path = bg.group(1)
        check("background path is a relative sibling",
              path == "gui_assets/background.png", f"got {path!r}")

    print()
    print("[bridge contract]")
    # The shell pushes results into the page by evaluating `window.__vtdnX(...)`,
    # and the bridge is what defines those handlers. A name emitted by Python
    # with no matching assignment in the bridge is a silent no-op — the run would
    # appear to hang with an empty progress sheet. Assert the two sides agree.
    bridge_src = webapp._BRIDGE_JS
    shell_src = Path(webapp.__file__).read_text(encoding="utf-8")
    emitted = set(re.findall(r'_emit\(\s*["\'](__vtdn\w+)["\']', shell_src))
    handled = set(re.findall(r'window\.(__vtdn\w+)\s*=', bridge_src))
    check("shell emits at least one callback", bool(emitted), str(emitted))
    for name in sorted(emitted):
        check(f"bridge handles {name}", name in handled,
              f"emitted by webapp.py but never assigned in the bridge")
    for name in sorted(handled - emitted):
        check(f"bridge handler {name} is actually used", False,
              "assigned in the bridge but nothing emits it (dead handler)")

    # Every page function the bridge calls must be defined in the HTML.
    for fn in ("pgStart", "pgFile", "pgDone1", "pgFinish", "pgSetETA",
               "drawSegs", "drawRate", "drawGuarantee", "gate", "setPath", "setState"):
        check(f"page defines {fn}()", re.search(rf"function {fn}\b", html) is not None)

    # Seams the bridge REPLACES rather than calls: the page ships a mock, the
    # shell overrides it. Both halves must exist or Stop/Start silently no-op.
    for seam, api_method in (("pickSource", "pick_source"), ("pickDest", "pick_dest"),
                             ("startRun", "run"), ("cancelRun", "cancel_run")):
        check(f"page ships a {seam} mock", f"window.{seam} =" in html)
        check(f"bridge overrides {seam}", f"window.{seam} =" in bridge_src)
        check(f"Api.{api_method}() exists", hasattr(webapp.Api, api_method))

    print()
    print("[Api.formats() matches the engine]")
    api = webapp.Api()
    f = api.formats()
    check("same format keys as the engine",
          list(f["formats"]) == list(normalizer.OUTPUT_FORMATS),
          str(list(f["formats"])))
    for key, spec in normalizer.OUTPUT_FORMATS.items():
        got = f["formats"][key]
        check(f"{key}: lossy/preserves/gear carried over",
              got["lossy"] == spec["lossy"]
              and got["preserves"] == spec["preserves"]
              and got["gear"] == spec["gear"])
    check("bitrates match", f["bitrates"] == list(normalizer.BITRATES))
    check("default bitrate matches", f["default_bitrate"] == normalizer.DEFAULT_BITRATE)
    # The HTML's standalone literal must carry the same keys, or a browser run
    # of the design silently drifts from the shipped app.
    for key in normalizer.OUTPUT_FORMATS:
        check(f"html literal knows {key}", re.search(rf"\b{key}\s*:\s*\{{", html) is not None)

    print()
    print("[scan classifies sources]")
    with tempfile.TemporaryDirectory(prefix="vtdn_smoke_") as tmp:
        d = Path(tmp)
        specs = [
            ("lossless_44k.flac", ["-c:a", "flac"], 44100),
            ("lossless_48k.aiff", ["-c:a", "pcm_s24be"], 48000),
            ("hires_96k.flac", ["-c:a", "flac", "-sample_fmt", "s32"], 96000),
            ("lossy.mp3", ["-c:a", "libmp3lame", "-b:a", "320k"], 44100),
        ]
        for name, codec, rate in specs:
            subprocess.run(
                [FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
                 "-f", "lavfi", "-i", f"anoisesrc=d=1:c=pink:r={rate}:a=0.4",
                 "-ac", "2", *codec, str(d / name)],
                check=True, capture_output=True)

        seen = []
        api._emit = lambda fn, *a: seen.append((fn, a))
        api._src = d
        api._scan_gen = 1

        t0 = time.monotonic()
        api._scan(d, 1)
        elapsed = time.monotonic() - t0

        # Regression guard. The scan used to run `ffmpeg -i` on EVERY file
        # before the UI unblocked, which took minutes on a real library. The
        # first pass must now classify by extension alone — no subprocesses —
        # so it has to be effectively instant even though these files exist.
        check(f"first pass is instant ({elapsed*1000:.0f}ms)", elapsed < 0.5,
              "extension-based classification must not spawn ffmpeg")

        first = [a[0] for fn, a in seen if fn == "__vtdnScan"][0]
        check("first result is already final (never blocks the UI)",
              first.get("final") is True, str(first))
        check("total = 4", first["total"] == 4, str(first))
        check("lossless = 3 immediately", first["lossless"] == 3, str(first))
        check("lossy = 1 immediately", first["lossy"] == 1, str(first))

        # The >48 kHz count is a background detail that lands afterwards.
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            last = [a[0] for fn, a in seen if fn == "__vtdnScan"][-1]
            if last.get("hires"):
                break
            time.sleep(0.2)
        last = [a[0] for fn, a in seen if fn == "__vtdnScan"][-1]
        check("hires (>48k) = 1 after refinement", last["hires"] == 1, str(last))
        check("refinement kept the counts", last["lossless"] == 3 and last["lossy"] == 1,
              str(last))

    print()
    print(f"{'ALL PASS' if FAIL == 0 else 'FAILURES'}: {PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
