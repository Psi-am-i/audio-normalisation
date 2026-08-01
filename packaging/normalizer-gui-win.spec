# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec — Windows build of "Very Thoughtful Normalisation (but in a good way)" (the GUI).

Windows counterpart of normalizer-gui.spec: a windowed onedir build bundling the
Python runtime + pywebview (EdgeChromium / WebView2 backend), the engine
(normalizer.py), the shell (webapp.py), the interface HTML, the tinted
background, and a static ffmpeg.exe (resolved at runtime by
normalizer.resolve_ffmpeg()).

Only ffmpeg.exe is bundled — NOT ffprobe.exe. The engine reads stream properties
out of ffmpeg's own stderr (normalizer._parse_input_stream) precisely so the app
needs one binary, not two.

vtdn_app.html and gui_assets/ must stay side by side at the bundle root: the page
pulls the background as a relative sibling.

FFMPEG_BINARY_PATH must point at a static GPL ffmpeg.exe (the release CI
downloads one from gyan.dev). Built by .github/workflows/release.yml on a
windows-latest runner — PyInstaller cannot cross-compile.

WebView2: the recipient needs the Microsoft Edge WebView2 runtime. It ships with
Windows 11 and current Windows 10; on an older box it installs once (see
packaging/BUILD.md and the recipient README).
"""

import os

repo_root = os.path.dirname(SPECPATH)
ffmpeg_binary = os.environ.get('FFMPEG_BINARY_PATH')
if not ffmpeg_binary or not os.path.exists(ffmpeg_binary):
    raise SystemExit(
        "FFMPEG_BINARY_PATH must point to a static ffmpeg.exe. "
        "See .github/workflows/release.yml for how CI obtains one."
    )

html = os.path.join(repo_root, 'vtdn_app.html')
if not os.path.exists(html):
    raise SystemExit("vtdn_app.html missing from the repo.")

bg_png = os.path.join(repo_root, 'gui_assets', 'background.png')
if not os.path.exists(bg_png):
    raise SystemExit(
        "gui_assets/background.png missing. Run: python packaging/make_bg.py"
    )

a = Analysis(
    [os.path.join(repo_root, 'webapp.py')],
    pathex=[repo_root],
    binaries=[(ffmpeg_binary, '.')],
    datas=[(html, '.'), (bg_png, 'gui_assets')],
    hiddenimports=['webview', 'webview.platforms.edgechromium', 'normalizer'],
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
    name='VTNormalisation',
    debug=False,
    strip=False,
    upx=False,
    console=False,             # windowed GUI, no console window
    argv_emulation=False,
    icon=os.path.join(repo_root, 'packaging', 'app_icon.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='VTNormalisation',
)
