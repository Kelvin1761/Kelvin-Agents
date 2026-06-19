#!/bin/zsh
set -eu

LABEL="com.antigravity.tennis-wong-choi.daily"
PROJECT_DIR="/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/tennis-wong-choi"
TEMPLATE="$PROJECT_DIR/launchd/$LABEL.plist.template"
DEST_DIR="$HOME/Library/LaunchAgents"
DEST="$DEST_DIR/$LABEL.plist"
SERVICE="gui/$(id -u)/$LABEL"

mkdir -p "$DEST_DIR" "$PROJECT_DIR/data/logs"
sed "s#__PROJECT_DIR__#$PROJECT_DIR#g" "$TEMPLATE" > "$DEST"
chmod 644 "$DEST"
chmod +x "$PROJECT_DIR/scripts/run_tennis_daily_schedule.sh" "$PROJECT_DIR/scripts/tennis_daily_schedule.py"

launchctl bootout "gui/$(id -u)" "$DEST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$DEST"
launchctl enable "$SERVICE"

echo "Installed $LABEL"
echo "Schedule: daily at 18:00 local time"
echo "Plist: $DEST"
echo "Logs: $PROJECT_DIR/data/logs/"
