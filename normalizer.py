#!/usr/bin/env python3
"""
Core audio normalization module using ffmpeg's loudnorm filter.
Implements two-pass loudness normalization to achieve consistent -12 LUFS output.
"""

import subprocess
import json
import os
from pathlib import Path
from typing import Optional, Dict, Tuple


SUPPORTED_FORMATS = {'.m4a', '.wav', '.flac', '.mp3', '.aiff', '.ogg'}


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


def analyze_loudness(input_file: str, target_lufs: float = -12.0) -> Optional[Dict[str, float]]:
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
        'ffmpeg',
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
        return {
            'measured_I': float(measurements['input_i']),
            'measured_LRA': float(measurements['input_lra']),
            'measured_TP': float(measurements['input_tp']),
            'measured_thresh': float(measurements['input_thresh'])
        }

    except subprocess.CalledProcessError as e:
        print(f"Error analyzing {input_file}: {e.stderr}")
        return None
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        print(f"Error parsing loudness measurements: {e}")
        return None


def normalize_audio(
    input_file: str,
    output_file: str,
    target_lufs: float = -12.0,
    compression_level: int = 8
) -> Tuple[bool, str]:
    """
    Two-pass audio normalization to target LUFS level.

    Args:
        input_file: Path to input audio file
        output_file: Path to output FLAC file
        target_lufs: Target loudness level in LUFS (default: -12.0)
        compression_level: FLAC compression level 0-12 (default: 8)

    Returns:
        Tuple of (success: bool, message: str)
    """
    # Validate input file
    if not validate_file(input_file):
        return False, f"Invalid input file: {input_file}"

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

    cmd = [
        'ffmpeg',
        '-i', input_file,
        '-map', '0:a',            # explicit audio stream
        '-map', '0:v?',           # cover art if present (? = optional, no error if absent)
        '-af', loudnorm_filter,
        '-c:a', 'flac',
        '-compression_level', str(compression_level),
        '-c:v', 'copy',           # copy cover art without re-encoding
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
        return False, f"FFmpeg error: {e.stderr}"


def get_output_filename(input_file: str, destination_folder: str) -> str:
    """
    Generate output filename by replacing extension with .flac.

    Args:
        input_file: Path to input file
        destination_folder: Destination folder path

    Returns:
        Full path to output file
    """
    input_path = Path(input_file)
    output_name = input_path.stem + '.flac'
    return str(Path(destination_folder) / output_name)


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
