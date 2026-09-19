"""One SQLite file, ``data/welkin.sqlite``, shared by every Welkin component.

Rules that every table follows:

- Paths are relative to the data directory, never URLs, so the data can move.
- Times are UTC ISO8601 with a ``Z`` suffix, second precision.
- Anything a machine said about a frame (a score, a reading) is in its own table,
  never in the same row as anything a human said. They join on ``frame_id``.
- Every machine opinion records which instrument produced it (``scorer`` /
  ``model``) and which version (``scorer_version`` / ``prompt_version``), so
  numbers from two versions are never pooled by accident.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS frames (
    id          INTEGER PRIMARY KEY,
    camera_id   TEXT NOT NULL,
    captured_at TEXT NOT NULL,   -- UTC, from the device
    received_at TEXT NOT NULL,   -- UTC, from the ingest
    profile     TEXT,
    path        TEXT NOT NULL,   -- relative to the data directory
    bytes       INTEGER NOT NULL,
    sha256      TEXT NOT NULL,
    UNIQUE (camera_id, captured_at)
);
CREATE INDEX IF NOT EXISTS frames_by_time ON frames (camera_id, captured_at);

-- The picker's opinion of every frame it looked at, not just the winners.
-- Selection can only be audited if the losers' scores are kept too.
CREATE TABLE IF NOT EXISTS frame_scores (
    id             INTEGER PRIMARY KEY,
    frame_id       INTEGER NOT NULL REFERENCES frames(id),
    scorer         TEXT NOT NULL,      -- e.g. 'texture'
    scorer_version TEXT NOT NULL,      -- e.g. 'v0'
    score          REAL NOT NULL,
    scored_at      TEXT NOT NULL,
    UNIQUE (frame_id, scorer, scorer_version)
);

-- A frame the picker chose to offer. The station shows the latest freeze.
CREATE TABLE IF NOT EXISTS freezes (
    id             INTEGER PRIMARY KEY,
    camera_id      TEXT NOT NULL,
    frame_id       INTEGER NOT NULL REFERENCES frames(id),
    frozen_at      TEXT NOT NULL,
    scorer         TEXT NOT NULL,
    scorer_version TEXT NOT NULL,
    score          REAL NOT NULL,
    candidates     INTEGER NOT NULL   -- how many frames were in the running
);

-- One visit to the station: from the first frame offered to the person walking
-- away. Provenance lives here, assigned by the server, never sent by the client.
CREATE TABLE IF NOT EXISTS sittings (
    id             INTEGER PRIMARY KEY,
    camera_id      TEXT NOT NULL,
    started_at     TEXT NOT NULL,
    ended_at       TEXT,
    origin         TEXT NOT NULL,      -- e.g. 'exhibit_v0'
    rubric_version TEXT NOT NULL,      -- e.g. 'v0'
    rater          TEXT                -- who, when known; NULL for an anonymous visitor
);

-- What a person said about a frame: strokes and words, committed together.
-- Never holds a score, a reading, or anything the machine said (that is in
-- frame_scores / readings, joined on frame_id).
CREATE TABLE IF NOT EXISTS responses (
    id           INTEGER PRIMARY KEY,
    sitting_id   INTEGER NOT NULL REFERENCES sittings(id),
    frame_id     INTEGER NOT NULL REFERENCES frames(id),
    freeze_id    INTEGER REFERENCES freezes(id),
    text         TEXT NOT NULL,        -- "what do you see?", may be empty
    strokes      TEXT NOT NULL,        -- JSON: [[[x,y],[x,y],...], ...], coords in 0..1
    committed_at TEXT NOT NULL,
    revealed_at  TEXT                  -- when the seer's reading was shown; NULL if never
);

-- The station's timeline, for the pre-registered bar (docs/m1-bar.md):
-- 'offered', 'committed', 'revealed', 'again', 'skipped'.
CREATE TABLE IF NOT EXISTS station_events (
    id         INTEGER PRIMARY KEY,
    sitting_id INTEGER NOT NULL REFERENCES sittings(id),
    kind       TEXT NOT NULL,
    frame_id   INTEGER REFERENCES frames(id),
    at         TEXT NOT NULL
);

-- The seer's reading of a frame. status is 'ok' or 'error'; an error row has
-- no readings and must never be shown as "the seer saw nothing".
CREATE TABLE IF NOT EXISTS readings (
    id             INTEGER PRIMARY KEY,
    frame_id       INTEGER NOT NULL REFERENCES frames(id),
    model          TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    status         TEXT NOT NULL,      -- 'ok' | 'error'
    readings       TEXT,               -- JSON list of {thing, where, strength}
    structure      REAL,
    note           TEXT,
    error          TEXT,
    in_tokens      INTEGER,
    out_tokens     INTEGER,
    read_at        TEXT NOT NULL,
    UNIQUE (frame_id, model, prompt_version)
);
"""


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def connect(data_dir: str | Path) -> sqlite3.Connection:
    """Open (creating if needed) the data directory's database with the schema applied."""
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(data_dir / "welkin.sqlite", timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(SCHEMA)
    return con
