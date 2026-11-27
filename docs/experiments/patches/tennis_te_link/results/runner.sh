#!/bin/bash
# EXP-20261127-71 unattended runner (Claude 2026-11-27, Kelvin switching accounts).
# Waits for A0 scoring + A1 linking already in flight, scores A1, compares, writes
# result.md here and pushes one Telegram (primary). Never touches the production DB.
set -u
X="/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-te-link-20261127"
S="/private/tmp/claude-501/-Users-imac-Antigravity-repo/fb01f595-189b-4d9d-8502-2f59e4b78d84/scratchpad"
EV="$X/code/docs/experiments/patches/tennis_te_link/evaluate.py"
PY=/usr/bin/python3
LOG="$X/runner.log"
export PYTHONDONTWRITEBYTECODE=1
log() { echo "[$(date '+%F %T')] $*" >> "$LOG"; }
notify() {
  cd /Users/imac/Antigravity-repo && PATH=/usr/bin:$PATH $PY - "$1" <<'EOF' >> "$LOG" 2>&1
import sys; sys.path.insert(0, ".agents/skills/shared_racing/scripts")
import racing_telegram as t
print(t.send_message(sys.argv[1], audience="primary"))
EOF
}
cd "$X" || exit 1
log "runner start"

# 1. A0 scoring (3 shards started 11:50 from the session scratchpad)
while pgrep -f "evaluate.py score --db $X/A0.db" >/dev/null; do sleep 60; done
for i in 0 1 2; do
  if [ -s "$S/A0_$i.json" ]; then cp "$S/A0_$i.json" "$X/A0_$i.json"; fi
  if [ ! -s "$X/A0_$i.json" ]; then
    log "A0 shard $i missing -> rescoring"
    SHARD=$i/3 $PY "$EV" score --db "$X/A0.db" --out "$X/A0_$i.json" >> "$LOG" 2>&1 &
  fi
done
wait
log "A0 done: $(ls -la $X/A0_*.json | wc -l) shards"

# 2. A1 linking (started 12:19)
while pgrep -f "evaluate.py apply --db $X/A1.db" >/dev/null; do sleep 60; done
APPLY=$(cat "$S/A1_apply.log" 2>/dev/null)
log "A1 apply log: $APPLY"
if ! echo "$APPLY" | grep -q '"ids_merged"'; then
  log "A1 apply did not report success -> re-applying"
  $PY "$EV" apply --db "$X/A1.db" >> "$LOG" 2>&1 || { log "A1 apply FAILED"; notify "⚠️ 網球 EXP-20261127-71 評估：A1 連結失敗，見 $LOG"; exit 1; }
fi

# 3. A1 scoring
for i in 0 1 2; do
  SHARD=$i/3 $PY "$EV" score --db "$X/A1.db" --out "$X/A1_$i.json" >> "$LOG" 2>&1 &
done
wait
log "A1 done"

# 4. compare (pre-registered rule is printed by compare: KEEP candidate iff CI upper < 0)
$PY "$EV" compare "$X/A0_0.json+$X/A0_1.json+$X/A0_2.json" "$X/A1_0.json+$X/A1_1.json+$X/A1_2.json" > "$X/result.md" 2>&1
log "compare exit $?"
cat "$X/result.md" >> "$LOG"

# 5. tonight's tennis run timing (follow-up from EXP-20261127-70)
L=/Users/imac/Antigravity-repo/tennis-wong-choi/data/logs/tennis_daily_schedule.log
grep -E "^\[2026-11-27T1[89]" "$L" | grep -E "Running analysis|Analysis complete" > "$X/timing_1800.txt" 2>/dev/null

# 6. Sol independent read-only review of the result (verdict stays with Claude)
cd /Users/imac/Antigravity-repo && /usr/bin/python3 .agents/scripts/codex_delegate.py run review \
  --cd "$X/code" --add-dir "$X" --prompt-file "$X/sol_brief.md" --out "$X/sol_review.md" \
  --title "覆核 EXP-20261127-71 A/B 結果（無人值守）" >> "$LOG" 2>&1
log "sol review exit $?"
cd "$X"

notify "🎾 網球 EXP-20261127-71（TE 縮寫名連結）評估跑完 —— 未判決，等 Claude 覆核
$(head -12 "$X/result.md")

Sol 覆核（摘要）：
$(head -c 900 "$X/sol_review.md" 2>/dev/null || echo '（Sol 未有回覆，見 runner.log）')

檔案：$X/result.md、sol_review.md、HANDOFF.md
（生產冇郁；連結開關仍然關。開新 session 判決。）"
log "runner end"
