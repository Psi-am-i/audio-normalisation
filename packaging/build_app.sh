#!/usr/bin/env bash
#
# Build a self-contained, double-clickable macOS app for the Audio Normalizer.
#
# Output: packaging/dist/Normalizer.app  (+ Normalizer.zip for sending to people)
#
# The .app is a tiny launcher that opens Terminal and runs a PyInstaller binary
# with ffmpeg bundled inside — recipients install nothing.
#
# Usage:
#   packaging/build_app.sh
#
# ffmpeg source (a STATIC binary is required — Homebrew's ffmpeg links against
# many dylibs and is not portable). In priority order:
#   1. $FFMPEG_STATIC  — path to a static ffmpeg binary you already have
#   2. downloaded from $FFMPEG_URL (default: evermeet.cx, a self-contained
#      static GPLv3 build — redistributable)
#
# The build REFUSES ffmpeg built with --enable-nonfree, which is not legally
# redistributable. evermeet's default build is GPLv3 (redistributable); the
# GPL license + attribution are placed in the zip automatically.
#
# Note: evermeet is an x86_64 build. It runs natively on Intel Macs and on
# Apple Silicon via Rosetta 2. See BUILD.md for arch details.
#
set -euo pipefail

PKG_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$PKG_DIR/.." && pwd)"
# shellcheck source=lib_licenses.sh
source "$PKG_DIR/lib_licenses.sh"
BUILD_DIR="$PKG_DIR/build"
DIST_DIR="$PKG_DIR/dist"
VENV_DIR="$BUILD_DIR/venv"
APP_NAME="Normalizer"
APP_DIR="$DIST_DIR/$APP_NAME.app"

echo "==> Cleaning previous build"
rm -rf "$BUILD_DIR" "$DIST_DIR"
mkdir -p "$BUILD_DIR" "$DIST_DIR"

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
pip install --quiet -r "$REPO_ROOT/requirements.txt" || true  # tqdm needed; watchdog optional

echo "==> Running PyInstaller"
export FFMPEG_BINARY_PATH="$FFMPEG_BIN"
pyinstaller \
    --clean --noconfirm \
    --distpath "$BUILD_DIR/pyi-dist" \
    --workpath "$BUILD_DIR/pyi-work" \
    "$PKG_DIR/normalizer.spec"

CLI_BIN="$BUILD_DIR/pyi-dist/normalizer-cli"
[[ -f "$CLI_BIN" ]] || { echo "ERROR: PyInstaller did not produce $CLI_BIN"; exit 1; }

echo "==> Assembling $APP_NAME.app"
mkdir -p "$APP_DIR/Contents/MacOS" "$APP_DIR/Contents/Resources"
cp "$CLI_BIN" "$APP_DIR/Contents/Resources/normalizer-cli"
chmod +x "$APP_DIR/Contents/Resources/normalizer-cli"

# Launcher: opens Terminal and runs the bundled interactive CLI.
cat > "$APP_DIR/Contents/MacOS/$APP_NAME" <<'LAUNCHER'
#!/bin/bash
RES="$(cd "$(dirname "$0")/../Resources" && pwd)"
open -a Terminal "$RES/normalizer-cli"
LAUNCHER
chmod +x "$APP_DIR/Contents/MacOS/$APP_NAME"

cat > "$APP_DIR/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>            <string>$APP_NAME</string>
    <key>CFBundleDisplayName</key>     <string>Audio Normalizer</string>
    <key>CFBundleIdentifier</key>      <string>com.picniclabs.audionormalizer</string>
    <key>CFBundleVersion</key>         <string>1.0</string>
    <key>CFBundleShortVersionString</key> <string>1.0</string>
    <key>CFBundlePackageType</key>     <string>APPL</string>
    <key>CFBundleExecutable</key>      <string>$APP_NAME</string>
    <key>LSMinimumSystemVersion</key>  <string>10.13</string>
</dict>
</plist>
PLIST

echo "==> Writing recipient README"
STAGE="$BUILD_DIR/stage/$APP_NAME"
rm -rf "$BUILD_DIR/stage"
mkdir -p "$STAGE"
cp -R "$APP_DIR" "$STAGE/"
cat > "$STAGE/README.txt" <<'READMEEOF'
Audio Normalizer
================

1. Double-click "Normalizer.app".

2. The FIRST time, macOS blocks unsigned apps ("unidentified developer").
   -> Right-click (or Control-click) the app -> Open -> Open.
      On macOS Sequoia: System Settings -> Privacy & Security -> "Open Anyway".
   After this one time, it opens normally by double-click.

3. A Terminal window opens. Follow the prompts:
   - source: a folder (or single file) of your tracks
   - destination: a folder for the normalized files
   - format: 1 = AIFF (plays on ALL Pioneer/CDJ gear) or 2 = FLAC (smaller)

Your original files are never changed. Output is normalized to -12 LUFS.

This app bundles FFmpeg (GPLv3). See the "licenses" folder.
READMEEOF

write_ffmpeg_licenses "$STAGE/licenses" "$FFVER"

echo "==> Zipping for distribution"
( cd "$BUILD_DIR/stage" && ditto -c -k --sequesterRsrc --keepParent "$APP_NAME" "$DIST_DIR/$APP_NAME.zip" )

deactivate || true
echo ""
echo "Done."
echo "  App: $APP_DIR"
echo "  Zip: $DIST_DIR/$APP_NAME.zip  (send this)"
echo ""
echo "NOTE: the app is unsigned. First launch on another Mac: right-click the"
echo "app -> Open -> Open, to get past Gatekeeper. See packaging/BUILD.md."
