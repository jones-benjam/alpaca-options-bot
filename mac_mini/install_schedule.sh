#!/bin/zsh
# Schedules mac_mini/nightly.sh on this Mac: 6:00 pm Monday to Friday (after the
# market closes in every US time zone) and 6:30 am Tuesday to Saturday (to pick
# up Alpaca's official closing figures). Run it once. To remove the schedule:
#
#   launchctl bootout gui/$(id -u)/com.optbot.trader
#   rm ~/Library/LaunchAgents/com.optbot.trader.plist
set -e
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PLIST="$HOME/Library/LaunchAgents/com.optbot.trader.plist"
mkdir -p "$HOME/Library/LaunchAgents"

TIMES=""
for day in 1 2 3 4 5; do
  TIMES="$TIMES<dict><key>Weekday</key><integer>$day</integer><key>Hour</key><integer>18</integer><key>Minute</key><integer>0</integer></dict>"
done
for day in 2 3 4 5 6; do
  TIMES="$TIMES<dict><key>Weekday</key><integer>$day</integer><key>Hour</key><integer>6</integer><key>Minute</key><integer>30</integer></dict>"
done

cat > "$PLIST" <<PLIST_END
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.optbot.trader</string>
  <key>ProgramArguments</key>
  <array><string>/bin/zsh</string><string>$REPO/mac_mini/nightly.sh</string></array>
  <key>StartCalendarInterval</key><array>$TIMES</array>
  <key>StandardOutPath</key><string>$REPO/mac_mini/nightly.log</string>
  <key>StandardErrorPath</key><string>$REPO/mac_mini/nightly.log</string>
</dict>
</plist>
PLIST_END

launchctl bootout "gui/$(id -u)/com.optbot.trader" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Scheduled. It will run at 6:00 pm on weekdays and 6:30 am Tuesday to Saturday."
echo "Run it now with:   $REPO/mac_mini/nightly.sh"
echo "Its log is at:     $REPO/mac_mini/nightly.log"
