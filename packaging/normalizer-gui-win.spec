# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for the Windows build of "Psi'sDJnormalizerButInAgoodWay".

Windows counterpart of normalizer-gui.spec: a windowed onedir build bundling
the Python runtime + tkinter, the engine + GUI, the tinted background, and a
static ffmpeg.exe (resolved at runtime by normalizer.resolve_ffmpeg()).

FFMPEG_BINARY_PATH must point at a static GPL ffmpeg.exe (the release CI
downloads one from gyan.dev). Built by .github/workflows/release.yml on a
windows-latest runner — PyInstaller cannot cross-compile.
"""

import os

repo_root = os.path.dirname(SPECPATH)
ffmpeg_binary = os.environ.get('FFMPEG_BINARY_PATH')
if not ffmpeg_binary or not os.path.exists(ffmpeg_binary):
    raise SystemExit(
        "FFMPEG_BINARY_PATH must point to a static ffmpeg.exe. "
        "See .github/workflows/release.yml for how CI obtains one."
    )

bg_png = os.path.join(repo_root, 'gui_assets', 'background.png')
if not os.path.exists(bg_png):
    raise SystemExit(
        "gui_assets/background.png missing. Run: python packaging/make_bg.py"
    )

a = Analysis(
    [os.path.join(repo_root, 'gui.py')],
    pathex=[repo_root],
    binaries=[(ffmpeg_binary, '.')],
    datas=[(bg_png, 'gui_assets')],
    hiddenimports=['normalizer'],
    hookspath=[],
    runtime_hooks=[],
    excludes=['watchdog', 'tqdm', 'PIL', 'numpy'],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PsiDJNormalizer',
    debug=False,
    strip=False,
    upx=False,
    console=False,             # windowed GUI, no console window
    argv_emulation=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='PsiDJNormalizer',
)
