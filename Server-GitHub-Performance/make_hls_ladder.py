from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path


QUALITIES = (
    ("240p", 426, 240, "450k", "550k", "900k", "64k"),
    ("360p", 640, 360, "900k", "1100k", "1800k", "96k"),
    ("720p", 1280, 720, "3000k", "3600k", "6000k", "128k"),
    ("1080p", 1920, 1080, "5500k", "6500k", "11000k", "160k"),
)


def has_audio(source: Path) -> bool:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=index", "-of", "csv=p=0", str(source)],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, check=False, timeout=60,
        )
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return False
    return result.returncode == 0 and bool(result.stdout.strip())


def main() -> int:
    parser = argparse.ArgumentParser(description="Adaptive HLS-Ladder für VOD erzeugen")
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    source = args.input.expanduser().resolve()
    if not source.is_file():
        print(f"Eingabedatei nicht gefunden: {source}")
        return 1

    out = source.parent / "hls" / source.stem
    out.parent.mkdir(parents=True, exist_ok=True)
    # Never destroy a known-good ladder before the replacement is complete.
    build_out = out.parent / f".{out.name}.building-{os.getpid()}"
    if build_out.exists():
        shutil.rmtree(build_out)
    build_out.mkdir(parents=True, exist_ok=True)
    for name, *_ in QUALITIES:
        (build_out / name).mkdir(parents=True, exist_ok=True)

    audio = has_audio(source)
    filter_parts = [f"[0:v]split={len(QUALITIES)}" + "".join(f"[v{i}]" for i in range(len(QUALITIES)))]
    for i, (_, width, height, *_rest) in enumerate(QUALITIES):
        filter_parts.append(f"[v{i}]scale=w={width}:h={height}:force_original_aspect_ratio=decrease:force_divisible_by=2[v{i}out]")

    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", str(source)]
    command += ["-filter_complex", ";".join(filter_parts)]
    for i, (_name, _width, _height, bitrate, maxrate, bufsize, audio_bitrate) in enumerate(QUALITIES):
        command += [
            "-map", f"[v{i}out]",
            "-c:v:" + str(i), "libx264", "-b:v:" + str(i), bitrate,
            "-maxrate:v:" + str(i), maxrate, "-bufsize:v:" + str(i), bufsize,
            "-preset", "veryfast", "-profile:v:" + str(i), "main" if i < 2 else "high",
            "-pix_fmt", "yuv420p", "-force_key_frames", "expr:gte(t,n_forced*4)",
            "-sc_threshold", "0",
        ]
        if audio:
            command += ["-map", "0:a:0", "-c:a:" + str(i), "aac", "-b:a:" + str(i), audio_bitrate, "-ar", "48000", "-ac", "2"]

    command += ["-f", "hls", "-hls_time", "4", "-hls_playlist_type", "vod", "-hls_flags", "independent_segments"]
    if audio:
        variant_map = " ".join(f"v:{i},a:{i},name:{name}" for i, (name, *_rest) in enumerate(QUALITIES))
    else:
        variant_map = " ".join(f"v:{i},name:{name}" for i, (name, *_rest) in enumerate(QUALITIES))
    command += ["-var_stream_map", variant_map, "-master_pl_name", "master.m3u8", "-hls_segment_filename", str(build_out / "%v" / "segment_%05d.ts"), str(build_out / "%v" / "index.m3u8")]

    print(f"Erzeuge HLS-Ladder ({'mit' if audio else 'ohne'} Audio): {out}")
    try:
        result = subprocess.run(command, stdin=subprocess.DEVNULL, check=False)
    except (FileNotFoundError, subprocess.SubprocessError, OSError) as exc:
        print(f"FFmpeg konnte nicht gestartet werden: {exc}")
        shutil.rmtree(build_out, ignore_errors=True)
        return 1
    if result.returncode != 0 or not (build_out / "master.m3u8").is_file():
        print("FFmpeg konnte die HLS-Ladder nicht vollständig erstellen; vorhandene Ladder bleibt erhalten.")
        shutil.rmtree(build_out, ignore_errors=True)
        return 1
    backup = out.parent / f".{out.name}.previous-{os.getpid()}"
    try:
        if backup.exists():
            shutil.rmtree(backup)
        if out.exists():
            out.replace(backup)
        try:
            build_out.replace(out)
        except OSError:
            if backup.exists() and not out.exists():
                backup.replace(out)
            raise
        shutil.rmtree(backup, ignore_errors=True)
    except OSError as exc:
        print(f"HLS-Ladder konnte nicht aktiviert werden: {exc}")
        shutil.rmtree(build_out, ignore_errors=True)
        shutil.rmtree(backup, ignore_errors=True)
        return 1
    print(f"Fertig: {out / 'master.m3u8'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
