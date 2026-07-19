#!/bin/bash
# PF backfill slow runner — Kelvin-approved pacing (2026-07-17).
# 2 meetings per cycle (~22 requests), 45-60 min rest between cycles,
# hard stop on any block signal (driver exit code 2) or repeated failure.
set -u
CYCLES="${1:-12}"
DRIVER="/Users/imac/Antigravity-repo/scratch/au_pf_backfill_driver.py"
APPLY="/Users/imac/Antigravity-repo/scratch/au_pf_apply_and_gate.py"

for ((i=1; i<=CYCLES; i++)); do
    echo "=== cycle $i/$CYCLES $(date '+%H:%M') ==="
    python3 "$DRIVER" --run --limit 2 2>&1 | grep -v NotOpenSSL | grep -v warnings.warn | grep -v curl_cffi
    rc=${PIPESTATUS[0]}
    if [ "$rc" -eq 2 ]; then
        echo "BLOCK SIGNAL — stopping the slow runner entirely."
        exit 2
    elif [ "$rc" -ne 0 ]; then
        echo "driver failed rc=$rc — stopping to be safe."
        exit "$rc"
    fi
    # local-only apply of anything staged (zero network)
    python3 "$APPLY" --limit 99 2>&1 | grep -v NotOpenSSL | grep -v warnings.warn | grep "^==" | tail -4
    if [ "$i" -lt "$CYCLES" ]; then
        rest=$((2700 + RANDOM % 900))
        echo "resting ${rest}s until next cycle..."
        sleep "$rest"
    fi
done
echo "SLOW RUNNER COMPLETE: $((CYCLES*2)) meetings attempted."
