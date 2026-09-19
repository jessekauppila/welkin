"""Frame ingest: where the Pi's frames land.

Runs on a laptop on the same LAN as the camera. The firmware's ``welkin``
sink (sunset-cam-firmware ``upload.upload_frame``) sends::

    POST /frames/{camera_id}
    Content-Type: image/jpeg
    X-Captured-At: 2026-09-18T20:05:00Z
    X-Profile: clouds
    Authorization: Bearer <token>        (only if a token is configured)
    <raw JPEG bytes>

Each frame is written to ``data/frames/{camera_id}/{YYYY-MM-DD}/{HHMMSS}Z.jpg``
and gets one row in the ``frames`` table of ``data/welkin.sqlite``. Rows hold
paths relative to the data directory, never URLs, so the data can move.

A retry of the same frame is idempotent (200, ``duplicate: true``). A
different image claiming the same camera and instant is refused (409): that
means two devices share an id, or a clock is wrong, and either is worth
seeing rather than silently overwriting.

Also served, for eyeballing a deployment from a browser:
``GET /health`` and ``GET /frames/{camera_id}/latest.jpg``.

Run: ``welkin-ingest --port 8000`` (``--token`` or ``WELKIN_INGEST_TOKEN`` to
require a bearer token).
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import logging
import os
import re
import socket
import sqlite3
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

log = logging.getLogger("welkin.ingest")

MAX_FRAME_BYTES = 20 * 1024 * 1024
CAMERA_ID = r"[A-Za-z0-9_-]{1,64}"
_POST_FRAME = re.compile(rf"^/frames/({CAMERA_ID})$")
_GET_LATEST = re.compile(rf"^/frames/({CAMERA_ID})/latest\.jpg$")

SCHEMA = """
CREATE TABLE IF NOT EXISTS frames (
    id          INTEGER PRIMARY KEY,
    camera_id   TEXT NOT NULL,
    captured_at TEXT NOT NULL,   -- UTC, 'YYYY-MM-DDTHH:MM:SSZ', from the device
    received_at TEXT NOT NULL,   -- UTC, from this server
    profile     TEXT,
    path        TEXT NOT NULL,   -- relative to the data directory
    bytes       INTEGER NOT NULL,
    sha256      TEXT NOT NULL,
    UNIQUE (camera_id, captured_at)
);
CREATE INDEX IF NOT EXISTS frames_by_time ON frames (camera_id, captured_at);
"""


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_captured_at(value: str | None) -> datetime:
    """A timezone-aware instant, or ValueError. Naive times are refused: a
    frame without a timezone cannot be placed against the sun."""
    if not value:
        raise ValueError("X-Captured-At header is required")
    dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("X-Captured-At must carry a timezone (use a Z suffix)")
    return dt


class FrameStore:
    """Frames on disk plus one SQLite row each."""

    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "welkin.sqlite"
        with self._connect() as con:
            con.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path, timeout=10)
        con.row_factory = sqlite3.Row
        return con

    def add(self, camera_id: str, captured_at: datetime, profile: str | None, jpeg: bytes) -> tuple[str, dict]:
        """Store a frame. Returns ("created" | "duplicate" | "conflict", row)."""
        at = _iso(captured_at)
        digest = hashlib.sha256(jpeg).hexdigest()
        utc = captured_at.astimezone(timezone.utc)
        rel = Path("frames") / camera_id / utc.strftime("%Y-%m-%d") / (utc.strftime("%H%M%S") + "Z.jpg")

        with self._connect() as con:
            existing = con.execute(
                "SELECT * FROM frames WHERE camera_id = ? AND captured_at = ?", (camera_id, at)
            ).fetchone()
            if existing is not None:
                kind = "duplicate" if existing["sha256"] == digest else "conflict"
                return kind, dict(existing)

            dest = self.data_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_suffix(".part")
            tmp.write_bytes(jpeg)
            os.replace(tmp, dest)  # atomic: a reader never sees half a frame

            row = {
                "camera_id": camera_id,
                "captured_at": at,
                "received_at": _iso(datetime.now(timezone.utc)),
                "profile": profile,
                "path": rel.as_posix(),
                "bytes": len(jpeg),
                "sha256": digest,
            }
            con.execute(
                "INSERT INTO frames (camera_id, captured_at, received_at, profile, path, bytes, sha256) "
                "VALUES (:camera_id, :captured_at, :received_at, :profile, :path, :bytes, :sha256)",
                row,
            )
        return "created", row

    def recent(self, camera_id: str, since: str) -> list[dict]:
        """Frames for a camera captured at or after ``since`` (ISO, UTC Z), oldest first."""
        with self._connect() as con:
            rows = con.execute(
                "SELECT * FROM frames WHERE camera_id = ? AND captured_at >= ? ORDER BY captured_at",
                (camera_id, _iso(parse_captured_at(since))),
            ).fetchall()
        return [dict(r) for r in rows]

    def latest_path(self, camera_id: str) -> Path | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT path FROM frames WHERE camera_id = ? ORDER BY captured_at DESC LIMIT 1", (camera_id,)
            ).fetchone()
        return self.data_dir / row["path"] if row else None

    def summary(self) -> dict:
        with self._connect() as con:
            rows = con.execute(
                "SELECT camera_id, COUNT(*) AS n, MAX(captured_at) AS last FROM frames GROUP BY camera_id"
            ).fetchall()
        return {r["camera_id"]: {"frames": r["n"], "last_captured_at": r["last"]} for r in rows}


def make_server(
    store: FrameStore,
    host: str = "0.0.0.0",
    port: int = 8000,
    token: str | None = None,
    max_bytes: int = MAX_FRAME_BYTES,
) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        server_version = "welkin-ingest/0"

        def log_message(self, fmt: str, *args: object) -> None:
            log.info("%s %s", self.address_string(), fmt % args)

        def _json(self, status: int, body: dict) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _authorized(self) -> bool:
            if not token:
                return True
            given = self.headers.get("Authorization", "")
            return hmac.compare_digest(given, f"Bearer {token}")

        def do_POST(self) -> None:  # noqa: N802 (http.server naming)
            m = _POST_FRAME.match(self.path)
            if not m:
                return self._json(HTTPStatus.NOT_FOUND, {"error": "POST /frames/{camera_id}"})
            if not self._authorized():
                return self._json(HTTPStatus.UNAUTHORIZED, {"error": "bad or missing bearer token"})

            length = self.headers.get("Content-Length")
            if length is None or not length.isdigit():
                return self._json(HTTPStatus.LENGTH_REQUIRED, {"error": "Content-Length required"})
            if int(length) > max_bytes:
                return self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": f"frame over {max_bytes} bytes"})
            body = self.rfile.read(int(length))

            ctype = self.headers.get("Content-Type", "").split(";")[0].strip().lower()
            if ctype != "image/jpeg":
                return self._json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "Content-Type must be image/jpeg"})
            if not body.startswith(b"\xff\xd8"):
                return self._json(HTTPStatus.BAD_REQUEST, {"error": "body is not a JPEG"})
            try:
                captured_at = parse_captured_at(self.headers.get("X-Captured-At"))
            except ValueError as exc:
                return self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

            kind, row = store.add(m.group(1), captured_at, self.headers.get("X-Profile"), body)
            payload = {k: row[k] for k in ("camera_id", "captured_at", "path", "bytes")}
            if kind == "conflict":
                return self._json(
                    HTTPStatus.CONFLICT,
                    {"error": "a different frame already exists for this camera and instant", **payload},
                )
            status = HTTPStatus.CREATED if kind == "created" else HTTPStatus.OK
            return self._json(status, {**payload, "duplicate": kind == "duplicate"})

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health":
                return self._json(HTTPStatus.OK, {"ok": True, "cameras": store.summary()})
            m = _GET_LATEST.match(self.path)
            if m:
                path = store.latest_path(m.group(1))
                if path is None or not path.exists():
                    return self._json(HTTPStatus.NOT_FOUND, {"error": "no frames yet"})
                data = path.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)
                return None
            return self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    return ThreadingHTTPServer((host, port), Handler)


def _lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))  # TEST-NET; nothing is sent
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Receive frames from Welkin cameras.")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--data", default="data", help="data directory (default: ./data)")
    ap.add_argument("--token", default=os.environ.get("WELKIN_INGEST_TOKEN"))
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    store = FrameStore(args.data)
    server = make_server(store, host=args.host, port=args.port, token=args.token)
    url = f"http://{_lan_ip()}:{server.server_address[1]}"
    log.info("listening; point the camera's welkin sink at %s  (data: %s)", url, store.data_dir.resolve())
    log.info("check: %s/health", url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
