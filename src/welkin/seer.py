"""The seer: the AI's turn in freeze-and-draw.

It looks at the frozen frame once and says what, if anything, it sees. Its
reading is the AI's *voice* in the game, shown only after the human commits
their own answer. Whether the seer may also be a *score* is open question 8
in the brief; nothing here ranks frames by it.

Two rules the station must keep:

- **Error is not empty.** A reading with ``status == "error"`` means the seer
  could not look. It is stored and returned with no readings, and must be shown
  as "the seer could not look", never as "the seer saw nothing". The prototype's
  batch reader collapsed the two into one shape; this module keeps them apart.
- **Empty is a real answer.** An ``ok`` reading with an empty list is the model
  saying the sky is just texture. The prompt makes that explicit on purpose;
  without a blessed way to say "nothing", an obliging model invents something
  for a blank frame and the negative control measures the prompt, not the sky.

Ported from the cloud prototype:
    origin: ~/GitHub/pareidolia-hub/apps/cloud-pareidolia/notebooks/vlm_lab.py
    commit: be5c86a (2026-09-16)
    kept verbatim: PROMPT, Reading, SkyReading, MODEL, IMAGE_MAX_SIDE, the
      messages.parse call shape
    changed: credentials come from the SDK's own resolution only (no .env
      fallback into the sunset repo); the per-call JSON file cache becomes the
      ``readings`` table keyed on (frame, model, prompt_version); errors are a
      stored status instead of an empty row.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import sqlite3
from pathlib import Path
from typing import Any, Protocol

from PIL import Image
from pydantic import BaseModel, Field

from welkin import db

MODEL = "claude-opus-5"
MAX_TOKENS = 8000
IMAGE_MAX_SIDE = 1024  # bigger costs more tokens for no gain at this task

# $ per million tokens (input, output). Used to report spend, not to decide anything.
PRICING = {"claude-opus-5": (5.00, 25.00), "claude-sonnet-5": (2.00, 10.00)}


class Reading(BaseModel):
    thing: str = Field(description="What it looks like, in a few words")
    where: str = Field(description="Roughly where in the frame")
    strength: float = Field(
        description="0-1: how strongly this reads, not how confident you are that "
        "it is really there. 0.2 = you have to want to see it."
    )


class SkyReading(BaseModel):
    readings: list[Reading] = Field(
        description="Up to 4, strongest first. EMPTY if nothing reads as anything."
    )
    structure: float = Field(
        description="0-1: how much shape-like structure this sky has at all, "
        "independent of whether any of it resolves into something nameable."
    )
    note: str = Field(description="One sentence on the sky's character.")


# The escape hatch is load-bearing. Without an explicit, blessed way to answer
# "nothing", an obliging model invents something for a blank sky and the negative
# control measures the prompt instead of the model.
PROMPT = """Look at this photograph the way a child watching clouds would — what,
if anything, does it look like?

Report only what genuinely reads as a shape or figure to you. An empty `readings`
list is a perfectly good answer, and the right one for an image that is just
texture, haze or flat tone. Do not reach. Do not pad the list to seem useful.

Use `strength` for how strongly a shape reads, not how sure you are it is "really"
there — nothing is really there, that is the point. Something unmistakable is 0.9;
something you only see once it is pointed out is 0.2."""

# Changing PROMPT changes what is being measured. The version is derived from the
# text so two prompts can never share a row, and named so a human can read it.
PROMPT_VERSION = "cloud-prototype-v1+" + hashlib.sha256(PROMPT.encode()).hexdigest()[:8]


class MessagesClient(Protocol):
    """The slice of ``anthropic.Anthropic`` the seer uses. Tests pass a fake."""

    messages: Any


def make_client() -> Any:
    """An Anthropic client using the SDK's own credential resolution
    (ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN, or an ``ant auth login`` profile)."""
    import anthropic

    return anthropic.Anthropic()


def encode(jpeg_or_path: bytes | str | Path, max_side: int = IMAGE_MAX_SIDE) -> str:
    """Base64 JPEG, downscaled so the longer side is at most ``max_side``."""
    img = Image.open(io.BytesIO(jpeg_or_path) if isinstance(jpeg_or_path, bytes) else jpeg_or_path).convert("RGB")
    if max(img.size) > max_side:
        scale = max_side / max(img.size)
        img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return base64.standard_b64encode(buf.getvalue()).decode()


def read_sky(client: MessagesClient, image: bytes | str | Path, model: str = MODEL) -> dict:
    """One reading of one image. Raises on any API failure; callers decide how
    to record that. Returns a flat dict with status 'ok'."""
    response = client.messages.parse(
        model=model,
        max_tokens=MAX_TOKENS,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": encode(image)}},
                    {"type": "text", "text": PROMPT},
                ],
            }
        ],
        output_format=SkyReading,
    )
    if response.stop_reason == "refusal":
        details = getattr(response, "stop_details", None)
        why = getattr(details, "explanation", None) or "the model declined to look at this image"
        raise RuntimeError(f"refusal: {why}")
    parsed = response.parsed_output
    if parsed is None:
        raise RuntimeError(f"no structured output (stop_reason={response.stop_reason!r})")
    return {
        "status": "ok",
        "model": model,
        "prompt_version": PROMPT_VERSION,
        "readings": [r.model_dump() for r in parsed.readings],
        "structure": parsed.structure,
        "note": parsed.note,
        "in_tokens": response.usage.input_tokens,
        "out_tokens": response.usage.output_tokens,
    }


def cost_usd(row: dict, model: str | None = None) -> float:
    price_in, price_out = PRICING.get(model or row.get("model", MODEL), PRICING[MODEL])
    return (row.get("in_tokens") or 0) / 1e6 * price_in + (row.get("out_tokens") or 0) / 1e6 * price_out


def see(
    con: sqlite3.Connection,
    data_dir: Path,
    frame_id: int,
    client: MessagesClient | None = None,
    model: str = MODEL,
    retry_errors: bool = True,
) -> dict:
    """The seer's reading of a stored frame, from the ``readings`` table when it
    exists, else from the model. An API failure is stored as ``status='error'``
    with the message, and returned in the same shape. Error rows are retried on
    the next call unless ``retry_errors`` is False."""
    cached = con.execute(
        "SELECT * FROM readings WHERE frame_id = ? AND model = ? AND prompt_version = ?",
        (frame_id, model, PROMPT_VERSION),
    ).fetchone()
    if cached is not None and not (cached["status"] == "error" and retry_errors):
        return _row_to_dict(cached, cached_hit=True)

    frame = con.execute("SELECT path FROM frames WHERE id = ?", (frame_id,)).fetchone()
    if frame is None:
        raise LookupError(f"no frame with id {frame_id}")

    client = client or make_client()
    try:
        result = read_sky(client, data_dir / frame["path"], model=model)
    except Exception as exc:  # noqa: BLE001 — the point is to record, not to crash the station
        result = {
            "status": "error",
            "model": model,
            "prompt_version": PROMPT_VERSION,
            "readings": None,
            "structure": None,
            "note": None,
            "error": f"{type(exc).__name__}: {exc}",
            "in_tokens": None,
            "out_tokens": None,
        }

    with con:
        con.execute(
            "INSERT INTO readings (frame_id, model, prompt_version, status, readings, structure, note, error, "
            "in_tokens, out_tokens, read_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (frame_id, model, prompt_version) DO UPDATE SET status = excluded.status, "
            "readings = excluded.readings, structure = excluded.structure, note = excluded.note, "
            "error = excluded.error, in_tokens = excluded.in_tokens, out_tokens = excluded.out_tokens, "
            "read_at = excluded.read_at",
            (
                frame_id,
                model,
                PROMPT_VERSION,
                result["status"],
                json.dumps(result["readings"]) if result["readings"] is not None else None,
                result["structure"],
                result["note"],
                result.get("error"),
                result["in_tokens"],
                result["out_tokens"],
                db.utcnow_iso(),
            ),
        )
    return {**result, "frame_id": frame_id, "cached": False}


def _row_to_dict(row: sqlite3.Row, cached_hit: bool) -> dict:
    d = dict(row)
    d["readings"] = json.loads(d["readings"]) if d["readings"] else (None if d["status"] == "error" else [])
    d["cached"] = cached_hit
    return d


# --- command line -----------------------------------------------------------


def _print_reading(label: str, r: dict) -> None:
    if r["status"] == "error":
        print(f"{label}: the seer could not look ({r['error']})")
        return
    things = ", ".join(f"{x['thing']} ({x['strength']:.1f})" for x in r["readings"]) or "(nothing)"
    print(f"{label}: structure={r['structure']:.2f}  readings={len(r['readings'])}  {things}")
    print(f"    note: {r['note']}")


def main(argv: list[str] | None = None) -> int:
    """``welkin-seer``: read one stored frame, one image file, or run the negative
    control over a directory of images (lens cap, ceiling, flat sky)."""
    ap = argparse.ArgumentParser(description=main.__doc__)
    ap.add_argument("--data", default="data")
    ap.add_argument("--model", default=MODEL)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--frame-id", type=int, help="a row in the frames table")
    g.add_argument("--image", help="an image file, read directly (not stored)")
    g.add_argument("--control", help="directory of images that should read as nothing")
    args = ap.parse_args(argv)

    client = make_client()
    if args.frame_id is not None:
        con = db.connect(args.data)
        r = see(con, Path(args.data), args.frame_id, client, model=args.model)
        _print_reading(f"frame {args.frame_id}", r)
        return 0 if r["status"] == "ok" else 1

    if args.image:
        try:
            r = read_sky(client, args.image, model=args.model)
        except Exception as exc:  # noqa: BLE001
            print(f"the seer could not look: {type(exc).__name__}: {exc}")
            return 1
        _print_reading(Path(args.image).name, r)
        print(f"    cost: ${cost_usd(r):.4f}")
        return 0

    files = sorted(p for p in Path(args.control).iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    empty = errors = 0
    n_readings: list[int] = []
    structures: list[float] = []
    spent = 0.0
    for p in files:
        try:
            r = read_sky(client, p, model=args.model)
        except Exception as exc:  # noqa: BLE001
            errors += 1
            print(f"{p.name}: could not look ({type(exc).__name__}: {exc})")
            continue
        spent += cost_usd(r)
        n_readings.append(len(r["readings"]))
        structures.append(r["structure"])
        empty += not r["readings"]
        _print_reading(p.name, r)
    ok = len(n_readings)
    if ok:
        print(
            f"\ncontrol n={ok} errors={errors}: empty={empty}/{ok} ({100 * empty / ok:.0f}%)  "
            f"mean readings={sum(n_readings) / ok:.2f}  mean structure={sum(structures) / ok:.2f}  spent=${spent:.2f}"
        )
        print("prototype reference on Commons pools: flat sky 40% empty / 1.07 / 0.15; clouds 0% / 3.45 / 0.50")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
