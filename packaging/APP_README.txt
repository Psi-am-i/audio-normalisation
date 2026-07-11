# Psi's DJ Normalization (in a good way!) - by Picnic Labs

Professional audio normalization system for DJing. Normalizes music files to
consistent -12 LUFS loudness for club playback on high-quality sound systems.
Never fiddle with trim again...

## Features

- **Consistent Loudness:** Normalizes all tracks to -12 LUFS using EBU R128 standard
- **Five Output Formats:** Lossless AIFF (default), FLAC, WAV — or lossy MP3/AAC at 320/256/192 kbps
- **Two Modes:** Manual batch processing or automatic folder watching
- **Preserves Originals:** Never modifies source files
- **Club-Optimized:** No compression on lossless files, just loudness normalization
- Know exactly what Pioneer/AlphaTheta gear your files will work on
- **Format Support:** M4A, WAV, FLAC, MP3, AIFF, OGG

** INSTALLATION **

**macOS** (`PsiDJNormalizer-macos.zip`, Apple Silicon):

1. Unzip and drag `PsiDJNormalizer.app` to your Applications folder.
2. The app is unsigned, so macOS blocks the first launch. Pick either fix:
   - **Right-click → Open → Open** It will give an error. Go to System
     Settings → Privacy & Security, scroll down and say allow ("Open Anyway").
     Then open again (only need to do this once), or
   - **Self-sign it** — Before launch, open Terminal and paste the line below.
     Then it will behave like any normal app from then on:
     ```bash
     codesign --force --deep -s - /Applications/PsiDJNormalizer.app && xattr -rd com.apple.quarantine /Applications/PsiDJNormalizer.app
     ```
3. Start it by double-clicking, or `open /Applications/PsiDJNormalizer.app`.

**Windows** (`PsiDJNormalizer-windows.zip`):

1. Unzip the whole folder somewhere (keep the files together).
2. Double-click `PsiDJNormalizer.exe`. If SmartScreen objects, click
   **More info → Run anyway** (needed once only).

## In the window

- [ SOURCE ]       pick the folder with your tracks
- [ DESTINATION ]  pick where the normalized files go
- FORMAT           opens a menu: AIFF / FLAC / WAV / MP3 / AAC
- 320k             bitrate menu for MP3/AAC (320 / 256 / 192)
- ABOUT            the full gear-compatibility rundown
- > NORMALIZE      go

## How It Works

### Two-Pass Normalization

The tool uses ffmpeg's `loudnorm` filter with a two-pass process for accurate
loudness normalization:

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

---

Your originals are never changed. Everything is levelled to -12 LUFS.
Enjoy the terrible joke.

This app bundles FFmpeg (GPLv3) — see the "licenses" folder.
