# Lessons

Hard-won findings, one per file, in the shared format the sibling projects use. Read
these before proposing a scorer, a metric, or a control. Files with an origin header
are copies; fix them at the origin and re-copy.

| file | one line |
|---|---|
| `2026-06-06-fallbacks-must-not-impersonate-real-signal.md` | A fallback that writes a plausible value into the real column is worse than none. Write NULL and log. (sunset) |
| `2026-09-17-an-instrument-can-manufacture-the-signal-it-measures.md` | Show a detector something with nothing to detect. If it fires, it measures the instrument. (figment) |
| `2026-09-18-a-gap-at-the-top-of-a-selected-set-is-not-an-effect.md` | Never measure a feature on items selected by it. (figment) |
| `2026-09-18-a-category-label-is-not-a-control.md` | A control set is what is in the images, not what they are tagged. Look at the top scorers. (welkin) |
| `2026-09-18-an-llm-judge-of-agreement-has-a-chance-floor.md` | Do not score human-vs-AI agreement with an LLM judge. Store both, compare by hand. (cloud prototype) |

Workflow lessons (see CLAUDE.md "Branches"):

| file | one line |
|---|---|
| `2026-06-08-stacked-branch-missing-merged-dependency.md` | A branch cut before its dependency landed does not have it; green tests can hide the broken import. (sunset) |
| `2026-06-09-git-worktrees-for-js-and-python-repos.md` | Making worktrees cheap enough to use. Welkin differs on Python: each worktree gets its own `.venv`, because a shared editable install runs the `welkin-*` scripts from one checkout's `src/`. (sunset) |
| `2026-09-18-a-stacked-pr-merges-into-its-base-not-main.md` | #9 and #10 merged into their parent branches and read MERGED; #11 was needed to land them. Do not stack. (welkin) |
| `2026-06-13-integrate-frequently-dont-let-branches-sprawl.md` | Land small increments the same day; long-lived branches orphan fixes. Necessary, not sufficient. (sunset) |
| `2026-09-07-merged-is-a-claim-about-a-branch.md` | MERGED describes a branch. Only `git merge-base --is-ancestor <sha> origin/main` says it reached main. (sunset) |
