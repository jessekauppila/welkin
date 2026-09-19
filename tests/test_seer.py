import base64
import io
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from welkin import db
from welkin.ingest import FrameStore
from welkin.seer import MODEL, PROMPT, PROMPT_VERSION, SkyReading, cost_usd, encode, read_sky, see

T0 = datetime(2026, 9, 18, 20, 0, tzinfo=timezone.utc)


def jpeg(w: int = 640, h: int = 480) -> bytes:
    arr = np.random.default_rng(0).integers(100, 255, size=(h, w, 3), dtype=np.uint8)
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="JPEG", quality=90)
    return buf.getvalue()


class FakeMessages:
    """Records the request and returns a canned response, or raises."""

    def __init__(self, parsed=None, exc: Exception | None = None, stop_reason: str = "end_turn") -> None:
        self.parsed, self.exc, self.stop_reason = parsed, exc, stop_reason
        self.calls: list[dict] = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc:
            raise self.exc
        return SimpleNamespace(
            parsed_output=self.parsed,
            stop_reason=self.stop_reason,
            stop_details=None,
            usage=SimpleNamespace(input_tokens=1500, output_tokens=120),
        )


def fake_client(**kw) -> SimpleNamespace:
    return SimpleNamespace(messages=FakeMessages(**kw))


BEAR = SkyReading(
    readings=[{"thing": "a shaggy bear", "where": "upper left", "strength": 0.7}],
    structure=0.55,
    note="Lumpy cumulus with one strong figure.",
)
NOTHING = SkyReading(readings=[], structure=0.1, note="Flat haze.")


# --- read_sky ---------------------------------------------------------------


def test_read_sky_sends_the_prototype_prompt_with_a_downscaled_jpeg_and_the_schema() -> None:
    client = fake_client(parsed=BEAR)
    big = io.BytesIO()
    Image.fromarray(np.zeros((1500, 2000, 3), dtype=np.uint8)).save(big, format="JPEG")
    r = read_sky(client, big.getvalue())

    [call] = client.messages.calls
    assert call["model"] == MODEL and call["output_format"] is SkyReading
    [image_block, text_block] = call["messages"][0]["content"]
    assert text_block == {"type": "text", "text": PROMPT}
    sent = Image.open(io.BytesIO(base64.standard_b64decode(image_block["source"]["data"])))
    assert max(sent.size) == 1024
    assert image_block["source"]["media_type"] == "image/jpeg"

    assert r["status"] == "ok"
    assert r["readings"] == [{"thing": "a shaggy bear", "where": "upper left", "strength": 0.7}]
    assert r["structure"] == 0.55 and r["prompt_version"] == PROMPT_VERSION
    assert cost_usd(r) == pytest.approx(1500 / 1e6 * 5 + 120 / 1e6 * 25)


def test_an_empty_reading_is_a_real_ok_answer() -> None:
    r = read_sky(fake_client(parsed=NOTHING), jpeg())
    assert r["status"] == "ok" and r["readings"] == [] and r["structure"] == 0.1


def test_a_refusal_raises_rather_than_returning_empty() -> None:
    with pytest.raises(RuntimeError, match="refusal"):
        read_sky(fake_client(parsed=None, stop_reason="refusal"), jpeg())


def test_prompt_version_changes_when_the_prompt_changes() -> None:
    assert PROMPT_VERSION.startswith("cloud-prototype-v1+")
    import welkin.seer as seer_mod
    import hashlib
    assert PROMPT_VERSION.endswith(hashlib.sha256(seer_mod.PROMPT.encode()).hexdigest()[:8])


# --- see (stored frames) ------------------------------------------------------


def stored_frame(tmp_path: Path) -> tuple[Path, int]:
    store = FrameStore(tmp_path / "data")
    kind, row = store.add("3", T0, "clouds", jpeg())
    assert kind == "created"
    con = db.connect(tmp_path / "data")
    fid = con.execute("SELECT id FROM frames WHERE sha256 = ?", (row["sha256"],)).fetchone()["id"]
    con.close()
    return tmp_path / "data", fid


def test_see_stores_the_reading_and_serves_it_from_the_table_afterwards(tmp_path: Path) -> None:
    data, fid = stored_frame(tmp_path)
    con = db.connect(data)
    client = fake_client(parsed=BEAR)
    first = see(con, data, fid, client)
    assert first["status"] == "ok" and first["cached"] is False and first["frame_id"] == fid

    again = see(con, data, fid, fake_client(exc=AssertionError("must not be called")))
    assert again["cached"] is True
    assert again["readings"] == first["readings"] and again["structure"] == 0.55
    assert len(client.messages.calls) == 1
    row = con.execute("SELECT status, model, prompt_version FROM readings").fetchone()
    assert tuple(row) == ("ok", MODEL, PROMPT_VERSION)


def test_an_api_error_is_stored_as_error_not_as_an_empty_reading(tmp_path: Path) -> None:
    data, fid = stored_frame(tmp_path)
    con = db.connect(data)
    r = see(con, data, fid, fake_client(exc=ConnectionError("dns")))
    assert r["status"] == "error"
    assert r["readings"] is None  # not [] — the station must not show "saw nothing"
    assert "ConnectionError: dns" in r["error"]
    row = con.execute("SELECT status, readings, error FROM readings").fetchone()
    assert row["status"] == "error" and row["readings"] is None and "dns" in row["error"]


def test_error_rows_are_retried_by_default_and_kept_when_asked(tmp_path: Path) -> None:
    data, fid = stored_frame(tmp_path)
    con = db.connect(data)
    see(con, data, fid, fake_client(exc=TimeoutError("slow")))
    kept = see(con, data, fid, fake_client(parsed=BEAR), retry_errors=False)
    assert kept["status"] == "error" and kept["cached"] is True
    healed = see(con, data, fid, fake_client(parsed=BEAR))
    assert healed["status"] == "ok" and healed["readings"][0]["thing"] == "a shaggy bear"
    assert con.execute("SELECT COUNT(*) FROM readings").fetchone()[0] == 1  # upsert, one row per key


def test_see_of_an_unknown_frame_is_a_lookup_error(tmp_path: Path) -> None:
    con = db.connect(tmp_path / "data")
    with pytest.raises(LookupError):
        see(con, tmp_path / "data", 999, fake_client(parsed=BEAR))


def test_encode_accepts_bytes_and_paths_and_never_upscales(tmp_path: Path) -> None:
    small = jpeg(320, 240)
    p = tmp_path / "s.jpg"
    p.write_bytes(small)
    for src in (small, p, str(p)):
        out = Image.open(io.BytesIO(base64.standard_b64decode(encode(src))))
        assert out.size == (320, 240)
