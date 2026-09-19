"""The human response store: everything a person tells the station about a frame.

A *sitting* is one visit: the server opens it when the first frame is offered
and stamps it with provenance (``origin``, ``rubric_version``, ``rater``). A
*response* is one committed drawing plus words about one frame. Events record
the timeline the pre-registered bar (``docs/m1-bar.md``) is computed from.

Rules, enforced here rather than trusted to the client:

- The client never sends provenance. ``origin`` and ``rubric_version`` are
  module constants; ``sitting_id`` comes from :func:`start_sitting`.
- A response payload may not carry a score, a reading, a strength or any other
  machine opinion. :func:`commit_response` refuses such keys, so the human table
  can never quietly absorb the machine's view (figment's ``test_rate`` rule).
- Strokes are normalised to the frame (0..1 in both axes) so they survive a
  change of screen or camera resolution.
- Rubric versions are never pooled. Reports group by ``rubric_version``.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from welkin import db

ORIGIN = "exhibit_v0"
RUBRIC_VERSION = "v0"

EVENT_KINDS = ("offered", "committed", "revealed", "again", "skipped")

# Anything that would make the human table a copy of the machine's opinion.
FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {"score", "scores", "structure", "strength", "reading", "readings", "ai", "seer", "model", "rating", "label"}
)
ALLOWED_PAYLOAD_KEYS = frozenset({"text", "strokes"})

MAX_TEXT_CHARS = 500
MAX_STROKES = 500
MAX_POINTS_PER_STROKE = 5000


class StoreError(ValueError):
    """A response the store refuses to record."""


def start_sitting(con: sqlite3.Connection, camera_id: str, rater: str | None = None) -> int:
    with con:
        cur = con.execute(
            "INSERT INTO sittings (camera_id, started_at, origin, rubric_version, rater) VALUES (?, ?, ?, ?, ?)",
            (camera_id, db.utcnow_iso(), ORIGIN, RUBRIC_VERSION, rater),
        )
    return int(cur.lastrowid)


def end_sitting(con: sqlite3.Connection, sitting_id: int) -> None:
    with con:
        con.execute("UPDATE sittings SET ended_at = ? WHERE id = ? AND ended_at IS NULL", (db.utcnow_iso(), sitting_id))


def record_event(con: sqlite3.Connection, sitting_id: int, kind: str, frame_id: int | None = None) -> None:
    if kind not in EVENT_KINDS:
        raise StoreError(f"unknown event kind {kind!r}; one of {', '.join(EVENT_KINDS)}")
    with con:
        con.execute(
            "INSERT INTO station_events (sitting_id, kind, frame_id, at) VALUES (?, ?, ?, ?)",
            (sitting_id, kind, frame_id, db.utcnow_iso()),
        )


def validate_strokes(strokes: object) -> list[list[list[float]]]:
    """Strokes are a list of polylines; each point is [x, y] in 0..1."""
    if not isinstance(strokes, list):
        raise StoreError("strokes must be a list of polylines")
    if len(strokes) > MAX_STROKES:
        raise StoreError(f"too many strokes ({len(strokes)} > {MAX_STROKES})")
    out: list[list[list[float]]] = []
    for i, line in enumerate(strokes):
        if not isinstance(line, list) or not line:
            raise StoreError(f"stroke {i} must be a non-empty list of points")
        if len(line) > MAX_POINTS_PER_STROKE:
            raise StoreError(f"stroke {i} has too many points")
        pts: list[list[float]] = []
        for pt in line:
            if not (isinstance(pt, (list, tuple)) and len(pt) == 2) or any(isinstance(v, bool) for v in pt):
                raise StoreError(f"stroke {i} has a point that is not [x, y]")
            x, y = pt
            if not all(isinstance(v, (int, float)) and 0.0 <= v <= 1.0 for v in (x, y)):
                raise StoreError(f"stroke {i} has a point outside 0..1: {pt!r}")
            pts.append([round(float(x), 4), round(float(y), 4)])
        out.append(pts)
    return out


def commit_response(
    con: sqlite3.Connection,
    sitting_id: int,
    frame_id: int,
    payload: dict,
    freeze_id: int | None = None,
) -> int:
    """Record what the person drew and said about ``frame_id``. ``payload`` is
    exactly ``{"text": str, "strokes": [...]}``; anything else is refused."""
    if not isinstance(payload, dict):
        raise StoreError("payload must be an object")
    keys = set(payload)
    bad = keys & FORBIDDEN_PAYLOAD_KEYS
    if bad:
        raise StoreError(f"payload may not carry machine opinions: {sorted(bad)}")
    unknown = keys - ALLOWED_PAYLOAD_KEYS
    if unknown:
        raise StoreError(f"unknown payload keys: {sorted(unknown)}")
    if "strokes" not in payload:
        raise StoreError("payload needs strokes (an empty list is allowed)")
    text = payload.get("text", "")
    if not isinstance(text, str):
        raise StoreError("text must be a string")
    text = text.strip()
    if len(text) > MAX_TEXT_CHARS:
        raise StoreError(f"text longer than {MAX_TEXT_CHARS} characters")
    strokes = validate_strokes(payload["strokes"])
    if not strokes and not text:
        raise StoreError("a response needs a drawing or some words")

    sitting = con.execute("SELECT id, ended_at FROM sittings WHERE id = ?", (sitting_id,)).fetchone()
    if sitting is None:
        raise StoreError(f"no sitting {sitting_id}")
    if sitting["ended_at"] is not None:
        raise StoreError(f"sitting {sitting_id} has ended")
    if con.execute("SELECT 1 FROM frames WHERE id = ?", (frame_id,)).fetchone() is None:
        raise StoreError(f"no frame {frame_id}")

    with con:
        cur = con.execute(
            "INSERT INTO responses (sitting_id, frame_id, freeze_id, text, strokes, committed_at) VALUES (?, ?, ?, ?, ?, ?)",
            (sitting_id, frame_id, freeze_id, text, json.dumps(strokes, separators=(",", ":")), db.utcnow_iso()),
        )
        con.execute(
            "INSERT INTO station_events (sitting_id, kind, frame_id, at) VALUES (?, 'committed', ?, ?)",
            (sitting_id, frame_id, db.utcnow_iso()),
        )
    return int(cur.lastrowid)


def mark_revealed(con: sqlite3.Connection, response_id: int) -> None:
    row = con.execute("SELECT sitting_id, frame_id FROM responses WHERE id = ?", (response_id,)).fetchone()
    if row is None:
        raise StoreError(f"no response {response_id}")
    with con:
        con.execute("UPDATE responses SET revealed_at = ? WHERE id = ? AND revealed_at IS NULL", (db.utcnow_iso(), response_id))
        con.execute(
            "INSERT INTO station_events (sitting_id, kind, frame_id, at) VALUES (?, 'revealed', ?, ?)",
            (row["sitting_id"], row["frame_id"], db.utcnow_iso()),
        )


def response(con: sqlite3.Connection, response_id: int) -> dict | None:
    row = con.execute("SELECT * FROM responses WHERE id = ?", (response_id,)).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["strokes"] = json.loads(d["strokes"])
    return d


# --- the pre-registered bar --------------------------------------------------


def bar_report(con: sqlite3.Connection, since: str | None = None, until: str | None = None) -> list[dict]:
    """The numbers docs/m1-bar.md is judged on, per (origin, rubric_version).
    Computed from events, so a sitting with no commit still counts as started."""
    where, args = "", []
    if since:
        where += " AND s.started_at >= ?"
        args.append(since)
    if until:
        where += " AND s.started_at < ?"
        args.append(until)
    rows = con.execute(
        f"""
        SELECT s.origin, s.rubric_version,
               COUNT(*) AS started,
               SUM(CASE WHEN c.n >= 1 THEN 1 ELSE 0 END) AS committed,
               SUM(CASE WHEN c.n >= 2 THEN 1 ELSE 0 END) AS played_again,
               SUM(COALESCE(c.n, 0)) AS responses
        FROM sittings s
        LEFT JOIN (SELECT sitting_id, COUNT(*) AS n FROM responses GROUP BY sitting_id) c ON c.sitting_id = s.id
        WHERE 1 = 1 {where}
        GROUP BY s.origin, s.rubric_version
        ORDER BY s.origin, s.rubric_version
        """,
        args,
    ).fetchall()
    out = []
    for r in rows:
        started = r["started"] or 0
        out.append(
            {
                "origin": r["origin"],
                "rubric_version": r["rubric_version"],
                "started": started,
                "committed": r["committed"] or 0,
                "played_again": r["played_again"] or 0,
                "responses": r["responses"] or 0,
                "commit_rate": (r["committed"] or 0) / started if started else None,
                "again_rate": (r["played_again"] or 0) / started if started else None,
            }
        )
    return out


def main(argv: list[str] | None = None) -> int:
    """``welkin-report``: the pre-registered bar's numbers, per rubric version."""
    ap = argparse.ArgumentParser(description=main.__doc__)
    ap.add_argument("--data", default="data")
    ap.add_argument("--since", help="ISO UTC, inclusive")
    ap.add_argument("--until", help="ISO UTC, exclusive")
    args = ap.parse_args(argv)
    con = db.connect(Path(args.data))
    rows = bar_report(con, args.since, args.until)
    if not rows:
        print("no sittings")
        return 0
    for r in rows:
        cr = f"{r['commit_rate']:.0%}" if r["commit_rate"] is not None else "-"
        ar = f"{r['again_rate']:.0%}" if r["again_rate"] is not None else "-"
        print(
            f"{r['origin']} / rubric {r['rubric_version']}: started={r['started']}  "
            f"committed={r['committed']} ({cr})  played_again={r['played_again']} ({ar})  responses={r['responses']}"
        )
    print("bar: docs/m1-bar.md. Versions are reported separately on purpose; do not add them up.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
