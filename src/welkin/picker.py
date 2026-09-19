"""The cloud picker: which frame to freeze and offer.

v0 is a texture score, the std of a Laplacian over the greyscale image. It is
a stand-in for "how much shape is here" and nothing more. It knows nothing
about clouds; it fires on any high-frequency structure, including a tree in
the corner of the frame. That is why every frame's score is logged, not only
the winner's, and why the negative control (``welkin-control``) exists: run
it on flat sky and a lens cap before trusting the picker on a single sitting.

Ported from the cloud prototype:
    origin: ~/GitHub/pareidolia-hub/apps/cloud-pareidolia/notebooks/pareidolia_lab.py
    commit: be5c86a (2026-09-16)
    functions: Sample.load (as load_image), texture_score (verbatim)
    changed: the crop fraction defaults to None (whole frame) because a
    sky-pointed camera has no ground to remove; the prototype's photographs
    did, hence its SKY_CROP = 0.40.
"""

from __future__ import annotations

import argparse
import sqlite3
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from PIL import Image

from welkin import db

SCORER = "texture"
SCORER_VERSION = "v0"
MAX_SIDE = 1024  # score at this size so the number does not depend on camera resolution


def load_image(path: str | Path, sky_crop: float | None = None, max_side: int | None = MAX_SIDE) -> np.ndarray:
    """RGB array of an image, optionally keeping only the top ``sky_crop`` fraction,
    resized so the longer side is at most ``max_side``."""
    img = Image.open(path).convert("RGB")
    if sky_crop:
        img = img.crop((0, 0, img.width, max(1, round(img.height * sky_crop))))
    if max_side and max(img.size) > max_side:
        scale = max_side / max(img.size)
        img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    return np.array(img)


def texture_score(image: np.ndarray) -> float:
    """High-frequency energy: the std of a Laplacian over the greyscale image.

    Stands in for "how many spatial modes are here" — the quantity the paper's
    goldilocks model is about. Used to *measure* the gap between the cloud
    condition and the flat-sky control rather than asserting one exists.
    """
    a = np.asarray(Image.fromarray(image).convert("L"), dtype=float)
    lap = a[1:-1, 1:-1] * 4 - a[:-2, 1:-1] - a[2:, 1:-1] - a[1:-1, :-2] - a[1:-1, 2:]
    return float(lap.std())


def score_file(path: str | Path, sky_crop: float | None = None) -> float:
    return texture_score(load_image(path, sky_crop=sky_crop))


@dataclass(frozen=True)
class Scored:
    frame_id: int
    captured_at: str
    path: str
    score: float


def score_recent(
    con: sqlite3.Connection,
    data_dir: Path,
    camera_id: str,
    since: datetime,
    until: datetime | None = None,
    sky_crop: float | None = None,
) -> list[Scored]:
    """Score every frame of ``camera_id`` captured in [since, until], writing one
    ``frame_scores`` row per frame (skipping frames already scored by this
    scorer version). Returns all candidates, oldest first."""
    until = until or datetime.now(timezone.utc)
    rows = con.execute(
        "SELECT id, captured_at, path FROM frames WHERE camera_id = ? AND captured_at >= ? AND captured_at <= ? "
        "ORDER BY captured_at",
        (camera_id, _iso(since), _iso(until)),
    ).fetchall()

    out: list[Scored] = []
    for row in rows:
        existing = con.execute(
            "SELECT score FROM frame_scores WHERE frame_id = ? AND scorer = ? AND scorer_version = ?",
            (row["id"], SCORER, SCORER_VERSION),
        ).fetchone()
        if existing is not None:
            score = existing["score"]
        else:
            score = score_file(data_dir / row["path"], sky_crop=sky_crop)
            with con:
                con.execute(
                    "INSERT INTO frame_scores (frame_id, scorer, scorer_version, score, scored_at) VALUES (?, ?, ?, ?, ?)",
                    (row["id"], SCORER, SCORER_VERSION, score, db.utcnow_iso()),
                )
        out.append(Scored(row["id"], row["captured_at"], row["path"], score))
    return out


def freeze(con: sqlite3.Connection, camera_id: str, candidates: list[Scored]) -> Scored | None:
    """Pick the highest-scoring candidate and record the freeze. Ties go to the
    most recent frame. Returns None when there is nothing to pick."""
    if not candidates:
        return None
    best = max(candidates, key=lambda s: (s.score, s.captured_at))
    with con:
        con.execute(
            "INSERT INTO freezes (camera_id, frame_id, frozen_at, scorer, scorer_version, score, candidates) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (camera_id, best.frame_id, db.utcnow_iso(), SCORER, SCORER_VERSION, best.score, len(candidates)),
        )
    return best


def latest_freeze(con: sqlite3.Connection, camera_id: str) -> sqlite3.Row | None:
    return con.execute(
        "SELECT fz.*, f.path, f.captured_at FROM freezes fz JOIN frames f ON f.id = fz.frame_id "
        "WHERE fz.camera_id = ? ORDER BY fz.frozen_at DESC, fz.id DESC LIMIT 1",
        (camera_id,),
    ).fetchone()


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# --- command line -----------------------------------------------------------


def _summary(scores: list[float]) -> str:
    if not scores:
        return "n=0"
    q = statistics.quantiles(scores, n=4) if len(scores) >= 2 else [scores[0]] * 3
    return (
        f"n={len(scores)}  min={min(scores):.2f}  q1={q[0]:.2f}  median={statistics.median(scores):.2f}  "
        f"q3={q[2]:.2f}  max={max(scores):.2f}"
    )


def control_main(argv: list[str] | None = None) -> int:
    """``welkin-control``: the negative control. Score a directory of images that
    should NOT be picked (flat sky, lens cap, a ceiling) and, optionally, one that
    should (clouds). Prints both distributions and whether they separate. The
    picker is only trustworthy if the control's max sits below the clouds' median."""
    ap = argparse.ArgumentParser(description=control_main.__doc__)
    ap.add_argument("control", help="directory of images that must score low")
    ap.add_argument("--clouds", help="directory of images that should score high")
    ap.add_argument("--sky-crop", type=float, default=None, help="keep only this top fraction (prototype used 0.40)")
    ap.add_argument("--show", type=int, default=5, help="list this many highest control and lowest cloud files")
    args = ap.parse_args(argv)

    def scored_dir(d: str) -> list[tuple[float, str]]:
        files = sorted(p for p in Path(d).iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
        return sorted((score_file(p, sky_crop=args.sky_crop), p.name) for p in files)

    control = scored_dir(args.control)
    print(f"control  {_summary([s for s, _ in control])}")
    for s, name in control[-args.show :][::-1]:
        print(f"    high control {s:8.2f}  {name}")
    if args.clouds:
        clouds = scored_dir(args.clouds)
        print(f"clouds   {_summary([s for s, _ in clouds])}")
        for s, name in clouds[: args.show]:
            print(f"    low cloud    {s:8.2f}  {name}")
        cmax = max(s for s, _ in control)
        cmed = statistics.median([s for s, _ in clouds])
        overlap = sum(1 for s, _ in clouds if s <= cmax)
        print(
            f"separation: control max {cmax:.2f} vs cloud median {cmed:.2f}; "
            f"{overlap}/{len(clouds)} clouds score at or below the control max"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    """``welkin-picker``: score a camera's recent frames and freeze the best."""
    ap = argparse.ArgumentParser(description=main.__doc__)
    ap.add_argument("--data", default="data")
    ap.add_argument("--camera", required=True)
    ap.add_argument("--window-min", type=int, default=30, help="look back this many minutes")
    ap.add_argument("--sky-crop", type=float, default=None)
    ap.add_argument("--dry-run", action="store_true", help="score and print, do not record a freeze")
    args = ap.parse_args(argv)

    data_dir = Path(args.data)
    con = db.connect(data_dir)
    now = datetime.now(timezone.utc)
    candidates = score_recent(con, data_dir, args.camera, now - timedelta(minutes=args.window_min), now, args.sky_crop)
    for c in candidates:
        print(f"{c.captured_at}  {c.score:8.2f}  {c.path}")
    if not candidates:
        print(f"no frames for camera {args.camera!r} in the last {args.window_min} min")
        return 1
    if args.dry_run:
        best = max(candidates, key=lambda s: (s.score, s.captured_at))
        print(f"would freeze: {best.captured_at}  {best.score:.2f}")
    else:
        best = freeze(con, args.camera, candidates)
        print(f"froze: {best.captured_at}  {best.score:.2f}  ({len(candidates)} candidates)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
