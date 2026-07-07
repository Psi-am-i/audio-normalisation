#!/usr/bin/env bash
#
# Build the self-contained GUI app "Psi'sDJnormalizerButInAgoodWay".
#
# Output: packaging/dist-gui/PsiDJNormalizer.zip  (send this)
#
# A proper windowed macOS .app — double-click opens the green-terminal GUI with
# folder pickers. Python, tkinter, the tinted background, and ffmpeg are all
# bundled; recipients install nothing.
#
# ffmpeg source (redistributable GPLv3 static build; --enable-nonfree refused):
#   1. $FFMPEG_STATIC  — a static ffmpeg you already have
#   2. downloaded from evermeet.cx (self-contained static GPLv3, x86_64 —
#      runs on Intel natively and on Apple Silicon via Rosetta 2)
#
set -euo pipefail

PKG_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$PKG_DIR/.." && pwd)"
# shellcheck source=lib_licenses.sh
source "$PKG_DIR/lib_licenses.sh"
BUILD_DIR="$PKG_DIR/build-gui"
DIST_DIR="$PKG_DIR/dist-gui"
VENV_DIR="$BUILD_DIR/venv"
APP_NAME="PsiDJNormalizer"
APP_DIR="$DIST_DIR/$APP_NAME.app"

echo "==> Cleaning previous build"
rm -rf "$BUILD_DIR" "$DIST_DIR"
mkdir -p "$BUILD_DIR" "$DIST_DIR"

echo "==> Ensuring tinted background exists"
if [[ ! -f "$REPO_ROOT/gui_assets/background.png" ]]; then
    echo "    Generating gui_assets/background.png (needs Pillow)"
    python3 -m pip install --quiet pillow
    python3 "$PKG_DIR/make_bg.py"
fi

echo "==> Obtaining static ffmpeg (redistributable GPL build)"
FFMPEG_BIN="$BUILD_DIR/ffmpeg"
FFMPEG_URL="${FFMPEG_URL:-https://evermeet.cx/ffmpeg/getrelease/zip}"
if [[ -n "${FFMPEG_STATIC:-}" ]]; then
    echo "    Using \$FFMPEG_STATIC: $FFMPEG_STATIC"
    cp "$FFMPEG_STATIC" "$FFMPEG_BIN"
else
    echo "    Downloading evermeet static build"
    curl -L --fail -o "$BUILD_DIR/ffmpeg.zip" "$FFMPEG_URL"
    unzip -o -j "$BUILD_DIR/ffmpeg.zip" ffmpeg -d "$BUILD_DIR" >/dev/null
fi
chmod +x "$FFMPEG_BIN"

# License gate: --enable-nonfree builds are NOT redistributable.
if "$FFMPEG_BIN" -version 2>/dev/null | grep -q -- "--enable-nonfree"; then
    echo "ERROR: this ffmpeg is built --enable-nonfree and cannot be redistributed."
    echo "Use a GPL/LGPL build (the evermeet.cx default, or 'brew install ffmpeg')."
    exit 1
fi
FFVER="$("$FFMPEG_BIN" -version 2>/dev/null | head -1)"
echo "    $FFVER"

echo "==> Creating build virtualenv"
python3 -m venv "$VENV_DIR"
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet pyinstaller

echo "==> Running PyInstaller"
export FFMPEG_BINARY_PATH="$FFMPEG_BIN"
pyinstaller \
    --clean --noconfirm \
    --distpath "$DIST_DIR" \
    --workpath "$BUILD_DIR/pyi-work" \
    "$PKG_DIR/normalizer-gui.spec"

[[ -d "$APP_DIR" ]] || { echo "ERROR: PyInstaller did not produce $APP_DIR"; exit 1; }

echo "==> Writing recipient README + zipping"
STAGE="$BUILD_DIR/stage/$APP_NAME"
rm -rf "$BUILD_DIR/stage"
mkdir -p "$STAGE"
cp -R "$APP_DIR" "$STAGE/"
cat > "$STAGE/README.txt" <<'READMEEOF'
Psi'sDJnormalizerButInAgoodWay
==============================

1. Double-click the app.

2. The FIRST time, macOS blocks unsigned apps ("unidentified developer").
   -> Right-click (or Control-click) the app -> Open -> Open.
      On macOS Sequoia: System Settings -> Privacy & Security -> "Open Anyway".
   After this one time, it opens normally.

3. In the window:
   - [ SOURCE ]       pick the folder with your tracks
   - [ DESTINATION ]  pick where the normalized files go
   - FORMAT           toggles AIFF <-> FLAC
                      (AIFF plays on ALL Pioneer/CDJ gear; FLAC is smaller)
   - > NORMALIZE      go

Your originals are never changed. Everything is levelled to -12 LUFS.
Enjoy the terrible jokes.

This app bundles FFmpeg (GPLv3). See the "licenses" folder.
READMEEOF

write_ffmpeg_licenses "$STAGE/licenses" "$FFVER"

( cd "$BUILD_DIR/stage" && ditto -c -k --sequesterRsrc --keepParent "$APP_NAME" "$DIST_DIR/$APP_NAME.zip" )

deactivate || true
echo ""
echo "Done."
echo "  App: $APP_DIR"
echo "  Zip: $DIST_DIR/$APP_NAME.zip  (send this)"
echo ""
echo "NOTE: unsigned — first launch on another Mac is right-click -> Open -> Open."
