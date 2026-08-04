====================================================================
  VERY THOUGHTFUL NORMALISATION (but in a good way)
  by Picnic Labs
====================================================================

Professional audio normalization for performance. Normalizes music
files to a consistent -12 LUFS for playback on high-quality club
sound systems. Never fiddle with trim again...


--------------------------------------------------------------------
  FEATURES
--------------------------------------------------------------------

  * Consistent loudness — every track to -12 LUFS (EBU R128)
  * Five output formats — lossless AIFF (default), FLAC, WAV, or
    lossy MP3/AAC at 320/256/192 kbps
  * Two modes — manual batch processing or automatic folder watching
  * Preserves originals — never modifies your source files
  * Club-optimized — no compression on lossless files, just loudness
  * Know exactly what Pioneer/AlphaTheta gear your files work on
  * Reads M4A, WAV, FLAC, MP3, AIFF, OGG


--------------------------------------------------------------------
  MAC INSTALLATION  (VTNormal-macos.zip)
--------------------------------------------------------------------

One download — runs natively on both Apple Silicon and Intel Macs.

  1. Unzip.

  2. Move VTNormal.app to Applications.

  3. IMPORTANT — do this BEFORE you open it the first time.
     Open Terminal, paste this ONE line, press Enter:

codesign --force --deep -s - /Applications/VTNormal.app && xattr -rd com.apple.quarantine /Applications/VTNormal.app

  4. Launch the app. It will open normally from now on.

Why this step? The app isn't signed with a paid Apple certificate,
so macOS blocks it. Removing that warning permanently costs $99/year
for an Apple Developer ID. This app is free, so it uses the same
approach Radarr and Sonarr do: you sign it yourself, on your own
machine, in one command. It clears the "downloaded from the
internet" flag. Nothing is sent anywhere.

ALREADY TRIED TO OPEN IT AND GOT BLOCKED?
Running the command afterwards does NOT clear it — macOS has already
recorded its refusal. You have to go to:

    System Settings > Privacy & Security

scroll down, and choose "Open Anyway". A pop-up appears; choose
"Open Anyway" again. Doing the Terminal line FIRST skips all of this.


--------------------------------------------------------------------
  WINDOWS INSTALLATION  (VTNormal-windows.zip)
--------------------------------------------------------------------

  1. Unzip the whole folder somewhere. Keep the files together.

  2. Double-click VTNormal.exe.

If SmartScreen objects, click "More info" then "Run anyway" —
needed once only.


--------------------------------------------------------------------
  THE APP WINDOW
--------------------------------------------------------------------

  FROM      Pick the folder with your tracks
  TO        Pick where the normalized files go
  FORMAT    AIFF / FLAC / WAV / MP3 / AAC
            (a bitrate choice appears for MP3 and AAC)
  ABOUT     The full gear-compatibility rundown

Under the format row it tells you exactly what will happen to your
audio — e.g. "41 of 128 tracks are lossless — they stay lossless" —
counted from your own files. It turns into a warning if you pick a
lossy format.

While it runs you get a live list: what is queued, what is
processing, and what is done. Stop is graceful — it finishes the
track it is on, so nothing is left half-written.


--------------------------------------------------------------------
  HOW IT WORKS
--------------------------------------------------------------------

Two-pass normalization using ffmpeg's loudnorm filter:

  Pass 1 (Analysis) — measures current loudness
      * Integrated loudness (LUFS)
      * Loudness range (LRA)
      * True peak (TP)

  Pass 2 (Normalization) — applies precise gain adjustment
      * Uses the measurements from pass 1
      * Normalizes to the -12 LUFS target
      * Prevents clipping with a -1.5 dB true peak limit

ADVANTAGES
  * Outputs lossless AIFF or FLAC, or lossy MP3 or AAC
  * Matches modern dance music masters
  * Hot enough for club systems without distortion
  * Good headroom for system dynamics and effects
  * Consistent with club mastering standards


--------------------------------------------------------------------
  OUTPUT FORMATS & PIONEER GEAR COMPATIBILITY
--------------------------------------------------------------------

LOSSLESS STAYS LOSSLESS
Output keeps the source's OWN sample rate, up to 48 kHz. A 44.1 kHz
track stays 44.1 kHz; a 48 kHz master stays 48 kHz. Only sources
above 48 kHz (88.2 / 96 kHz) are resampled, and then to 48 kHz — the
highest rate every Pioneer/AlphaTheta player accepts, so everything
this app writes will play.

  FORMAT  TYPE                             BITRATE           GEAR
  ------  -------------------------------  ---------------  ----------------
  AIFF    Lossless, uncompressed 24-bit    —                ALL CDJ/XDJ
  WAV     Lossless, uncompressed 16-bit    —                ALL CDJ/XDJ
  FLAC    Lossless, compressed 24-bit      —                Newer gear only
  MP3     Lossy (libmp3lame, ID3v2.3)      320/256/192 kbps ALL CDJ/XDJ
  AAC     Lossy (beats MP3 at same rate)   320/256/192 kbps All modern gear

FLAC — SUPPORTED
  CDJ-3000, CDJ-2000NXS2, CDJ-TOUR1, XDJ-1000MK2, XDJ-RX2, XDJ-RX3,
  XDJ-XZ, XDJ-AZ, Opus Quad, Omnis Duo (and newer).

FLAC — NOT SUPPORTED
  CDJ-2000NXS and older, CDJ-900/900NXS, CDJ-850, CDJ-350, XDJ-700,
  XDJ-1000 (mk1), XDJ-RX (mk1), XDJ-RR.

AAC — SUPPORTED
  All modern players (CDJ-350/850/900/2000 onward and every XDJ).
  Only ancient CD-only decks (CDJ-800/1000 etc.) can't read it.

WHY 16-BIT WAV?
  24-bit WAV is written with a WAVE_FORMAT_EXTENSIBLE header that
  some CDJ firmware rejects. 16-bit WAV plays everywhere. If you want
  24-bit lossless use AIFF for the highest quality and maximum
  compatibility (that's why it's the default), or FLAC to save space
  and still be lossless.

  Note that WAV cannot carry embedded cover art — use AIFF or FLAC to
  keep artwork.

  On a Mac, Finder and Quick Look never show embedded FLAC artwork —
  that's an Apple limitation. The art IS in the file, and rekordbox,
  CDJs and VLC all display it.


--------------------------------------------------------------------

Your originals are never changed.
Enjoy the terrible jokes.

This app bundles FFmpeg (GPLv3) — see the "licenses" folder.
Source: ffmpeg.org
