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

## Dev

`python3.11 -m venv .venv && .venv/bin/pip install -e ".[dev]"`, then `.venv/bin/pytest`.
Stdlib first: no web framework, SQLite in `data/welkin.sqlite`, paths relative to `data/`
(never URLs). Work in a worktree on a branch and open a PR; Jesse merges (see Branches).

## Branches: one sibling worktree per feature, the main checkout is the merge desk

Every feature gets its own **git worktree in a sibling directory**. The main checkout
(`~/GitHub/welkin`) stays on `main`: it is where PRs merge and where the real
`data/welkin.sqlite` lives. Nobody edits code there.

```bash
scripts/wt.sh new feat/picker-v1   # worktree + its own .venv + .env copy (+ cmux workspace inside cmux)
scripts/wt.sh ls
scripts/wt.sh rm feat/picker-v1    # after the PR merges (refuses if dirty, unpushed, or data/ has files)
```

Worktrees live at `~/GitHub/welkin.worktrees/<branch-slug>/`, **beside** the repo, never
inside it. Each has its own `.venv`: an editable install points at one checkout's `src/`,
so a venv cannot be shared. `data/` is gitignored and per checkout; a worktree starts with
none, and `wt.sh rm` will not delete one that holds frames or responses.
Caveats: `docs/solutions/2026-06-09-git-worktrees-for-js-and-python-repos.md`.

Still true in every worktree:

- **Verify the branch in the same command as any commit**
  (`[ "$(git rev-parse --abbrev-ref HEAD)" = <branch> ] && git commit ...`). Worktrees make
  a wrong-branch commit rare, not impossible.
- **Stage explicit paths**, never `git add -A`.
- **Push as soon as a commit exists** and land small increments the same day. Long-lived
  branches orphan fixes: `docs/solutions/2026-06-13-integrate-frequently-dont-let-branches-sprawl.md`.
- **"Merged" is a claim about a branch, not about `main`.** Before pushing a follow-up to a
  branch that already has a PR, check `gh pr view <n> --json state,baseRefName`: MERGED
  means that branch is closed and the work needs a new one. Before saying anything shipped,
  run `git fetch origin && git merge-base --is-ancestor <sha> origin/main`; it is the only
  check that answers the question.
  `docs/solutions/2026-09-07-merged-is-a-claim-about-a-branch.md`.
- **Do not stack PRs.** A PR based on another feature branch merges into that branch, not
  `main`, and GitHub still says MERGED. If work depends on an unmerged PR, wait for it to
  land or fold it into the same PR. It happened here with #8, #9, #10 and #11:
  `docs/solutions/2026-09-18-a-stacked-pr-merges-into-its-base-not-main.md`.
- **CI runs `pytest` on 3.11 and 3.13** for every PR (`.github/workflows/ci.yml`; checks
  `test (3.11)` and `test (3.13)`). Do not merge on red.
- **Branch protection on `main` is pending.** Welkin is a private repo on a free plan, and
  GitHub refuses protection there. Until it is on, nothing forces a PR to be up to date with
  `main` before it merges, so a green PR that fell behind has not been tested against what
  it merges into: merge `origin/main` into it and let CI run again before merging. When the
  repo goes public or Pro, require `test (3.11)` and `test (3.13)` with "up to date" on, no
  force pushes, no deletions. Protection settings are Jesse's to change.
- **Remove the worktree when the PR merges.** `git worktree list` should read like the list
  of open PRs. Delete the merged branch too (GitHub does it on merge).

### Multi-session coordination

Sessions do not share a working tree, so there is nothing to negotiate about the checkout.
What remains:

1. **Shared modules get a heads-up.** A change to `src/welkin/db.py` (the schema every tool
   writes through) gets a message (`ListAgents` + `SendMessage`) to any other live session.
2. **Cap active writing lanes at three.** Jesse merges every PR; more open worktrees than
   that means work outrunning review. Close idle sessions.

## Ideas and unbuilt work go to GitHub issues

**An idea that is not being built right now is an issue, not a doc**, and not a memory
entry: otherwise the backlog ends up spread across memory, loose `.md` files and specs with
no PR, and nothing has one list.

Three labels, and only these:

- `idea`: captured, not designed. One paragraph. Costs 30 seconds.
- `speced`: has a design doc and could be picked up as-is.
- `open-question`: a decision to make, not work to do.

The lifecycle, and where brainstorming fits:

1. An idea shows up mid-session → `gh issue create --label idea` immediately. Do **not**
   design it. The point is to stop losing it, not to start it.
2. It gets picked up → the `superpowers:brainstorming` skill runs *on that issue* and
   writes its spec to `docs/superpowers/specs/`.
3. Paste the spec path into the issue, relabel `speced`.
4. The PR body says `Closes #N`.

Issues do not replace specs, plans, or `~/sky/docs/`. The issue is the spine and carries the
stable id from first mention to merge. The brief's numbered open questions stay in
`~/sky/docs/unified-brief.md`; an `open-question` issue is for a decision that arises here.
Docs are what is *known*; `gh issue list` is what is *open*.

## Rules

- Frames and human responses are data, not source. They live under `data/` (gitignored) or
  in the store, never committed.
- Every scorer gets a negative control (flat sky, lens cap) before its output is trusted.
  Runs are recorded in `docs/controls.md`; `docs/solutions/` holds the lessons they taught.
- A machine opinion (score, reading) never shares a row with a human response. Every one
  records its instrument and version (`scorer_version`, `prompt_version`); never pool versions.
- A seer `status='error'` is shown as "the seer could not look", never as an empty reading.
- The LLM may be the AI's *voice* in the game. Whether it may also be the *score* is open
  question 8 in the brief; do not decide it by accident.
- Children's drawings: consent and release are open question 11. Until decided, exhibit
  responses stay local and are not part of any dataset.
- Cloud frames from the Pi come to this repo's ingest, never to the sunset snapshot route.
