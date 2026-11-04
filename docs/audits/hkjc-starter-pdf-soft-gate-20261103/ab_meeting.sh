#!/usr/bin/env bash
# usage: ab_meeting.sh <worktree> <meeting_name> <variant A|B> <outroot>
set -uo pipefail
WT="$1"; M="$2"; V="$3"; OUT="$4"
SRC="$(cat "$WT/.wongchoi_hk_data_root")/$M"
DST="$OUT/$V/$M"
rm -rf "$DST"; mkdir -p "$DST"
rsync -a --exclude 'Prediction_Snapshots*' --exclude 'Dashboard_Snapshot' --exclude '*Facts.md' --exclude 'Race_*_Logic.json' --exclude 'Race_*_Auto_*' --exclude 'HKJC_Auto_Scoring.csv' "$SRC/" "$DST/"
if [ "$V" = "B" ]; then
  find "$DST" -maxdepth 1 -name '*全日出賽馬匹資料*' -delete
  export WC_HKJC_FSC_FALLBACK=force
fi
export PYTHONDONTWRITEBYTECODE=1
cd "$WT"
python3 -W ignore .agents/scripts/run_prerace_pipeline.py "$DST" --skip-std-times --skip-draw --skip-stats --inject-workers 3 > "$OUT/$V-$M-prerace.log" 2>&1 || echo "prerace rc=$?"
for f in "$DST"/*" Race "*" Facts.md"; do
  n=$(echo "$f" | sed -E 's/.* Race ([0-9]+) Facts.md/\1/')
  python3 -W ignore .agents/skills/hkjc_racing/hkjc_wong_choi/scripts/create_hkjc_logic_skeleton.py "$f" "$n" --all-horses --output "$DST/Race_${n}_Logic.json" >> "$OUT/$V-$M-logic.log" 2>&1 || echo "logic R$n rc=$?"
done
python3 -W ignore .agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts/hkjc_auto_orchestrator.py "$DST" > "$OUT/$V-$M-auto.log" 2>&1 || echo "auto rc=$?"
echo "done $V $M"
