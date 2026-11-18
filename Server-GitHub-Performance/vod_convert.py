from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

SOURCE_EXTENSIONS = {".mkv", ".webm"}


def probe_codec(source: Path, selector: str) -> str:
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", selector,
                "-show_entries", "stream=codec_name", "-of", "default=nw=1:nk=1", str(source),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return ""
    if result.returncode != 0:
        return ""
    lines = [line.strip().lower() for line in result.stdout.splitlines() if line.strip()]
    return lines[0] if lines else ""


def run_ffmpeg(command: list[str]) -> bool:
    try:
        result = subprocess.run(command, check=False, timeout=1800)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.SubprocessError, OSError):
        return False


def valid_output(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def replace_from_temp(temp: Path, target: Path) -> bool:
    if not valid_output(temp):
        temp.unlink(missing_ok=True)
        return False
    try:
        os.replace(temp, target)
        return True
    except OSError:
        temp.unlink(missing_ok=True)
        return False


def convert_one(source: Path, target: Path) -> str:
    try:
        if target.is_file() and target.stat().st_mtime_ns >= source.stat().st_mtime_ns:
            return "unchanged"
    except OSError:
        pass

    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(f".{target.stem}.vod_tmp_{os.getpid()}.mp4")
    temp.unlink(missing_ok=True)

    video_codec = probe_codec(source, "v:0")
    audio_codec = probe_codec(source, "a:0")
    can_remux = video_codec == "h264" and audio_codec in {"", "aac"}

    if can_remux:
        print(f"Schnell-Remux: {source.name}")
        remux_command = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
            "-map", "0:v:0", "-map", "0:a?", "-c", "copy", "-movflags", "+faststart", str(temp),
        ]
        if run_ffmpeg(remux_command) and replace_from_temp(temp, target):
            return "converted"
        temp.unlink(missing_ok=True)
        print(f"Remux fehlgeschlagen, starte Neucodierung: {source.name}")

    print(f"Qualitäts-Neucodierung: {source.name}")
    transcode_command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-fflags", "+genpts", "-i", str(source),
        "-map", "0:v:0", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast",
        "-vf", "scale=w='min(1920,iw)':h=-2:force_original_aspect_ratio=decrease",
        "-crf", "22", "-maxrate", "5500k", "-bufsize", "11000k",
        "-profile:v", "high", "-level", "4.1", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-ac", "2",
        "-movflags", "+faststart", "-threads", "0", str(temp),
    ]
    if run_ffmpeg(transcode_command) and replace_from_temp(temp, target):
        return "converted"
    temp.unlink(missing_ok=True)
    return "failed"


def main() -> int:
    parser = argparse.ArgumentParser(description="MKV/WebM-zu-kompatiblem MP4 konvertieren")
    parser.add_argument("--folder", required=True, help="Ordner mit den Quelldateien")
    args = parser.parse_args()

    folder = Path(args.folder).expanduser()
    if not folder.is_dir():
        print(f"Videoordner nicht gefunden: {folder}")
        return 1

    sources = sorted(
        (path for path in folder.iterdir() if path.is_file() and path.suffix.lower() in SOURCE_EXTENSIONS),
        key=lambda path: path.name.casefold(),
    )
    if not sources:
        print("Keine MKV- oder WebM-Dateien gefunden.")
        return 0

    converted = unchanged = failures = 0
    for source in sources:
        result = convert_one(source, source.with_suffix(".mp4"))
        if result == "converted":
            converted += 1
        elif result == "unchanged":
            unchanged += 1
            print(f"Unverändert: {source.name}")
        else:
            failures += 1
            print(f"FEHLER: Konvertierung fehlgeschlagen: {source.name}")

    print(f"Scan abgeschlossen: {len(sources)} geprüft, {converted} aktualisiert, {unchanged} unverändert, {failures} Fehler.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
