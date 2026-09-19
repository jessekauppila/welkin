import io
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from welkin import db
from welkin.ingest import FrameStore
from welkin.store import (
    ORIGIN,
    RUBRIC_VERSION,
    StoreError,
    bar_report,
    commit_response,
    end_sitting,
    main,
    mark_revealed,
    record_event,
    response,
    start_sitting,
    validate_strokes,
)

T0 = datetime(2026, 9, 18, 20, 0, tzinfo=timezone.utc)
STROKES = [[[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]], [[0.9, 0.9], [0.8, 0.85]]]


def frame(tmp_path: Path) -> tuple[Path, int]:
    store = FrameStore(tmp_path / "data")
    buf = io.BytesIO()
    Image.fromarray(np.full((48, 64, 3), 200, dtype=np.uint8)).save(buf, format="JPEG")
    _, row = store.add("3", T0, "clouds", buf.getvalue())
    con = db.connect(tmp_path / "data")
    fid = con.execute("SELECT id FROM frames WHERE sha256 = ?", (row["sha256"],)).fetchone()["id"]
    con.close()
    return tmp_path / "data", fid


def test_sitting_gets_server_assigned_provenance(tmp_path: Path) -> None:
    data, _ = frame(tmp_path)
    con = db.connect(data)
    sid = start_sitting(con, "3", rater="jesse")
    row = con.execute("SELECT * FROM sittings WHERE id = ?", (sid,)).fetchone()
    assert (row["origin"], row["rubric_version"], row["rater"], row["camera_id"]) == (ORIGIN, RUBRIC_VERSION, "jesse", "3")
    assert row["ended_at"] is None
    end_sitting(con, sid)
    assert con.execute("SELECT ended_at FROM sittings WHERE id = ?", (sid,)).fetchone()[0] is not None


def test_commit_stores_words_and_normalised_strokes_and_logs_the_event(tmp_path: Path) -> None:
    data, fid = frame(tmp_path)
    con = db.connect(data)
    sid = start_sitting(con, "3")
    rid = commit_response(con, sid, fid, {"text": "  a shaggy bear ", "strokes": STROKES})
    r = response(con, rid)
    assert r["text"] == "a shaggy bear"
    assert r["strokes"] == STROKES
    assert r["sitting_id"] == sid and r["frame_id"] == fid and r["revealed_at"] is None
    kinds = [e[0] for e in con.execute("SELECT kind FROM station_events WHERE sitting_id = ?", (sid,))]
    assert kinds == ["committed"]


def test_payload_may_not_carry_machine_opinions(tmp_path: Path) -> None:
    data, fid = frame(tmp_path)
    con = db.connect(data)
    sid = start_sitting(con, "3")
    for bad in ({"score": 0.9}, {"structure": 0.5}, {"readings": []}, {"strength": 1}, {"rating": 4}):
        with pytest.raises(StoreError, match="machine opinions"):
            commit_response(con, sid, fid, {"text": "x", "strokes": STROKES, **bad})
    with pytest.raises(StoreError, match="unknown payload keys"):
        commit_response(con, sid, fid, {"text": "x", "strokes": STROKES, "mood": "happy"})
    assert con.execute("SELECT COUNT(*) FROM responses").fetchone()[0] == 0


@pytest.mark.parametrize(
    "strokes, match",
    [
        ("not a list", "list of polylines"),
        ([[]], "non-empty"),
        ([[[0.1]]], "not \\[x, y\\]"),
        ([[[1.5, 0.2]]], "outside 0..1"),
        ([[[-0.1, 0.2]]], "outside 0..1"),
        ([[[True, 0.2]]], "not \\[x, y\\]"),
        ([[["0.1", 0.2]]], "outside 0..1"),
    ],
)
def test_bad_strokes_are_refused(strokes: object, match: str) -> None:
    with pytest.raises(StoreError, match=match):
        validate_strokes(strokes)


def test_strokes_are_rounded_to_four_places() -> None:
    assert validate_strokes([[[0.123456, 1], [0, 0.99999]]]) == [[[0.1235, 1.0], [0.0, 1.0]]]


def test_a_response_needs_a_drawing_or_words_but_either_alone_is_fine(tmp_path: Path) -> None:
    data, fid = frame(tmp_path)
    con = db.connect(data)
    sid = start_sitting(con, "3")
    with pytest.raises(StoreError, match="drawing or some words"):
        commit_response(con, sid, fid, {"text": "   ", "strokes": []})
    commit_response(con, sid, fid, {"text": "", "strokes": STROKES})
    commit_response(con, sid, fid, {"text": "just words", "strokes": []})
    with pytest.raises(StoreError, match="needs strokes"):
        commit_response(con, sid, fid, {"text": "no strokes key"})


def test_commit_refuses_unknown_sitting_ended_sitting_and_unknown_frame(tmp_path: Path) -> None:
    data, fid = frame(tmp_path)
    con = db.connect(data)
    with pytest.raises(StoreError, match="no sitting"):
        commit_response(con, 99, fid, {"text": "x", "strokes": STROKES})
    sid = start_sitting(con, "3")
    with pytest.raises(StoreError, match="no frame"):
        commit_response(con, sid, 999, {"text": "x", "strokes": STROKES})
    end_sitting(con, sid)
    with pytest.raises(StoreError, match="has ended"):
        commit_response(con, sid, fid, {"text": "x", "strokes": STROKES})


def test_reveal_is_recorded_once_and_events_are_validated(tmp_path: Path) -> None:
    data, fid = frame(tmp_path)
    con = db.connect(data)
    sid = start_sitting(con, "3")
    record_event(con, sid, "offered", fid)
    rid = commit_response(con, sid, fid, {"text": "bear", "strokes": STROKES})
    mark_revealed(con, rid)
    first = response(con, rid)["revealed_at"]
    mark_revealed(con, rid)
    assert response(con, rid)["revealed_at"] == first
    with pytest.raises(StoreError, match="unknown event kind"):
        record_event(con, sid, "liked")
    with pytest.raises(StoreError, match="no response"):
        mark_revealed(con, 999)


def test_bar_report_counts_started_committed_and_played_again_per_rubric(tmp_path: Path, capsys) -> None:
    data, fid = frame(tmp_path)
    con = db.connect(data)
    s1 = start_sitting(con, "3")  # walks away
    record_event(con, s1, "offered", fid)
    s2 = start_sitting(con, "3")  # one drawing
    commit_response(con, s2, fid, {"text": "bear", "strokes": STROKES})
    s3 = start_sitting(con, "3")  # two drawings = played again
    commit_response(con, s3, fid, {"text": "whale", "strokes": STROKES})
    record_event(con, s3, "again", fid)
    commit_response(con, s3, fid, {"text": "dog", "strokes": STROKES})

    [r] = bar_report(con)
    assert (r["origin"], r["rubric_version"]) == (ORIGIN, RUBRIC_VERSION)
    assert (r["started"], r["committed"], r["played_again"], r["responses"]) == (3, 2, 1, 3)
    assert r["commit_rate"] == pytest.approx(2 / 3) and r["again_rate"] == pytest.approx(1 / 3)

    # A different rubric version is reported on its own row, never pooled.
    with con:
        con.execute("UPDATE sittings SET rubric_version = 'v1' WHERE id = ?", (s3,))
    rows = bar_report(con)
    assert [(x["rubric_version"], x["started"]) for x in rows] == [("v0", 2), ("v1", 1)]

    assert main(["--data", str(data)]) == 0
    out = capsys.readouterr().out
    assert "rubric v0: started=2" in out and "rubric v1: started=1" in out and "do not add them up" in out


def test_human_and_machine_tables_are_disjoint(tmp_path: Path) -> None:
    data, _ = frame(tmp_path)
    con = db.connect(data)
    cols = {r[1] for r in con.execute("PRAGMA table_info(responses)")}
    assert not cols & {"score", "structure", "strength", "readings", "model", "prompt_version", "scorer"}
