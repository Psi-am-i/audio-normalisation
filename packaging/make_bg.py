#!/usr/bin/env python3
"""
Build-time helper: pre-tint the GUI background image to very dark green and
size it to the window, so the app can load it with stdlib tk.PhotoImage and
needs no Pillow at runtime.

    python3 packaging/make_bg.py

Reads  gui_assets/background_source.jpg  (personal photo, not in the repo)
Writes gui_assets/background.png  (WIN_W x WIN_H, dark-green tinted)

If the source photo is missing (e.g. CI builds of this public repo), a
procedural dark-green gradient is generated instead so the build still works.
"""
import math
from pathlib import Path
from PIL import Image, ImageOps, ImageEnhance

WIN_W, WIN_H = 900, 680

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "gui_assets" / "background_source.jpg"
DST = ROOT / "gui_assets" / "background.png"


def procedural_background() -> Image.Image:
    """Dark-green vertical gradient with a soft vignette — photo stand-in."""
    img = Image.new("RGB", (WIN_W, WIN_H))
    px = img.load()
    cx, cy = WIN_W / 2, WIN_H / 2
    max_d = math.hypot(cx, cy)
    for y in range(WIN_H):
        base = 10 + 20 * (1 - y / WIN_H)          # brighter at the top
        for x in range(WIN_W):
            vig = 1 - 0.55 * (math.hypot(x - cx, y - cy) / max_d) ** 2
            g = base * vig
            px[x, y] = (int(g * 0.25), int(g), int(g * 0.3))
    return img


if SRC.exists():
    img = ImageOps.exif_transpose(Image.open(SRC)).convert("RGB")
    img = img.rotate(-90, expand=True)                              # 90 deg right
    img = ImageOps.fit(img, (WIN_W, WIN_H), method=Image.LANCZOS)   # cover-crop
else:
    print(f"note: {SRC.name} not found — generating procedural background")
    img = procedural_background()

# Luminance -> dark green ramp (shadows near-black green, highlights dim green).
gray = ImageOps.grayscale(img)
tinted = ImageOps.colorize(
    gray,
    black=(0, 4, 0),
    mid=(8, 30, 10),
    white=(26, 74, 30),
    midpoint=120,
)
tinted = ImageEnhance.Brightness(tinted).enhance(0.70)
tinted = ImageEnhance.Contrast(tinted).enhance(1.05)
tinted.save(DST)
print(f"wrote {DST} ({WIN_W}x{WIN_H})")
