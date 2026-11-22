#!/bin/zsh
IFS='|' read -r name base cand <<< "$1"
S=/Users/imac/wt-draw-ruler/.agents/skills/hkjc_racing/hkjc_reflector/scripts
OUT=/private/tmp/claude-501/-Users-imac-Antigravity-repo/0f80c4bf-984b-44f7-9cea-eb1dd014771c/scratchpad/ruler
for v in v4 v5; do PYTHONDONTWRITEBYTECODE=1 python3 $S/hkjc_replay_compare_$v.py "$base" "$cand" --window dev --null 200 > $OUT/${name}_$v.txt 2>&1; done
