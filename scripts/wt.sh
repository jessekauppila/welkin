#!/usr/bin/env bash
# One sibling worktree per feature. See CLAUDE.md "Branches".
# Ported from ~/GitHub/the-sunset-webcam-map/scripts/wt.sh at fd9cd05b0, 2026-09-18,
# without the node_modules / ML cache symlinks and .vercel copy (Welkin has neither).
#
#   scripts/wt.sh new <branch> [base]   create worktree + its own .venv + .env copy
#                                       (+ cmux workspace when run inside cmux)
#   scripts/wt.sh rm  <branch>          remove the worktree (branch is kept)
#   scripts/wt.sh ls                    list worktrees
#
# Worktrees live BESIDE the repo, never inside it:
#   ~/GitHub/welkin.worktrees/<branch-with-slashes-as-dashes>/
set -euo pipefail

ROOT=$(git -C "$(dirname "$0")/.." rev-parse --show-toplevel)
# From inside a worktree, --show-toplevel is the worktree; the main checkout is
# the parent of the shared .git dir.
ROOT=$(cd "$(git -C "$ROOT" rev-parse --git-common-dir)/.." && pwd)
WT_DIR="${ROOT}.worktrees"

slug_of() { printf '%s' "$1" | tr '/' '-'; }

cmd=${1:-}
case "$cmd" in
  new)
    branch=${2:-}
    [ -n "$branch" ] || { echo "usage: scripts/wt.sh new <branch> [base]" >&2; exit 1; }
    base=${3:-origin/main}
    path="$WT_DIR/$(slug_of "$branch")"
    [ ! -e "$path" ] || { echo "already exists: $path" >&2; exit 1; }
    mkdir -p "$WT_DIR"
    git -C "$ROOT" fetch -q origin

    if git -C "$ROOT" show-ref --verify -q "refs/heads/$branch"; then
      git -C "$ROOT" worktree add "$path" "$branch"
    elif git -C "$ROOT" show-ref --verify -q "refs/remotes/origin/$branch"; then
      git -C "$ROOT" worktree add --track -b "$branch" "$path" "origin/$branch"
    else
      git -C "$ROOT" worktree add -b "$branch" "$path" "$base"
    fi

    [ -f "$ROOT/.env" ] && cp "$ROOT/.env" "$path/.env"

    # A venv is not shared: its editable install points at one checkout's src/.
    python3.11 -m venv "$path/.venv"
    "$path/.venv/bin/pip" install -q -e "$path[dev]"

    # cmux prints "OK workspace:N"; rename by ref — a bare rename-workspace
    # hits whichever workspace is focused, i.e. the one you ran this from.
    if [ -n "${CMUX_SOCKET_PATH:-}" ] && command -v cmux >/dev/null; then
      ws=$(CMUX_QUIET=1 cmux new-workspace --cwd "$path" | awk '{print $2}')
      [ -n "$ws" ] && CMUX_QUIET=1 cmux rename-workspace --workspace "$ws" "$branch" >/dev/null
    fi
    echo "$path"
    ;;
  rm)
    branch=${2:-}
    [ -n "$branch" ] || { echo "usage: scripts/wt.sh rm <branch>" >&2; exit 1; }
    path="$WT_DIR/$(slug_of "$branch")"
    [ -d "$path" ] || { echo "no worktree at $path" >&2; exit 1; }
    if [ -n "$(git -C "$path" status --porcelain)" ]; then
      echo "worktree is dirty, not removing: $path" >&2; exit 1
    fi
    if [ -z "$(git -C "$ROOT" branch -r --contains "$branch" 2>/dev/null)" ]; then
      echo "branch $branch has commits not on any remote — push first" >&2; exit 1
    fi
    # data/ is gitignored, so neither check above sees it and `worktree remove`
    # deletes it silently. It holds frames and human responses: move them first.
    if [ -n "$(find "$path/data" -type f 2>/dev/null | head -1)" ]; then
      echo "$path/data/ has files (frames or responses); move them, then retry" >&2; exit 1
    fi
    git -C "$ROOT" worktree remove "$path"
    git -C "$ROOT" worktree prune
    echo "removed $path (branch $branch kept; delete it after the PR merges)"
    ;;
  ls)
    git -C "$ROOT" worktree list
    ;;
  *)
    sed -n '2,12p' "$0" >&2; exit 1
    ;;
esac
