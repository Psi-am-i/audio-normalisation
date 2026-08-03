#!/usr/bin/env python3
"""
Build-time helper: produce a fully self-contained copy of the interface.

`vtdn_app.html` references the background as a relative sibling
(`url('gui_assets/background.png')`), which is right for development — you can
serve the repo and open the page in a browser.

Inside the packaged app it is not reliable. Whether that relative URL resolves
depends on how the platform's webview loads the page: macOS/WKWebView reads it
from disk, while Windows/WebView2 goes through pywebview's local HTTP server,
and the background silently failed to appear there. Chasing per-backend URL
behaviour is not worth it for one image.

So the build embeds the image as a data: URI instead. The shipped page then has
no external references at all and looks identical on every backend.

    python3 packaging/inline_assets.py <output.html>

Writes the inlined copy to the given path. The committed HTML is untouched.
"""

import base64
import mimetypes
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC_HTML = ROOT / "vtdn_app.html"


def inline(html: str, base_dir: Path) -> str:
    """Replace url('...') references to local files with data: URIs."""
    def repl(match):
        quote, rel = match.group(1), match.group(2)
        if rel.startswith(("data:", "http:", "https:")):
            return match.group(0)
        asset = (base_dir / rel).resolve()
        if not asset.is_file():
            raise SystemExit(
                f"inline_assets: {rel} not found at {asset}.\n"
                f"  Run: python3 packaging/make_bg.py"
            )
        raw = asset.read_bytes()
        mime = mimetypes.guess_type(asset.name)[0] or "application/octet-stream"
        original_kb = len(raw) / 1024

        # Base64 inflates by ~33%, and the webview parses the whole page at
        # every launch. The background is a photograph with no transparency, so
        # re-encoding it as JPEG costs nothing visible and saves several MB
        # against a lossless PNG. Best-effort: if Pillow is absent the PNG is
        # embedded as-is.
        if mime == "image/png" and len(raw) > 300_000:
            try:
                import io
                from PIL import Image
                buf = io.BytesIO()
                Image.open(io.BytesIO(raw)).convert("RGB").save(
                    buf, format="JPEG", quality=85, optimize=True, progressive=True)
                if buf.tell() < len(raw):
                    raw, mime = buf.getvalue(), "image/jpeg"
            except Exception as e:  # noqa: BLE001
                print(f"  note: could not re-encode {rel} as JPEG ({e}); using PNG")

        b64 = base64.b64encode(raw).decode("ascii")
        print(f"  inlined {rel}: {original_kb:.0f} KB -> {len(raw) / 1024:.0f} KB "
              f"{mime.split('/')[-1]} -> {len(b64) / 1024:.0f} KB base64")
        return f"url({quote}data:{mime};base64,{b64}{quote})"

    return re.sub(r"""url\((['"])([^'"]+)\1\)""", repl, html)


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(2)
    dest = Path(sys.argv[1])
    html = SRC_HTML.read_text(encoding="utf-8")
    out = inline(html, SRC_HTML.parent)

    # Nothing external may remain: the packaged app has no network, and a
    # missed reference shows up as a silently absent asset rather than an error.
    leftover = re.findall(r"""url\((['"])(?!data:)([^'"]+)\1\)""", out)
    if leftover:
        raise SystemExit(f"inline_assets: unresolved references: {leftover}")

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(out, encoding="utf-8")
    print(f"  wrote {dest} ({len(out) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
