---
title: A stacked PR merges into its base, not main
date: 2026-09-18
kind: workflow
status: active
applies_to: any PR whose base branch is not main
---

# A stacked PR merges into its base, not main

## What happened

Milestone 1 went up as a stack of three PRs, each based on the one before:

| PR | head → base | merged (UTC) |
|---|---|---|
| #8 | `feat/ingest` → `main` | 2026-09-19 01:48:41 |
| #9 | `feat/picker-seer` → `feat/ingest` | 2026-09-19 01:50:24 |
| #10 | `feat/store-station` → `feat/picker-seer` | 2026-09-19 02:01:30 |

#8 landed on `main`. #9 merged 103 seconds later, into `feat/ingest`, a branch that had
already done its job and was going nowhere. #10 merged into `feat/picker-seer`. GitHub
showed all three as MERGED. Only the ingest had reached `main`; the picker, the seer, the
store, the station, the rubric and the bar had not.

The ancestry check caught it, and #11 (`feat/picker-seer` → `main`, merged 02:11:39) was
opened only to land #9 and #10. Nothing was lost because the gap was found within the
hour, before anyone reported Milestone 1 as shipped. Afterwards `feat/ingest` still
pointed at `0fb231b`, #9's merge commit. Its tree is identical to `12f93e7` on `main`, but
the commit itself is on no path to `main`, so the branch was left for a human to delete.

This is sunset's shape 3 ("a stacked pull request merged into a corpse", PR #148, 21
seconds) and its stacked-branch lesson, arriving in a repo one day old. Having those
lessons in `~/sky/docs/overlap.md` did not stop it. They were written down as reading,
and the stack was built anyway.

## The rule

1. **Do not stack PRs in Welkin.** If work depends on an unmerged PR, wait for it to land,
   or fold the dependent work into the same PR. A bigger PR that lands is better than
   three small ones where two go nowhere.
2. **MERGED is not enough when `baseRefName` is not `main`.** `gh pr view <n> --json
   state,baseRefName` shows both. A MERGED PR with any other base has merged into a
   branch, and whether that reached `main` is a separate question.
3. **Before saying anything shipped:** `git fetch origin && git merge-base --is-ancestor
   <sha> origin/main`. It is the only check that answers the question.
4. **Before deleting a finished branch**, check its tip the same way. A tip that is not on
   `main` means either unlanded work or, as with `feat/ingest`, a stray merge commit.
   Tell them apart with `git log --oneline origin/main..origin/<branch>` and a tree diff,
   and have a person decide.

## Where it applies in Welkin

CLAUDE.md "Branches" carries the no-stacking rule. Sunset's two lessons it repeats are
copied here: `2026-09-07-merged-is-a-claim-about-a-branch.md` (shape 3) and
`2026-06-08-stacked-branch-missing-merged-dependency.md`.
