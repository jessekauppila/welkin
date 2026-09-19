import json
import sqlite3
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from welkin.ingest import FrameStore, make_server

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64 + b"\xff\xd9"


@pytest.fixture
def server(tmp_path: Path):
    store = FrameStore(tmp_path / "data")
    srv = make_server(store, host="127.0.0.1", port=0, token=None)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", store, tmp_path / "data"
    srv.shutdown()
    srv.server_close()


def post(base: str, path: str, body: bytes, headers: dict | None = None) -> tuple[int, dict]:
    h = {"Content-Type": "image/jpeg", "X-Captured-At": "2026-09-18T20:05:00Z", "X-Profile": "clouds"}
    h.update(headers or {})
    h = {k: v for k, v in h.items() if v is not None}
    req = urllib.request.Request(base + path, data=body, headers=h, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def get(base: str, path: str) -> tuple[int, bytes, str]:
    try:
        with urllib.request.urlopen(base + path) as resp:
            return resp.status, resp.read(), resp.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers.get("Content-Type", "")


def test_stores_a_frame_on_disk_and_in_the_table(server) -> None:
    base, store, data = server
    status, body = post(base, "/frames/3", JPEG)
    assert status == 201
    assert body["camera_id"] == "3"
    assert body["captured_at"] == "2026-09-18T20:05:00Z"
    path = data / "frames" / "3" / "2026-09-18" / "200500Z.jpg"
    assert path.read_bytes() == JPEG
    rows = store.recent("3", since="2026-09-18T00:00:00Z")
    assert [(r["captured_at"], r["profile"], r["bytes"]) for r in rows] == [
        ("2026-09-18T20:05:00Z", "clouds", len(JPEG))
    ]


def test_a_retry_of_the_same_frame_is_idempotent(server) -> None:
    base, store, _ = server
    assert post(base, "/frames/3", JPEG)[0] == 201
    status, body = post(base, "/frames/3", JPEG)
    assert status == 200
    assert body["duplicate"] is True
    assert len(store.recent("3", since="2026-09-18T00:00:00Z")) == 1


def test_a_different_frame_at_the_same_instant_is_a_conflict(server) -> None:
    base, _, _ = server
    assert post(base, "/frames/3", JPEG)[0] == 201
    other = JPEG[:-2] + b"\x01\xff\xd9"
    assert post(base, "/frames/3", other)[0] == 409


@pytest.mark.parametrize(
    "path, body, headers, code",
    [
        ("/frames/3", b"not a jpeg", {}, 400),
        ("/frames/3", JPEG, {"Content-Type": "application/octet-stream"}, 415),
        ("/frames/3", JPEG, {"X-Captured-At": None}, 400),
        ("/frames/3", JPEG, {"X-Captured-At": "yesterday"}, 400),
        ("/frames/3", JPEG, {"X-Captured-At": "2026-09-18T20:05:00"}, 400),
        ("/frames/../etc", JPEG, {}, 404),
        ("/frames/a%2Fb", JPEG, {}, 404),
        ("/other/3", JPEG, {}, 404),
    ],
)
def test_rejects_bad_requests(server, path: str, body: bytes, headers: dict, code: int) -> None:
    base, store, data = server
    assert post(base, path, body, headers)[0] == code
    assert not (data / "frames").exists() or not any((data / "frames").rglob("*.jpg"))


def test_latest_frame_can_be_viewed_in_a_browser(server) -> None:
    base, _, _ = server
    assert get(base, "/frames/3/latest.jpg")[0] == 404
    post(base, "/frames/3", JPEG, {"X-Captured-At": "2026-09-18T20:05:00Z"})
    later = JPEG[:-2] + b"\x02\xff\xd9"
    post(base, "/frames/3", later, {"X-Captured-At": "2026-09-18T20:10:00Z"})
    status, body, ctype = get(base, "/frames/3/latest.jpg")
    assert (status, body, ctype) == (200, later, "image/jpeg")


def test_health_reports_last_frame_per_camera(server) -> None:
    base, _, _ = server
    post(base, "/frames/3", JPEG)
    status, body, _ = get(base, "/health")
    assert status == 200
    assert json.loads(body)["cameras"]["3"]["last_captured_at"] == "2026-09-18T20:05:00Z"


def test_token_is_required_when_configured(tmp_path: Path) -> None:
    srv = make_server(FrameStore(tmp_path / "data"), host="127.0.0.1", port=0, token="s3cret")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        assert post(base, "/frames/3", JPEG)[0] == 401
        assert post(base, "/frames/3", JPEG, {"Authorization": "Bearer wrong"})[0] == 401
        assert post(base, "/frames/3", JPEG, {"Authorization": "Bearer s3cret"})[0] == 201
    finally:
        srv.shutdown()
        srv.server_close()


def test_oversized_bodies_are_refused(tmp_path: Path) -> None:
    srv = make_server(FrameStore(tmp_path / "data"), host="127.0.0.1", port=0, max_bytes=1024)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        assert post(base, "/frames/3", b"\xff\xd8" + b"\x00" * 2048)[0] == 413
        assert post(base, "/frames/3", JPEG)[0] == 201
    finally:
        srv.shutdown()
        srv.server_close()


def test_frames_table_is_plain_sqlite_for_the_picker(server) -> None:
    base, _, data = server
    post(base, "/frames/3", JPEG)
    con = sqlite3.connect(data / "welkin.sqlite")
    cols = [r[1] for r in con.execute("PRAGMA table_info(frames)")]
    assert {"camera_id", "captured_at", "received_at", "profile", "path", "bytes", "sha256"} <= set(cols)
