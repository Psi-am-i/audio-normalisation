#!/usr/bin/env python3
"""
Auto-watch daemon for audio normalization.
Monitors watch folder for new audio files and normalizes them automatically.
Designed to run via launchd as a background service.
"""

import os
import sys
import json
import time
import logging
from pathlib import Path
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

import normalizer


def load_config(config_path: str = 'config.json') -> dict:
    """
    Load configuration from JSON file.

    Args:
        config_path: Path to config file (default: config.json in same directory)

    Returns:
        Configuration dictionary
    """
    # Get absolute path relative to this script
    script_dir = Path(__file__).parent.resolve()
    config_file = script_dir / config_path

    if not config_file.exists():
        raise FileNotFoundError(f"Config file not found: {config_file}")

    with open(config_file, 'r') as f:
        config = json.load(f)

    return config


def setup_logging(log_file: str) -> logging.Logger:
    """
    Setup logging to file with rotation.

    Args:
        log_file: Path to log file

    Returns:
        Logger instance
    """
    # Expand user path
    log_path = Path(log_file).expanduser()

    # Create log directory if needed
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Configure logging
    logger = logging.getLogger('audio_normalizer')
    logger.setLevel(logging.INFO)

    # File handler
    file_handler = logging.FileHandler(log_path)
    file_handler.setLevel(logging.INFO)

    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)

    # Add handler
    logger.addHandler(file_handler)

    # Also log to console when running interactively
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


class AudioFileHandler(FileSystemEventHandler):
    """Handler for filesystem events in watch folder."""

    def __init__(self, config: dict, logger: logging.Logger):
        """
        Initialize handler.

        Args:
            config: Configuration dictionary
            logger: Logger instance
        """
        super().__init__()
        self.config = config
        self.logger = logger
        self.watch_folder = Path(config['watch_folder']).expanduser().resolve()
        self.dest_folder = Path(config['destination_folder']).expanduser().resolve()
        self.target_lufs = config.get('target_lufs', normalizer.DEFAULT_TARGET_LUFS)
        self.output_format = config.get('output_format', normalizer.DEFAULT_OUTPUT_FORMAT).lower()
        self.bitrate = int(config.get('bitrate', normalizer.DEFAULT_BITRATE))
        self.debounce_seconds = config.get('debounce_seconds', 2)
        # Format support is owned by the core engine; config no longer duplicates it.
        self.supported_formats = normalizer.SUPPORTED_FORMATS

        # Ensure destination exists
        self.dest_folder.mkdir(parents=True, exist_ok=True)

        self.logger.info(f"Initialized watcher:")
        self.logger.info(f"  Watch folder: {self.watch_folder}")
        self.logger.info(f"  Destination: {self.dest_folder}")
        self.logger.info(f"  Target LUFS: {self.target_lufs}")

    def on_created(self, event):
        """
        Handle file creation events.

        Args:
            event: Filesystem event
        """
        # Ignore directories
        if event.is_directory:
            return

        file_path = Path(event.src_path)

        # Check if file has supported extension
        if file_path.suffix.lower() not in self.supported_formats:
            return

        self.logger.info(f"Detected new file: {file_path.name}")

        # Debounce: wait for file to be fully written (Dropbox sync)
        self.logger.info(f"Waiting {self.debounce_seconds}s for file to complete...")
        time.sleep(self.debounce_seconds)

        # Check file still exists (might have been moved/deleted)
        if not file_path.exists():
            self.logger.warning(f"File disappeared: {file_path.name}")
            return

        # Process the file
        self.process_file(file_path)

    def process_file(self, file_path: Path):
        """
        Process an audio file (normalize and save to destination).

        Args:
            file_path: Path to audio file
        """
        try:
            start_time = time.time()

            self.logger.info(f"Processing: {file_path.name}")

            # Generate output filename
            output_file = normalizer.get_output_filename(
                str(file_path),
                str(self.dest_folder),
                self.output_format
            )

            # Normalize
            success, message = normalizer.normalize_audio(
                str(file_path),
                output_file,
                target_lufs=self.target_lufs,
                output_format=self.output_format,
                bitrate=self.bitrate
            )

            elapsed = time.time() - start_time

            if success:
                self.logger.info(f"Success: {file_path.name} -> {Path(output_file).name} ({elapsed:.1f}s)")
                self.logger.info(f"  {message}")
            else:
                self.logger.error(f"Failed: {file_path.name} - {message}")

        except Exception as e:
            self.logger.error(f"Error processing {file_path.name}: {e}")
            import traceback
            self.logger.error(traceback.format_exc())


def main():
    """Main entry point for watcher daemon."""
    try:
        # Load configuration
        config = load_config()

        # Setup logging
        log_file = config.get('log_file', '~/Library/Logs/audio-normalizer.log')
        logger = setup_logging(log_file)

        logger.info("=" * 60)
        logger.info("Audio Normalizer Daemon Starting")
        logger.info("=" * 60)

        # Validate watch folder exists
        watch_folder = Path(config['watch_folder']).expanduser().resolve()
        if not watch_folder.exists():
            logger.error(f"Watch folder does not exist: {watch_folder}")
            logger.error("Please create the folder or update config.json")
            sys.exit(1)

        # Create event handler and observer
        event_handler = AudioFileHandler(config, logger)
        observer = Observer()
        observer.schedule(event_handler, str(watch_folder), recursive=True)

        # Start watching
        observer.start()
        logger.info(f"Watching for audio files in: {watch_folder}")
        logger.info("Press Ctrl+C to stop (or use launchctl to stop daemon)")

        try:
            # Keep running until interrupted
            while observer.is_alive():
                observer.join(timeout=1)

        except KeyboardInterrupt:
            logger.info("Received interrupt signal, stopping...")
            observer.stop()

        observer.join()
        logger.info("Daemon stopped")

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
