# Audio Normalization DJ's - by Picnic Labs

Professional audio normalization system for DJing. Normalizes music files to consistent -12 LUFS loudness for club playback on high-quality sound systems. Never fiddle with trim again...

## Features

- **Consistent Loudness:** Normalizes all tracks to -12 LUFS using EBU R128 standard
- **Lossless Output:** All files converted to FLAC for maximum quality
- **Two Modes:** Manual batch processing or automatic folder watching
- **Preserves Originals:** Never modifies source files
- **Club-Optimized:** No compression, just loudness normalization
- **Format Support:** M4A, WAV, FLAC, MP3, AIFF, OGG

## Requirements

- macOS (for daemon mode via launchd)
- Python 3.7+
- ffmpeg (for audio processing)

## Installation

### 1. Install ffmpeg (if not already installed)

```bash
brew install ffmpeg
```

### 2. Clone the repository

```bash
git clone https://github.com/psi-i-am/audio-normalisation.git
cd audio-normalisation
```

### 3. Install Python dependencies

```bash
pip3 install -r requirements.txt
```

## Usage

### Manual Mode

Interactive mode that prompts for source and destination folders. Perfect for batch processing.

```bash
python3 normalize.py
```

You'll be prompted for:
1. **Source path:** Single file or folder with audio files
2. **Destination folder:** Where normalized FLAC files will be saved

The script will:
- Scan for supported audio files
- Show preview and ask for confirmation
- Display progress bar during processing
- Show summary with success/failure counts

**Example:**
```
$ python3 normalize.py

Enter source path (file or folder): ~/Music/DJ/New-Tracks
Enter destination folder: ~/Music/DJ/Normalized

Found 15 audio file(s)

Files to process (showing first 5):
  - track01.m4a
  - track02.wav
  - track03.flac
  - track04.mp3
  - track05.aiff
  ... and 10 more

Proceed with normalization? (y/n): y

Processing: 100%|██████████| 15/15 [05:23<00:00]

SUMMARY
Total files: 15
Successful: 15
Failed: 0
Time elapsed: 5.4m
```

### Auto-Watch Mode (Daemon)

Automatically monitors a Dropbox folder and normalizes any new audio files that appear.

**Configuration:**
Edit `config.json` to set your folders:
```json
{
  "watch_folder": "/path/to/your/watch/folder",
  "destination_folder": "/path/to/your/output/folder",
  "target_lufs": -12
}
```

**Install daemon:**
```bash
bash install_daemon.sh
```

The daemon will:
- Start automatically at login
- Watch the configured folder continuously
- Process new files immediately (after 2-second debounce for Dropbox sync)
- Log all activity to `~/Library/Logs/audio-normalizer.log`
- Auto-restart if it crashes

**Check daemon status:**
```bash
launchctl list | grep audiotools
```

**View logs:**
```bash
# Live tail
tail -f ~/Library/Logs/audio-normalizer.log

# View errors
cat ~/Library/Logs/audio-normalizer-error.log
```

**Uninstall daemon:**
```bash
bash uninstall_daemon.sh
```

## How It Works

### Two-Pass Normalization

The tool uses ffmpeg's `loudnorm` filter with a two-pass process for accurate loudness normalization:

1. **Pass 1 (Analysis):** Measures current loudness levels
   - Integrated loudness (LUFS)
   - Loudness range (LRA)
   - True peak (TP)

2. **Pass 2 (Normalization):** Applies precise gain adjustment
   - Uses measurements from pass 1
   - Normalizes to -12 LUFS target
   - Prevents clipping with -1.5 dB true peak limit
   - Outputs lossless FLAC with maximum compression

### Why -12 LUFS?

- Matches modern commercial dance music masters
- Hot enough for club systems without distortion
- Provides good headroom for system dynamics
- Consistent with streaming platform standards

### Why FLAC Output?

- **Lossless:** Bit-perfect audio quality
- **Compressed:** Smaller than WAV (~50-60% size)
- **Metadata:** Supports tags (unlike WAV)
- **Universal:** Plays on all modern DJ gear

## File Structure

```
audio-normalisation/
├── normalize.py                        # Manual mode script
├── normalizer.py                       # Core normalization engine
├── watcher.py                         # Auto-watch daemon
├── config.json                        # Daemon configuration
├── requirements.txt                   # Python dependencies
├── com.audiotools.normalizer.plist    # launchd configuration
├── install_daemon.sh                  # Daemon installer
├── uninstall_daemon.sh                # Daemon uninstaller
└── README.md                          # This file
```

## Supported Formats

**Input formats:**
- M4A (Apple AAC)
- WAV (Uncompressed)
- FLAC (Lossless)
- MP3 (Lossy)
- AIFF (Apple Uncompressed)
- OGG (Vorbis)

**Output format:**
- FLAC (lossless, compressed)

## Troubleshooting

### "ffmpeg: command not found"

Install ffmpeg:
```bash
brew install ffmpeg
```

### Daemon not starting

Check error log:
```bash
cat ~/Library/Logs/audio-normalizer-error.log
```

Verify paths in `config.json` exist and are correct

### Files not being processed

1. Check daemon is running:
   ```bash
   launchctl list | grep audiotools
   ```

2. Check file format is supported (case-sensitive extension)

3. Check logs for errors:
   ```bash
   tail -50 ~/Library/Logs/audio-normalizer.log
   ```

### Normalized files too quiet/loud

The tool targets -12 LUFS. You can adjust by editing `config.json`:
```json
{
  "target_lufs": -11  // Louder: -11, -10, etc.
                      // Quieter: -13, -14, etc.
}
```

Then restart daemon:
```bash
bash uninstall_daemon.sh
bash install_daemon.sh
```

## Verifying Results

Check loudness of normalized file:
```bash
ffmpeg -i output.flac -af loudnorm=print_format=summary -f null - 2>&1 | grep -A 12 "Parsed_loudnorm"
```

Look for "Output Integrated" value - should be close to -12.0 LUFS.

## Tips for DJs

1. **Batch process before gigs:** Use manual mode to normalize your entire library
2. **Auto-process new purchases:** Enable daemon to handle new tracks automatically
3. **Test on your system:** Always audition normalized tracks on your DJ setup
4. **Keep originals:** Never delete source files - FLAC output is separate
5. **USB stick preparation:** Copy normalized FLACs to USB for CDJ/standalone gear

## Technical Details

- **Normalization standard:** EBU R128 (ITU-R BS.1770)
- **Target loudness:** -12 LUFS (Loudness Units relative to Full Scale)
- **True peak limit:** -1.5 dB (prevents inter-sample peaks)
- **Loudness range:** 11 LU (preserves dynamics)
- **FLAC compression:** Level 8 (maximum)
- **Processing:** Two-pass for accuracy

## License

MIT License - Free to use for personal and commercial purposes. See [LICENSE](LICENSE) file for details.

This tool uses FFMPEG, which is licensed under LGPL 2.1+. You must have FFMPEG installed separately.

## Support

For issues or questions, check the logs first:
- `~/Library/Logs/audio-normalizer.log`
- `~/Library/Logs/audio-normalizer-error.log`

## Contributing

Issues and pull requests are welcome! This tool was created for the DJ community.

---

**Happy DJing! 🎧🔊**
