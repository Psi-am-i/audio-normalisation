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
import sys

from PyInstaller.utils.hooks import collect_all

repo_root = os.path.dirname(SPECPATH)

# pywebview on Windows does NOT load the edgechromium module directly: it loads
# webview.platforms.winforms (see webview/guilib.py import_winforms), which is a
# .NET WinForms host, and EdgeChromium is only the renderer inside it. That host
# runs on pythonnet, whose clr_loader ships runtime DLLs and .runtimeconfig.json
# as DATA files — PyInstaller does not pick those up from an import graph alone.
#
# Declaring only 'webview.platforms.edgechromium' produced an app that showed a
# window and then hung, because the WinForms/pythonnet host never came up.
# collect_all pulls the modules, binaries and data for each.
_pn_datas, _pn_bins, _pn_hidden = collect_all('pythonnet')
_cl_datas, _cl_bins, _cl_hidden = collect_all('clr_loader')
ffmpeg_binary = os.environ.get('FFMPEG_BINARY_PATH')
if not ffmpeg_binary or not os.path.exists(ffmpeg_binary):
    raise SystemExit(
        "FFMPEG_BINARY_PATH must point to a static ffmpeg.exe. "
        "See .github/workflows/release.yml for how CI obtains one."
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
    binaries=[(ffmpeg_binary, '.'), *_pn_bins, *_cl_bins],
    datas=[(html, '.'), *_pn_datas, *_cl_datas],
    hiddenimports=[
        'webview',
        'webview.platforms.winforms',      # the actual Windows host
        'webview.platforms.edgechromium',  # the renderer it uses
        'clr',                             # pythonnet's entry point
        'clr_loader',
        'normalizer',
        *_pn_hidden, *_cl_hidden,
    ],
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
