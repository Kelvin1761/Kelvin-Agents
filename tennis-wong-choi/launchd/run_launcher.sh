#!/bin/zsh
# Bootstrap launcher copied to ~/Library/Application Support/TennisWongChoi.
# It stays on the local disk so launchd can wait for the Google Drive project
# to become available after a wake or login.

set -u

PROJECT_DIR="/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/tennis-wong-choi"
RUN_SCRIPT="$PROJECT_DIR/scripts/run_tennis_daily_schedule.sh"
VENV_PY="$PROJECT_DIR/.venv/bin/python"

LOCAL_LOG_DIR="$HOME/Library/Application Support/TennisWongChoi"
LOCAL_LOG="$LOCAL_LOG_DIR/launcher.log"
mkdir -p "$LOCAL_LOG_DIR"

log() {
  local line="[$(date '+%Y-%m-%dT%H:%M:%S%z')] $1"
  # Do not use tee here: launchd may redirect stdout to a file on the same
  # Google Drive volume, which can trigger a stdout resource-deadlock error.
  print -r -- "$line" >> "$LOCAL_LOG"
  print -r -- "$line"
}

materialised() {
  head -c 1 "$1" >/dev/null 2>&1
}

# Wait up to 20 minutes for Google Drive File Stream to materialise the
# project. The daily run is skipped loudly if the project never becomes ready.
MAX_TRIES=40
SLEEP_SECONDS=30
attempt=1
while [ "$attempt" -le "$MAX_TRIES" ]; do
  if materialised "$VENV_PY" && materialised "$RUN_SCRIPT"; then
    log "Project ready on attempt $attempt; launching daily run."
    exec /bin/zsh "$RUN_SCRIPT" "$@"
  fi
  log "Project not materialised yet (attempt $attempt/$MAX_TRIES): waiting for $RUN_SCRIPT"
  sleep "$SLEEP_SECONDS"
  attempt=$((attempt + 1))
done

log "ERROR: Google Drive project never became readable after $MAX_TRIES attempts. Daily run skipped."
exit 1
