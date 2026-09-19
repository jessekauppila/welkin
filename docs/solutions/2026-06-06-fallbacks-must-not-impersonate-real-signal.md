<!-- Copied near-verbatim into Welkin, 2026-09-18.
     origin: ~/GitHub/the-sunset-webcam-map/docs/solutions/2026-06-06-fallbacks-must-not-impersonate-real-signal.md
     commit: 47f67d595
     Do not edit here; fix at the origin and re-copy. -->

# Fallbacks must not impersonate the real signal

**Date:** 2026-06-06
**Area:** ML scoring / data integrity

## The trap

`scoreImage` had a "fallback": when the ONNX model failed to load, it scored the
image from **webcam popularity + a default manual rating** (`baselineRaw`) and
wrote that guess into `ai_regression_score` / `ai_rating` — the SAME columns the
real model writes. The mode selector even defaulted to it
(`AI_SCORING_MODE_DEFAULT = 'baseline'`), so a missing env var silently
fabricated scores. Two writers (the Windy cron and `customBackfill`) shipped the
guess to the DB; the leaderboard ranked it as if it were real. Result: broken
infrastructure looked perfectly healthy, and "we think it's working but it isn't"
recurred for weeks.

## The rule

**A fallback that writes a plausible value into the same column as the real
signal is worse than no fallback — it is undetectable.** A heuristic that never
reads the input it claims to score produces silent, confidently-wrong data.

Fallbacks must be either:
1. **Absent** — write `NULL`, increment a counter, log loudly. Honest absence is
   recoverable (a `WHERE col IS NULL` finder reclaims it); a fake number is not.
2. **A distinct, clearly-labeled channel** — never the column reserved for the
   real signal.

And never default a mode selector to the fake path.

## What we did

Deleted `baselineRaw` + the `AI_SCORING_MODE` knob; `scoreImage` now returns
`pathTaken: 'unscored'` with `null` scores on any ONNX failure; all writers skip
the write on `'unscored'`; a migration nulled the existing junk so the real model
reclaims it. A second-order effect: the cleanup cron deleted by `ai_rating` while
the leaderboard ranks by `llm_quality`, so nulling `ai_rating` widened the
deletion net — we added an `AND llm_quality IS NULL` retention guard so
Claude-scored frames are never deleted. See
`docs/superpowers/specs/2026-06-06-remove-metadata-heuristic-fallback-design.md`.
