#!/usr/bin/env python3
"""
One-off script to backfill metadata and cover art into existing normalised FLACs.

For each FLAC in NORMALISED, finds the matching source file in the main collection
and re-muxes: audio from FLAC + all metadata/cover art from source, no re-encoding.
"""

import os
import re
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

SOURCE_DIR = "/Users/simondavis/Library/CloudStorage/Dropbox/Open Music"
NORMALISED_DIR = "/Volumes/Cuz 4TB/NORMALISED"
AUDIO_EXTS = {'.mp3', '.wav', '.flac', '.m4a', '.mp4', '.aif', '.aiff'}


def normalise_key(filename):
    """Stem with leading '- ' stripped, NFC-normalised for cross-filesystem matching."""
    name = os.path.splitext(filename)[0]
    name = re.sub(r'^- ', '', name)
    return unicodedata.normalize('NFC', name.strip())


def build_source_map(source_dir):
    """Walk source dir and return {key: full_path} for all audio files."""
    source_map = {}
    for root, dirs, files in os.walk(source_dir):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for f in files:
            if Path(f).suffix.lower() in AUDIO_EXTS:
                k = normalise_key(f)
                source_map[k] = os.path.join(root, f)
    return source_map


def remux_metadata(flac_path, source_path):
    """
    Re-mux flac_path: keep audio from FLAC, pull all metadata + cover art from source.
    Writes to a temp file then replaces the original on success.
    """
    tmp = flac_path + '.tmp.flac'
    cmd = [
        'ffmpeg',
        '-i', flac_path,       # input 0: existing normalised audio
        '-i', source_path,     # input 1: original source for metadata/art
        '-map', '0:a',         # audio from normalised FLAC
        '-map', '1:v?',        # cover art from source (optional)
        '-c:a', 'copy',        # no re-encoding
        '-c:v', 'copy',
        '-map_metadata', '1',  # all tags from source
        '-y',
        tmp
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        if os.path.exists(tmp):
            os.remove(tmp)
        return False, result.stderr.splitlines()[-1] if result.stderr else 'unknown error'

    os.replace(tmp, flac_path)
    return True, 'ok'


def main():
    print("Building source file index...")
    source_map = build_source_map(SOURCE_DIR)
    print(f"  {len(source_map)} source files indexed")
    print()

    flac_files = sorted(f for f in os.listdir(NORMALISED_DIR) if f.endswith('.flac'))
    print(f"Processing {len(flac_files)} FLAC files in NORMALISED...\n")

    ok = []
    no_source = []
    failed = []

    for i, fname in enumerate(flac_files, 1):
        k = normalise_key(fname)
        source_path = source_map.get(k)

        if not source_path:
            no_source.append(fname)
            print(f"[{i}/{len(flac_files)}] NO SOURCE  {fname}")
            continue

        flac_path = os.path.join(NORMALISED_DIR, fname)
        success, msg = remux_metadata(flac_path, source_path)

        if success:
            ok.append(fname)
            print(f"[{i}/{len(flac_files)}] OK         {fname}")
        else:
            failed.append((fname, msg))
            print(f"[{i}/{len(flac_files)}] FAILED     {fname}: {msg}")

    print()
    print("=" * 60)
    print(f"Done:       {len(ok)}")
    print(f"No source:  {len(no_source)}")
    print(f"Failed:     {len(failed)}")

    if no_source:
        print("\nNo source found for:")
        for f in no_source:
            print(f"  {f}")

    if failed:
        print("\nFailed:")
        for f, msg in failed:
            print(f"  {f}: {msg}")

    sys.exit(0 if not failed else 1)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
