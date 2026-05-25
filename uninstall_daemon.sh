#!/bin/bash
#
# Uninstall audio normalizer daemon
#

set -e

PLIST_FILE="com.audiotools.normalizer.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/$PLIST_FILE"

echo "=========================================="
echo "Audio Normalizer Daemon Uninstaller"
echo "=========================================="
echo

# Check if installed
if [ ! -f "$PLIST_DEST" ]; then
    echo "Daemon is not installed."
    exit 0
fi

# Stop the agent
echo "Stopping daemon..."
launchctl stop com.audiotools.normalizer 2>/dev/null || true

# Unload it
echo "Unloading launchd agent..."
launchctl unload "$PLIST_DEST" 2>/dev/null || true

# Remove plist
echo "Removing plist file..."
rm "$PLIST_DEST"

echo
echo "=========================================="
echo "✅ Daemon uninstalled successfully"
echo "=========================================="
echo
echo "Note: Log files have been preserved at:"
echo "  ~/Library/Logs/audio-normalizer*.log"
echo
echo "To reinstall: bash install_daemon.sh"
