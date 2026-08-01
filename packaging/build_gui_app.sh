#!/usr/bin/env bash
#
# Build the self-contained GUI app "Very Thoughtful DJ Normalization".
#
# Output: packaging/dist-gui/VTDNormalization.zip  (send this)
#
# A proper windowed macOS .app — double-click opens the interface (pywebview /
# WKWebView) with native folder pickers. Python, pywebview, the interface HTML,
# the tinted background and ffmpeg are all bundled; recipients install nothing.
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
APP_NAME="VTDNormalization"
APP_DIR="$DIST_DIR/Very Thoughtful DJ Normalization.app"

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

echo "==> Selecting a build Python (>= 3.9)"
# The old tkinter Tk-version gate is gone with the tkinter front-end: the
# interface is now HTML in a WKWebView, so Tk is irrelevant and tkinter is
# excluded from the bundle entirely.
py_ok() {
    "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null
}

BUILD_PYTHON=""
for cand in "${PYTHON:-}" python3.13 python3.12 python3.11 python3; do
    [[ -n "$cand" ]] || continue
    command -v "$cand" >/dev/null || continue
    if py_ok "$(command -v "$cand")"; then
        BUILD_PYTHON="$(command -v "$cand")"
        break
    fi
done
if [[ -z "$BUILD_PYTHON" ]]; then
    echo "ERROR: no Python >= 3.9 found."
    echo "  Set PYTHON=/path/to/python before running this script."
    exit 1
fi
echo "    Using $BUILD_PYTHON ($("$BUILD_PYTHON" --version))"

# Encoder gate: MP3 and AAC output need these in the bundled ffmpeg.
for enc in libmp3lame aac; do
    if ! "$FFMPEG_BIN" -hide_banner -encoders 2>/dev/null | grep -q " $enc "; then
        echo "ERROR: bundled ffmpeg is missing the '$enc' encoder."
        exit 1
    fi
done

echo "==> Creating build virtualenv"
"$BUILD_PYTHON" -m venv "$VENV_DIR"
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
pip install --quiet --upgrade pip
# pywebview pulls the pyobjc WKWebView backend on macOS
pip install --quiet pyinstaller pywebview

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
# Canonical recipient README, shared with the Windows build (release.yml)
cp "$PKG_DIR/APP_README.txt" "$STAGE/README.txt"

write_ffmpeg_licenses "$STAGE/licenses" "$FFVER"

( cd "$BUILD_DIR/stage" && ditto -c -k --sequesterRsrc --keepParent "$APP_NAME" "$DIST_DIR/$APP_NAME.zip" )

# PyInstaller's COLLECT stage leaves its onedir output ("$DIST_DIR/$APP_NAME/")
# beside the finished .app that BUNDLE wrapped around it. On macOS that folder
# is a ~100MB intermediate nobody should open — and having two things in
# dist-gui that both look like the app is just confusing. Drop it; the .app and
# the .zip are the only real outputs.
rm -rf "${DIST_DIR:?}/$APP_NAME"

deactivate || true
echo ""
echo "Done. Two outputs, nothing else:"
echo "  App: $APP_DIR"
echo "       (double-click to run it here)"
echo "  Zip: $DIST_DIR/$APP_NAME.zip  <- send THIS"
echo ""
echo "NOTE: unsigned — first launch on another Mac is right-click -> Open -> Open."
echo "NOTE: macOS only. Windows cannot be cross-compiled from here; that build"
echo "      comes from the windows-latest job in .github/workflows/release.yml."
