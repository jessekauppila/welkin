# Welkin

A distributed network of cameras pointed at the sky, watching continuously. Machine-learning
models rank what they see: the beauty of a sunset, the suggestiveness of a cloud. People
respond by rating, naming, drawing. Those responses train the models, which changes what the
network chooses to show, which changes what people respond to.

The through-line: a machine looks at the sky, forms an opinion, and a human corrects it.

Welkin is the shared system under two existing projects:

- **Sunrise / Sunset** (`~/GitHub/the-sunset-webcam-map`), the web face and the sunset rater.
- **Figment** (`~/GitHub/figment`), generative LEGO sculpture scored for pareidolia.

and the home of the new one:

- **Freeze and draw**, an exhibit where children draw on a frozen live cloud and name what
  they see, and the AI plays alongside.

## Where things are

Planning and reference docs live in the `~/sky` workspace, not here:

- `~/sky/docs/unified-brief.md`: the project brief, build order, and open questions.
- `~/sky/docs/decisions-log.md`: decisions as they are made, with reasoning.
- `~/sky/docs/inventory-*.md` and `overlap.md`: what the sibling repos contain and share.

The sibling repos are reachable read-only as `~/sky/repos/{sunset,sunset-firmware,figment,cloud}`.

## Milestone 1

One Pi Zero 2 W camera pointed at the venue's sky, one frame every 5 to 10 minutes, posting
to an ingest in this repo. One touch screen: freeze a frame, draw on it, name it, then see
what the AI saw. A response store. A pre-registered bar for "did they enjoy it."

## Run

```bash
python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

**Frame ingest** (issue #1). Run it on a laptop on the camera's LAN:

```bash
.venv/bin/welkin-ingest --port 8000
```

It prints the URL to put in the camera's `welkin` sink. Open `/health` to see
the last frame per camera, and `/frames/<camera_id>/latest.jpg` to see the
frame itself. Frames go to `data/frames/`, with one row each in
`data/welkin.sqlite`. Pass `--token` or set `WELKIN_INGEST_TOKEN` to require a
bearer token. The camera side is `sunset-cam-firmware`'s capture profiles.

## Status

- Frame ingest: built (#1).
- Response store, picker, seer, station, rubric: open, milestone "M1: Freeze and draw".
