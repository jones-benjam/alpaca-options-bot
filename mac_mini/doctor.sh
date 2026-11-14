#!/bin/zsh
# Checks everything the trader needs on this Mac and says how to fix what is
# wrong. It changes nothing. Run it whenever something seems off:
#
#   ~/alpaca-options-bot/mac_mini/doctor.sh
REPO="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
cd "$REPO"
PROBLEMS=0
ok()  { echo "  OK    $1"; }
bad() { echo "  FIX   $1"; echo "        -> $2"; PROBLEMS=$((PROBLEMS + 1)); }
note(){ echo "  NOTE  $1"; }

echo "This Mac"
echo "  $(sysctl -n machdep.cpu.brand_string), $(( $(sysctl -n hw.memsize) / 1073741824 )) GB memory, $(df -g "$HOME" | awk 'NR==2 {print $4}') GB free disk"
[ "$(uname -m)" = "arm64" ] && ok "Apple silicon" || bad "Intel chip" "A local model needs an M-series Mac."
SLEEP=$(pmset -g 2>/dev/null | awk '$1=="sleep" {print $2}')
[ "$SLEEP" = "0" ] && ok "The Mac will not go to sleep" \
  || bad "The Mac is set to sleep after ${SLEEP:-?} minutes, so scheduled runs can be missed" \
         "System Settings > Energy > turn on 'Prevent automatic sleeping when the display is off'"
[ "$(pmset -g 2>/dev/null | awk '$1=="autorestart" {print $2}')" = "1" ] && ok "Restarts by itself after a power cut" \
  || note "Will not restart after a power cut (System Settings > Energy, optional)"

echo; echo "Ollama and the model"
if curl -fs http://localhost:11434/api/version >/dev/null 2>&1; then
  ok "Ollama is running ($(curl -fs http://localhost:11434/api/version | sed -E 's/.*"version":"([^"]+)".*/\1/'))"
else
  bad "Ollama is not running" "brew services start ollama"
fi
MODEL=$(grep '^MODEL=' mac_mini/config.env 2>/dev/null | cut -d= -f2)
if [ -z "$MODEL" ]; then
  bad "No mac_mini/config.env" "Run mac_mini/setup.sh"
elif ollama list 2>/dev/null | awk '{print $1}' | grep -qx "$MODEL"; then
  ok "Model $MODEL is downloaded"
else
  bad "Model $MODEL is not downloaded" "ollama pull $MODEL"
fi
brew services list 2>/dev/null | awk '$1=="ollama" {print $2}' | grep -q started \
  && ok "Ollama starts by itself after a restart" || note "Ollama is not set to start by itself (brew services start ollama)"

echo; echo "The project and GitHub"
git fetch -q origin 2>/dev/null && ok "Can reach GitHub" || bad "Cannot reach GitHub" "Check the internet connection"
BEHIND=$(git rev-list --count HEAD..origin/main 2>/dev/null)
[ "${BEHIND:-0}" = "0" ] && ok "Up to date with GitHub" || note "$BEHIND update(s) waiting on GitHub; the next run fetches them"
[ -z "$(git status --porcelain 2>/dev/null)" ] && ok "No unsaved local changes" \
  || note "Local changes not yet saved to GitHub: $(git status --porcelain | wc -l | tr -d ' ') file(s)"
if gh auth status >/dev/null 2>&1; then
  [ "$(gh api repos/jones-benjam/alpaca-options-bot -q .permissions.push 2>/dev/null)" = "true" ] \
    && ok "Signed in to GitHub as $(gh api user -q .login) and allowed to save" \
    || bad "Signed in as $(gh api user -q .login), but that account cannot save to the project" "Ask the owner to add it as a collaborator"
else
  bad "Not signed in to GitHub" "gh auth login   then   gh auth setup-git"
fi
[ -f .env ] && ok "Alpaca paper keys present (this Mac keeps the daily record current)" \
  || note "No Alpaca keys (optional): he reads whatever GitHub last saved"

echo; echo "The schedule"
if launchctl print "gui/$(id -u)/com.optbot.trader" >/dev/null 2>&1; then
  ok "The daily job is scheduled (6:00 pm weekdays, 6:30 am the next morning)"
else
  bad "The daily job is not scheduled" "mac_mini/install_schedule.sh"
fi
if [ -f mac_mini/nightly.log ]; then
  LAST=$(grep '^=== ' mac_mini/nightly.log | tail -1)
  note "Last run: ${LAST:-unknown}"
  tail -3 mac_mini/nightly.log | sed 's/^/        /'
else
  note "It has not run yet. Run it now with: mac_mini/nightly.sh"
fi

echo; echo "His work"
if [ -f memory/DIARY.md ]; then
  ok "Latest diary entry: $(grep '^## ' memory/DIARY.md | tail -1 | cut -c4-)"
else
  note "No diary yet. Write one with: python3 trader.py diary"
fi
python3 trader.py selftest >/dev/null 2>&1 && ok "The self-test passes" || bad "The self-test fails" "python3 trader.py selftest   and send the output to Claude"

echo
[ $PROBLEMS = 0 ] && echo "Everything checks out." || echo "$PROBLEMS thing(s) to fix, marked FIX above."
