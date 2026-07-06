#!/usr/bin/env bash
#
# Tennis Wong Choi — one-command daily run.
#
#   ./daily.sh [YYYY-MM-DD]      (defaults to today)
#
# It does, in order:
#   1. Settle the PRIOR day and sync CLV / combo trackers  -> measures profitability over time
#   2. LIVE run-daily for the target day                   -> fixtures + ALL Sportsbet markets
#      (per-event enrichment, with retries) + predictions + agents + the ONE merged
#      betting report (Tennis_Daily_Report.txt) + the raw odds appendix
#   3. Print the betting report and flag if multi-market odds did NOT fully extract
#
# Run it on a machine with Sportsbet (AU) network access. Do NOT pass --mvp-snapshot;
# snapshot mode skips the live multi-market enrichment.
set -uo pipefail
cd "$(dirname "$0")"
export PYTHONPATH=src
PY=(python3 -m tennis_wc.cli)

DATE="${1:-$(date +%F)}"
# previous day (works on both macOS and Linux date)
PREV="$(date -v-1d -j -f %F "$DATE" +%F 2>/dev/null || date -d "$DATE -1 day" +%F 2>/dev/null || echo "")"

echo "==================== Tennis Wong Choi daily: $DATE ===================="

if [ -n "$PREV" ]; then
  echo "--- [1/3] settle prior day $PREV + update trackers (profitability) ---"
  "${PY[@]}" fetch-closing-odds --date "$PREV"  || echo "  (fetch-closing-odds skipped/failed)"
  "${PY[@]}" settle-bets        --date "$PREV"  || echo "  (settle-bets skipped/failed)"
  "${PY[@]}" sync-clv-tracker   --date "$PREV"  || echo "  (sync-clv-tracker skipped/failed)"
  "${PY[@]}" sync-combo-tracker --date "$PREV"  || echo "  (sync-combo-tracker skipped/failed)"
fi

echo "--- [2/3] LIVE run for $DATE (fixtures + ALL markets + predict + report) ---"
"${PY[@]}" run-daily --date "$DATE"

echo "--- [3/3] market coverage + combos ---"
MARKETS=$(python3 - "$DATE" <<'PY'
import sys, sqlite3
from tennis_wc.config import get_settings
c = sqlite3.connect(get_settings().sqlite_path)
n = c.execute(
    "SELECT COUNT(DISTINCT mo.market_key) FROM market_odds_snapshots mo "
    "JOIN matches m ON m.id=mo.match_id WHERE m.match_date=?", (sys.argv[1],)
).fetchone()[0]
print(n or 0)
PY
)
echo "  distinct market types captured: ${MARKETS}"
if [ "${MARKETS:-0}" -le 1 ]; then
  echo "  ⚠️  ONLY match-winner odds captured — multi-market enrichment did NOT complete."
  echo "     Combos will be limited. Check network to www.sportsbet.com.au and re-run (live, no --mvp-snapshot)."
fi

REPORT="../${DATE} Tennis Analysis/Tennis_Daily_Report.txt"
echo "----------------------------------------------------------------------"
[ -f "$REPORT" ] && cat "$REPORT" || echo "  (no daily report found at: $REPORT)"

echo "--- profitability so far (flat-1u, needs settled history) ---"
"${PY[@]}" tier-roi   || true
"${PY[@]}" combo-roi  || true
