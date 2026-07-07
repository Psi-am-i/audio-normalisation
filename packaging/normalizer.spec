# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for the self-contained Audio Normalizer CLI.

Produces a single-file executable that bundles:
  - the Python runtime + tqdm
  - the core engine (normalizer.py) and manual front-end (normalize.py)
  - a static ffmpeg binary (resolved at runtime by normalizer.resolve_ffmpeg())

The ffmpeg binary to embed is passed via the FFMPEG_BINARY_PATH env var
(build_app.sh sets this). It is placed at the root of the extraction dir,
where resolve_ffmpeg() looks first for frozen builds.

The distributable ships ONLY the manual/interactive flow — the autowatch
daemon (watcher.py) is intentionally excluded.
"""

import os

repo_root = os.path.dirname(SPECPATH)  # SPECPATH is the packaging/ dir
ffmpeg_binary = os.environ.get('FFMPEG_BINARY_PATH')
if not ffmpeg_binary or not os.path.exists(ffmpeg_binary):
    raise SystemExit(
        "FFMPEG_BINARY_PATH must point to a static ffmpeg binary. "
        "Run packaging/build_app.sh, which sets it for you."
    )

a = Analysis(
    [os.path.join(repo_root, 'normalize.py')],
    pathex=[repo_root],
    binaries=[(ffmpeg_binary, '.')],   # -> extracted next to sys._MEIPASS root
    datas=[],
    hiddenimports=['normalizer'],
    hookspath=[],
    runtime_hooks=[],
    excludes=['watchdog'],             # daemon dependency, not needed here
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='normalizer-cli',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,          # interactive stdin/stdout in Terminal
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
