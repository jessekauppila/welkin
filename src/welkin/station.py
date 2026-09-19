"""The station: one touch screen, freeze and draw.

Flow, and the state machine the page runs:

    offering --(touch)--> drawing --(commit)--> committed --(seer)--> revealed --(again)--> offering
                                                                        \\--(skip)---------> offering

- ``GET /``: the page.
- ``GET /api/offer?camera=ID``: the latest frozen frame for a camera. Opens a
  sitting and logs an ``offered`` event. 404 with a friendly message when the
  picker has not frozen anything yet.
- ``GET /frames/<frame_id>.jpg``: the frame image.
- ``POST /api/commit``: ``{sitting_id, frame_id, text, strokes}``. Stores the
  response (server assigns provenance), then asks the seer about the frame
  and returns its reading, or ``{"status": "error"}`` when it could not look.
  The reading is only ever computed and returned *after* the response is
  stored: showing it first would anchor the person.
- ``POST /api/event``: ``{sitting_id, kind, frame_id?}`` for ``again`` / ``skipped``.

The seer is injectable (``seer_fn``) so the station runs in tests and, with
``--no-seer``, on a laptop without an API key, where the reveal honestly says
the seer could not look.

Ported from the cloud prototype's ``LabelingLoop.tsx`` (commit be5c86a): the
commit-then-reveal ordering and its rationale. The free-text box gains a canvas.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlparse

from welkin import db, picker, store

log = logging.getLogger("welkin.station")

SeerFn = Callable[[sqlite3.Connection, Path, int], dict]

_GET_FRAME = re.compile(r"^/frames/(\d+)\.jpg$")
MAX_BODY = 2 * 1024 * 1024
RECENT_FALLBACK = 6  # frames to consider when the lookback window is empty


def no_seer(con: sqlite3.Connection, data_dir: Path, frame_id: int) -> dict:
    return {"status": "error", "error": "no seer configured on this station", "readings": None}


def offer(con: sqlite3.Connection, data_dir: Path, camera_id: str, auto_pick_min: int | None, rater: str | None) -> dict | None:
    """The latest freeze for a camera, running the picker first if the freeze is
    stale and auto-picking is on. Opens a sitting. None when nothing to offer."""
    fz = picker.latest_freeze(con, camera_id)
    now = datetime.now(timezone.utc)
    if auto_pick_min is not None:
        stale = fz is None or datetime.fromisoformat(fz["frozen_at"].replace("Z", "+00:00")) < now - timedelta(minutes=auto_pick_min)
        if stale:
            cands = picker.score_recent(con, data_dir, camera_id, now - timedelta(minutes=max(30, auto_pick_min * 3)), now)
            if not cands:
                # The camera has been dark a while (night, Wi-Fi). Offer the best of
                # its last few frames rather than nothing; the page shows captured_at.
                cands = picker.score_latest(con, data_dir, camera_id, limit=RECENT_FALLBACK)
            if cands:
                picker.freeze(con, camera_id, cands)
                fz = picker.latest_freeze(con, camera_id)
    if fz is None:
        return None
    sitting_id = store.start_sitting(con, camera_id, rater=rater)
    store.record_event(con, sitting_id, "offered", fz["frame_id"])
    return {
        "sitting_id": sitting_id,
        "frame_id": fz["frame_id"],
        "freeze_id": fz["id"],
        "captured_at": fz["captured_at"],
        "score": fz["score"],
        "image": f"/frames/{fz['frame_id']}.jpg",
    }


def commit(con: sqlite3.Connection, data_dir: Path, body: dict, seer_fn: SeerFn) -> dict:
    """Store the response, then (and only then) ask the seer."""
    try:
        sitting_id = int(body["sitting_id"])
        frame_id = int(body["frame_id"])
    except (KeyError, TypeError, ValueError):
        raise store.StoreError("sitting_id and frame_id are required integers")
    freeze_id = body.get("freeze_id")
    payload = {k: v for k, v in body.items() if k not in ("sitting_id", "frame_id", "freeze_id")}
    response_id = store.commit_response(con, sitting_id, frame_id, payload, freeze_id=freeze_id)

    try:
        reading = seer_fn(con, data_dir, frame_id)
    except Exception as exc:  # noqa: BLE001 — the person's response is already safe; report honestly
        log.error("seer failed for frame %s: %s", frame_id, exc)
        reading = {"status": "error", "error": f"{type(exc).__name__}: {exc}", "readings": None}
    store.mark_revealed(con, response_id)

    if reading.get("status") == "ok":
        seer = {"status": "ok", "readings": reading.get("readings") or [], "structure": reading.get("structure"), "note": reading.get("note")}
    else:
        seer = {"status": "error", "message": "the seer could not look", "detail": reading.get("error")}
    return {"response_id": response_id, "seer": seer}


def make_server(
    data_dir: Path,
    host: str = "0.0.0.0",
    port: int = 8100,
    seer_fn: SeerFn = no_seer,
    auto_pick_min: int | None = 10,
    rater: str | None = None,
) -> ThreadingHTTPServer:
    data_dir = Path(data_dir)
    lock = threading.Lock()  # one SQLite writer at a time keeps things simple
    page = (Path(__file__).parent / "station.html").read_text()

    class Handler(BaseHTTPRequestHandler):
        server_version = "welkin-station/0"

        def log_message(self, fmt: str, *args: object) -> None:
            log.info("%s %s", self.address_string(), fmt % args)

        def _send(self, status: int, body: bytes, ctype: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, obj: dict) -> None:
            self._send(status, json.dumps(obj).encode(), "application/json")

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                raise store.StoreError("request too large")
            raw = self.rfile.read(length) if length else b"{}"
            obj = json.loads(raw or b"{}")
            if not isinstance(obj, dict):
                raise store.StoreError("body must be a JSON object")
            return obj

        def do_GET(self) -> None:  # noqa: N802
            url = urlparse(self.path)
            if url.path == "/":
                return self._send(HTTPStatus.OK, page.encode(), "text/html; charset=utf-8")
            if url.path == "/api/offer":
                camera = (parse_qs(url.query).get("camera") or [""])[0]
                if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", camera):
                    return self._json(HTTPStatus.BAD_REQUEST, {"error": "camera is required"})
                with lock:
                    con = db.connect(data_dir)
                    try:
                        o = offer(con, data_dir, camera, auto_pick_min, rater)
                    finally:
                        con.close()
                if o is None:
                    return self._json(HTTPStatus.NOT_FOUND, {"error": "no cloud yet", "message": "The camera has not offered a cloud yet. Look up instead."})
                return self._json(HTTPStatus.OK, o)
            m = _GET_FRAME.match(url.path)
            if m:
                con = db.connect(data_dir)
                try:
                    row = con.execute("SELECT path FROM frames WHERE id = ?", (int(m.group(1)),)).fetchone()
                finally:
                    con.close()
                if row is None or not (data_dir / row["path"]).exists():
                    return self._json(HTTPStatus.NOT_FOUND, {"error": "no such frame"})
                return self._send(HTTPStatus.OK, (data_dir / row["path"]).read_bytes(), "image/jpeg")
            return self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            url = urlparse(self.path)
            try:
                body = self._body()
            except (ValueError, store.StoreError) as exc:
                return self._json(HTTPStatus.BAD_REQUEST, {"error": f"bad body: {exc}"})
            if url.path == "/api/commit":
                with lock:
                    con = db.connect(data_dir)
                    try:
                        result = commit(con, data_dir, body, seer_fn)
                    except store.StoreError as exc:
                        return self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                    finally:
                        con.close()
                return self._json(HTTPStatus.CREATED, result)
            if url.path == "/api/event":
                try:
                    sitting_id = int(body["sitting_id"])
                    kind = str(body["kind"])
                except (KeyError, TypeError, ValueError):
                    return self._json(HTTPStatus.BAD_REQUEST, {"error": "sitting_id and kind are required"})
                frame_id = body.get("frame_id")
                with lock:
                    con = db.connect(data_dir)
                    try:
                        store.record_event(con, sitting_id, kind, int(frame_id) if frame_id is not None else None)
                        if kind == "skipped":
                            store.end_sitting(con, sitting_id)
                    except (store.StoreError, sqlite3.IntegrityError) as exc:
                        return self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                    finally:
                        con.close()
                return self._json(HTTPStatus.OK, {"ok": True})
            return self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    return ThreadingHTTPServer((host, port), Handler)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Freeze-and-draw station.")
    ap.add_argument("--data", default="data")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8100)
    ap.add_argument("--auto-pick-min", type=int, default=10, help="re-run the picker when the freeze is older than this; 0 disables")
    ap.add_argument("--rater", default=None, help="stamp sittings with this rater (e.g. jesse); blank for visitors")
    ap.add_argument("--no-seer", action="store_true", help="run without the AI's turn; the reveal says the seer could not look")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if args.no_seer:
        seer_fn: SeerFn = no_seer
    else:
        from welkin import seer as seer_mod

        client = seer_mod.make_client()
        seer_fn = lambda con, data_dir, frame_id: seer_mod.see(con, data_dir, frame_id, client)  # noqa: E731

    server = make_server(
        Path(args.data), args.host, args.port, seer_fn,
        auto_pick_min=args.auto_pick_min or None, rater=args.rater,
    )
    log.info("station on http://%s:%s/  (data: %s, seer: %s)", args.host, server.server_address[1], Path(args.data).resolve(), "off" if args.no_seer else "on")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
