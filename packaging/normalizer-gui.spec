# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec — macOS build of "Very Thoughtful Normalisation (but in a good way)" (the GUI).

Produces a windowed macOS .app (WKWebView via pywebview) bundling:
  - the Python runtime + pywebview (+ the pyobjc cocoa backend)
  - the engine (normalizer.py) and the shell (webapp.py)
  - the interface: vtdn_app.html, loaded from the bundle root at runtime
  - the indigo-tinted background (gui_assets/background.png)
  - a static ffmpeg binary (resolved at runtime by normalizer.resolve_ffmpeg())

Only ffmpeg is bundled — NOT ffprobe. The engine deliberately reads stream
properties out of ffmpeg's own stderr (normalizer._parse_input_stream) so the
app never depends on a second binary. Don't "helpfully" add ffprobe here; the
code path that would use it does not exist.

vtdn_app.html and gui_assets/ land side by side at the bundle root, because the
page pulls the background as a RELATIVE sibling (url('gui_assets/background.png')).
Move one without the other and the app loads with a black window.

PIL/Pillow is build-time only (make_bg.py) and is excluded. tkinter is excluded
outright — the old tkinter front-end is gone.

PyInstaller cannot cross-compile; the Windows build uses normalizer-gui-win.spec
on a Windows runner.
"""

import os
import sys

repo_root = os.path.dirname(SPECPATH)
ffmpeg_binary = os.environ.get('FFMPEG_BINARY_PATH')
if not ffmpeg_binary or not os.path.exists(ffmpeg_binary):
    raise SystemExit(
        "FFMPEG_BINARY_PATH must point to a static ffmpeg binary. "
        "Run packaging/build_gui_app.sh, which sets it for you."
    )

# The interface is inlined at build time: the background becomes a data: URI so
# the shipped page has no external references. A relative sibling path works on
# macOS/WKWebView but silently failed to load under Windows/WebView2, which
# serves the page over pywebview's local HTTP server — the app ran fine but with
# no background at all. See packaging/inline_assets.py.
import subprocess as _sp
import tempfile as _tf

# WORKPATH is not a spec global in PyInstaller 6.x, and the file must keep
# the basename 'vtdn_app.html' because PyInstaller preserves it and
# webapp.py looks that name up in the bundle.
html = os.path.join(_tf.mkdtemp(prefix='vtn-inlined-'), 'vtdn_app.html')
_sp.run([sys.executable, os.path.join(repo_root, 'packaging', 'inline_assets.py'), html],
        check=True)
if not os.path.exists(html):
    raise SystemExit("inline_assets.py did not produce the interface HTML.")

a = Analysis(
    [os.path.join(repo_root, 'webapp.py')],
    pathex=[repo_root],
    binaries=[(ffmpeg_binary, '.')],
    datas=[(html, '.')],
    hiddenimports=['webview', 'webview.platforms.cocoa', 'normalizer'],
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'watchdog', 'tqdm', 'PIL', 'numpy', 'pytest'],
    noarchive=False,
)

pyz = PYZ(a.pure)

# target_arch is read from $VTN_TARGET_ARCH so the build script can ask for a
# universal2 app when it has a universal2 Python, and fall back to a native
# single-arch build when it does not.
#
# This matters more than it looks: PyInstaller THINS every bundled binary to the
# target architecture. Handing it a universal ffmpeg while building arm64 threw
# the x86_64 half away silently, producing an "Intel-compatible" app that was
# arm64-only. Setting universal2 keeps both halves — but it also requires the
# Python and every wheel to be universal2, which is why it is conditional.
target_arch = os.environ.get('VTN_TARGET_ARCH') or None

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='VTNormalisation',
    debug=False,
    strip=False,
    upx=False,
    console=False,             # windowed GUI, no Terminal
    argv_emulation=False,
    target_arch=target_arch,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='VTNormalisation',
)

app = BUNDLE(
    coll,
    name='Very Thoughtful Normalisation.app',
    icon=os.path.join(repo_root, 'packaging', 'app_icon.icns'),
    bundle_identifier='com.picniclabs.vtnormalisation',
    info_plist={
        'CFBundleName': 'VTNormalisation',
        'CFBundleDisplayName': 'Very Thoughtful Normalisation (but in a good way)',
        'CFBundleShortVersionString': '2.0',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '10.14',   # WKWebView via pywebview
    },
)
