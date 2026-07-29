#!/bin/zsh
set -eu

# Two agents, deliberately:
#   .daily    20:00        -- review yesterday, archive, analyse TOMORROW (preview)
#   .refresh  09/12/15:00  -- rebuild TODAY's card once Sportsbet has priced the day
# The evening job alone was not enough: it analyses tomorrow against a book that
# is barely open, so 2026-07-29 produced a card from 2 priced matches out of 102
# fixtures. The refresh agent is what makes the published card actionable.
PROJECT_DIR="/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/tennis-wong-choi"
DEST_DIR="$HOME/Library/LaunchAgents"

mkdir -p "$DEST_DIR" "$PROJECT_DIR/data/logs"
chmod +x "$PROJECT_DIR/scripts/run_tennis_daily_schedule.sh" "$PROJECT_DIR/scripts/tennis_daily_schedule.py"

install_agent() {
  local label="$1" schedule_note="$2"
  local template="$PROJECT_DIR/launchd/$label.plist.template"
  local dest="$DEST_DIR/$label.plist"
  local service="gui/$(id -u)/$label"

  if [ ! -f "$template" ]; then
    echo "MISSING template: $template" >&2
    return 1
  fi

  sed "s#__PROJECT_DIR__#$PROJECT_DIR#g" "$template" > "$dest"
  chmod 644 "$dest"

  launchctl bootout "gui/$(id -u)" "$dest" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$dest"
  launchctl enable "$service"

  echo "Installed $label"
  echo "  Schedule: $schedule_note"
  echo "  Plist:    $dest"
}

install_agent "com.antigravity.tennis-wong-choi.daily" \
  "20:00 local -- review yesterday + archive + analyse tomorrow"
install_agent "com.antigravity.tennis-wong-choi.refresh" \
  "09:00 / 12:00 / 15:00 local -- rebuild today's card (retries if the book is still thin)"

echo "Logs: $PROJECT_DIR/data/logs/"
