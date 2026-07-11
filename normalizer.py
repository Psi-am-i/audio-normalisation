#!/usr/bin/env python3
"""
Core audio normalization module using ffmpeg's loudnorm filter.
Implements two-pass loudness normalization to achieve consistent -12 LUFS output.
"""

import subprocess
import json
import math
import os
import shutil
import sys
from pathlib import Path
from typing import Optional, Dict, Tuple


SUPPORTED_FORMATS = {'.m4a', '.wav', '.flac', '.mp3', '.aiff', '.ogg'}

# Single source of truth for defaults. Front-ends (normalize.py, watcher.py)
# import these rather than hardcoding, so behaviour can't drift between modes.
DEFAULT_TARGET_LUFS = -12.0
DEFAULT_OUTPUT_FORMAT = 'aiff'  # uncompressed PCM; plays on all Pioneer/CDJ gear
DEFAULT_BITRATE = 320           # kbps, lossy formats only
BITRATES = (320, 256, 192)      # offered choices, kbps

# Output format registry — single source of truth for every front-end.
#   ext        output file extension
#   lossy      True if a bitrate applies
#   art        cover-art strategy: 'copy' (map + stream-copy), 'copy_front'
#              (copy + label the picture "Cover (front)" — FLAC takes its
#              PICTURE type from the stream comment and defaults to "Other",
#              which some players won't display), 'attached_pic' (m4a needs
#              the disposition set), or None (container can't carry art — WAV)
#   summary    one-line description for menus/log lines
#   gear       Pioneer support note (verified against pioneerdj.com specs and
#              the joeselway/Pioneer-DJ-File-Formats matrix, Jul 2026)
OUTPUT_FORMATS = {
    'aiff': {
        'ext': '.aiff', 'lossy': False, 'art': 'copy',
        'summary': 'uncompressed lossless, 24-bit (largest files)',
        'gear': 'plays on ALL Pioneer/CDJ gear',
    },
    'flac': {
        'ext': '.flac', 'lossy': False, 'art': 'copy_front',
        'summary': 'compressed lossless (smaller than AIFF/WAV)',
        'gear': ('CDJ-3000/2000NXS2/TOUR1, XDJ-1000MK2/RX2/RX3/XZ/AZ, Opus '
                 'Quad only — NOT CDJ-2000NXS & older, CDJ-900, XDJ-700/1000/RX'),
    },
    'wav': {
        'ext': '.wav', 'lossy': False, 'art': None,
        'summary': 'uncompressed lossless, 16-bit (no cover art in WAV)',
        'gear': ('plays on ALL Pioneer/CDJ gear (written 16-bit: 24-bit WAV '
                 'uses a WAVE_EXTENSIBLE header some CDJ firmware rejects)'),
    },
    'mp3': {
        'ext': '.mp3', 'lossy': True, 'art': 'copy',
        'summary': 'the granddaddy of lossy formats — good at high bitrates',
        'gear': 'plays on ALL Pioneer/CDJ gear',
    },
    'aac': {
        'ext': '.m4a', 'lossy': True, 'art': 'attached_pic',
        'summary': 'lossy like MP3 but more modern — better at the same size/bitrate',
        'gear': 'plays on all modern Pioneer/CDJ gear (CDJ-350/850/900/2000 onward, all XDJ)',
    },
}


_AAC_ENCODER = None


def aac_encoder() -> str:
    """
    Best available AAC encoder. Apple's AudioToolbox encoder (aac_at, present
    in macOS ffmpeg builds) honours the requested bitrate and sounds better;
    ffmpeg's native 'aac' clamps around ~224k for 44.1kHz stereo no matter
    what is asked for. Probed once, then cached.
    """
    global _AAC_ENCODER
    if _AAC_ENCODER is None:
        try:
            out = subprocess.run([resolve_ffmpeg(), '-hide_banner', '-encoders'],
                                 capture_output=True, text=True).stdout
            _AAC_ENCODER = 'aac_at' if ' aac_at ' in out else 'aac'
        except Exception:
            _AAC_ENCODER = 'aac'
    return _AAC_ENCODER


def codec_args(output_format: str, bitrate: int = DEFAULT_BITRATE,
               compression_level: int = 8) -> list:
    """ffmpeg codec arguments for an output format (bitrate: lossy only)."""
    if output_format == 'aiff':
        # 24-bit big-endian PCM; ID3v2 chunk so tags survive in AIFF
        return ['-c:a', 'pcm_s24be', '-write_id3v2', '1']
    if output_format == 'flac':
        return ['-c:a', 'flac', '-compression_level', str(compression_level)]
    if output_format == 'wav':
        # 16-bit: >16-bit WAV gets a WAVE_EXTENSIBLE header that some CDJ
        # firmware rejects. Use AIFF for 24-bit lossless instead.
        return ['-c:a', 'pcm_s16le']
    if output_format == 'mp3':
        # ID3v2.3 — the version rekordbox/CDJ firmware handles most reliably
        return ['-c:a', 'libmp3lame', '-b:a', f'{bitrate}k', '-id3v2_version', '3']
    if output_format == 'aac':
        return ['-c:a', aac_encoder(), '-b:a', f'{bitrate}k',
                '-movflags', '+faststart']
    raise ValueError(f"unknown output format: {output_format}")


def resolve_ffmpeg() -> str:
    """
    Locate the ffmpeg binary to use, in priority order:

    1. Bundled alongside a frozen (PyInstaller) build
    2. FFMPEG_BINARY environment override
    3. ffmpeg found on PATH
    4. Common Homebrew locations (launchd runs with a minimal PATH)

    Returns the resolved path, or bare 'ffmpeg' as a last resort so the
    subprocess call fails with a clear error rather than silently.
    """
    candidates = []

    # Bundled binary (PyInstaller sets sys.frozen / sys._MEIPASS)
    exe = 'ffmpeg.exe' if sys.platform.startswith('win') else 'ffmpeg'
    if getattr(sys, 'frozen', False):
        base = Path(getattr(sys, '_MEIPASS', Path(sys.executable).parent))
        candidates.append(base / exe)
        candidates.append(Path(sys.executable).parent / exe)

    env_override = os.environ.get('FFMPEG_BINARY')
    if env_override:
        candidates.insert(0, Path(env_override))

    on_path = shutil.which('ffmpeg')
    if on_path:
        candidates.append(Path(on_path))

    candidates.append(Path('/opt/homebrew/bin/ffmpeg'))
    candidates.append(Path('/usr/local/bin/ffmpeg'))

    for candidate in candidates:
        if candidate and candidate.exists():
            return str(candidate)

    return 'ffmpeg'


def _ffmpeg_error_summary(stderr: str) -> str:
    """Pull a concise, human-readable reason out of ffmpeg's verbose stderr."""
    if not stderr:
        return "no error output from ffmpeg"
    lines = [ln.strip() for ln in stderr.strip().splitlines() if ln.strip()]
    # The actual cause is almost always on the last meaningful line.
    for ln in reversed(lines):
        low = ln.lower()
        if any(k in low for k in ("error", "invalid", "no such", "denied",
                                  "does not contain", "unable", "failed",
                                  "not found", "permission")):
            return ln
    return lines[-1] if lines else "unknown ffmpeg error"


def validate_file(file_path: str) -> bool:
    """
    Validate that file exists and has supported format.

    Args:
        file_path: Path to audio file

    Returns:
        True if valid, False otherwise
    """
    path = Path(file_path)

    if not path.exists():
        return False

    if not path.is_file():
        return False

    if path.suffix.lower() not in SUPPORTED_FORMATS:
        return False

    return True


def analyze_loudness(input_file: str, target_lufs: float = DEFAULT_TARGET_LUFS) -> Optional[Dict[str, float]]:
    """
    First pass: Analyze audio file to measure current loudness.

    Args:
        input_file: Path to input audio file
        target_lufs: Target loudness level in LUFS (default: -12.0)

    Returns:
        Dictionary with measured values or None if analysis fails
        Keys: measured_I, measured_LRA, measured_TP, measured_thresh
    """
    # Build ffmpeg command for analysis pass
    cmd = [
        resolve_ffmpeg(),
        '-i', input_file,
        '-af', f'loudnorm=I={target_lufs}:print_format=json',
        '-f', 'null',
        '-'
    ]

    try:
        # Run ffmpeg and capture stderr (where loudnorm outputs JSON)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )

        # Extract JSON from stderr
        # loudnorm outputs JSON at the end of stderr
        stderr_lines = result.stderr.strip().split('\n')

        # Find the JSON block (starts with opening brace after '[Parsed_loudnorm')
        json_start = None
        json_end = None

        for i, line in enumerate(stderr_lines):
            if 'Parsed_loudnorm' in line:
                # JSON starts on the next line
                json_start = i + 1
                break

        if json_start is None:
            print(f"Error: Could not find loudnorm output in ffmpeg stderr")
            return None

        # Find where JSON ends (look for closing brace)
        brace_count = 0
        for i in range(json_start, len(stderr_lines)):
            line = stderr_lines[i].strip()
            if '{' in line:
                brace_count += line.count('{')
            if '}' in line:
                brace_count -= line.count('}')
                if brace_count == 0:
                    json_end = i + 1
                    break

        if json_end is None:
            print(f"Error: Could not find end of JSON block")
            return None

        # Extract only the JSON lines
        json_str = '\n'.join(stderr_lines[json_start:json_end])
        measurements = json.loads(json_str)

        # Extract the measured values we need
        values = {
            'measured_I': float(measurements['input_i']),
            'measured_LRA': float(measurements['input_lra']),
            'measured_TP': float(measurements['input_tp']),
            'measured_thresh': float(measurements['input_thresh'])
        }

        # Silent or near-empty audio measures -inf; passing that back into the
        # loudnorm filter makes ffmpeg abort with a cryptic "Result too large".
        if not all(map(math.isfinite, values.values())):
            print(f"Error: {Path(input_file).name} has no measurable audio (silent or empty?)")
            return None

        return values

    except subprocess.CalledProcessError as e:
        print(f"Error analyzing {input_file}: {e.stderr}")
        return None
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        print(f"Error parsing loudness measurements: {e}")
        return None


def normalize_audio(
    input_file: str,
    output_file: str,
    target_lufs: float = DEFAULT_TARGET_LUFS,
    output_format: str = DEFAULT_OUTPUT_FORMAT,
    bitrate: int = DEFAULT_BITRATE,
    compression_level: int = 8
) -> Tuple[bool, str]:
    """
    Two-pass audio normalization to target LUFS level.

    Args:
        input_file: Path to input audio file
        output_file: Path to output file
        target_lufs: Target loudness level in LUFS (default: -12.0)
        output_format: one of OUTPUT_FORMATS ('aiff', 'flac', 'wav', 'mp3',
            'aac'). Default 'aiff'.
        bitrate: kbps for lossy formats (mp3/aac); ignored for lossless
        compression_level: FLAC compression level 0-12 (default: 8)

    Returns:
        Tuple of (success: bool, message: str)
    """
    if output_format not in OUTPUT_FORMATS:
        return False, f"unknown output format: {output_format}"
    # Validate input file
    if not validate_file(input_file):
        return False, f"not a supported audio file: {Path(input_file).name}"

    # Guard: never read and write the same file. This is the classic "I already
    # had an AIFF in the folder" case — when SOURCE and DESTINATION are the same
    # folder, an existing track.aiff maps to an output named track.aiff, i.e. the
    # very file we're reading. ffmpeg can't do a safe in-place overwrite.
    try:
        same_file = Path(input_file).resolve() == Path(output_file).resolve()
    except OSError:
        same_file = False
    if same_file:
        return False, ("output would overwrite the source file — "
                       "pick a DESTINATION folder that isn't the source folder")

    # Pass 1: Analyze loudness
    print(f"Analyzing: {Path(input_file).name}")
    measurements = analyze_loudness(input_file, target_lufs)

    if measurements is None:
        return False, "Failed to analyze loudness"

    # Pass 2: Apply normalization with measured values
    print(f"Normalizing to {target_lufs} LUFS...")

    loudnorm_filter = (
        f"loudnorm=I={target_lufs}:"
        f"LRA=11:"
        f"TP=-1.5:"
        f"measured_I={measurements['measured_I']}:"
        f"measured_LRA={measurements['measured_LRA']}:"
        f"measured_TP={measurements['measured_TP']}:"
        f"measured_thresh={measurements['measured_thresh']}:"
        f"print_format=summary"
    )

    art = OUTPUT_FORMATS[output_format]['art']

    # Cover-art stream mapping is per-container: WAV can't carry a picture at
    # all, and .m4a needs the stream flagged as attached_pic or the muxer
    # refuses it.
    art_map_args = [] if art is None else ['-map', '0:v?']
    art_out_args = []
    if art is not None:
        art_out_args = ['-c:v', 'copy']       # copy cover art without re-encoding
        if art == 'attached_pic':
            art_out_args += ['-disposition:v', 'attached_pic']
        elif art == 'copy_front':
            art_out_args += ['-metadata:s:v', 'comment=Cover (front)']

    cmd = [
        resolve_ffmpeg(),
        '-i', input_file,
        '-map', '0:a',            # explicit audio stream
        *art_map_args,            # cover art if present (? = optional, no error if absent)
        '-af', loudnorm_filter,
        '-ar', '44100',           # loudnorm outputs 192kHz by default; pin to 44.1k
                                  # (rekordbox/CDJs reject audio above 48kHz)
        *codec_args(output_format, bitrate, compression_level),
        *art_out_args,
        '-map_metadata', '0',     # copy all metadata tags
        '-y',  # Overwrite output file if exists
        output_file
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )

        output_path = Path(output_file)
        if output_path.exists():
            size_mb = output_path.stat().st_size / (1024 * 1024)
            return True, f"Success: {output_path.name} ({size_mb:.2f} MB)"
        else:
            return False, "Output file was not created"

    except subprocess.CalledProcessError as e:
        return False, f"ffmpeg failed — {_ffmpeg_error_summary(e.stderr)}"


def get_output_filename(input_file: str, destination_folder: str,
                        output_format: str = DEFAULT_OUTPUT_FORMAT) -> str:
    """
    Generate output filename with the extension for the chosen format.

    Args:
        input_file: Path to input file
        destination_folder: Destination folder path
        output_format: one of OUTPUT_FORMATS

    Returns:
        Full path to output file
    """
    input_path = Path(input_file)
    ext = OUTPUT_FORMATS[output_format]['ext']
    output_name = input_path.stem + ext
    return str(Path(destination_folder) / output_name)


def find_audio_files(source_path) -> list:
    """
    Find all supported audio files at a path (single file or directory tree).

    Args:
        source_path: str or Path to a file or directory

    Returns:
        Sorted list of Path objects for supported audio files.
    """
    path = Path(source_path)

    if path.is_file():
        return [path] if path.suffix.lower() in SUPPORTED_FORMATS else []

    audio_files = []
    for ext in SUPPORTED_FORMATS:
        audio_files.extend(path.rglob(f'*{ext}'))
        audio_files.extend(path.rglob(f'*{ext.upper()}'))

    return sorted(set(audio_files))


if __name__ == '__main__':
    # Simple test mode
    import sys

    if len(sys.argv) < 3:
        print("Usage: python normalizer.py <input_file> <output_folder>")
        sys.exit(1)

    input_file = sys.argv[1]
    output_folder = sys.argv[2]

    if not os.path.exists(output_folder):
        print(f"Creating output folder: {output_folder}")
        os.makedirs(output_folder)

    output_file = get_output_filename(input_file, output_folder)

    success, message = normalize_audio(input_file, output_file)
    print(message)
    sys.exit(0 if success else 1)
