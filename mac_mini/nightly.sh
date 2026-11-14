#!/bin/zsh
# The Mac mini's daily job. Safe to run by hand, and safe to run twice.
#
#   1. Fetch the latest code and memory from GitHub.
#   2. If this Mac has the Alpaca paper keys (.env), bring the daily record and
#      the memory files up to date itself, so nothing depends on GitHub's timing.
#   3. Have the trader persona write his diary and picks (and, on Fridays, his notes).
#   4. Save the result back to GitHub.
set -e
cd "$(dirname "$0")/.."
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
echo "=== $(date '+%Y-%m-%d %H:%M:%S') nightly run ==="

git pull --rebase --autostash -q origin main

if [ -f .env ]; then
  python3 bot.py journal || echo "journal failed; carrying on"
  python3 bot.py memory  || echo "memory refresh failed; carrying on"
fi

if python3 trader.py check; then
  python3 trader.py nightly
else
  echo "The model is not ready, so the trader wrote nothing today."
fi

python3 dashboard.py || echo "dashboard failed; carrying on"

git add STRATEGY_LOG.md memory docs
if git diff --cached --quiet; then
  echo "Nothing new to save."
  exit 0
fi
git commit -q -m "Mac mini: daily record and trader diary, $(date +%Y-%m-%d)"
if ! git pull --rebase -q origin main; then
  # GitHub's own daily job changed the same lines. Drop this run's copy; the
  # next run rebuilds everything from scratch, so nothing is lost.
  git rebase --abort 2>/dev/null || true
  git reset -q --hard origin/main
  echo "GitHub updated the same lines first. Will redo on the next run."
  exit 0
fi
git push -q origin main
echo "Saved to GitHub."
