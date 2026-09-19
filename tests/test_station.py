import io
import json
import threading
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from welkin import db, picker
from welkin.ingest import FrameStore
from welkin.station import make_server, no_seer

T0 = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=12)
STROKES = [[[0.1, 0.2], [0.3, 0.4]]]


def jpeg(seed: int) -> bytes:
    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 255, size=(96, 128, 3), dtype=np.uint8)
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def seed_frames(data: Path, n: int = 3) -> None:
    store = FrameStore(data)
    for i in range(n):
        store.add("3", T0 + timedelta(minutes=5 * i), "clouds", jpeg(i))


def ok_seer(con, data_dir, frame_id):
    return {"status": "ok", "readings": [{"thing": "a bear", "where": "top left", "strength": 0.7}], "structure": 0.6, "note": "lumpy"}


def error_seer(con, data_dir, frame_id):
    raise ConnectionError("no network")


def calls(fn):
    def wrapped(con, data_dir, frame_id):
        wrapped.n += 1
        return fn(con, data_dir, frame_id)
    wrapped.n = 0
    return wrapped


@pytest.fixture
def station(tmp_path: Path):
    servers = []

    def start(seer_fn=ok_seer, auto_pick_min=10, rater=None, frames=3):
        data = tmp_path / "data"
        if frames:
            seed_frames(data, frames)
        srv = make_server(data, host="127.0.0.1", port=0, seer_fn=seer_fn, auto_pick_min=auto_pick_min, rater=rater)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        servers.append(srv)
        return f"http://127.0.0.1:{srv.server_address[1]}", data

    yield start
    for s in servers:
        s.shutdown()
        s.server_close()


def get(base: str, path: str):
    try:
        with urllib.request.urlopen(base + path) as r:
            body = r.read()
            return r.status, (json.loads(body) if r.headers.get("Content-Type", "").startswith("application/json") else body)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def post(base: str, path: str, body: dict):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def test_page_is_served(station) -> None:
    base, _ = station()
    status, body = get(base, "/")
    assert status == 200 and b"What do you see?" in body and b"pointerdown" in body


def test_offer_runs_the_picker_when_nothing_is_frozen_and_opens_a_sitting(station) -> None:
    base, data = station()
    status, o = get(base, "/api/offer?camera=3")
    assert status == 200
    assert set(o) >= {"sitting_id", "frame_id", "freeze_id", "image", "score", "captured_at"}
    con = db.connect(data)
    assert con.execute("SELECT COUNT(*) FROM freezes").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM frame_scores").fetchone()[0] == 3  # every candidate logged
    ev = con.execute("SELECT kind, frame_id FROM station_events WHERE sitting_id = ?", (o["sitting_id"],)).fetchone()
    assert tuple(ev) == ("offered", o["frame_id"])
    status, img = get(base, o["image"])
    assert status == 200 and img.startswith(b"\xff\xd8")


def test_offer_falls_back_to_the_latest_frames_when_the_camera_has_been_dark(tmp_path: Path) -> None:
    data = tmp_path / "data"
    store = FrameStore(data)
    old = datetime(2026, 9, 18, 20, 0, tzinfo=timezone.utc)  # hours or days ago
    for i in range(3):
        store.add("3", old + timedelta(minutes=5 * i), "clouds", jpeg(i))
    srv = make_server(data, host="127.0.0.1", port=0, seer_fn=ok_seer, auto_pick_min=10)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        status, o = get(f"http://127.0.0.1:{srv.server_address[1]}", "/api/offer?camera=3")
        assert status == 200
        assert o["captured_at"].startswith("2026-09-18T20:")
    finally:
        srv.shutdown(); srv.server_close()


def test_offer_with_no_frames_says_so_kindly(station) -> None:
    base, _ = station(frames=0)
    status, body = get(base, "/api/offer?camera=3")
    assert status == 404 and "Look up" in body["message"]
    assert get(base, "/api/offer")[0] == 400
    assert get(base, "/api/offer?camera=../x")[0] == 400


def test_offer_reuses_a_fresh_freeze_instead_of_repicking(station) -> None:
    base, data = station()
    a = get(base, "/api/offer?camera=3")[1]
    b = get(base, "/api/offer?camera=3")[1]
    assert a["freeze_id"] == b["freeze_id"]
    assert a["sitting_id"] != b["sitting_id"]  # but each visitor gets their own sitting
    con = db.connect(data)
    assert con.execute("SELECT COUNT(*) FROM freezes").fetchone()[0] == 1


def test_commit_stores_the_response_before_the_seer_is_asked_and_reveals_after(station) -> None:
    order = []

    def spy_seer(con, data_dir, frame_id):
        order.append(("seer", con.execute("SELECT COUNT(*) FROM responses").fetchone()[0]))
        return ok_seer(con, data_dir, frame_id)

    base, data = station(seer_fn=spy_seer)
    o = get(base, "/api/offer?camera=3")[1]
    status, r = post(base, "/api/commit", {"sitting_id": o["sitting_id"], "frame_id": o["frame_id"], "freeze_id": o["freeze_id"],
                                           "text": "a bear", "strokes": STROKES})
    assert status == 201
    assert order == [("seer", 1)]  # the response was already stored when the seer ran
    assert r["seer"]["status"] == "ok" and r["seer"]["readings"][0]["thing"] == "a bear"
    con = db.connect(data)
    row = con.execute("SELECT text, strokes, revealed_at, freeze_id FROM responses WHERE id = ?", (r["response_id"],)).fetchone()
    assert row["text"] == "a bear" and json.loads(row["strokes"]) == STROKES and row["revealed_at"] is not None
    assert row["freeze_id"] == o["freeze_id"]
    kinds = [k[0] for k in con.execute("SELECT kind FROM station_events WHERE sitting_id = ? ORDER BY id", (o["sitting_id"],))]
    assert kinds == ["offered", "committed", "revealed"]


def test_a_failing_seer_does_not_lose_the_response_and_is_reported_as_could_not_look(station) -> None:
    base, data = station(seer_fn=error_seer)
    o = get(base, "/api/offer?camera=3")[1]
    status, r = post(base, "/api/commit", {"sitting_id": o["sitting_id"], "frame_id": o["frame_id"], "text": "x", "strokes": STROKES})
    assert status == 201
    assert r["seer"] == {"status": "error", "message": "the seer could not look", "detail": "ConnectionError: no network"}
    con = db.connect(data)
    assert con.execute("SELECT COUNT(*) FROM responses").fetchone()[0] == 1


def test_no_seer_mode_says_so(station) -> None:
    base, _ = station(seer_fn=no_seer)
    o = get(base, "/api/offer?camera=3")[1]
    _, r = post(base, "/api/commit", {"sitting_id": o["sitting_id"], "frame_id": o["frame_id"], "text": "x", "strokes": []})
    assert r["seer"]["status"] == "error" and r["seer"]["message"] == "the seer could not look"


def test_commit_refuses_machine_opinions_and_bad_bodies(station) -> None:
    base, _ = station()
    o = get(base, "/api/offer?camera=3")[1]
    base_body = {"sitting_id": o["sitting_id"], "frame_id": o["frame_id"], "text": "x", "strokes": STROKES}
    assert post(base, "/api/commit", {**base_body, "score": 0.9})[0] == 400
    assert post(base, "/api/commit", {**base_body, "strokes": [[[2, 2]]]})[0] == 400
    assert post(base, "/api/commit", {"text": "x", "strokes": STROKES})[0] == 400
    assert post(base, "/api/commit", {**base_body, "sitting_id": 999})[0] == 400
    req = urllib.request.Request(base + "/api/commit", data=b"[1,2]", headers={"Content-Type": "application/json"}, method="POST")
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(req)
    assert e.value.code == 400


def test_again_and_skip_events_are_recorded_and_skip_ends_the_sitting(station) -> None:
    base, data = station()
    o = get(base, "/api/offer?camera=3")[1]
    assert post(base, "/api/event", {"sitting_id": o["sitting_id"], "kind": "again", "frame_id": o["frame_id"]})[0] == 200
    assert post(base, "/api/event", {"sitting_id": o["sitting_id"], "kind": "skipped", "frame_id": o["frame_id"]})[0] == 200
    assert post(base, "/api/event", {"sitting_id": o["sitting_id"], "kind": "liked"})[0] == 400
    assert post(base, "/api/event", {"kind": "again"})[0] == 400
    con = db.connect(data)
    kinds = [k[0] for k in con.execute("SELECT kind FROM station_events WHERE sitting_id = ? ORDER BY id", (o["sitting_id"],))]
    assert kinds == ["offered", "again", "skipped"]
    assert con.execute("SELECT ended_at FROM sittings WHERE id = ?", (o["sitting_id"],)).fetchone()[0] is not None


def test_rater_is_stamped_on_sittings_by_the_server_not_the_client(station) -> None:
    base, data = station(rater="jesse")
    o = get(base, "/api/offer?camera=3")[1]
    con = db.connect(data)
    assert con.execute("SELECT rater FROM sittings WHERE id = ?", (o["sitting_id"],)).fetchone()[0] == "jesse"


def test_unknown_frame_and_paths_are_404(station) -> None:
    base, _ = station()
    assert get(base, "/frames/999.jpg")[0] == 404
    assert get(base, "/nope")[0] == 404
    assert post(base, "/api/nope", {})[0] == 404
