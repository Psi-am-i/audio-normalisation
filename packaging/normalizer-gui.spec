# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for the GUI app "Psi'sDJnormalizerButInAgoodWay".

Produces a proper windowed macOS .app (no Terminal) bundling:
  - the Python runtime + tkinter
  - the core engine (normalizer.py) and GUI front-end (gui.py)
  - the pre-tinted background (gui_assets/background.png)
  - a static ffmpeg binary (resolved at runtime by normalizer.resolve_ffmpeg())

The ffmpeg binary to embed is passed via FFMPEG_BINARY_PATH (build_gui_app.sh
sets it). PIL/Pillow is only used at build time (make_bg.py) and is excluded.
"""

import os

repo_root = os.path.dirname(SPECPATH)
ffmpeg_binary = os.environ.get('FFMPEG_BINARY_PATH')
if not ffmpeg_binary or not os.path.exists(ffmpeg_binary):
    raise SystemExit(
        "FFMPEG_BINARY_PATH must point to a static ffmpeg binary. "
        "Run packaging/build_gui_app.sh, which sets it for you."
    )

bg_png = os.path.join(repo_root, 'gui_assets', 'background.png')
if not os.path.exists(bg_png):
    raise SystemExit(
        "gui_assets/background.png missing. Run: python3 packaging/make_bg.py"
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
    console=False,             # windowed GUI, no Terminal
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

app = BUNDLE(
    coll,
    name='PsiDJNormalizer.app',
    icon=None,
    bundle_identifier='com.picniclabs.psidjnormalizer',
    info_plist={
        'CFBundleName': 'PsiDJNormalizer',
        'CFBundleDisplayName': "Psi'sDJnormalizerButInAgoodWay",
        'CFBundleShortVersionString': '1.1',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '10.13',
    },
)
