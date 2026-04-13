#!/bin/bash
# ──────────────────────────────────────────────
# Horse Racing Dashboard — Cross-Platform Start Script
# 
# macOS: Double-click or run from Terminal
# Windows: Use start-dashboard.bat instead
#
# Why not LaunchAgent?
#   macOS blocks LaunchAgents from accessing Google Drive 
#   (Files & Folders privacy restriction). 
#   Scripts must be launched from a user-interactive context
#   (Terminal, Login Items via AppleScript, etc.)
# ──────────────────────────────────────────────

DASHBOARD_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$DASHBOARD_DIR/logs"
mkdir -p "$LOG_DIR"

echo "$(date) — Starting Horse Racing Dashboard..." >> "$LOG_DIR/startup.log"

# Kill any existing watcher
pkill -f "auto_regenerate.py" 2>/dev/null
sleep 1

# Start Auto-Regenerate Watcher (watches for analysis file changes & rebuilds dashboard)
cd "$DASHBOARD_DIR"
nohup python3 "$DASHBOARD_DIR/auto_regenerate.py" >> "$LOG_DIR/auto_regenerate.log" 2>&1 &
WATCHER_PID=$!
echo "$(date) — Watcher started (PID: $WATCHER_PID)" >> "$LOG_DIR/startup.log"
echo "✅ Auto-regenerate watcher started (PID: $WATCHER_PID)"
echo "   Dashboard will auto-rebuild when analysis files change."
echo ""

# Optional: Start backend server
if command -v uvicorn &>/dev/null || python3 -c "import uvicorn" 2>/dev/null; then
    lsof -ti:8000 | xargs kill -9 2>/dev/null
    cd "$DASHBOARD_DIR/backend"
    nohup python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 >> "$LOG_DIR/backend.log" 2>&1 &
    echo "$(date) — Backend started on :8000" >> "$LOG_DIR/startup.log"
    echo "🏠 API server: http://localhost:8000"
fi

# Optional: Cloudflare tunnel
if [ -f /tmp/cloudflared ]; then
    pkill -f cloudflared 2>/dev/null
    > "$LOG_DIR/tunnel.log"
    nohup /tmp/cloudflared tunnel --url http://localhost:8000 >> "$LOG_DIR/tunnel.log" 2>&1 &
    
    URL_FILE="$DASHBOARD_DIR/CURRENT_URL.txt"
    for i in $(seq 1 15); do
        TUNNEL_URL=$(grep -o 'https://[a-z\-]*\.trycloudflare\.com' "$LOG_DIR/tunnel.log" 2>/dev/null | head -1)
        [ -n "$TUNNEL_URL" ] && break
        sleep 1
    done
    
    if [ -n "$TUNNEL_URL" ]; then
        echo "$TUNNEL_URL" > "$URL_FILE"
        echo "$TUNNEL_URL" | pbcopy 2>/dev/null
        echo "🔗 Tunnel: $TUNNEL_URL (copied to clipboard)"
        osascript -e "display notification \"$TUNNEL_URL\" with title \"🏇 Dashboard Ready\"" 2>/dev/null
    fi
fi

echo ""
echo "📂 Dashboard file: $DASHBOARD_DIR/Open Dashboard.html"
echo "   (double-click to view — no server needed)"
