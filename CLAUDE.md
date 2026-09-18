# Welkin

Shared sky-watching system; see `README.md`. Created 2026-09-18.

## Read first

- `~/sky/docs/unified-brief.md` for the plan and the open questions.
- `~/sky/docs/decisions-log.md` before proposing anything already decided.
- `~/sky/docs/overlap.md` §4 for lessons the sibling projects already paid for. Do not
  re-learn them: negative controls before trusting a detector, never measure a feature on a
  set selected by it, retest agreement is the fit ceiling, LLM judges have a chance floor.

## Sibling repos

`~/sky/repos/{sunset,sunset-firmware,figment,cloud}` are read-only symlinks to live projects.
Reuse from them by copying with a header that records origin path, commit SHA and date, the
way `figment/labelkit/` does. Never edit them from here.

## Rules

- Frames and human responses are data, not source. They live under `data/` (gitignored) or
  in the store, never committed.
- Every scorer gets a negative control (flat sky, lens cap) before its output is trusted.
- The LLM may be the AI's *voice* in the game. Whether it may also be the *score* is open
  question 8 in the brief; do not decide it by accident.
- Children's drawings: consent and release are open question 11. Until decided, exhibit
  responses stay local and are not part of any dataset.
- Cloud frames from the Pi come to this repo's ingest, never to the sunset snapshot route.
