#!/bin/bash
# ──────────────────────────────────────────────
# Launch Wrapper — Copied to /usr/local/bin at install time.
# This wrapper and the dashboard code run locally.  Race reports remain in
# Google Drive and are resolved by wongchoi_paths.py.
# ──────────────────────────────────────────────

DASHBOARD_DIR="/Users/imac/Antigravity-repo/Horse_Racing_Dashboard"
LOG_DIR="$DASHBOARD_DIR/logs"
mkdir -p "$LOG_DIR"

if [ ! -d "$DASHBOARD_DIR" ]; then
    echo "$(date) — ❌ Local dashboard folder is missing, aborting" >> "$LOG_DIR/startup.log" 2>/dev/null
    exit 1
fi

exec /bin/bash "$DASHBOARD_DIR/start-dashboard.sh"
