# Audio Normalization DJ's - by Picnic Labs

Professional audio normalization system for DJing. Normalizes music files to consistent -12 LUFS loudness for club playback on high-quality sound systems. Never fiddle with trim again...

## Features

- **Consistent Loudness:** Normalizes all tracks to -12 LUFS using EBU R128 standard
- **Five Output Formats:** Lossless AIFF (default), FLAC, WAV — or lossy MP3/AAC at 320/256/192 kbps
- **Two Modes:** Manual batch processing or automatic folder watching
- **Preserves Originals:** Never modifies source files
- **Club-Optimized:** No compression, just loudness normalization
- **Format Support:** M4A, WAV, FLAC, MP3, AIFF, OGG

## Download the app (easiest — nothing to install)

Grab the GUI app for your platform from the
[releases page](https://github.com/Psi-am-i/audio-normalisation/releases/latest).
Python and ffmpeg are bundled inside.

**macOS** (`PsiDJNormalizer-macos.zip`, Apple Silicon):

1. Unzip and drag `PsiDJNormalizer.app` to your Applications folder.
2. The app is unsigned, so macOS blocks the first launch. Pick either fix:
   - **Right-click → Open → Open** (needed once only), or
   - **Self-sign it** — one Terminal command, and it behaves like any normal
     app from then on:
     ```bash
     codesign --force --deep -s - /Applications/PsiDJNormalizer.app && xattr -rd com.apple.quarantine /Applications/PsiDJNormalizer.app
     ```
3. Start it by double-clicking, or `open /Applications/PsiDJNormalizer.app`.

**Windows** (`PsiDJNormalizer-windows.zip`):

1. Unzip the whole folder somewhere (keep the files together).
2. Double-click `PsiDJNormalizer.exe`. If SmartScreen objects, click
   **More info → Run anyway** (needed once only).

Everything below is for running from source (CLI + auto-watch daemon).

## Requirements (running from source)

- Python 3.7+
- ffmpeg (for audio processing)
- Auto-watch daemon mode: **macOS or Linux only** (the installer script uses
  launchd, so it's macOS; on Linux run `watcher.py` under systemd or similar)

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
2. **Destination folder:** Where normalized files will be saved

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

Automatically monitors a folder and normalizes any new audio files that appear.
Any folder works — local, external drive, or a cloud-synced one like Dropbox
(handy for dropping in purchases from your phone). **macOS/Linux only** — the
`install_daemon.sh` installer is macOS (launchd); on Linux run `watcher.py`
as a service yourself (e.g. systemd).

**Configuration:**
Edit `config.json` to set your folders:
```json
{
  "watch_folder": "/path/to/your/watch/folder",
  "destination_folder": "/path/to/your/output/folder",
  "target_lufs": -12,
  "output_format": "aiff",
  "bitrate": 320
}
```

**Install daemon:**
```bash
bash install_daemon.sh
```

The daemon will:
- Start automatically at login
- Watch the configured folder continuously
- Process new files immediately (after a 2-second debounce so files still
  arriving via cloud sync are complete)
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

## Shareable CLI App (for non-technical users)

Besides the GUI app above, you can build a self-contained, double-clickable
`Normalizer.app` that bundles Python and ffmpeg — recipients install nothing.
Double-clicking opens Terminal with the manual flow (source → destination →
format → bitrate, all five formats). The autowatch daemon is not included in
the app.

```bash
packaging/build_app.sh
```

Send `packaging/dist/Normalizer.zip` (the final outputs live in
`packaging/dist/`; anything under `packaging/build/` is an intermediate).
The app is unsigned, so on first launch the recipient either right-clicks →
**Open** → **Open**, or self-signs it once (see the Download section above,
substituting `Normalizer.app`). See [packaging/BUILD.md](packaging/BUILD.md)
for details and the architecture notes.

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
   - Outputs lossless AIFF (default) or FLAC with maximum compression

### Why -12 LUFS?

- Matches modern commercial dance music masters
- Hot enough for club systems without distortion
- Provides good headroom for system dynamics
- Consistent with streaming platform standards

### Output Formats & Pioneer Gear Compatibility

Five output formats are available in every mode (CLI menu, GUI FORMAT/BITRATE
buttons, `output_format` + `bitrate` in `config.json`). All output is pinned to
44.1 kHz — CDJs/rekordbox reject anything above 48 kHz.

| Format | Type | Bitrate | Pioneer support |
|--------|------|---------|-----------------|
| **AIFF** (default) | Lossless, uncompressed 24-bit | — | **ALL** CDJ/XDJ gear |
| **WAV** | Lossless, uncompressed 16-bit | — | **ALL** CDJ/XDJ gear |
| **FLAC** | Lossless, compressed (much smaller) | — | **Newer gear only** — see below |
| **MP3** | Lossy (libmp3lame, ID3v2.3) | 320/256/192 kbps | **ALL** CDJ/XDJ gear |
| **AAC** (.m4a) | Lossy (better than MP3 at same bitrate) | 320/256/192 kbps | All **modern** gear — see below |

**FLAC — supported:** CDJ-3000, CDJ-2000NXS2, CDJ-TOUR1, XDJ-1000MK2, XDJ-RX2,
XDJ-RX3, XDJ-XZ, XDJ-AZ, Opus Quad, Omnis Duo (and newer).
**FLAC — NOT supported:** CDJ-2000NXS and older, CDJ-900/900NXS, CDJ-850,
CDJ-350, XDJ-700, XDJ-1000 (mk1), XDJ-RX (mk1), XDJ-RR.

**AAC — supported** on all modern players (CDJ-350/850/900/2000 onward and every
XDJ). Only ancient CD-only decks (CDJ-800/1000 etc.) can't read it.

**FLAC cover art on macOS:** Finder and Quick Look never display embedded FLAC
artwork — an Apple limitation (they read FLAC's tags but ignore its PICTURE
block, so you get the generic music-note icon). The art **is** embedded in the
file, typed "Cover (front)", and rekordbox, CDJs, VLC etc. display it normally.

**Why 16-bit WAV?** ffmpeg writes 24-bit WAV with a `WAVE_FORMAT_EXTENSIBLE`
header that some CDJ firmware rejects. 16-bit WAV plays everywhere; if you want
24-bit lossless, use AIFF (that's why it's the default). Note WAV also cannot
carry embedded cover art — use AIFF/FLAC to keep artwork.

**AAC encoder note:** on macOS the bundled/detected ffmpeg uses Apple's
AudioToolbox encoder (`aac_at`), which genuinely hits 320 kbps. ffmpeg's
built-in `aac` encoder (used on Windows/Linux) caps out around ~224 kbps for
44.1 kHz stereo even when 320 is requested.

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

**Output formats** (CLI menu / GUI buttons / `output_format` in `config.json`):
- AIFF (lossless, uncompressed 24-bit — default)
- FLAC (lossless, compressed)
- WAV (lossless, uncompressed 16-bit)
- MP3 (lossy, 320/256/192 kbps)
- AAC/.m4a (lossy, 320/256/192 kbps)

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
ffmpeg -i output.aiff -af loudnorm=print_format=summary -f null - 2>&1 | grep -A 12 "Parsed_loudnorm"
```

Look for "Output Integrated" value - should be close to -12.0 LUFS.

## Tips for DJs

1. **Batch process before gigs:** Use manual mode to normalize your entire library
2. **Auto-process new purchases:** Enable daemon to handle new tracks automatically
3. **Test on your system:** Always audition normalized tracks on your DJ setup
4. **Keep originals:** Never delete source files - normalized output is separate
5. **USB stick preparation:** Copy normalized files to USB for CDJ/standalone gear

## Technical Details

- **Normalization standard:** EBU R128 (ITU-R BS.1770)
- **Target loudness:** -12 LUFS (Loudness Units relative to Full Scale)
- **True peak limit:** -1.5 dB (prevents inter-sample peaks)
- **Loudness range:** 11 LU (preserves dynamics)
- **Output formats:** AIFF (24-bit PCM, default), FLAC, WAV (16-bit PCM), MP3, AAC
- **FLAC compression:** Level 8 (maximum, when FLAC selected)
- **Lossy bitrates:** 320 (default) / 256 / 192 kbps CBR
- **Processing:** Two-pass for accuracy

## License

MIT License - Free to use for personal and commercial purposes. See [LICENSE](LICENSE) file for details.

This tool uses FFmpeg. When run from source you must have ffmpeg installed
separately (e.g. `brew install ffmpeg`). The distributable apps (see
`packaging/`) bundle a self-contained static **GPLv3** build of FFmpeg; the GPL
license text and attribution travel inside each app's zip (a `licenses` folder).
FFmpeg source: https://ffmpeg.org/releases/ — builds with `--enable-nonfree` are
deliberately refused by the build scripts, as they are not redistributable.

## Support

For issues or questions, check the logs first:
- `~/Library/Logs/audio-normalizer.log`
- `~/Library/Logs/audio-normalizer-error.log`

## Contributing

Issues and pull requests are welcome! This tool was created for the DJ community.

---

**Happy DJing! 🎧🔊**
