#!/bin/zsh
# One command to set up the trader on a Mac mini. Safe to run again at any
# time: it skips whatever is already done.
#
#   ~/alpaca-options-bot/mac_mini/setup.sh            # do it
#   ~/alpaca-options-bot/mac_mini/setup.sh --dry-run  # only show what it would do
#
# It installs Ollama and GitHub's tool with Homebrew, picks and downloads a
# model that fits this Mac's memory, signs you in to GitHub, tests everything,
# writes the first diary entry and puts the daily job on a schedule.
# It does not trade, and it changes no macOS settings.

REPO="$(cd "$(dirname "$0")/.." && pwd)"
DRY=0
[ "$1" = "--dry-run" ] && DRY=1
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

step() { echo; echo "== $1"; }
run()  { if [ $DRY = 1 ]; then echo "   would run: $*"; else "$@"; fi; }
stop() { echo; echo "STOPPED: $1"; exit 1; }

step "1 of 9: Checking this Mac"
[ "$(uname -m)" = "arm64" ] || stop "This Mac has an Intel chip. A local model needs Apple silicon (M1 or later)."
MEM_GB=$(( $(sysctl -n hw.memsize) / 1073741824 ))
FREE_GB=$(df -g "$HOME" | awk 'NR==2 {print $4}')
echo "   $(sysctl -n machdep.cpu.brand_string), ${MEM_GB} GB memory, ${FREE_GB} GB free disk"

# The largest model that leaves macOS comfortable room. Sizes are downloads.
if   [ $MEM_GB -lt 12 ]; then PICK="qwen3.5:4b";  SIZE=4
elif [ $MEM_GB -lt 20 ]; then PICK="qwen3.5:9b";  SIZE=7
elif [ $MEM_GB -lt 28 ]; then PICK="gpt-oss:20b"; SIZE=14
elif [ $MEM_GB -lt 40 ]; then PICK="qwen3.5:27b"; SIZE=17
else                          PICK="qwen3.5:35b"; SIZE=22
fi

step "2 of 9: Homebrew"
if ! command -v brew >/dev/null; then
  echo "   Homebrew is not installed. Paste this line, follow its prompts (it asks for"
  echo "   this Mac's password), run the two 'Next steps' lines it prints, then run"
  echo "   this setup again:"
  echo
  echo '   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
  [ $DRY = 1 ] || exit 1
else
  echo "   found: $(brew --version | head -1)"
fi

step "3 of 9: Ollama and GitHub's tool"
for tool in ollama gh; do
  if command -v $tool >/dev/null; then echo "   $tool is already installed"; else run brew install $tool; fi
done

step "4 of 9: Starting Ollama (and keeping it running after restarts)"
if curl -fs http://localhost:11434/api/version >/dev/null 2>&1; then
  echo "   already running"
else
  run brew services start ollama
  if [ $DRY = 0 ]; then
    for i in {1..30}; do
      curl -fs http://localhost:11434/api/version >/dev/null 2>&1 && break
      sleep 1
    done
    curl -fs http://localhost:11434/api/version >/dev/null 2>&1 || stop "Ollama did not start. Try: brew services restart ollama"
    echo "   running"
  fi
fi

step "5 of 9: Settings and model"
CONFIG="$REPO/mac_mini/config.env"
if [ -f "$CONFIG" ]; then
  echo "   keeping your existing mac_mini/config.env"
else
  echo "   creating mac_mini/config.env with MODEL=$PICK (chosen for ${MEM_GB} GB of memory)"
  [ $DRY = 1 ] || sed "s|^MODEL=.*|MODEL=$PICK|" "$REPO/mac_mini/config.env.example" > "$CONFIG"
fi
MODEL=$PICK
[ -f "$CONFIG" ] && MODEL=$(grep '^MODEL=' "$CONFIG" | cut -d= -f2)
if [ $DRY = 0 ] && ollama list 2>/dev/null | awk '{print $1}' | grep -qx "$MODEL"; then
  echo "   $MODEL is already downloaded"
else
  [ "$FREE_GB" -gt $(( SIZE + 10 )) ] || stop "Not enough free disk for $MODEL (about ${SIZE} GB)."
  echo "   downloading $MODEL (about ${SIZE} GB; this is the long step)"
  run ollama pull "$MODEL"
fi

step "6 of 9: GitHub sign-in (needed to save his diary)"
if [ $DRY = 1 ]; then
  echo "   would check 'gh auth status', and run 'gh auth login' if needed"
else
  gh auth status >/dev/null 2>&1 || {
    echo "   Choose: GitHub.com, HTTPS, 'Login with a web browser'."
    gh auth login || stop "GitHub sign-in did not finish. Run this setup again when ready."
  }
  gh auth setup-git
  git config --global user.name  >/dev/null || git config --global user.name  "$(gh api user -q '.name // .login')"
  git config --global user.email >/dev/null || git config --global user.email "$(gh api user -q '.login')@users.noreply.github.com"
  echo "   signed in as $(gh api user -q .login); changes will be saved as $(git config --global user.name)"
fi

step "7 of 9: Testing"
cd "$REPO"
run python3 trader.py selftest || stop "The self-test failed. Send the lines above to Claude."
run python3 trader.py check    || stop "The model is not ready. See the message above."
if [ -f "$REPO/.env" ]; then
  echo "   Alpaca paper keys found: this Mac will also keep the daily record up to date."
else
  echo "   No Alpaca keys here (optional). Without them he reads whatever GitHub last saved."
  echo "   To add them: AirDrop ~/alpaca-options-bot/.env from the MacBook, then run"
  echo "   mv ~/Downloads/.env $REPO/.env && chmod 600 $REPO/.env"
fi

step "8 of 9: His first day"
run "$REPO/mac_mini/nightly.sh" || echo "   The first run hit a problem; see the lines above. Setup continues."

step "9 of 9: Daily schedule"
run "$REPO/mac_mini/install_schedule.sh"

echo
echo "DONE. Three things only you can do, in System Settings > Energy:"
echo "  - turn on 'Prevent automatic sleeping when the display is off'"
echo "  - turn on 'Start up automatically after a power failure'"
echo "  - leave the Mac mini plugged in and logged in"
echo
echo "Talk to him:            cd $REPO && python3 trader.py chat"
echo "Compare models:         cd $REPO && python3 trader.py compare"
echo "His diary:              $REPO/memory/DIARY.md"
echo "Chat in the Ollama app: cd $REPO && python3 trader.py modelfile   (then follow what it prints)"
