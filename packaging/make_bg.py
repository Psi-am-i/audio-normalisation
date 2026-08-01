#!/usr/bin/env python3
"""
Build-time helper: pre-tint the GUI background image to cool grey/blue and size it
for the window, so the app ships a ready-to-use image and needs no Pillow at
runtime.

    python3 packaging/make_bg.py

Reads  gui_assets/background_source.jpg  (personal photo, not in the repo)
Writes gui_assets/background.png  (BG_W x BG_H, grey/blue tinted)

If the source photo is missing (e.g. CI builds of this public repo), a
procedural grey/blue gradient is generated instead so the build still works.

The grey/blue ramp matches the app palette (ground #0E1217, panel #19202A,
accent #5AA9F0). The intended source is a vinyl-groove macro — the grooves give
directional texture that sits well behind the panels.
"""
import math
from pathlib import Path
from PIL import Image, ImageOps, ImageEnhance

# Generated larger than the window: the page uses background-size:cover, so the
# photo has to survive the window being resized up without going soft.
BG_W, BG_H = 1400, 1000

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "gui_assets" / "background_source.jpg"
DST = ROOT / "gui_assets" / "background.png"

# Luminance -> cool grey/blue ramp, matching the palette (ground #0E1217, panel
# #19202A, accent #5AA9F0). Shadows fall to near-black, highlights lift to a
# steely blue-grey — deliberately NOT to the accent blue itself, or the
# background starts competing with the one element meant to be blue.
#
# Tuned so the image reads as TEXTURE behind the panels, not as a picture: an
# earlier pass at brightness .82 left the photo bright enough to fight the
# foreground once real panels sat on top of it.
# Tuned for the vinyl-groove macro. A near-uniform texture like this can sit far
# brighter than a photograph of a subject: there is nothing in it for the eye to
# lock onto, so it never competes with the panels. Values that suited the earlier
# portrait (brightness .60) crushed the grooves into flat black.
RAMP_BLACK = (10, 13, 18)
RAMP_MID = (38, 48, 62)
RAMP_WHITE = (116, 136, 162)
RAMP_MIDPOINT = 128
BRIGHTNESS = 1.05
CONTRAST = 1.22


def procedural_background() -> Image.Image:
    """Cool grey/blue vertical gradient with a soft vignette — image stand-in."""
    img = Image.new("RGB", (BG_W, BG_H))
    px = img.load()
    cx, cy = BG_W / 2, BG_H / 2
    max_d = math.hypot(cx, cy)
    for y in range(BG_H):
        base = 12 + 26 * (1 - y / BG_H)           # brighter at the top
        for x in range(BG_W):
            vig = 1 - 0.55 * (math.hypot(x - cx, y - cy) / max_d) ** 2
            v = base * vig
            px[x, y] = (int(v * 0.72), int(v * 0.88), int(v * 1.20))
    return img


def main() -> None:
    if SRC.exists():
        img = ImageOps.exif_transpose(Image.open(SRC)).convert("RGB")
        # Only rotate a PORTRAIT source. The rotation used to be unconditional,
        # which suited the original upright photo but would tip a landscape
        # source (such as the vinyl-groove macro) onto its side.
        if img.height > img.width:
            img = img.rotate(-90, expand=True)
        img = ImageOps.fit(img, (BG_W, BG_H), method=Image.LANCZOS)   # cover-crop
    else:
        print(f"note: {SRC.name} not found — generating procedural background")
        img = procedural_background()

    gray = ImageOps.grayscale(img)
    tinted = ImageOps.colorize(gray, black=RAMP_BLACK, mid=RAMP_MID,
                               white=RAMP_WHITE, midpoint=RAMP_MIDPOINT)
    tinted = ImageEnhance.Brightness(tinted).enhance(BRIGHTNESS)
    tinted = ImageEnhance.Contrast(tinted).enhance(CONTRAST)

    DST.parent.mkdir(parents=True, exist_ok=True)  # gui_assets/ is fully gitignored
    tinted.save(DST)
    print(f"wrote {DST} ({BG_W}x{BG_H}, grey/blue)")


if __name__ == "__main__":
    main()
