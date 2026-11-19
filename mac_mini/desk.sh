#!/bin/zsh
# Midas's live desk notes. Scheduled every 30 minutes by install_schedule.sh; when
# the market is closed it only checks and exits, so it is safe to run any time.
#
#   1. Read the bot's live data from the dashboard (no keys needed).
#   2. Have him write a two-to-four sentence note, number-checked like the diary.
#   3. Save memory/desk.json to GitHub; the /midas page shows it within minutes.
#
# The notes are commentary only: nothing here changes what the bot trades.
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

LOCK="${TMPDIR:-/tmp}/optbot-desk.lock"
mkdir "$LOCK" 2>/dev/null || exit 0      # the previous note is still being written
trap 'rmdir "$LOCK"' EXIT

python3 trader.py desk > "${TMPDIR:-/tmp}/optbot-desk.out" 2>&1
code=$?
if [ $code = 2 ]; then exit 0; fi        # market closed or bot unreachable: nothing to say
echo "=== $(date '+%Y-%m-%d %H:%M:%S') desk note ==="
cat "${TMPDIR:-/tmp}/optbot-desk.out"
[ $code = 0 ] || exit $code

git add memory/desk.json
git diff --cached --quiet && exit 0
git commit -q -m "Midas desk note, $(date '+%Y-%m-%d %H:%M')"
if ! git pull --rebase --autostash -q origin main; then
  git rebase --abort 2>/dev/null || true
  echo "Could not combine with GitHub's latest; the next note will try again."
  exit 0
fi
git push -q origin main && echo "Saved to GitHub."
