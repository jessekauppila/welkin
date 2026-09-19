<!-- Copied near-verbatim into Welkin, 2026-09-18.
     origin: ~/GitHub/the-sunset-webcam-map/docs/solutions/workflow-issues/merged-is-a-claim-about-a-branch.md
     commit: 456aa3534
     Paths in the body are sunset's (npm, vercel, the kiosk, its docs/); the rules carry over.
     Do not edit here; fix at the origin and re-copy. -->

---
title: Merged is a claim about a branch, not about main
date: 2026-09-07
category: docs/solutions/workflow-issues
module: dev-workflow
problem_type: workflow_issue
component: development_workflow
severity: high
root_cause: missing_workflow_step
resolution_type: workflow_improvement
applies_when:
  - "About to report work as shipped, merged, live, or landed"
  - "About to push a follow-up commit to a branch that already has a PR"
  - "Merging a stacked PR whose base branch may itself have merged already"
  - "Two branches are ready at once and each is green on its own"
  - "Cutting a branch that depends on a symbol another in-flight PR adds"
  - "Extracting or moving code into a NEW file on a branch cut before other work landed in that same area"
symptoms:
  - "A pull request reads MERGED while a later commit on the same head branch has never reached main"
  - "Two branches with zero overlapping files break main on merge"
  - "A stacked pull request reads MERGED but its files are absent from main"
  - "Green tests on a branch hide a break that only the build or an untested entrypoint reveals"
  - "A file that is new on a branch merges with no conflict and silently reverts a feature already on main"
  - "Someone asks where work went after it was reported as shipped"
related_components:
  - tooling
  - testing_framework
tags: [git, github, pull-requests, merge-verification, stacked-prs, worktrees, ancestry]
---

# Merged is a claim about a branch, not about main

## Context

Six incidents across three months, in two repos, all from one mistake: treating
a cheap git or GitHub signal as evidence that code reached `main`.

**Shape 1 — a branch cut before its dependency landed** (2026-06-08, firmware).
A branch referenced `make_orientation_reader`, which only reached `main` in a
later PR. The suite was green because the broken import lived in a launcher
script no test imports. Deep dive:
`docs/solutions/integration-issues/stacked-branch-missing-merged-dependency.md`.

**Shape 2 — the merge result was never built** (2026-09-06). PR #147 made
`kiosk_deploys.deployed_at` nullable, changing `DeployRow.deployedAt` to
`string | null`. PR #149 added a script passing that value to `Date.parse`. The
two shared **no files**, so the merge-desk audit — "empty file intersection,
merge order does not matter" — was true and useless. `main` stopped compiling
the moment both landed, and every deploy failed until #150. **Tests all passed;
only `npm run build` caught it.**

**Shape 3 — a stacked PR merged into a corpse** (2026-09-06). PR #148 was based
on `feat/one-studio-takes`. That base merged to `main` at 23:50:24Z; #148 merged
into the base 21 seconds later, at 23:50:45Z. GitHub showed #148 as merged, its
branch looked finished, and its five files never reached `main`.

**Shape 4 — a PR merged out from under an in-flight branch** (2026-09-06
evening, and again 2026-09-07). PR #155 was merged while commits were still
being pushed to its branch, so only its first commit reached `main` and the
commit that fixed the reported bug was left behind; recovered as #159. The
identical thing happened the next day: PR #168 merged at 21:10:59Z carrying only
its first commit, and a second commit was pushed to that same branch at
21:42:50Z, thirty-two minutes after the branch had closed. GitHub still read
MERGED and warned about nothing. The work was reported as shipped while it sat
orphaned. Jesse caught it: *"I already merged that PR an hour ago, where did
this go?"* Recovered as #169.

**Shape 5 — a new file auto-merged clean and reverted a merged feature** (2026-09-16).
`feat/glass-mirror` was cut from `c1bf14cf6`, before PR #224 merged the rendezvous. The
branch extracted the advance route's draw into a new file, `app/lib/solo/advance.ts` — a
faithful extraction of the *pre-rendezvous* body.

Two halves, and only one of them was loud. `app/api/kiosk/solo/advance/route.ts` existed
on both sides and conflicted, so git stopped and asked; the tempting resolution, "take the
branch's version", was the pre-rendezvous route. `advance.ts` was **new on the branch**, so
it had nothing to conflict with and merged in silence. Its `drawSlot` never called
`version.fitNext`, had no grow branch, used `dwellMs` where `main` used `dwellMsFor`, and
called `commitAdvance` with eight arguments — and on `main` parameters nine and ten are
`peakAtMs: number | null = null, rendezvous = false`. **The defaults made it compile,
build, lint and pass the whole suite while writing `peak_at_ms = null, rendezvous = false`
on every draw.**

The PR inverted the severity. Before it, that code was one of two draw paths. After it the
kiosk stops posting and the projection route's `advanceIfDue` is the *only* path a solo2
draw takes, so the rendezvous would not have degraded — it would have stopped, with
nothing failing anywhere. Caught by a second session that read the merge result instead of
the branches; fixed by re-extracting from `main`'s current body, with `main`'s 23
rendezvous route tests kept byte-identical as the guard.

**The unifying root cause.** Every cheap signal — the PR's state, "the branch
exists", "the push succeeded", "tests are green on the branch" — is a statement
about a **branch**. None is a statement about `main`. They are not merely
unreliable; they answer a different question, so reading them more carefully
does not help. A merged PR is a *snapshot of a branch at merge time*, not a live
channel: push to that branch afterwards and no UI anywhere says a word.

This repo's conventions make the collision routine rather than exceptional. Work
happens in one sibling worktree per feature while the main checkout serves as the
merge desk, and Jesse merges PRs from parallel sessions while agent sessions are
still working on those same branches. A PR merging mid-task is a normal Tuesday.

## Guidance

**1. The only signal that means "this is on main" is an ancestry check.**

```bash
git fetch origin main --quiet
git merge-base --is-ancestor <sha> origin/main && echo "ON MAIN" || echo "NOT ON MAIN"
```

Takes a commit SHA, a local branch name, or `origin/<branch>`. The fetch is not
optional: a stale `origin/main` answers confidently and wrongly.

Note this command reads in both directions, and the two readings are different
questions. `--is-ancestor origin/main <branch>` asks *does my branch contain
main* (shape 1). `--is-ancestor <sha> origin/main` asks *did my work reach main*
(shapes 2 through 4). The second is the general rule.

**2. Before pushing a follow-up to a branch that already has a PR, check the PR
is still open.**

```bash
gh pr view <n> --json state,baseRefName,headRefOid,mergeCommit
```

- `state` is `MERGED` — that branch is **closed for business**. New work needs a
  new branch and a new PR. Pushing to it succeeds and accomplishes nothing.
- `baseRefName` is not `main` — this was stacked. MERGED means it merged into its
  *base*, which may itself never have reached `main`. Ancestry-check
  `mergeCommit.oid` before believing it.
- `headRefOid` should equal your local tip. If the PR merged before your last
  commit, it will not, and that difference is the orphaned work.

**3. Build the merge RESULT, not the branch.** Green tests on a branch say
nothing about that branch merged into current `main`. Type coupling, changed
signatures, and renamed exports break across branches with no file overlap at
all.

```bash
git fetch origin main --quiet
git switch -c merge-check/<branch> origin/main
git merge --no-commit --no-ff <branch>     # a REAL merge
npm run test && npm run build              # BUILD, not just test
git merge --abort; git switch -; git branch -D merge-check/<branch>
```

`npm run build` is not optional here. In shape 2 the whole suite passed and only
the type-check in the build caught it.

**Do not** substitute `git merge-tree ... | grep '^<<<<<<<'`. Old-style
`merge-tree` output is diff-prefixed, so conflict markers arrive as `+<<<<<<<`
and the anchored grep reports zero conflicts while a real conflict exists.
Likewise `git diff A...B` between two tips is not a merge preview and shows
phantom deletions when the merge base is old.

**4. Recovering orphaned work.**

```bash
git fetch origin --quiet
git switch -c <fresh-branch> <orphaned-sha>
git merge --no-edit origin/main
npm run test && npm run build              # against the MERGE RESULT
git push -u origin <fresh-branch>
gh pr create --base main --title "..." --body "..."
git push origin --delete <stale-branch>    # so nobody pushes into a dead branch again
```

**5. Verify the claim, not just the action.** This is as much a reporting failure
as a git one. Any sentence containing *merged*, *shipped*, *live*, *on main*, or
*deployed* must be backed by an ancestry check run **after** the last relevant
push — never by a status field read earlier in the session.

**6. A file that is new on your branch is the one the merge cannot check.**

Shapes 2 and 5 both live in the gap between text and meaning, but shape 5 survives the
merge-result build as well: an extraction that lost a feature still type-checks when the
caller's newer parameters carry defaults. Nothing in git, the suite, or the build is
asking whether your new file still matches the code it was extracted from — the merge
cannot, because there is no other side to compare it against.

Before extracting or moving code on a branch cut before other work in the same area:

```bash
git fetch origin main --quiet
git log --oneline $(git merge-base HEAD origin/main)..origin/main -- <the area>
```

If that prints anything, diff your extraction against the **current** source rather than
the one you copied, and keep the original caller's tests unchanged as the guard. Passing
them against your version is what proves the move was faithful; finding yourself editing
them to fit is the signal that it was not. Optional parameters with defaults are where a
lost feature hides — a call two arguments short is a compile error only until someone
gives those parameters defaults.

## Why This Matters

**The failure is silent by construction.** All six incidents produced zero
errors, zero warnings, and a green-looking UI. Nothing notifies you when you push
to a merged branch, nothing flags a stacked PR whose base is already gone,
nothing signals that two conflict-free branches are type-incompatible. The
failure surfaces later — in `main`, in a failed deploy, or when someone asks
where the work went.

**A broken `main` is not an inconvenience here.** The kiosk renders whatever
`main` built, and the show has a fixed date. On 2026-09-06 `main` broke twice in
one day and every deploy failed until a follow-up PR landed.

**It costs trust, which is worse than it costs time.** Reporting work as shipped
when it is orphaned means every future report has to be independently checked,
which erases the value of reporting at all.

**Landing fast is not the same as landing.** The existing advice to integrate
frequently
(`docs/solutions/best-practices/integrate-frequently-dont-let-branches-sprawl.md`)
treats orphaning as a function of *time*. It is not sufficient: shape 3 orphaned
five files in 21 seconds, and shape 4 in under an hour, on branches doing
everything that doc asks. Short-lived branches orphan work just as silently.

## When to Apply

These are deliberate checks at specific moments. Run reflexively at every git
command they become noise, and noise gets skipped.

**Ancestry check** — before *saying* work is merged, shipped, live, or on main,
every time without exception; when a session resumed or minutes of other work
passed and you are about to act on a PR state you read earlier; when a PR reads
MERGED but its base was another branch; before removing a worktree, since
`scripts/wt.sh rm` refuses on unpushed work but not on unmerged-to-main work.

**PR-state check** — before pushing to a branch that already has a PR, unless
you opened that PR seconds ago. Any elapsed time is enough in this repo.

**Merge-result build** — when anything landed on `main` after your branch was
cut and your branch touches shared types, exported signatures, or shared helpers.
File overlap is *not* the trigger; shape 2 had none. Also when merging a stacked
PR whose base has already merged.

**Extraction check** — when your branch adds a new file holding code moved out of an
existing one, and anything landed on `main` in that area since the branch was cut. This
is the one the merge is silent about by construction; see guidance 6.

**You may skip all four** only when you merged the PR yourself, watched the
merge commit land, and nothing has been pushed since.

## Examples

**The misleading signal against the authoritative one** (shape 4, 2026-09-07):

```
$ git push origin fix/solo2-arrival-segment      # succeeds
$ gh pr view 168 --json state
{"state":"MERGED"}
```

Both facts true, both irrelevant. #168 merged 32 minutes earlier at head
`c1ce49bfd`; the new commit `cc7af753c` was on nobody's path to `main`.

```
$ git fetch origin main --quiet
$ git merge-base --is-ancestor cc7af753c origin/main && echo "ON MAIN" || echo "NOT ON MAIN"
NOT ON MAIN
```

One command, run before speaking, catches it.

**Same word, two different situations** (shape 3): `gh pr view 148 --json state`
returns `MERGED`. Adding one field returns
`{"state":"MERGED","baseRefName":"feat/one-studio-takes"}` — it merged into a
branch that had itself already merged, so its commits went nowhere reachable.
The word MERGED is identical in both cases; only the ancestry check separates
them.

**Conflict-free is a fact about text** (shape 2): `git diff --name-only A...B`
showed no shared files, both branches were green, and the merge raised no
conflict. `git switch -c check origin/main && git merge --no-commit --no-ff B &&
npm run build` fails immediately on a type error. Conflict-freedom is a statement
about text; the build is a statement about meaning.

**Coverage is a floor, not a proof** (shape 1): the suite passed because the
missing import lived in a launcher script no test file imports.

## Related

- `docs/solutions/integration-issues/stacked-branch-missing-merged-dependency.md`
  — shape 1 in depth, and the other reading of the ancestry check.
- `docs/solutions/best-practices/integrate-frequently-dont-let-branches-sprawl.md`
  — why work must land quickly. Necessary but not sufficient; see above.
- `docs/solutions/workflow-issues/migrations-need-a-ledger.md` — the same move
  applied to migrations: a rule in a spec that kept being missed became a command
  that exits non-zero. The ancestry check wants the same promotion.
- `docs/solutions/developer-experience/git-worktrees-for-js-and-python-repos.md`
  — the worktree layout these incidents happen inside.
- `CONCEPTS.md`, the **Glass** entry, states the same epistemology one step
  downstream: *"On the Glass always means verified at the surface, never inferred
  from an upstream step succeeding."* Merged-versus-on-main is its upstream
  sibling — deployed is not on the glass, and merged is not on main.
