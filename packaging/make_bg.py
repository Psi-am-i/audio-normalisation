#!/usr/bin/env python3
"""
Build-time helper: pre-tint the GUI background image to very dark green and
size it to the window, so the app can load it with stdlib tk.PhotoImage and
needs no Pillow at runtime.

    python3 packaging/make_bg.py

Reads  gui_assets/background_source.jpg
Writes gui_assets/background.png  (WIN_W x WIN_H, dark-green tinted)
"""
from pathlib import Path
from PIL import Image, ImageOps, ImageEnhance

WIN_W, WIN_H = 900, 680

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "gui_assets" / "background_source.jpg"
DST = ROOT / "gui_assets" / "background.png"

img = ImageOps.exif_transpose(Image.open(SRC)).convert("RGB")
img = img.rotate(-90, expand=True)                              # 90 deg right
img = ImageOps.fit(img, (WIN_W, WIN_H), method=Image.LANCZOS)   # cover-crop

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
