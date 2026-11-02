#!/bin/zsh
S="/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/class-rebuild"
cd "$(dirname "$0")/.."
export TMPDIR="$S" PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1
run() { WC_AU_CLASS_ARM="$2" python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_dump_engine_leaves.py --out "$S/$1.json" > "$S/$1.log" 2>&1; echo "done $1 $(date +%T)"; }
run F1 F1 & run C1 F1,C1 & run C2 F1,C2 & run C3 F1,C1,C2 & wait
# FINAL（採用組合）： WC_AU_CLASS_ARM=F1,R2,RM —— 開關喺定稿 code 已拆走，要重跑 arm 見 docs/experiments/EXP-20261102-04-evidence/class_rating_arms.py
run R0 F1,R0 & run R2 F1,R2 & run R5 F1,R5 & run RD F1,RD & wait
run RM F1,RM & run RALL F1,RALL & wait
echo ALL DONE
