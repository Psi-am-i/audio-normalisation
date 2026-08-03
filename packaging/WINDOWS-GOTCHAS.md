# Windows build gotchas — Python + pywebview + PyInstaller

Every problem below was hit for real shipping this app, in this order, each one
hiding behind the last. All were invisible on macOS and none failed the build.
Wire them in up front and a Windows build should work first time.

**Architecture this applies to:** a Python engine, a pywebview desktop shell
loading a self-contained HTML interface, frozen with PyInstaller (onedir,
`console=False`), bundling a static `ffmpeg.exe`. Applies equally to
Very Thoughtful Compression.

The theme, if you want one sentence: **the Windows GUI lives on a thread and in
a process model that macOS doesn't have, and the packaging layer silently drops
things the import graph can't see.**

---

## 1. The app launches and hangs, with nothing logged

**Symptom.** A window appears, then the process is unresponsive and needs a
force quit. No error, no traceback, and the log stops after startup.

**Cause.** pywebview on Windows does *not* load the EdgeChromium module
directly. It loads `webview.platforms.winforms` — a .NET WinForms host running
on **pythonnet** — and EdgeChromium is only the renderer *inside* that host
(see `webview/guilib.py`, `import_winforms`). Declaring only
`webview.platforms.edgechromium` leaves the host itself unbundled. Worse,
`clr_loader` ships runtime DLLs and `.runtimeconfig.json` as **data** files,
which PyInstaller cannot discover from an import graph at all.

pythonnet *is* installed at build time (pywebview declares it for `win32`), so
nothing fails during the build. The pieces simply never reach the app.

**Fix.** In the Windows spec:

```python
from PyInstaller.utils.hooks import collect_all

_pn_datas, _pn_bins, _pn_hidden = collect_all('pythonnet')
_cl_datas, _cl_bins, _cl_hidden = collect_all('clr_loader')

a = Analysis(
    ...,
    binaries=[(ffmpeg, '.'), *_pn_bins, *_cl_bins],
    datas=[(html, '.'), *_pn_datas, *_cl_datas],
    hiddenimports=[
        'webview',
        'webview.platforms.winforms',      # the actual Windows host
        'webview.platforms.edgechromium',  # the renderer it uses
        'clr', 'clr_loader',
        *_pn_hidden, *_cl_hidden,
    ],
)
```

---

## 2. Opening a file/folder dialog hangs the app

**Symptom.** The app runs fine until you click a "Choose folder" button, then it
spins forever.

**Cause.** pywebview creates its GUI on a dedicated **STA** thread
(`winforms.py`: `thread.SetApartmentState(ApartmentState.STA)`), but `js_api`
methods run on a **separate, MTA thread** — `js_bridge_call` deliberately uses a
worker thread so Python can't block the UI. The Windows folder picker is the
Vista COM `IFileDialog`, and showing a COM dialog from an MTA thread hangs
outright. `Window.create_file_dialog` does no marshalling of its own.

**Fix.** Marshal onto the owning form's thread — the same mechanism pywebview
uses internally for secondary windows:

```python
def _show_folder_dialog(self):
    import webview
    if sys.platform != 'win32':
        return self.window.create_file_dialog(webview.FOLDER_DIALOG)

    from System import Func, Type                     # pythonnet
    from webview.platforms.winforms import BrowserView
    form = BrowserView.instances.get(self.window.uid)
    if form is None:                                  # fall back rather than crash
        return self.window.create_file_dialog(webview.FOLDER_DIALOG)

    box = {}
    def _on_gui_thread():
        box['result'] = self.window.create_file_dialog(webview.FOLDER_DIALOG)
        return None
    form.Invoke(Func[Type](_on_gui_thread))
    return box.get('result')
```

Guard by platform — macOS and Linux have no such requirement.

---

## 3. A console window flashes for every subprocess

**Symptom.** Console windows strobe open and shut — one per file during a scan,
another per file while processing. Everything works; it just looks broken and
steals focus continuously.

**Cause.** A windowed app (`console=False`) has **no console of its own**, so
Windows creates a fresh one for each child process. Spawning ffmpeg once per
file to probe and twice more to encode means ~150 console windows for 50 tracks.

**Fix.** `CREATE_NO_WINDOW` on *every* spawn:

```python
_NO_CONSOLE_WINDOW = (
    {'creationflags': subprocess.CREATE_NO_WINDOW}
    if sys.platform == 'win32' and hasattr(subprocess, 'CREATE_NO_WINDOW')
    else {}
)

subprocess.run([...], capture_output=True, text=True, **_NO_CONSOLE_WINDOW)
```

Worth a test that walks the AST and asserts every `subprocess.run` passes it —
one missed spawn brings the strobe back.

---

## 4. A filename fails its own track

**Symptom.**

```
unexpected error: 'charmap' codec can't encode character '' in position 64
```

Reported as a failed file. Nothing is wrong with the file.

**Cause.** Two separate instances of the same problem:

- **Printing.** Progress lines contain the filename; on Windows stdout is
  **cp1252**, which cannot represent accents, CJK, em dashes, or the
  private-use codepoints macOS substitutes for `/` in filenames. The
  `UnicodeEncodeError` propagates out of the encode.
- **Reading.** `subprocess.run(..., text=True)` decodes with the **locale**
  encoding — cp1252 again — while ffmpeg emits UTF-8.

**Fix.** Both ends:

```python
# at startup, before anything can print a filename
for name in ('stdout', 'stderr'):
    stream = getattr(sys, name, None)
    if stream is not None:
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass        # a windowed frozen app may have no stdout at all

# every subprocess
subprocess.run([...], text=True, encoding='utf-8', errors='replace')
```

Test with a real filename containing ``, an em dash and CJK, with stdout
pointed at a strict cp1252 stream — that reproduces it exactly on any OS.

---

## 5. "Not Responding" while completely idle

**Symptom.** The window renders correctly, the user touches nothing, and it sits
at "Not Responding" — recovering briefly, then stalling again.

**Cause.** Not Python. `js_bridge_call` already runs API methods on a worker
thread, so a slow bridge call cannot do this. "Not Responding" is a stalled
**Win32 message pump**, which means the renderer.

`backdrop-filter` is the usual culprit. Each layer forces WebView2 to
recomposite whatever is behind it, and if that's a fixed full-viewport
background image the compositor has continuous full-screen work on a completely
static page. This is a known stall under software rendering, which is common on
PCs and rare on Macs.

**Fix.** Drop `backdrop-filter` and make the panels more opaque instead. Over a
dark background the blur is barely perceptible anyway. Treat any expensive
always-on compositing (large blurs, big `box-shadow` spreads, permanent
animations) as suspect on WebView2.

---

## 6. Relative asset URLs silently don't load

**Symptom.** The app works, but an image referenced as
`url('assets/background.png')` never appears. No error in the log.

**Cause.** How the page is loaded differs per backend. macOS/WKWebView reads
from disk; Windows/WebView2 goes through pywebview's local bottle HTTP server.
Relative resolution is not equivalent, and a missing asset fails silently.

**Fix.** Don't depend on it. Inline assets as `data:` URIs at build time so the
shipped page has **no external references**. Keep the relative path in the
committed HTML so the page still works when served for design work.

Re-encode photos to JPEG on the way in — base64 inflates by a third, and the
webview parses the whole page at every launch. Here: 1974 KB PNG → 240 KB JPEG
→ a 581 KB page instead of 2.9 MB.

---

## 7. PyInstaller specifics that cost time

- **`WORKPATH` is not a spec global** in PyInstaller 6.x. Use `tempfile.mkdtemp()`
  for generated build artefacts.
- **`datas` preserves the source basename.** A generated file must literally be
  named `vtdn_app.html` if that's what the app looks up — writing
  `vtdn_app.inlined.html` ships under that name and is never found.
- **PyInstaller thins bundled binaries to the target architecture.** Handing it a
  universal ffmpeg from a single-arch Python silently discards the other slice.
  A universal app needs *both* a lipo'd binary *and* `target_arch='universal2'`
  *and* a universal2 interpreter. (macOS, but the same trap in spirit.)
- **With `noarchive=False`, pure-Python modules live inside the PYZ**, not as
  loose `.pyc` files. Verifying a bundle with `find … -name winforms.pyc` always
  "fails". Check PyInstaller's own `Analysis-00.toc` for modules; check the
  filesystem only for binaries and data.

---

## 8. Verify the bundle in CI — a hang is not a crash

Most of the above produce **no non-zero exit and no log output**, so CI happily
publishes a broken app. Assert the bundle's contents instead:

```bash
root=dist-win/VTNormalisation
toc=$(find build-win -name 'Analysis-00.toc' | head -1)

# binaries and data live on disk
need_file "Python.Runtime.dll"     # pythonnet <-> .NET bridge
need_file "ffmpeg.exe"
need_file "vtdn_app.html"

# assets must actually be inlined
grep -rq "url(.data:image" "$root" --include=vtdn_app.html

# modules come from the TOC, not the filesystem
need_mod "webview.platforms.winforms"
need_mod "webview.platforms.edgechromium"
need_mod "clr"
need_mod "clr_loader"
```

---

## 9. Things that look like bugs and aren't

- **An older instance still running.** Starting a new build while the previous
  one is open produced ~20 seconds of "Not Responding" that vanished once the
  old window was closed. Always close the old app and delete the old unzipped
  folder before testing.
- **WebView2 runtime.** The recipient needs it. It ships with Windows 11 and
  current Windows 10; on an older machine it installs once. Worth stating in the
  recipient README.
- **SmartScreen.** Unsigned builds prompt once — "More info → Run anyway".
  Nothing to fix short of a code-signing certificate.

---

## Pre-flight checklist

- [ ] `webview.platforms.winforms` in `hiddenimports` (not just `edgechromium`)
- [ ] `collect_all('pythonnet')` and `collect_all('clr_loader')`
- [ ] File dialogs marshalled onto the GUI thread on Windows
- [ ] `CREATE_NO_WINDOW` on every `subprocess` call
- [ ] stdout/stderr reconfigured to UTF-8 with `errors='replace'` at startup
- [ ] `encoding='utf-8', errors='replace'` on every subprocess
- [ ] No `backdrop-filter` or other always-on full-screen compositing
- [ ] Assets inlined as `data:` URIs, nothing relative
- [ ] Generated files keep the basename the app looks up
- [ ] Log to a file — a windowed app has no console
- [ ] CI asserts bundle contents, because a hang exits zero
