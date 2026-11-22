#!/bin/zsh
# EXP-20261123-06：舊候選喺現行 live（fcedd248）重建，v2 尺判。dump 全部寫外置碟。
set -u
cd "$(dirname "$0")/../../../.."
D="/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/au-v2-rescreen-20261123"
[ -d "/Volumes/Kelvin Hardisk 1" ] || { echo "外置碟冇掛載"; exit 1; }
mkdir -p "$D"; export PYTHONDONTWRITEBYTECODE=1 TMPDIR="$D"
S=.agents/skills/au_racing/au_wong_choi_auto/scripts
python3 $S/au_dump_engine_leaves.py --out "$D/BASE.json" > "$D/BASE.log" 2>&1 &
WC_AU_FQ_SCALE=floor python3 $S/au_dump_engine_leaves.py --out "$D/F1.json" > "$D/F1.log" 2>&1 &
WC_AU_TRACK_SPECIALISM_ARM=SPG python3 $S/au_dump_engine_leaves.py --out "$D/SPG.json" > "$D/SPG.log" 2>&1 &
wait
python3 docs/experiments/patches/au_v2_rescreen/judge.py "$D" F1 SPG > "$D/judge.txt" 2>&1
echo DONE
