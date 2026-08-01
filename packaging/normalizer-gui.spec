# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec — macOS build of "Very Thoughtful DJ Normalization" (the GUI).

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

repo_root = os.path.dirname(SPECPATH)
ffmpeg_binary = os.environ.get('FFMPEG_BINARY_PATH')
if not ffmpeg_binary or not os.path.exists(ffmpeg_binary):
    raise SystemExit(
        "FFMPEG_BINARY_PATH must point to a static ffmpeg binary. "
        "Run packaging/build_gui_app.sh, which sets it for you."
    )

html = os.path.join(repo_root, 'vtdn_app.html')
if not os.path.exists(html):
    raise SystemExit("vtdn_app.html missing from the repo.")

bg_png = os.path.join(repo_root, 'gui_assets', 'background.png')
if not os.path.exists(bg_png):
    raise SystemExit(
        "gui_assets/background.png missing. Run: python3 packaging/make_bg.py"
    )

a = Analysis(
    [os.path.join(repo_root, 'webapp.py')],
    pathex=[repo_root],
    binaries=[(ffmpeg_binary, '.')],
    datas=[(html, '.'), (bg_png, 'gui_assets')],
    hiddenimports=['webview', 'webview.platforms.cocoa', 'normalizer'],
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'watchdog', 'tqdm', 'PIL', 'numpy', 'pytest'],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='VTDNormalization',
    debug=False,
    strip=False,
    upx=False,
    console=False,             # windowed GUI, no Terminal
    argv_emulation=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='VTDNormalization',
)

app = BUNDLE(
    coll,
    name='Very Thoughtful DJ Normalization.app',
    icon=os.path.join(repo_root, 'packaging', 'app_icon.icns'),
    bundle_identifier='com.picniclabs.vtdnormalization',
    info_plist={
        'CFBundleName': 'VTDNormalization',
        'CFBundleDisplayName': 'Very Thoughtful DJ Normalization',
        'CFBundleShortVersionString': '2.0',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '10.14',   # WKWebView via pywebview
    },
)
