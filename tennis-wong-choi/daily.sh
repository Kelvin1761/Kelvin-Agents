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
# How far back to re-pull results / re-attempt settlement each run. Results
# arrive late and unevenly, so a 1-day window permanently strands anything the
# provider was slow on. 14 days is cheap (TML ships whole-season CSVs anyway).
RESULT_LOOKBACK_DAYS="${RESULT_LOOKBACK_DAYS:-14}"
INGEST_FROM="$(date -v-${RESULT_LOOKBACK_DAYS}d -j -f %F "$DATE" +%F 2>/dev/null \
  || date -d "$DATE -${RESULT_LOOKBACK_DAYS} day" +%F 2>/dev/null || echo "$PREV")"

echo "==================== Tennis Wong Choi daily: $DATE ===================="

if [ -n "$PREV" ]; then
  echo "--- [1/3] settle prior day $PREV + update trackers (profitability) ---"
  # Results FIRST, or there is nothing to settle against. settle-bets only pulls
  # results via the tennis provider, which covers ~40% of our fixtures (it misses
  # most Challenger/ITF, i.e. most of what we price). Without this step the
  # trackers silently stall: on 2026-07-25 we found 76 props and 83 tracker rows
  # stuck PENDING back to 2026-05-10, and MARKET_REVIEW was 0/16 settled, which
  # made every ROI/graduation number optimistic. Backfilling 390 results fixed it.
  # The window is deliberately wider than one day: TML publishes late, so a
  # yesterday-only pull keeps missing the same matches forever.
  "${PY[@]}" ingest-tennismylife-results --start "$INGEST_FROM" --end "$PREV" \
    || echo "  (ingest-tennismylife-results skipped/failed)"
  "${PY[@]}" fetch-closing-odds --date "$PREV"  || echo "  (fetch-closing-odds skipped/failed)"
  "${PY[@]}" settle-bets        --date "$PREV"  || echo "  (settle-bets skipped/failed)"
  # Sweep older PENDING rows whose results only just arrived above.
  "${PY[@]}" settle-backlog     --date "$DATE" --lookback-days "$RESULT_LOOKBACK_DAYS" \
    || echo "  (settle-backlog skipped/failed)"
  "${PY[@]}" settle-props       || echo "  (settle-props skipped/failed)"
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
