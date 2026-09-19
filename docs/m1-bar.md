# Milestone 1: the pre-registered bar

Written before the first sitting, 2026-09-18. **Do not change the numbers after the
first afternoon.** If they turn out wrong, write that down here and set a new bar for
milestone 2. The sunset project was saved from three false wins by this habit.

## What milestone 1 is testing

Whether freeze-and-draw is a game people want to play. Not whether the picker is good,
not whether the seer is clever, not whether the drawings make a dataset. Those come
later and each gets its own bar.

## What it is *not* testing, honestly

There is no venue and no children in M1 (decisions-log, 2026-09-18). The people at the
station will be Jesse and any adults present at his own sky. So M1 is a **rehearsal of
the instrument**: does the loop run for an afternoon, do the numbers below get recorded
correctly, does anything about the game feel wrong to an adult. The pass line below is
kept because rehearsals need one too, but a pass here is not evidence about children.

## The two numbers

Both are computed by `welkin-report` from `station_events` and `responses`, per rubric
version. A *sitting* starts when the station offers a frame to someone (an `offered`
event). It is the denominator whether or not they touch the screen.

1. **Commit rate.** Fraction of started sittings with at least one committed response.
   Measures: did the frame invite a drawing at all.
2. **Again rate.** Fraction of started sittings with two or more committed responses.
   Measures: having seen the seer's reading, did they want another round. This is the
   one that says "game", not "survey".

## The bar (proposed; Jesse confirms before the first sitting)

| number | pass | wash | fail |
|---|---|---|---|
| commit rate | ≥ 0.70 | 0.50 – 0.70 | < 0.50 |
| again rate | ≥ 0.40 | 0.25 – 0.40 | < 0.25 |

Minimum sample before reading either: **20 started sittings** over at least **2
afternoons**, so one good sky does not decide it. Under 20, report the numbers and say
"not enough".

Why these values: the cloud prototype's one labelling session committed on 6 of the 20
images offered (0.30) with a free-text box and no drawing, no seer reveal, and the
prototype's author as the only player. Drawing and a reveal are the two additions M1
is betting on. If they do not lift commit above 0.70 and produce a second round in 4 of
10 sittings among willing adults, the bet has not paid and the design changes before
any child sees it.

## What would make the numbers lie

- **A bad frame.** If the picker freezes a blank sky, nobody draws, and the game is
  blamed for the picker. Log the freeze's texture score with each sitting (the station
  does) and report commit rate on frames above and below the control ceiling separately
  once the control exists (`docs/controls.md`).
- **The operator playing.** Sittings with `rater = 'jesse'` are reported, but the
  headline number is sittings by other people. In M1 that may be nobody; say so.
- **A dead seer.** If the seer errors, the reveal shows "the seer could not look" and
  the again rate measures a different game. Report the error count beside the rates.
- **Changing the rubric mid-run.** Then there are two `rubric_version`s and two rows.
  Never add them.

## What "done" looks like

Two afternoons, twenty sittings, the report printed, and one paragraph written under
this line saying what happened and what changes for M2.

---

_Results: (not yet run)_
