#!/bin/bash
#
# Install audio normalizer daemon as launchd agent
#

set -e

PLIST_FILE="com.audiotools.normalizer.plist"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
PLIST_DEST="$LAUNCH_AGENTS_DIR/$PLIST_FILE"

echo "=========================================="
echo "Audio Normalizer Daemon Installer"
echo "=========================================="
echo

# Check if plist file exists
if [ ! -f "$PLIST_FILE" ]; then
    echo "Error: $PLIST_FILE not found in current directory"
    echo "Please run this script from the audio-normalisation directory"
    exit 1
fi

# Create LaunchAgents directory if it doesn't exist
if [ ! -d "$LAUNCH_AGENTS_DIR" ]; then
    echo "Creating LaunchAgents directory..."
    mkdir -p "$LAUNCH_AGENTS_DIR"
fi

# Check if already installed
if [ -f "$PLIST_DEST" ]; then
    echo "Daemon is already installed. Uninstalling first..."
    bash uninstall_daemon.sh
    echo
fi

# Copy plist to LaunchAgents
echo "Installing daemon..."
cp "$PLIST_FILE" "$PLIST_DEST"

# Load the agent
echo "Loading launchd agent..."
launchctl load "$PLIST_DEST"

# Start it immediately (it should start automatically, but just to be sure)
echo "Starting daemon..."
launchctl start com.audiotools.normalizer

# Wait a moment for it to start
sleep 2

# Check if it's running
if launchctl list | grep -q "com.audiotools.normalizer"; then
    echo
    echo "=========================================="
    echo "✅ Daemon installed and running!"
    echo "=========================================="
    echo
    echo "The audio normalizer will now watch:"
    echo "  $(python3 -c 'import json; print(json.load(open("config.json"))["watch_folder"])')"
    echo
    echo "Normalized files will be saved to:"
    echo "  $(python3 -c 'import json; print(json.load(open("config.json"))["destination_folder"])')"
    echo
    echo "Logs can be found at:"
    echo "  ~/Library/Logs/audio-normalizer.log"
    echo "  ~/Library/Logs/audio-normalizer-error.log"
    echo
    echo "To check status: launchctl list | grep audiotools"
    echo "To view logs: tail -f ~/Library/Logs/audio-normalizer.log"
    echo "To uninstall: bash uninstall_daemon.sh"
else
    echo
    echo "⚠️  Warning: Daemon may not be running"
    echo "Check logs: cat ~/Library/Logs/audio-normalizer-error.log"
    exit 1
fi
