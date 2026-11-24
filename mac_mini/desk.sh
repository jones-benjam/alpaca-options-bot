#!/bin/zsh
# Dionysus's live desk notes (the AI trader). Scheduled every 30 minutes by install_schedule.sh; when
# the market is closed it only checks and exits, so it is safe to run any time.
#
#   1. Read the bot's live data from the dashboard (no keys needed).
#   2. Have him write a two-to-four sentence note, number-checked like the diary.
#   3. Save memory/desk.json to GitHub; the /midas page shows it within minutes.
#   4. In the last run before the close, also save the day's market archive
#      (archive.py: option chains and Midas's view, for the strategy lab).
#
# The notes are commentary only: nothing here changes what the bot trades.
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

# Never save a file that still holds git conflict markers (it happened on Nov 24).
no_conflicts() {
  if git diff --cached -U0 | grep -qE '^\+(<<<<<<<|=======|>>>>>>>)'; then
    echo "Refusing to save: conflict markers found. Resetting to GitHub's copy; the next run redoes this."
    git reset -q --hard origin/main
    exit 1
  fi
}
# Put aside this Mac's own leftover edits (they are all rebuilt by the scripts),
# instead of git's --autostash, which leaves conflict markers in place without failing.
set_aside() {
  if ! git diff --quiet || ! git diff --cached --quiet; then
    git stash push -q -m "mac mini leftovers $(date '+%Y-%m-%d %H:%M')" && echo "Put aside local leftovers (git stash list)."
  fi
}

LOCK="${TMPDIR:-/tmp}/optbot-desk.lock"
mkdir "$LOCK" 2>/dev/null || exit 0      # the previous note is still being written
trap 'rmdir "$LOCK"' EXIT

if [ -f .env ]; then                     # only near the close; otherwise it does nothing
  python3 archive.py > "${TMPDIR:-/tmp}/optbot-archive.out" 2>&1 || echo "archive failed" >> "${TMPDIR:-/tmp}/optbot-archive.out"
  if [ -s "${TMPDIR:-/tmp}/optbot-archive.out" ]; then
    echo "=== $(date '+%Y-%m-%d %H:%M:%S') market archive ==="
    cat "${TMPDIR:-/tmp}/optbot-archive.out"
  fi
fi

python3 trader.py desk > "${TMPDIR:-/tmp}/optbot-desk.out" 2>&1
code=$?
if [ $code != 2 ]; then                  # 2: market closed or bot unreachable, nothing to say
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') desk note ==="
  cat "${TMPDIR:-/tmp}/optbot-desk.out"
  [ $code = 0 ] || exit $code
fi

git add memory/desk.json archive
git diff --cached --quiet && exit 0
no_conflicts
git commit -q -m "Dionysus desk note, $(date '+%Y-%m-%d %H:%M')"
set_aside
if ! git pull --rebase -q origin main; then
  git rebase --abort 2>/dev/null || true
  echo "Could not combine with GitHub's latest; the next note will try again."
  exit 0
fi
git push -q origin main && echo "Saved to GitHub."
