#!/bin/bash
# ──────────────────────────────────────────────
# Horse Racing Dashboard — Stop Script
# ──────────────────────────────────────────────

echo "Stopping Horse Racing Dashboard..."
lsof -ti:8000 | xargs kill -9 2>/dev/null
lsof -ti:5173 | xargs kill -9 2>/dev/null
pkill -f cloudflared 2>/dev/null
pkill -f "auto_regenerate.py" 2>/dev/null
echo "✅ All services stopped."
