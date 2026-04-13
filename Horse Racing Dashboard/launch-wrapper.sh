#!/bin/bash
# ──────────────────────────────────────────────
# Launch Wrapper — Copied to /usr/local/bin at install time.
# macOS LaunchAgents can't reliably execute scripts on Google Drive
# due to sandboxing/permission restrictions (Operation not permitted).
# This wrapper lives locally and delegates to the real script.
# ──────────────────────────────────────────────

DASHBOARD_DIR="/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/Horse Racing Dashboard"
LOG_DIR="$DASHBOARD_DIR/logs"
mkdir -p "$LOG_DIR"

# Wait for Google Drive to mount (up to 30s after login)
for i in $(seq 1 30); do
    [ -d "$DASHBOARD_DIR" ] && break
    sleep 1
done

if [ ! -d "$DASHBOARD_DIR" ]; then
    echo "$(date) — ❌ Google Drive not mounted after 30s, aborting" >> "$LOG_DIR/startup.log" 2>/dev/null
    exit 1
fi

exec /bin/bash "$DASHBOARD_DIR/start-dashboard.sh"
