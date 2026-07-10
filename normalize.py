#!/usr/bin/env python3
"""
Manual mode audio normalization script.
Prompts user for source and destination paths, then batch processes audio files.
"""

import os
import sys
import time
import multiprocessing
from pathlib import Path
from typing import List, Tuple
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm

import normalizer


def unescape_path(path_str: str) -> str:
    """
    Unescape shell-style escaped paths (handles drag-and-drop from Terminal).
    Removes backslash escapes before spaces and other special characters.

    Args:
        path_str: Path string potentially with shell escapes

    Returns:
        Unescaped path string
    """
    # Remove quotes if present
    path_str = path_str.strip().strip('"').strip("'")

    # Replace escaped spaces and other common shell escapes
    # This handles paths like: /Volumes/Cuz\ 4TB/Open\ Music
    result = []
    i = 0
    while i < len(path_str):
        if path_str[i] == '\\' and i + 1 < len(path_str):
            # Skip the backslash, keep the next character
            i += 1
            result.append(path_str[i])
        else:
            result.append(path_str[i])
        i += 1

    return ''.join(result)


def get_user_input(prompt: str) -> str:
    """Get user input with a prompt."""
    return unescape_path(input(prompt).strip())


def validate_source_path(path_str: str) -> Tuple[bool, str]:
    """
    Validate source path exists and is file or directory.

    Returns:
        (is_valid, error_message)
    """
    path = Path(path_str).expanduser()

    if not path.exists():
        return False, f"Path does not exist: {path_str}"

    if not (path.is_file() or path.is_dir()):
        return False, f"Path is not a file or directory: {path_str}"

    return True, ""


def validate_destination_path(path_str: str) -> Tuple[bool, str]:
    """
    Validate destination directory. Create if doesn't exist.

    Returns:
        (is_valid, error_message)
    """
    path = Path(path_str).expanduser()

    # If exists, must be a directory
    if path.exists() and not path.is_dir():
        return False, f"Destination exists but is not a directory: {path_str}"

    # Try to create if doesn't exist
    if not path.exists():
        try:
            path.mkdir(parents=True, exist_ok=True)
            print(f"Created destination directory: {path}")
        except Exception as e:
            return False, f"Could not create destination directory: {e}"

    return True, ""


def format_time(seconds: float) -> str:
    """Format seconds into human-readable time."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        mins = seconds / 60
        return f"{mins:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"


def process_single_file(args: Tuple[Path, Path, str, int]) -> Tuple[str, bool, str]:
    """
    Process a single audio file (wrapper for multiprocessing).

    Args:
        args: Tuple of (audio_file_path, dest_path, output_format, bitrate)

    Returns:
        Tuple of (filename, success, message)
    """
    audio_file, dest_path, output_format, bitrate = args

    # Generate output filename
    output_file = normalizer.get_output_filename(
        str(audio_file),
        str(dest_path),
        output_format
    )

    # Normalize
    success, message = normalizer.normalize_audio(
        str(audio_file),
        output_file,
        target_lufs=normalizer.DEFAULT_TARGET_LUFS,
        output_format=output_format,
        bitrate=bitrate
    )

    return (audio_file.name, success, message)


def main():
    """Main entry point for manual normalization mode."""
    print("=" * 60)
    print("Audio Normalization Tool - Manual Mode")
    print("=" * 60)
    print()

    # Get source path
    while True:
        source_input = get_user_input("Enter source path (file or folder): ")
        if not source_input:
            print("Error: Source path cannot be empty")
            continue

        is_valid, error = validate_source_path(source_input)
        if not is_valid:
            print(f"Error: {error}")
            continue

        source_path = Path(source_input).expanduser().resolve()
        break

    # Get destination path
    while True:
        dest_input = get_user_input("Enter destination folder: ")
        if not dest_input:
            print("Error: Destination path cannot be empty")
            continue

        is_valid, error = validate_destination_path(dest_input)
        if not is_valid:
            print(f"Error: {error}")
            continue

        dest_path = Path(dest_input).expanduser().resolve()
        break

    # Choose output format
    fmt_keys = list(normalizer.OUTPUT_FORMATS)  # aiff, flac, wav, mp3, aac
    print()
    print("Output format:")
    for n, key in enumerate(fmt_keys, 1):
        info = normalizer.OUTPUT_FORMATS[key]
        print(f"  [{n}] {key.upper():4s} — {info['summary']}")
        print(f"        gear: {info['gear']}")
    while True:
        fmt_in = get_user_input(
            f"Choose format [1-{len(fmt_keys)} or name, default 1=AIFF]: ").lower()
        if fmt_in == '':
            output_format = normalizer.DEFAULT_OUTPUT_FORMAT
            break
        if fmt_in in fmt_keys:
            output_format = fmt_in
            break
        if fmt_in.isdigit() and 1 <= int(fmt_in) <= len(fmt_keys):
            output_format = fmt_keys[int(fmt_in) - 1]
            break
        print(f"Please enter 1-{len(fmt_keys)} or a format name.")

    # Choose bitrate (lossy formats only)
    bitrate = normalizer.DEFAULT_BITRATE
    if normalizer.OUTPUT_FORMATS[output_format]['lossy']:
        choices = "/".join(str(b) for b in normalizer.BITRATES)
        while True:
            br_in = get_user_input(
                f"Bitrate in kbps [{choices}, default {normalizer.DEFAULT_BITRATE}]: ")
            if br_in == '':
                break
            if br_in.isdigit() and int(br_in) in normalizer.BITRATES:
                bitrate = int(br_in)
                break
            print(f"Please enter one of: {choices}.")

    fmt_desc = output_format.upper()
    if normalizer.OUTPUT_FORMATS[output_format]['lossy']:
        fmt_desc += f" {bitrate}kbps"
    print()
    print(f"Source: {source_path}")
    print(f"Destination: {dest_path}")
    print(f"Output format: {fmt_desc}")
    print()

    # Find audio files
    print("Scanning for audio files...")
    audio_files = normalizer.find_audio_files(source_path)

    if not audio_files:
        print("No supported audio files found!")
        print(f"Supported formats: {', '.join(sorted(normalizer.SUPPORTED_FORMATS))}")
        sys.exit(1)

    print(f"Found {len(audio_files)} audio file(s)")
    print()

    # Show some files as preview
    preview_count = min(5, len(audio_files))
    print("Files to process (showing first {}):".format(preview_count))
    for f in audio_files[:preview_count]:
        print(f"  - {f.name}")
    if len(audio_files) > preview_count:
        print(f"  ... and {len(audio_files) - preview_count} more")
    print()

    # Confirm
    confirm = get_user_input("Proceed with normalization? (y/n): ")
    if confirm.lower() != 'y':
        print("Cancelled.")
        sys.exit(0)

    # Ask about parallel processing
    workers_input = get_user_input("Number of parallel workers (default: auto, 1 for sequential): ").strip()
    if workers_input == '' or workers_input.lower() == 'auto':
        max_workers = min(os.cpu_count() or 4, len(audio_files))
    else:
        try:
            max_workers = int(workers_input)
            if max_workers < 1:
                max_workers = 1
        except ValueError:
            print(f"Invalid input, using auto ({os.cpu_count()} workers)")
            max_workers = min(os.cpu_count() or 4, len(audio_files))

    print()
    print(f"Starting normalization to -12 LUFS with {max_workers} worker(s)...")
    print("=" * 60)
    print()

    # Process files with progress bar
    successful = []
    failed = []
    start_time = time.time()

    # Prepare arguments for parallel processing
    process_args = [(audio_file, dest_path, output_format, bitrate) for audio_file in audio_files]

    # Process files in parallel with progress bar
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        futures = {executor.submit(process_single_file, args): args[0] for args in process_args}

        # Track progress
        with tqdm(total=len(audio_files), unit='file', ncols=80) as pbar:
            for future in as_completed(futures):
                audio_file = futures[future]
                pbar.set_description(f"Processing: {audio_file.name[:30]}")

                try:
                    filename, success, message = future.result()

                    if success:
                        successful.append((filename, message))
                    else:
                        failed.append((filename, message))

                except Exception as e:
                    failed.append((audio_file.name, f"Exception: {str(e)}"))

                pbar.update(1)

    # Print summary
    elapsed_time = time.time() - start_time

    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total files: {len(audio_files)}")
    print(f"Successful: {len(successful)}")
    print(f"Failed: {len(failed)}")
    print(f"Time elapsed: {format_time(elapsed_time)}")
    print()

    if failed:
        print("Failed files:")
        for filename, error in failed:
            print(f"  - {filename}: {error}")
        print()

    if successful:
        print(f"Normalized files saved to: {dest_path}")

    sys.exit(0 if len(failed) == 0 else 1)


if __name__ == '__main__':
    # Required for ProcessPoolExecutor in a frozen (PyInstaller) build: worker
    # processes re-exec this binary and must not re-run main(). No-op otherwise.
    multiprocessing.freeze_support()
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Exiting...")
        sys.exit(130)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
