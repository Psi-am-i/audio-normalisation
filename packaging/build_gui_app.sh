#!/usr/bin/env bash
#
# Build the self-contained GUI app "Very Thoughtful Normalisation (but in a good way)".
#
# Output: packaging/dist-gui/VTNormal.zip  (send this)
#
# A proper windowed macOS .app — double-click opens the interface (pywebview /
# WKWebView) with native folder pickers. Python, pywebview, the interface HTML,
# the tinted background and ffmpeg are all bundled; recipients install nothing.
#
# ffmpeg (redistributable GPLv3 static builds; --enable-nonfree refused). BOTH
# architectures are fetched and lipo'd into one universal binary:
#   arm64  <- ffmpeg.martin-riedl.de   (override with $FFMPEG_STATIC_ARM64)
#   x86_64 <- evermeet.cx              (override with $FFMPEG_STATIC_X86_64)
#
set -euo pipefail

PKG_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$PKG_DIR/.." && pwd)"
# shellcheck source=lib_licenses.sh
source "$PKG_DIR/lib_licenses.sh"
BUILD_DIR="$PKG_DIR/build-gui"
DIST_DIR="$PKG_DIR/dist-gui"
VENV_DIR="$BUILD_DIR/venv"
APP_NAME="VTNormal"
APP_DIR="$DIST_DIR/VTNormal.app"

echo "==> Cleaning previous build"
rm -rf "$BUILD_DIR" "$DIST_DIR"
mkdir -p "$BUILD_DIR" "$DIST_DIR"

echo "==> Ensuring tinted background exists"
if [[ ! -f "$REPO_ROOT/gui_assets/background.png" ]]; then
    echo "    Generating gui_assets/background.png (needs Pillow)"
    python3 -m pip install --quiet pillow
    python3 "$PKG_DIR/make_bg.py"
fi

echo "==> Building a UNIVERSAL static ffmpeg (arm64 + x86_64)"
# Both architectures are bundled and lipo'd into one binary so the app runs
# NATIVELY on Apple Silicon and on Intel. Shipping x86_64 alone meant every
# Apple Silicon user went through Rosetta, which is bad for two reasons: the
# first exec of a ~77MB binary is slow enough to look broken, and Rosetta is an
# optional install on current macOS — without it the app cannot encode at all.
#
# (Measured: audio encoding itself is fine under Rosetta — aac_at, libmp3lame,
# pcm and loudnorm all behave. The flaky-under-Rosetta encoders are the
# VideoToolbox ones, which this app never touches. Avoiding Rosetta here is
# about startup cost and Rosetta's absence, not audio correctness.)
FFMPEG_BIN="$BUILD_DIR/ffmpeg"
FF_ARM="$BUILD_DIR/ffmpeg-arm64"
FF_X86="$BUILD_DIR/ffmpeg-x86_64"
FFMPEG_URL_ARM="${FFMPEG_URL_ARM:-https://ffmpeg.martin-riedl.de/redirect/latest/macos/arm64/release/ffmpeg.zip}"
FFMPEG_URL_X86="${FFMPEG_URL_X86:-https://evermeet.cx/ffmpeg/getrelease/zip}"

fetch_slice() {   # fetch_slice <dest> <override> <url> <label>
    local dest="$1" override="$2" url="$3" label="$4"
    if [[ -n "$override" ]]; then
        echo "    Using provided $label: $override"
        cp "$override" "$dest"
    else
        echo "    Downloading $label"
        curl -L --fail -o "$dest.zip" "$url"
        unzip -o -j "$dest.zip" ffmpeg -d "$BUILD_DIR" >/dev/null
        mv "$BUILD_DIR/ffmpeg" "$dest"
    fi
    chmod +x "$dest"
}

fetch_slice "$FF_ARM" "${FFMPEG_STATIC_ARM64:-}" "$FFMPEG_URL_ARM" "arm64 static build"
fetch_slice "$FF_X86" "${FFMPEG_STATIC_X86_64:-}" "$FFMPEG_URL_X86" "x86_64 static build"

# Gate each slice BEFORE merging: check the architecture is what we asked for and
# that the build is redistributable. --enable-nonfree builds are NOT.
for slice in "arm64:$FF_ARM" "x86_64:$FF_X86"; do
    want="${slice%%:*}"; path="${slice#*:}"
    got="$(lipo -archs "$path" 2>/dev/null || echo unknown)"
    if [[ "$got" != *"$want"* ]]; then
        echo "ERROR: expected a $want binary, got '$got' ($path)."; exit 1
    fi
    if "$path" -version 2>/dev/null | grep -q -- "--enable-nonfree"; then
        echo "ERROR: the $want ffmpeg is --enable-nonfree and cannot be redistributed."
        echo "Use a GPL/LGPL build."; exit 1
    fi
done

lipo -create "$FF_ARM" "$FF_X86" -output "$FFMPEG_BIN"
chmod +x "$FFMPEG_BIN"
FF_ARCHS="$(lipo -archs "$FFMPEG_BIN")"
if [[ "$FF_ARCHS" != *arm64* || "$FF_ARCHS" != *x86_64* ]]; then
    echo "ERROR: merged ffmpeg is not universal (archs: $FF_ARCHS)."; exit 1
fi
FFVER="$("$FFMPEG_BIN" -version 2>/dev/null | head -1)"
echo "    universal ffmpeg: $FF_ARCHS ($(du -h "$FFMPEG_BIN" | cut -f1))"
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

# A genuinely universal .app needs a universal2 interpreter — PyInstaller thins
# every bundled binary (including our universal ffmpeg) to the target arch, and
# it cannot target universal2 from a single-arch Python. Prefer a universal2
# interpreter if one is installed; otherwise build native and say so plainly,
# rather than shipping something labelled universal that is not.
PY_ARCHS="$(lipo -archs "$("$BUILD_PYTHON" -c 'import sys; print(sys.executable)')" 2>/dev/null || echo '')"
if [[ "$PY_ARCHS" == *arm64* && "$PY_ARCHS" == *x86_64* ]]; then
    export VTN_TARGET_ARCH="universal2"
    echo "    universal2 Python -> building a UNIVERSAL app (Apple Silicon + Intel)"
else
    unset VTN_TARGET_ARCH || true
    echo "    NOTE: this Python is '$PY_ARCHS' only, so the app will be $PY_ARCHS-only."
    echo "          The bundled ffmpeg gets thinned to match. For a universal app,"
    echo "          build with a universal2 Python, e.g."
    echo "          PYTHON=/Library/Frameworks/Python.framework/Versions/3.11/bin/python3"
fi

# Encoder gate: MP3 and AAC output need these present in EVERY slice — a
# universal binary whose arm64 half lacked libmp3lame would ship a build that
# silently fails MP3 output on exactly the machines most people now use.
#
# The foreign slice can only be run if the build host can execute it (an x86_64
# slice needs Rosetta on Apple Silicon, and an arm64 slice cannot run on Intel
# at all), so that check is best-effort and says so rather than failing a build
# it cannot actually verify.
check_encoders() {   # check_encoders <arch> <binary>
    local a="$1" bin="$2"
    if ! arch -"$a" "$bin" -hide_banner -encoders >/dev/null 2>&1; then
        echo "    NOTE: cannot exec the $a slice on this host — encoders unverified there"
        return 0
    fi
    for enc in libmp3lame aac; do
        if ! arch -"$a" "$bin" -hide_banner -encoders 2>/dev/null | grep -q " $enc "; then
            echo "ERROR: the $a slice is missing the '$enc' encoder."
            exit 1
        fi
    done
    echo "    $a slice: libmp3lame + aac present"
}
echo "==> Checking encoders in both slices"
check_encoders arm64  "$FFMPEG_BIN"
check_encoders x86_64 "$FFMPEG_BIN"

echo "==> Creating build virtualenv"
"$BUILD_PYTHON" -m venv "$VENV_DIR"
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
pip install --quiet --upgrade pip
# pywebview pulls the pyobjc WKWebView backend on macOS
# pillow: the spec inlines the background into the HTML and re-encodes
# it as JPEG (see packaging/inline_assets.py). Without pillow it still
# builds, but embeds the far larger PNG.
pip install --quiet pyinstaller pywebview pillow

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
