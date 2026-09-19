import io
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from welkin import db
from welkin.ingest import FrameStore
from welkin.picker import (
    SCORER,
    SCORER_VERSION,
    control_main,
    freeze,
    latest_freeze,
    load_image,
    main,
    score_file,
    score_recent,
    texture_score,
)

T0 = datetime(2026, 9, 18, 20, 0, tzinfo=timezone.utc)


def flat(w: int = 320, h: int = 240, value: int = 180) -> np.ndarray:
    return np.full((h, w, 3), value, dtype=np.uint8)


def gradient(w: int = 320, h: int = 240) -> np.ndarray:
    col = np.linspace(120, 220, h, dtype=np.uint8)
    return np.repeat(np.repeat(col[:, None], w, axis=1)[:, :, None], 3, axis=2)


def lumpy(w: int = 320, h: int = 240, seed: int = 0) -> np.ndarray:
    """Hard-edged blobs on a flat ground: a stand-in for 'something is here'.
    (Real cumulus is softer; see docs/controls.md for why that matters.)"""
    rng = np.random.default_rng(seed)
    small = rng.uniform(20, 255, size=(h // 8, w // 8))
    img = Image.fromarray(small.astype(np.uint8)).resize((w, h), Image.NEAREST)
    return np.repeat(np.array(img)[:, :, None], 3, axis=2)


def jpeg(arr: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="JPEG", quality=92)
    return buf.getvalue()


# --- the score itself --------------------------------------------------------


def test_flat_and_gradient_score_near_zero_and_lumpy_scores_higher() -> None:
    assert texture_score(flat()) == 0.0
    assert texture_score(gradient()) < 1.0
    assert texture_score(lumpy()) > 10 * texture_score(gradient())


def test_score_is_resolution_stable_after_resize(tmp_path: Path) -> None:
    big = tmp_path / "big.jpg"
    Image.fromarray(lumpy(1920, 1440)).save(big, quality=92)
    small = tmp_path / "small.jpg"
    Image.fromarray(lumpy(960, 720)).save(small, quality=92)
    # Not identical (different resampling paths) but the same order of magnitude,
    # and both far above a flat frame. The point is that a 1920px camera and a
    # 960px camera are comparable.
    a, b = score_file(big), score_file(small)
    assert 0.4 < a / b < 2.5
    assert min(a, b) > 5 * texture_score(gradient())


def test_sky_crop_keeps_only_the_top_fraction(tmp_path: Path) -> None:
    arr = flat(320, 240)
    arr[120:] = lumpy(320, 120)  # ground clutter in the bottom half
    p = tmp_path / "half.jpg"
    Image.fromarray(arr).save(p, quality=92)
    assert score_file(p, sky_crop=0.5) < 1.0
    assert score_file(p) > 5.0
    assert load_image(p, sky_crop=0.5).shape[0] == 120


# --- scoring a camera's window -----------------------------------------------


def make_frames(tmp_path: Path, arrays: list[np.ndarray]) -> tuple[FrameStore, Path]:
    store = FrameStore(tmp_path / "data")
    for i, arr in enumerate(arrays):
        kind, _ = store.add("3", T0 + timedelta(minutes=5 * i), "clouds", jpeg(arr))
        assert kind == "created"
    return store, tmp_path / "data"


def test_score_recent_logs_every_candidate_and_freeze_picks_the_max(tmp_path: Path) -> None:
    _, data = make_frames(tmp_path, [flat(), lumpy(seed=1), gradient(), lumpy(seed=2)])
    con = db.connect(data)
    cands = score_recent(con, data, "3", T0, T0 + timedelta(hours=1))
    assert [c.captured_at for c in cands] == [
        "2026-09-18T20:00:00Z", "2026-09-18T20:05:00Z", "2026-09-18T20:10:00Z", "2026-09-18T20:15:00Z",
    ]
    logged = con.execute("SELECT COUNT(*) FROM frame_scores WHERE scorer = ? AND scorer_version = ?", (SCORER, SCORER_VERSION)).fetchone()[0]
    assert logged == 4  # losers too

    best = freeze(con, "3", cands)
    assert best is not None
    assert best.captured_at in ("2026-09-18T20:05:00Z", "2026-09-18T20:15:00Z")
    fz = latest_freeze(con, "3")
    assert fz["frame_id"] == best.frame_id
    assert fz["candidates"] == 4
    assert fz["scorer_version"] == SCORER_VERSION


def test_score_recent_does_not_rescore_and_respects_the_window(tmp_path: Path) -> None:
    _, data = make_frames(tmp_path, [flat(), lumpy(), flat()])
    con = db.connect(data)
    first = score_recent(con, data, "3", T0, T0 + timedelta(minutes=5))
    assert len(first) == 2
    again = score_recent(con, data, "3", T0, T0 + timedelta(minutes=5))
    assert again == first
    assert con.execute("SELECT COUNT(*) FROM frame_scores").fetchone()[0] == 2


def test_freeze_with_no_candidates_returns_none_and_records_nothing(tmp_path: Path) -> None:
    con = db.connect(tmp_path / "data")
    assert freeze(con, "3", []) is None
    assert con.execute("SELECT COUNT(*) FROM freezes").fetchone()[0] == 0


def test_a_lens_cap_window_still_freezes_something_so_the_station_must_check_the_score(tmp_path: Path) -> None:
    # The picker has no notion of "good enough". A window of black frames
    # yields a freeze with score ~0. The station (not the picker) decides
    # whether that is worth offering. This test pins that division of labour.
    _, data = make_frames(tmp_path, [flat(value=0), flat(value=0)])
    con = db.connect(data)
    best = freeze(con, "3", score_recent(con, data, "3", T0, T0 + timedelta(hours=1)))
    assert best is not None and best.score == 0.0


# --- command lines -------------------------------------------------------------


def test_picker_cli_dry_run_and_real_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _, data = make_frames(tmp_path, [flat(), lumpy()])
    # Frames are dated 2026-09-18; use a huge window so "now" reaches them.
    assert main(["--data", str(data), "--camera", "3", "--window-min", str(60 * 24 * 365 * 5), "--dry-run"]) == 0
    assert "would freeze" in capsys.readouterr().out
    assert main(["--data", str(data), "--camera", "3", "--window-min", str(60 * 24 * 365 * 5)]) == 0
    assert "froze" in capsys.readouterr().out
    assert main(["--data", str(data), "--camera", "9", "--window-min", "10"]) == 1


def test_control_cli_reports_separation(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ctrl, clouds = tmp_path / "control", tmp_path / "clouds"
    ctrl.mkdir(); clouds.mkdir()
    for i, arr in enumerate([flat(), gradient(), flat(value=0)]):
        Image.fromarray(arr).save(ctrl / f"c{i}.jpg", quality=92)
    for i in range(3):
        Image.fromarray(lumpy(seed=i)).save(clouds / f"k{i}.jpg", quality=92)
    assert control_main([str(ctrl), "--clouds", str(clouds)]) == 0
    out = capsys.readouterr().out
    assert "control  n=3" in out and "clouds   n=3" in out
    assert "0/3 clouds score at or below the control max" in out
