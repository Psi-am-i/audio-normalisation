#!/usr/bin/env python3
"""
Core audio normalization module using ffmpeg's loudnorm filter.
Implements two-pass loudness normalization to achieve consistent -12 LUFS output.
"""

import subprocess
import json
import math
import os
import re
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

# Highest sample rate EVERY Pioneer/AlphaTheta player accepts. Verified against
# per-model specs (Aug 2026): CDJ-350, CDJ-850, CDJ-900, CDJ-2000, CDJ-2000NXS,
# XDJ-700, XDJ-1000/MK2 and XDJ-XZ all top out at 48 kHz for WAV/AIFF; only
# CDJ-3000, CDJ-2000NXS2 and Opus Quad reach 88.2/96 kHz.
#
# Sources at or below this are passed through at their OWN rate — a 48 kHz
# master stays 48 kHz. Only 88.2/96 kHz sources are resampled, and then to
# 48 kHz (not 44.1), because that is the least destructive rate every player
# can read. The previous unconditional '-ar 44100' bought no compatibility
# whatsoever and silently resampled every 48 kHz file.
MAX_GEAR_SAMPLE_RATE = 48000

# Input codecs that carry the audio without generation loss. Anything else
# (mp3, aac, vorbis, opus) has already been through a lossy encoder, so no
# output format can restore what it discarded.
LOSSLESS_CODECS = frozenset({'flac', 'alac', 'wavpack', 'tta', 'ape'})

# Losslessness by extension, for the cases where the container settles it. This
# exists so a front-end can classify a whole library INSTANTLY, without spawning
# ffmpeg once per file — probing a few thousand tracks takes minutes and is not
# worth it to answer a question the filename already answers.
#
# '.m4a' is deliberately absent: it carries AAC (lossy) or ALAC (lossless), so
# it is the one extension that genuinely needs a probe.
LOSSLESS_BY_EXT = {'.flac': True, '.wav': True, '.aiff': True,
                   '.mp3': False, '.ogg': False}


def lossless_by_extension(path) -> Optional[bool]:
    """
    True/False if the extension settles whether a file is lossless, else None.

    None means "ask probe_source()" — currently only .m4a, which may be ALAC
    (lossless) or AAC (lossy).
    """
    return LOSSLESS_BY_EXT.get(Path(path).suffix.lower())

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
#   preserves  what this format does to a LOSSLESS source. Front-ends turn this
#              into the plain-English guarantee shown next to the format picker:
#                'exact'  lossless in -> lossless out, full bit depth kept
#                '16bit'  still lossless, but bit depth is cut to 16
#                'lossy'  re-encoded through a lossy codec; not reversible
OUTPUT_FORMATS = {
    'aiff': {
        'ext': '.aiff', 'lossy': False, 'art': 'copy', 'preserves': 'exact',
        'summary': 'uncompressed lossless, 24-bit (largest files)',
        'gear': 'plays on ALL Pioneer/CDJ gear',
    },
    'flac': {
        'ext': '.flac', 'lossy': False, 'art': 'copy_front', 'preserves': 'exact',
        'summary': 'compressed lossless (smaller than AIFF/WAV)',
        'gear': ('CDJ-3000/2000NXS2/TOUR1, XDJ-1000MK2/RX2/RX3/XZ/AZ, Opus '
                 'Quad only — NOT CDJ-2000NXS & older, CDJ-900, XDJ-700/1000/RX'),
    },
    'wav': {
        'ext': '.wav', 'lossy': False, 'art': None, 'preserves': '16bit',
        'summary': 'uncompressed lossless, 16-bit (no cover art in WAV)',
        'gear': ('plays on ALL Pioneer/CDJ gear (written 16-bit: 24-bit WAV '
                 'uses a WAVE_EXTENSIBLE header some CDJ firmware rejects)'),
    },
    'mp3': {
        'ext': '.mp3', 'lossy': True, 'art': 'copy', 'preserves': 'lossy',
        'summary': 'the granddaddy of lossy formats — good at high bitrates',
        'gear': 'plays on ALL Pioneer/CDJ gear',
    },
    'aac': {
        'ext': '.m4a', 'lossy': True, 'art': 'attached_pic', 'preserves': 'lossy',
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
        # Pinned to 24-bit like AIFF. loudnorm works in float and applies a gain
        # change, so writing back to 16 bits would requantize the result and
        # throw away a little of what the filter just computed. Every player
        # that reads FLAC at all (CDJ-3000/2000NXS2/Opus Quad) reads 24-bit
        # FLAC, so this costs nothing in compatibility.
        return ['-c:a', 'flac', '-sample_fmt', 's32',
                '-compression_level', str(compression_level)]
    if output_format == 'wav':
        # 16-bit: >16-bit WAV gets a WAVE_EXTENSIBLE header (wFormatTag 0xFFFE)
        # that some CDJ firmware rejects — ffmpeg emits it for ANY 24-bit WAV
        # and offers no way to suppress it. This is the one output format that
        # cannot preserve a 24-bit source; OUTPUT_FORMATS marks it '16bit' so
        # front-ends can say so. Use AIFF for 24-bit lossless instead.
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


def _parse_input_stream(stderr: str) -> Dict:
    """
    Pull codec / sample rate / bit depth out of ffmpeg's 'Input #0' block.

    ffmpeg prints the same 'Stream #0:0: Audio: ...' shape for both the input
    and the output, so this is scoped to the lines between 'Input #0' and the
    first 'Output #' — taking the wrong one would report the output's format as
    if it were the source's.

    Deliberately parsed from ffmpeg rather than ffprobe: the packaged app
    bundles only the ffmpeg binary (see packaging/normalizer-gui.spec), so a
    dependency on ffprobe would work from source and break in the shipped app.

    Returns {'codec', 'sample_rate', 'bits', 'lossless'} with None for anything
    that couldn't be read.
    """
    info = {'codec': None, 'sample_rate': None, 'bits': None, 'lossless': None}

    in_input = False
    line = None
    for raw in stderr.splitlines():
        s = raw.strip()
        if s.startswith('Input #'):
            in_input = True
            continue
        if s.startswith('Output #'):
            break
        if in_input and ': Audio:' in s:
            line = s
            break

    if line is None:
        return info

    detail = line.split(': Audio:', 1)[1].strip()
    codec = re.split(r'[\s,(]', detail, 1)[0].strip().lower()
    info['codec'] = codec or None

    rate = re.search(r'(\d+)\s*Hz', detail)
    if rate:
        info['sample_rate'] = int(rate.group(1))

    # Bit depth, in order of reliability: ffmpeg's explicit "(24 bit)" note,
    # then the PCM codec name, then the sample-format token. Lossy codecs
    # decode to float and have no meaningful source bit depth.
    explicit = re.search(r'\((\d+)\s*bit\)', detail)
    if explicit:
        info['bits'] = int(explicit.group(1))
    elif codec.startswith('pcm_'):
        m = re.search(r'pcm_[su](\d+)', codec)
        if m:
            info['bits'] = int(m.group(1))
    else:
        m = re.search(r'(?:^|,\s*)s(16|32)(?:\s*,|\s*$)', detail)
        if m:
            info['bits'] = int(m.group(1))

    if codec:
        info['lossless'] = codec.startswith('pcm_') or codec in LOSSLESS_CODECS

    return info


def probe_source(input_file: str) -> Dict:
    """
    Read a file's codec / sample rate / bit depth without decoding it.

    'ffmpeg -i FILE' with no output prints the stream info, then exits non-zero
    with "At least one output file must be specified" — which is exactly what
    we want: header-only, ~60ms, no transcoding. Used by front-ends to tell the
    user up front how many of their tracks are lossless.
    """
    try:
        result = subprocess.run(
            [resolve_ffmpeg(), '-hide_banner', '-i', input_file],
            capture_output=True, text=True)
        return _parse_input_stream(result.stderr)
    except OSError:
        return {'codec': None, 'sample_rate': None, 'bits': None, 'lossless': None}


def target_sample_rate(source_rate: Optional[int]) -> Optional[int]:
    """
    The rate to write, given the source's rate.

    At or below MAX_GEAR_SAMPLE_RATE the source rate is kept exactly — a 48 kHz
    master stays 48 kHz, a 44.1 kHz one stays 44.1 kHz. Above it (88.2/96 kHz)
    the file is resampled down to 48 kHz, which is the highest rate every
    Pioneer player can read.

    Returns None when the source rate could not be read. Callers must supply
    their own fallback: loudnorm resamples to 192 kHz internally, so an output
    rate always has to be stated explicitly.
    """
    if source_rate is None:
        return None
    return source_rate if source_rate <= MAX_GEAR_SAMPLE_RATE else MAX_GEAR_SAMPLE_RATE


def preservation_note(output_format: str, source: Optional[Dict] = None) -> str:
    """
    One plain-English line describing what will happen to this file's quality.

    Front-ends show this next to the format picker so the lossless guarantee is
    visible at the moment of choosing, not buried in an About screen.
    """
    preserves = OUTPUT_FORMATS[output_format]['preserves']
    lossless_source = (source or {}).get('lossless')
    rate = (source or {}).get('sample_rate')
    resampled = rate is not None and rate > MAX_GEAR_SAMPLE_RATE

    if preserves == 'lossy':
        if lossless_source:
            return (f"lossless source will be compressed to "
                    f"{output_format.upper()} — this cannot be undone")
        return f"already lossy; re-encoded to {output_format.upper()}"

    if not lossless_source:
        return "lossy source — levelled, but quality can't be recovered"

    if preserves == '16bit':
        return "stays lossless, but WAV cuts bit depth to 16-bit"

    if resampled:
        return f"stays lossless; {rate} Hz resampled to {MAX_GEAR_SAMPLE_RATE} Hz for gear support"

    return "stays lossless — same sample rate, full bit depth"


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
    return _analyze(input_file, target_lufs)[0]


def _analyze(input_file: str,
             target_lufs: float = DEFAULT_TARGET_LUFS) -> Tuple[Optional[Dict[str, float]], Dict]:
    """
    The analysis pass, returning both the loudness measurements and the source's
    stream properties.

    The properties come free: this pass already runs ffmpeg over the file and
    captures its stderr, and that stderr carries the 'Input #0' block. Parsing
    it here means normalize_audio can pick the right output sample rate without
    spawning a second process per track.

    Returns (measurements or None, source info dict).
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

        # The source's codec/rate/bit depth, read from the same stderr.
        source = _parse_input_stream(result.stderr)

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
            return None, source

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
            return None, source

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
            return None, source

        return values, source

    except subprocess.CalledProcessError as e:
        print(f"Error analyzing {input_file}: {e.stderr}")
        return None, _parse_input_stream(e.stderr or '')
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        print(f"Error parsing loudness measurements: {e}")
        return None, {'codec': None, 'sample_rate': None, 'bits': None, 'lossless': None}


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

    # Pass 1: Analyze loudness (also reports the source's rate/depth/codec)
    print(f"Analyzing: {Path(input_file).name}")
    measurements, source = _analyze(input_file, target_lufs)

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

    # loudnorm resamples to 192 kHz internally, so an explicit output rate is
    # always required — without one the file would be written at 192 kHz and
    # play on nothing. The rate is the SOURCE's own, unless it exceeds what
    # every Pioneer player can read (see MAX_GEAR_SAMPLE_RATE). A 48 kHz master
    # therefore stays 48 kHz instead of being silently pulled down to 44.1.
    # If the rate couldn't be read, fall back to 44.1 kHz rather than guessing
    # higher: it is the near-universal DJ rate and plays on every player, so a
    # parse failure degrades to the old behaviour instead of upsampling.
    out_rate = target_sample_rate(source.get('sample_rate')) or 44100

    cmd = [
        resolve_ffmpeg(),
        '-i', input_file,
        '-map', '0:a',            # explicit audio stream
        *art_map_args,            # cover art if present (? = optional, no error if absent)
        '-af', loudnorm_filter,
        '-ar', str(out_rate),
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
