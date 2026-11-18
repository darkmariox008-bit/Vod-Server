from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import mimetypes
import os
import random
import socket
import subprocess
import threading
import time
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

VIDEO_EXTENSIONS = {".mp4", ".webm", ".m4v"}
HLS_EXTENSIONS = {".m3u8", ".ts", ".m4s", ".mp4"}
MAX_RANGE = 16 * 1024 * 1024  # Weniger Range-Anfragen bei entfernten Mobilgeräten
ADMIN_PASSWORD = "19516798"
THUMBNAIL_SLOTS = threading.BoundedSemaphore(2)


def scan_videos(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    result: list[Path] = []
    for path in folder.iterdir():
        try:
            if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS and path.stat().st_size > 0:
                result.append(path)
        except OSError:
            continue
    return result


def safe_child(root: Path, name: str) -> Path | None:
    candidate = (root / Path(name).name).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate


def safe_nested_child(root: Path, name: str) -> Path | None:
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts:
        return None
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate


def hls_manifest(folder: Path, file_name: str) -> str | None:
    stem = Path(file_name).stem
    manifest = folder / "hls" / stem / "master.m3u8"
    return f"/hls/{quote(stem, safe='')}/master.m3u8" if manifest.is_file() else None


class PlaybackState:
    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.lock = threading.RLock()
        self.file: str | None = None
        self.started_at = time.monotonic()
        self.last_advance_at = 0.0
        self.playlist: list[str] = []
        self.folder_signature: tuple[tuple[str, int, int], ...] = ()
        self.last_scan_at = 0.0
        self.refresh_playlist(force=True)

    def _signature(self, items: list[Path]) -> tuple[tuple[str, int, int], ...]:
        signature = []
        for path in items:
            try:
                stat = path.stat()
                signature.append((path.name, stat.st_size, stat.st_mtime_ns))
            except OSError:
                continue
        return tuple(sorted(signature))

    def refresh_playlist(self, force: bool = False) -> None:
        # API-Abfragen kommen bei mehreren Zuschauern parallel. Ein kurzer
        # Scan-Cache verhindert wiederholte Verzeichnis-/Stat-Aufrufe, ohne
        # neue Videos spürbar verzögert zu erkennen.
        now = time.monotonic()
        if not force and now - self.last_scan_at < 3.0:
            return
        items = scan_videos(self.folder)
        signature = self._signature(items)
        self.last_scan_at = now
        if not force and signature == self.folder_signature:
            return

        names = [item.name for item in items]
        names.sort(key=str.casefold)
        random.SystemRandom().shuffle(names)
        self.playlist = names
        self.folder_signature = signature

        if self.file not in self.playlist:
            self.file = self.playlist[0] if self.playlist else None
            self.started_at = time.monotonic()

    def live(self) -> dict[str, object]:
        with self.lock:
            self.refresh_playlist()
            position = max(0.0, time.monotonic() - self.started_at) if self.file else 0.0
            return {
                "online": True,
                "file": self.file,
                "position": round(position, 3),
                "serverNow": time.time(),
                "sync": "server-authoritative",
            }

    def next_file(self) -> str | None:
        with self.lock:
            self.refresh_playlist()
            if not self.playlist:
                return None
            if self.file not in self.playlist:
                return self.playlist[0]
            return self.playlist[(self.playlist.index(self.file) + 1) % len(self.playlist)]

    def advance(self, expected_file: str | None = None) -> dict[str, object]:
        with self.lock:
            self.refresh_playlist()
            if not self.playlist:
                self.file = None
                return self.live()
            if expected_file and self.file != expected_file:
                return self.live()
            if time.monotonic() - self.last_advance_at < 1.5:
                return self.live()

            current_index = self.playlist.index(self.file) if self.file in self.playlist else -1
            self.file = self.playlist[(current_index + 1) % len(self.playlist)]
            self.started_at = time.monotonic()
            self.last_advance_at = self.started_at
            return self.live()


    def previous(self) -> dict[str, object]:
        with self.lock:
            self.refresh_playlist()
            if not self.playlist:
                self.file = None
                return self.live()
            current_index = self.playlist.index(self.file) if self.file in self.playlist else 0
            self.file = self.playlist[(current_index - 1) % len(self.playlist)]
            self.started_at = time.monotonic()
            return self.live()

    def shuffle(self) -> dict[str, object]:
        with self.lock:
            self.refresh_playlist(force=True)
            random.SystemRandom().shuffle(self.playlist)
            self.started_at = time.monotonic()
            return self.live()

    def select(self, file_name: str) -> dict[str, object]:
        with self.lock:
            self.refresh_playlist()
            if file_name not in self.playlist:
                raise ValueError("Video nicht gefunden")
            self.file = file_name
            self.started_at = time.monotonic()
            return self.live()

class VODServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address, handler, folder: Path, web_root: Path, access_token: str):
        super().__init__(address, handler)
        self.folder = folder
        self.web_root = web_root
        self.playback = PlaybackState(folder)
        self.access_token = access_token
        self.started_at = time.monotonic()
        self.viewers: dict[str, dict[str, object]] = {}
        self.errors: list[str] = []
        self.meta_lock = threading.RLock()

    def server_bind(self) -> None:
        super().server_bind()
        # Viele parallele HLS-Anfragen sollen nicht unnötig auf Nagle warten.
        try:
            self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1024 * 1024)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 256 * 1024)
        except OSError:
            pass


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "LocalVODSync/3.0"

    @property
    def vod_server(self) -> VODServer:
        return self.server  # type: ignore[return-value]

    def log_message(self, fmt: str, *args: object) -> None:
        message = fmt % args
        print(message)
        if '" 4' in message or '" 5' in message or 'error' in message.lower():
            with self.vod_server.meta_lock:
                self.vod_server.errors.append(f"{time.strftime('%H:%M:%S')} {message}")
                self.vod_server.errors = self.vod_server.errors[-20:]

    def touch_viewer(self, parsed) -> None:
        query_viewer = parse_qs(parsed.query).get('viewer', [''])[0]
        forwarded_ip = self.headers.get('CF-Connecting-IP') or self.headers.get('X-Forwarded-For', '').split(',')[0].strip()
        ip = forwarded_ip or self.client_address[0]
        user_agent = self.headers.get('User-Agent', '')
        viewer_key = query_viewer or f"{ip}:{user_agent}"
        now = time.monotonic()
        with self.vod_server.meta_lock:
            current = self.vod_server.viewers.get(viewer_key)
            self.vod_server.viewers[viewer_key] = {
                'last_seen': now,
                'connected_at': current.get('connected_at', time.time()) if current else time.time(),
                'ip': ip,
                'user_agent': user_agent,
            }
            cutoff = now - 15
            self.vod_server.viewers = {key: value for key, value in self.vod_server.viewers.items() if float(value['last_seen']) >= cutoff}

    @staticmethod
    def mask_ip(ip: str) -> str:
        if ':' in ip:
            parts = ip.split(':')
            return ':'.join(parts[:2] + ['xxxx', 'xxxx']) if len(parts) > 2 else ip
        parts = ip.split('.')
        return '.'.join(parts[:2] + ['xxx', 'xxx']) if len(parts) == 4 else 'xxx.xxx.xxx.xxx'

    def viewer_rows(self) -> list[dict[str, object]]:
        now_mono = time.monotonic()
        now_wall = time.time()
        with self.vod_server.meta_lock:
            rows = []
            for viewer_id, value in self.vod_server.viewers.items():
                rows.append({
                    'id': viewer_id[:8],
                    'ip': self.mask_ip(str(value['ip'])),
                    'connectedAt': time.strftime('%H:%M:%S', time.localtime(float(value['connected_at']))),
                    'duration': max(0, int(now_wall - float(value['connected_at']))),
                    'lastActive': max(0, int(now_mono - float(value['last_seen']))),
                    'browser': str(value['user_agent']).split(')')[0][-52:] or 'Unbekannt',
                })
            return rows

    def admin_allowed(self, parsed) -> bool:
        supplied = parse_qs(parsed.query).get('admin', [''])[0]
        return hmac.compare_digest(supplied, ADMIN_PASSWORD)

    def valid_token(self) -> bool:
        if not self.vod_server.access_token:
            return True
        supplied = parse_qs(urlparse(self.path).query).get("key", [""])[0]
        return bool(supplied) and hmac.compare_digest(supplied, self.vod_server.access_token)

    def protected(self, path: str) -> bool:
        return (
            path in {"", "/", "/api/status", "/api/ping", "/api/live", "/api/next", "/api/advance"}
            or path.startswith("/api/admin/")
            or path.startswith("/media/")
            or path.startswith("/thumb/")
            or path.startswith("/hls/")
        )

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if self.protected(path) and not self.valid_token():
            self.send_error(HTTPStatus.FORBIDDEN, "Access key required")
            return

        if path == "/api/status":
            live = self.vod_server.playback.live()
            self.send_json({
                "online": True,
                "videoCount": len(self.vod_server.playback.playlist),
                "current": live["file"],
                "sync": live["sync"],
            })
            return

        if path == "/api/ping":
            self.send_json({"online": True, "serverNow": time.time()})
            return

        if path == "/api/live":
            self.touch_viewer(parsed)
            live = self.vod_server.playback.live()
            file_name = live.get("file")
            if file_name:
                suffix = f"?key={quote(self.vod_server.access_token, safe='')}" if self.vod_server.access_token else ""
                live["url"] = f"/media/{quote(str(file_name), safe='')}{suffix}"
                live["hlsUrl"] = hls_manifest(self.vod_server.folder, str(file_name))
            else:
                live["url"] = None
                live["hlsUrl"] = None
            self.send_json(live)
            return

        if path == "/api/next":
            upcoming = self.vod_server.playback.next_file()
            if not upcoming:
                self.send_json({"file": None, "thumb": None})
                return
            suffix = f"?key={quote(self.vod_server.access_token, safe='')}" if self.vod_server.access_token else ""
            self.send_json({
                "file": upcoming,
                "thumb": f"/thumb/{quote(upcoming, safe='')}{suffix}",
            })
            return

        if path == "/api/advance":
            expected = parse_qs(parsed.query).get("from", [None])[0]
            self.send_json(self.vod_server.playback.advance(expected))
            return

        if path.startswith("/api/admin/"):
            if not self.admin_allowed(parsed):
                self.send_error(HTTPStatus.FORBIDDEN, "Admin password required")
                return
            try:
                if path == "/api/admin/viewers":
                    self.send_json({"viewers": self.viewer_rows()})
                    return
                if path == "/api/admin/status":
                    self.vod_server.playback.refresh_playlist()
                    with self.vod_server.meta_lock:
                        viewers = len(self.vod_server.viewers)
                        errors = list(self.vod_server.errors[-10:])
                    self.send_json({
                        "online": True,
                        "current": self.vod_server.playback.file,
                        "videoCount": len(self.vod_server.playback.playlist),
                        "viewers": viewers,
                        "uptime": int(time.monotonic() - self.vod_server.started_at),
                        "errors": errors,
                    })
                    return
                if path == "/api/admin/videos":
                    self.vod_server.playback.refresh_playlist()
                    self.send_json({"videos": self.vod_server.playback.playlist})
                    return
                if path == "/api/admin/previous":
                    self.send_json(self.vod_server.playback.previous())
                    return
                if path == "/api/admin/next":
                    self.send_json(self.vod_server.playback.advance())
                    return
                if path == "/api/admin/shuffle":
                    self.send_json(self.vod_server.playback.shuffle())
                    return
                if path == "/api/admin/reload":
                    self.vod_server.playback.refresh_playlist(force=True)
                    self.send_json({"ok": True, "count": len(self.vod_server.playback.playlist)})
                    return
                if path == "/api/admin/select":
                    file_name = parse_qs(parsed.query).get("file", [""])[0]
                    self.send_json(self.vod_server.playback.select(file_name))
                    return
            except ValueError as exc:
                self.send_error(HTTPStatus.NOT_FOUND, str(exc))
                return

        if path.startswith("/media/"):
            self.serve_media(path[len("/media/"):])
            return
        if path.startswith("/thumb/"):
            self.serve_thumbnail(path[len("/thumb/"):])
            return
        if path.startswith("/hls/"):
            self.serve_hls(path[len("/hls/"):])
            return
        self.serve_static("index.html" if path in {"", "/"} else path.lstrip("/"))

    def do_HEAD(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path.startswith("/media/") and self.valid_token():
            self.serve_media(path[len("/media/"):], head_only=True)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def send_json(self, payload: object) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        self.wfile.write(data)

    def serve_static(self, name: str) -> None:
        target = safe_child(self.vod_server.web_root, name)
        if target is None or not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        data = target.read_bytes()
        if name == "index.html":
            live = self.vod_server.playback.live()
            if live["file"]:
                file_name = str(live["file"])
                display_name = escape(file_name, quote=True)
                suffix = f"?key={quote(self.vod_server.access_token, safe='')}" if self.vod_server.access_token else ""
                hls_url = hls_manifest(self.vod_server.folder, file_name)
                hls_attribute = f' data-hls-url="{hls_url}{suffix}"' if hls_url else ""
                element = f'<video id="player" autoplay muted playsinline preload="auto" webkit-playsinline="true" poster="/thumb/{quote(file_name, safe="")}{suffix}" data-file="{display_name}"{hls_attribute} src="/media/{quote(file_name, safe="")}{suffix}"></video>'
                data = data.replace(b"__VIDEO_NAME__", display_name.encode("utf-8"))
            else:
                element = '<div class="video-error">Kein Video im VOD-Ordner gefunden.</div>'
                data = data.replace(b"__VIDEO_NAME__", b"Kein Video gefunden")
            data = data.replace(b"__VIDEO_ELEMENT__", element.encode("utf-8"))

        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        # HTML blijft actueel; statische assets mogen browser-side worden gecachet.
        cache_control = "no-store" if target.suffix.lower() == ".html" else "public, max-age=3600"
        self.send_header("Cache-Control", cache_control)
        self.end_headers()
        self.wfile.write(data)

    def serve_media(self, name: str, head_only: bool = False) -> None:
        target = safe_child(self.vod_server.folder, name)
        if target is None or not target.is_file() or target.suffix.lower() not in VIDEO_EXTENSIONS:
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        try:
            size = target.stat().st_size
            start, end = 0, size - 1
            header = self.headers.get("Range", "")
            if header.startswith("bytes="):
                raw_start, _, raw_end = header[6:].split(",", 1)[0].partition("-")
                if raw_start:
                    start = int(raw_start)
                    end = min(int(raw_end), size - 1, start + MAX_RANGE - 1) if raw_end else min(size - 1, start + MAX_RANGE - 1)
                elif raw_end:
                    length = min(int(raw_end), size)
                    start = size - length
                else:
                    raise ValueError
                if start < 0 or start >= size or start > end:
                    raise ValueError
                self.send_response(HTTPStatus.PARTIAL_CONTENT)
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            else:
                self.send_response(HTTPStatus.OK)

            self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "video/mp4")
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Disposition", "inline")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            if head_only:
                return

            with target.open("rb") as stream:
                stream.seek(start)
                remaining = end - start + 1
                while remaining:
                    chunk = stream.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        except (ValueError, OSError):
            try:
                self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

    def serve_hls(self, name: str) -> None:
        target = safe_nested_child(self.vod_server.folder / "hls", name)
        if target is None or not target.is_file() or target.suffix.lower() not in HLS_EXTENSIONS:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_type = {
            ".m3u8": "application/vnd.apple.mpegurl",
            ".ts": "video/mp2t",
            ".m4s": "video/iso.segment",
            ".mp4": "video/mp4",
        }[target.suffix.lower()]
        try:
            data = target.read_bytes()
            # HLS-Playlists enthalten relative Segment-URLs. Der Zugriffsschlüssel
            # muss an jede davon weitergereicht werden, sonst funktionieren
            # Remote-Wiedergaben in HLS.js/Safari nach dem Master-Manifest nicht.
            if target.suffix.lower() == ".m3u8" and self.vod_server.access_token:
                key = quote(self.vod_server.access_token, safe="")
                lines = data.decode("utf-8", errors="replace").splitlines()
                rewritten = []
                for line in lines:
                    stripped = line.strip()
                    if stripped and not stripped.startswith("#") and "?" not in stripped:
                        line = f"{line}?key={key}"
                    rewritten.append(line)
                data = ("\n".join(rewritten) + "\n").encode("utf-8")
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache" if target.suffix.lower() == ".m3u8" else "public, max-age=3600")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def serve_thumbnail(self, name: str) -> None:
        target = safe_child(self.vod_server.folder, name)
        if target is None or not target.is_file() or target.suffix.lower() not in VIDEO_EXTENSIONS:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        thumb_dir = self.vod_server.folder / ".vod_thumbnails"
        thumb_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(f"{target.resolve()}:{target.stat().st_mtime_ns}".encode("utf-8")).hexdigest()[:24]
        thumb = thumb_dir / f"{digest}.jpg"
        with THUMBNAIL_SLOTS:
            if not thumb.is_file():
                temp = thumb.with_name(f".{thumb.stem}.{os.getpid()}.{threading.get_ident()}.tmp.jpg")
                try:
                    command = [
                        "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-ss", "1", "-i", str(target),
                        "-frames:v", "1", "-vf", "scale=320:-2", str(temp),
                    ]
                    try:
                        subprocess.run(command, check=True, timeout=20, stdin=subprocess.DEVNULL)
                    except (subprocess.SubprocessError, OSError):
                        # Manche Container/Codecs können nicht zuverlässig auf
                        # Sekunde 1 springen. Dann den ersten Frame verwenden.
                        temp.unlink(missing_ok=True)
                        fallback = [
                            "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", str(target),
                            "-frames:v", "1", "-vf", "scale=320:-2", str(temp),
                        ]
                        subprocess.run(fallback, check=True, timeout=20, stdin=subprocess.DEVNULL)
                    if not thumb.is_file():
                        os.replace(temp, thumb)
                    else:
                        temp.unlink(missing_ok=True)
                except (FileNotFoundError, subprocess.SubprocessError, OSError):
                    temp.unlink(missing_ok=True)
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
        data = thumb.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Synchronisierter lokaler VOD-Server")
    parser.add_argument("--folder", default=r"G:\Bilder Und Videos\Server")
    parser.add_argument("--web-root", default=str(Path(__file__).with_name("website")))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--access-token-file", default="")
    args = parser.parse_args()

    folder = Path(args.folder).expanduser()
    web_root = Path(args.web_root).expanduser().resolve()
    token_file = Path(args.access_token_file).expanduser() if args.access_token_file else None
    access_token = token_file.read_text(encoding="utf-8").strip() if token_file and token_file.is_file() else ""
    loopback_hosts = {"127.0.0.1", "localhost", "::1"}
    if not access_token and args.host not in loopback_hosts:
        raise SystemExit("Für einen Netzwerk-Host ist ein Zugriffsschlüssel erforderlich.")

    server = VODServer((args.host, args.port), Handler, folder, web_root, access_token)
    print(f"Lokaler synchronisierter VOD-Server: http://{args.host}:{args.port}/")
    print(f"Videoordner: {folder}")
    print(f"Zugriffsschutz: {'aktiv' if access_token else 'inaktiv'}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
