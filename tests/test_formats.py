#!/usr/bin/env python3
"""
End-to-end format tests for the normalizer core.

Generates test audio with ffmpeg (stereo pink noise, tagged, with cover art),
normalizes it to every output format (and every bitrate for the lossy ones),
then verifies with ffprobe:

  - container/codec/extension are correct
  - sample rate is pinned to 44.1 kHz
  - bit depth (16-bit WAV, 24-bit AIFF)
  - lossy bitrate lands near the requested figure
  - title/artist metadata survives
  - cover art survives (except WAV, whose container can't hold it)
  - re-measured integrated loudness is within ±1 LU of the -12 LUFS target

Stdlib + ffmpeg only. Run:  python3 tests/test_formats.py
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import normalizer  # noqa: E402

FFMPEG = normalizer.resolve_ffmpeg()
FFPROBE = str(Path(FFMPEG).parent / 'ffprobe') if Path(FFMPEG).is_absolute() else 'ffprobe'

TITLE, ARTIST = "Format Test Tone", "Psi Test Suite"

PASS = 0
FAIL = 0


def check(label: str, cond: bool, detail: str = ""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}  {detail}")


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def make_test_input(workdir: Path) -> Path:
    """Stereo pink noise, 6s, tagged, with a cover image attached."""
    audio = workdir / "src_audio.flac"
    cover = workdir / "cover.jpg"
    tagged = workdir / "source.flac"
    r = run([FFMPEG, '-hide_banner', '-loglevel', 'error',
             '-f', 'lavfi', '-i', 'anoisesrc=d=6:c=pink:r=44100:a=0.4',
             '-af', 'aformat=channel_layouts=stereo',
             '-c:a', 'flac', str(audio)])
    assert r.returncode == 0, r.stderr
    r = run([FFMPEG, '-hide_banner', '-loglevel', 'error',
             '-f', 'lavfi', '-i', 'color=c=purple:s=300x300:d=0.1',
             '-frames:v', '1', str(cover)])
    assert r.returncode == 0, r.stderr
    r = run([FFMPEG, '-hide_banner', '-loglevel', 'error',
             '-i', str(audio), '-i', str(cover),
             '-map', '0:a', '-map', '1:v', '-c', 'copy',
             '-metadata', f'title={TITLE}', '-metadata', f'artist={ARTIST}',
             '-disposition:v', 'attached_pic', str(tagged)])
    assert r.returncode == 0, r.stderr
    return tagged


def probe(path: str) -> dict:
    r = run([FFPROBE, '-v', 'error', '-show_streams', '-show_format',
             '-of', 'json', path])
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def measure_lufs(path: str) -> float:
    """Integrated loudness of a file, via a loudnorm analysis pass."""
    m = normalizer.analyze_loudness(path)
    assert m is not None, f"could not measure {path}"
    return m['measured_I']


EXPECT = {
    #        codec         bits  art
    'aiff': ('pcm_s24be',  24,   True),
    'flac': ('flac',       None, True),
    'wav':  ('pcm_s16le',  16,   False),
    'mp3':  ('mp3',        None, True),
    'aac':  ('aac',        None, True),
}


def test_format(src: Path, outdir: Path, fmt: str, bitrate: int):
    lossy = normalizer.OUTPUT_FORMATS[fmt]['lossy']
    tag = f"{fmt}" + (f" @{bitrate}k" if lossy else "")
    print(f"[{tag}]")

    out = normalizer.get_output_filename(str(src), str(outdir), fmt)
    ok, msg = normalizer.normalize_audio(str(src), out, output_format=fmt,
                                         bitrate=bitrate)
    check("normalize succeeds", ok, msg)
    if not ok:
        return

    expected_codec, expected_bits, expect_art = EXPECT[fmt]
    check("extension", out.endswith(normalizer.OUTPUT_FORMATS[fmt]['ext']), out)

    info = probe(out)
    audio = [s for s in info['streams'] if s['codec_type'] == 'audio'][0]
    art = [s for s in info['streams'] if s['codec_type'] == 'video']

    check("codec", audio['codec_name'] == expected_codec,
          f"got {audio['codec_name']}")
    check("sample rate 44100", audio.get('sample_rate') == '44100',
          f"got {audio.get('sample_rate')}")
    if expected_bits:
        got = int(audio.get('bits_per_raw_sample')
                  or audio.get('bits_per_sample') or 0)
        check(f"bit depth {expected_bits}", got == expected_bits, f"got {got}")
    if lossy:
        got_br = int(audio.get('bit_rate') or 0)
        if fmt == 'aac' and bitrate == 320 and normalizer.aac_encoder() == 'aac':
            # ffmpeg's native aac encoder tops out ~224k for 44.1kHz stereo;
            # only aac_at (macOS AudioToolbox) genuinely reaches 320k.
            print(f"  skip bitrate check (native aac encoder caps ~224k; got {got_br})")
        else:
            tol = 0.25 * bitrate * 1000
            check(f"bitrate ≈ {bitrate}k", abs(got_br - bitrate * 1000) <= tol,
                  f"got {got_br}")

    tags = {k.lower(): v for k, v in info.get('format', {}).get('tags', {}).items()}
    # AIFF keeps tags in an id3 chunk that ffprobe surfaces on the format;
    # allow stream-level tags as fallback.
    if not tags:
        tags = {k.lower(): v for k, v in audio.get('tags', {}).items()}
    check("title tag", tags.get('title') == TITLE, str(tags))
    check("artist tag", tags.get('artist') == ARTIST, str(tags))

    if expect_art:
        check("cover art present", len(art) == 1
              and (fmt in ('flac',)  # flac pictures aren't flagged attached_pic by all builds
                   or art[0].get('disposition', {}).get('attached_pic') == 1),
              f"video streams: {len(art)}")
    else:
        check("no art stream (container limit)", len(art) == 0,
              f"video streams: {len(art)}")

    lufs = measure_lufs(out)
    check(f"loudness {lufs:.1f} ≈ -12 LUFS", abs(lufs - (-12.0)) <= 1.0)
    print()


def main():
    with tempfile.TemporaryDirectory(prefix="annorm_test_") as tmp:
        workdir = Path(tmp)
        outdir = workdir / "out"
        outdir.mkdir()
        print("Generating test input (6s stereo pink noise, tagged, cover art)")
        src = make_test_input(workdir)
        print(f"Source loudness: {measure_lufs(str(src)):.1f} LUFS\n")

        for fmt, spec in normalizer.OUTPUT_FORMATS.items():
            if spec['lossy']:
                for bitrate in normalizer.BITRATES:
                    test_format(src, outdir, fmt, bitrate)
            else:
                test_format(src, outdir, fmt, normalizer.DEFAULT_BITRATE)

        # Guard rails
        print("[guards]")
        ok, msg = normalizer.normalize_audio(str(src), str(src),
                                             output_format='flac')
        check("same-file overwrite refused", not ok, msg)
        ok, msg = normalizer.normalize_audio(str(src), str(outdir / "x.xyz"),
                                             output_format='xyz')
        check("unknown format refused", not ok, msg)

    print(f"\n{'ALL PASS' if FAIL == 0 else 'FAILURES'}: {PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == '__main__':
    main()
