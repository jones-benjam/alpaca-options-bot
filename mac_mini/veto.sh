#!/bin/zsh
# Cancel Dionysus's latest change to one of Midas's settings, and save that to
# GitHub so Midas sees it. Midas goes back to the value before the change from
# its next trading day (it applies settings once a day, before trading).
#
#   mac_mini/veto.sh CORE_STOP
#
# To stop him changing settings at all, on any computer with fly:
#   fly secrets set AI_TUNING=0 -a msbc5220-optbot
set -e
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
[ -n "$1" ] || { echo "Usage: mac_mini/veto.sh DIAL   (for example CORE_STOP)"; exit 1; }
git pull --rebase --autostash -q origin main
python3 trader.py veto "$1"
git add memory/dials.json STRATEGY_LOG.md
git commit -q -m "Veto Dionysus's change to $1"
git push -q origin main && echo "Saved to GitHub. Midas uses the earlier value from its next trading day."
