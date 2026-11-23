#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
if [[ $# -ne 1 || ! -d "$1" ]]; then
    echo 'Usage: run_offs.sh OUT_DIR (existing directory)' >&2
    exit 1
fi
OUT_DIR="$(cd "$1" && pwd)"
export OUT_DIR PYTHONDONTWRITEBYTECODE=1 TMPDIR="$OUT_DIR"
run_one() {
    local name="$1" arm="$2" out="$OUT_DIR/off_${1}.jsonl" log="$OUT_DIR/off_${1}.log"
    if [[ -f "$out" && -f "$log" ]] && grep -Fq 'wrote 6047 rows' "$log"; then
        echo "Skipping $name"
        return
    fi
    python3 .agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_history_replay_eval.py run \
        --meeting-root '/Volumes/Kelvin Hardisk 1/WongChoi-Archive/hkjc-history/replay_all' \
        --dump-matrix --arm "docs/experiments/patches/$arm" --out "$out" > "$log" 2>&1
}
export -f run_one
printf '%s\n' \
    'market_history hkjc_arm_market_history_revert.py' \
    'draw_style hkjc_arm_draw_style_revert.py' \
    'incident_history hkjc_arm_incident_history_revert.py' \
    'distance_move hkjc_arm_distance_move_revert.py' \
    'surface_move hkjc_arm_surface_move_revert.py' \
    'excuse_streak hkjc_arm_excuse_streak_revert.py' \
    'thin_evidence hkjc_arm_thin_shrink_revert.py' \
    'venue_distance hkjc_arm_venue_distance_off.py' \
    'horse_age hkjc_arm_horse_age_off.py' | xargs -n 2 -P 3 bash -c 'run_one "$@"' _
