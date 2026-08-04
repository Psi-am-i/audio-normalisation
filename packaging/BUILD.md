# Building the distributable app

> **Building for Windows?** Read [WINDOWS-GOTCHAS.md](WINDOWS-GOTCHAS.md) first.
> Every issue in it was hit for real, none of them failed the build, and all
> were invisible on macOS.

This produces **VTNormal.app** — a windowed macOS app (pywebview / WKWebView)
that bundles Python, the interface and ffmpeg. Recipients install nothing.

The bundle is deliberately named `VTNormal.app`, with no spaces: the install
instructions ask people to paste a `codesign` line into Terminal, and a space in
the path means quoting that recipients get wrong. The full name
*Very Thoughtful Normalisation (but in a good way)* is the window title and
`CFBundleDisplayName` only.

## Build it

```bash
packaging/build_gui_app.sh
```

Two outputs, nothing else:

- `packaging/dist-gui/VTNormal.app` — double-click to run it here
- `packaging/dist-gui/VTNormal.zip` — **send this**

Everything under `packaging/build-gui/` is intermediate and safe to delete.

### Universal (Apple Silicon + Intel)

The build wants a **universal2 Python**, e.g.

```bash
PYTHON=/Library/Frameworks/Python.framework/Versions/3.11/bin/python3 packaging/build_gui_app.sh
```

This is not optional polish. PyInstaller **thins every bundled binary to the
target architecture**, so building from an arm64 Python silently discards the
x86_64 half of the universal ffmpeg and produces an "Intel-compatible" app that
is arm64-only. The script checks the interpreter and prints a plain warning if
it can only manage a native build, rather than mislabelling the result.

### ffmpeg source & licensing

Two static GPL builds are downloaded and `lipo`'d into one universal binary:

| arch | source | override |
|------|--------|----------|
| arm64 | ffmpeg.martin-riedl.de | `$FFMPEG_STATIC_ARM64` |
| x86_64 | evermeet.cx | `$FFMPEG_STATIC_X86_64` |

Each slice is gated before merging: the architecture must be what was asked
for, and `--enable-nonfree` builds are refused because they cannot be
redistributed. Both slices are then checked for `libmp3lame` and `aac` — a
universal binary whose arm64 half lacked an encoder would fail on exactly the
machines most people now use.

FFmpeg is GPLv3, so the zip carries `licenses/` (see `lib_licenses.sh`).

### The interface is inlined

`vtdn_app.html` references its background as a relative sibling, which is right
for development — serve the repo and open it in a browser. At build time
`inline_assets.py` produces a copy with the image embedded as a `data:` URI, and
that is what ships.

This is not tidiness. A relative path resolves under macOS/WKWebView but
silently does not under Windows/WebView2, which loads the page through
pywebview's local HTTP server — the app ran fine with no background at all. The
inlined page has no external references, so it cannot depend on how it is
served. The image is re-encoded to JPEG on the way in (1974 KB PNG → 240 KB).

The background itself comes from `make_bg.py`, which prefers a gitignored
personal `gui_assets/background_source.*` if present, then the tracked
`gui_assets/vinyl-texture.jpg`, then a procedural gradient. **The tracked
texture matters**: when only the gitignored name existed, every CI build fell
back to the gradient and shipped with no texture at all.

## Gatekeeper (unsigned app)

The app is unsigned, so macOS blocks it. Recipients self-sign once — the
approach Radarr and Sonarr use — **before** the first launch:

```bash
codesign --force --deep -s - /Applications/VTNormal.app && xattr -rd com.apple.quarantine /Applications/VTNormal.app
```

Order matters. Opening it first gets it blocked, and running the command
afterwards does **not** clear it: macOS has already recorded the refusal, and
the only way out is System Settings → Privacy & Security → *Open Anyway*, twice.

To sign properly instead, set `codesign_identity` in `normalizer-gui.spec` and
run `xcrun notarytool`. That needs an Apple Developer ID ($99/year).

## Windows

PyInstaller cannot cross-compile, so the Windows build only comes from the
`windows-latest` job in `.github/workflows/release.yml` (or a real Windows box)
using `normalizer-gui-win.spec`.

That job also **asserts the bundle's contents** — the .NET host, the interface,
a big enough inlined background. Most Windows failures in this stack produce no
non-zero exit and no log output, so without those checks CI happily publishes an
app that hangs. Again: [WINDOWS-GOTCHAS.md](WINDOWS-GOTCHAS.md).

## How the app is structured

```
VTNormal.app/Contents/
  MacOS/VTNormal          the launcher
  Frameworks/             Python, pywebview, pyobjc, universal ffmpeg
    vtdn_app.html         the interface, background inlined
  Resources/              icon, and the same payload via symlink
```

`normalizer.py` is the engine and is UI-agnostic; `webapp.py` is the shell that
drives it, and `vtdn_app.html` is the interface. The manual CLI (`normalize.py`)
and the autowatch daemon (`watcher.py`) are separate front-ends over the same
engine and are not part of this app.
