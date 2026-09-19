<!-- Copied near-verbatim into Welkin, 2026-09-18.
     origin: ~/GitHub/the-sunset-webcam-map/docs/solutions/developer-experience/git-worktrees-for-js-and-python-repos.md
     commit: fa5342993
     Paths in the body are sunset's (npm, vercel, the kiosk, its docs/); the rules carry over.
     Do not edit here; fix at the origin and re-copy. -->

---
title: Running isolated git worktrees that can actually run the test suite (JS/TS and Python)
date: 2026-06-09
category: docs/solutions/developer-experience
module: dev-workflow
problem_type: developer_experience
component: development_workflow
severity: low
applies_when:
  - Doing parallel/stacked feature work in git worktrees to keep branches isolated
  - A fresh worktree can't run the test suite because deps aren't present (node_modules) or a stacked dependency isn't merged yet
tags: [git, worktrees, node_modules, vitest, pytest, monorepo, parallel-work]
---

# Running isolated git worktrees that can actually run the test suite

## Context

Stacked/parallel feature work across two repos (a Next.js app + a Python firmware repo) used many `git worktree`s for isolation. A fresh worktree shares the `.git` dir but **not** the working files' siblings — notably `node_modules`. So a JS/TS worktree can't run `vitest`/`tsc` until its dependencies exist, and re-installing per worktree is slow. There are a couple of small gotchas worth writing down.

## Guidance

**JS/TS repos — symlink `node_modules` into the worktree** so it reuses the main checkout's installed deps:
```bash
git worktree add ~/repo-feature -b feat/x origin/main
ln -s ~/main-repo/node_modules ~/repo-feature/node_modules
cd ~/repo-feature && npx vitest run <path>   # works immediately
```
Caveats:
- If the branch **adds a new dependency**, run `npm install <pkg>` in the worktree. Observed 2026-09-04 (npm 10): npm does **not** install through the symlink — it replaces the worktree's `node_modules` symlink with a real, full install (~20 s, 1,300 packages) and leaves the main checkout's tree without the package. That is fine for the branch (package.json/lock changes stay on it), but after the PR merges the main checkout needs its own `npm install` before it can build or test that code. Check with `ls -ld node_modules` in the worktree if unsure which state you are in.
- `git worktree remove --force` removes the symlink (a dir entry), **not** the real `node_modules` it points to.

**Python repos — usually nothing needed** if the package is installed editable (`pip install -e`) into a shared interpreter, since `pythonpath = ["src"]` (pytest) resolves from the worktree's own `src/`. Just run `python3 -m pytest` in the worktree.

**Stacked dependencies — verify the import chain before you trust the worktree.** A branch cut off `main` before a dependency PR merged won't have it; the unit suite can stay green while a launcher/entrypoint import is broken. Before deploying/merging a stacked branch, run an explicit import-chain smoke check and `git merge-base --is-ancestor origin/main <branch>` — see `../integration-issues/stacked-branch-missing-merged-dependency.md`.

**Clean up.** Worktrees accumulate. List with `git worktree list` (both repos), remove the ones whose branches are pushed with `git worktree remove --force <path>`, then `git worktree prune`. Don't remove a worktree another session is actively using (its branch shows as `+` / checked-out elsewhere).

## Why This Matters

Without the `node_modules` symlink, each TS worktree needs a full `npm install` (minutes) before any test runs — enough friction to discourage isolation entirely. The symlink makes worktrees cheap, which keeps parallel/stacked work clean (one branch per worktree, no cross-contamination) instead of juggling branches in one checkout.

## When to Apply

- Any multi-branch or stacked work where you want isolated checkouts that can run tests/lint immediately.
- Especially in a TS repo, where the missing-`node_modules` wall hits on the first `vitest`/`tsc` invocation.

## Examples

- TS: `ln -s ~/GitHub/the-sunset-webcam-map/node_modules ~/GitHub/swm-qr-label/node_modules` → `npx vitest run` works at once; adding `qrcode` later needed a one-time `npm install` in a sibling worktree.
- Python: `git worktree add ~/GitHub/scf-supervisor -b feat/x origin/feat/base` → `python3 -m pytest` runs directly (editable install + `pythonpath=["src"]`).

## Related
- `../integration-issues/stacked-branch-missing-merged-dependency.md` — the import-chain / ancestry check for stacked branches.
- [[build-ahead-of-validation]] — when stacking branches, validate the foundation before piling on.
