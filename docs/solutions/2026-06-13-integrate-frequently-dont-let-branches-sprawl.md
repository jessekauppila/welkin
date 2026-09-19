<!-- Copied near-verbatim into Welkin, 2026-09-18.
     origin: ~/GitHub/the-sunset-webcam-map/docs/solutions/best-practices/integrate-frequently-dont-let-branches-sprawl.md
     commit: 64dfe255e
     Paths in the body are sunset's (npm, vercel, the kiosk, its docs/); the rules carry over.
     Do not edit here; fix at the origin and re-copy. -->

# Integrate frequently — long-lived branches sprawl, orphan, and regress

**Date:** 2026-06-13
**Area:** Workflow / git hygiene (both repos)

## The trap

A genuinely productive multi-thread session (device bringup + a prototype round-trip + a
cleanup) accumulated work across **~38 branches and 5 worktrees**, with **18+ commits
unpushed** and several real fixes stranded in unmerged branches. It *felt* fine — each branch
made sense in isolation. The damage was invisible until it bit:

- A **fixed bug regressed** because its fix sat in an unmerged branch (`hotfix/marker-positioning`)
  while the buggy feature merged to `main` (markers stacked off-globe). See
  `dont-set-inline-position-on-mapbox-markers.md`.
- A whole feature (the **QR-label generator**) was nearly rebuilt from scratch because it was
  orphaned off `main` — "wait, didn't we already build this?"
- The session ended owing a large **consolidation tax**: audit + land + prune **27 branches**,
  remove worktrees, reconcile a diverged `main`.

## The rule

**Pull work into `main` frequently.** Land and push small, self-contained increments as you go,
rather than letting long-lived branches accumulate. Run *periodic* "pull stuff in" passes — not
one big cleanup at the end of an arc. The longer work sits off `main`, the more it drifts,
orphans, and regresses, and the more `main` stops being a trustworthy single source of truth.

## Why it matters

Sprawl doesn't announce itself; the cost compounds silently (regressions, duplicated work, merge
debt) until a consolidation pass is *forced*. Frequent integration keeps the answer to "did we
already fix/build this?" a one-line `git log main` away.

## How to apply

- After a fix or small feature **lands and passes**, merge it to `main` + push **the same day**.
- Treat **learnings as land-immediately** — an orphaned learning can't prevent the regression it
  documents (the marker fix proved this twice).
- Prefer a few short integration checkpoints over a heroic end-of-arc tidy.
- When you *do* spin up parallel worktrees, set a reminder to reconcile them back soon — a
  worktree is a loan against `main`, not a parking lot.

## Necessary, but not sufficient (added 2026-09-07)

Landing fast is not the same as landing. This doc treats orphaning as a function
of *time*, and that reading is incomplete: on 2026-09-06 a stacked PR orphaned
five files in **21 seconds**, and on 2026-09-07 a commit was orphaned within the
hour, both on branches doing exactly what this doc asks. Speed narrows the window
for drift; it does nothing about work that never reached `main` at all.

The complement is to verify rather than infer — `git merge-base --is-ancestor
<sha> origin/main` is the only signal that means "on main". See
`docs/solutions/workflow-issues/merged-is-a-claim-about-a-branch.md`.
