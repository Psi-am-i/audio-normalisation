# Very Thoughtful Normalisation (but in a good way) - by Picnic Labs

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

**macOS** (`VTNormalisation-macos.zip`)

ONE download — it runs natively on both Apple Silicon and Intel Macs, so there
is nothing to choose between.

1. Unzip and drag "Very Thoughtful Normalisation.app" into your Applications
   folder.

2. The app isn't signed with a paid Apple certificate, so macOS will block it.
   Self-sign it once: open Terminal, paste this WHOLE line, press Return.

   codesign --force --deep -s - '/Applications/Very Thoughtful Normalisation.app' && xattr -rd com.apple.quarantine '/Applications/Very Thoughtful Normalisation.app'

3. Done — double-click to open it, now and every time after.

Why the Terminal step? Removing that warning permanently costs $99/year for an
Apple Developer ID. This app is free, so it uses the same approach Radarr and
Sonarr do: you sign it yourself, on your own machine, in one command. It
re-signs the app with a local ad-hoc signature and clears the "downloaded from
the internet" flag. Nothing is sent anywhere.

Don't bother with right-click then Open — macOS 15 (Sequoia) removed that
shortcut. Since then it means a trip through System Settings > Privacy &
Security plus an admin password. The one-liner above skips all of it.

**Windows** (`VTNormalisation-windows.zip`):

1. Unzip the whole folder somewhere (keep the files together).
2. Double-click `VTNormalisation.exe`. If SmartScreen objects, click
   **More info → Run anyway** (needed once only).

## In the window

- FROM      pick the folder with your tracks
- TO        pick where the normalized files go
- FORMAT    AIFF / FLAC / WAV / MP3 / AAC (bitrate appears for MP3/AAC)
- ABOUT     the full gear-compatibility rundown

Under the format row is a line telling you exactly what will happen to your
audio — e.g. "41 of 128 tracks are lossless — they stay lossless" — counted
from your own files, and it turns into a warning if you pick a lossy format.

While it runs you get a live list: what is queued, what is processing now, and
what is done. Stop is graceful — it finishes the track it is on, so nothing is
left half-written.

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
buttons, `output_format` + `bitrate` in `config.json`).

Lossless stays lossless: output keeps the source's OWN sample rate, up to
48 kHz. A 44.1 kHz track stays 44.1 kHz, a 48 kHz master stays 48 kHz. Only
sources above 48 kHz (88.2/96 kHz) are resampled, and then to 48 kHz — the
highest rate every Pioneer/AlphaTheta player accepts, so everything this app
writes plays on all of them.

| Format | Type | Bitrate | Pioneer support |
|--------|------|---------|-----------------|
| **AIFF** (default) | Lossless, uncompressed 24-bit | — | **ALL** CDJ/XDJ gear |
| **WAV** | Lossless, uncompressed 16-bit | — | **ALL** CDJ/XDJ gear |
| **FLAC** | Lossless, compressed 24-bit (much smaller) | — | **Newer gear only** — see below |
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
