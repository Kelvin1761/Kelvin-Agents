"""Rebuild the ace-model calibration curve from player_match_history.

Emits the CALIBRATION_CURVE list embedded in tennis_wc.props.ace_model. Re-run
after a large history backfill and paste the printed CURVE back into ace_model.py.

    PYTHONPATH=src .venv/bin/python scripts/build_ace_calibration.py

Method (matches the model exactly): pair player_match_history rows into matches
(-winner/-loser share a base id), walk forward in date order using only prior
matches per player, predict the match total-ace mean (overall+surface serve rate
blended with the opponent's conceded-aces), then bucket ratio = line/predicted
against the realised P(total >= line). ~12k samples per 0.05 ratio bucket.
"""
from __future__ import annotations

from collections import defaultdict, deque

from tennis_wc.database.db import get_connection
from tennis_wc.props.ace_model import (
    _CONCEDE_WEIGHT, _GLOBAL_ACE_FALLBACK, _LAST_N, _MIN_HISTORY, _SURFACE_WEIGHT,
)


def _base_id(pid: str) -> str:
    for suf in ("-winner", "-loser"):
        if pid.endswith(suf):
            return pid[: -len(suf)]
    return pid


def build_curve() -> list[tuple[float, float]]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT provider_match_id, player_id, opponent_id, match_date, surface, ace_count "
        "FROM player_match_history WHERE ace_count IS NOT NULL "
        "ORDER BY match_date ASC, provider_match_id ASC"
    ).fetchall()
    by_match = defaultdict(list)
    for r in rows:
        by_match[_base_id(r["provider_match_id"])].append(r)
    paired = {k: v for k, v in by_match.items() if len(v) == 2}
    order = sorted(paired.items(), key=lambda kv: (kv[1][0]["match_date"], kv[0]))

    ph = defaultdict(lambda: deque(maxlen=_LAST_N))
    ps = defaultdict(lambda: defaultdict(lambda: deque(maxlen=_LAST_N)))
    oc = defaultdict(lambda: deque(maxlen=_LAST_N))

    def pm(dq, fb):
        return sum(dq) / len(dq) if dq else fb

    recs: list[tuple[float, float]] = []
    for _mid, (a, b) in order:
        surf = (a["surface"] or "hard").lower()
        ah, bh = ph[a["player_id"]], ph[b["player_id"]]
        if len(ah) >= _MIN_HISTORY and len(bh) >= _MIN_HISTORY:
            ab, bb = pm(ah, _GLOBAL_ACE_FALLBACK), pm(bh, _GLOBAL_ACE_FALLBACK)
            asf = pm(ps[a["player_id"]][surf], ab)
            bsf = pm(ps[b["player_id"]][surf], bb)
            ap = (1 - _SURFACE_WEIGHT) * ab + _SURFACE_WEIGHT * asf
            bp = (1 - _SURFACE_WEIGHT) * bb + _SURFACE_WEIGHT * bsf
            ac, bc = pm(oc[a["player_id"]], None), pm(oc[b["player_id"]], None)
            if bc is not None:
                ap = (1 - _CONCEDE_WEIGHT) * ap + _CONCEDE_WEIGHT * bc
            if ac is not None:
                bp = (1 - _CONCEDE_WEIGHT) * bp + _CONCEDE_WEIGHT * ac
            recs.append((ap + bp, a["ace_count"] + b["ace_count"]))
        ph[a["player_id"]].append(a["ace_count"]); ph[b["player_id"]].append(b["ace_count"])
        ps[a["player_id"]][surf].append(a["ace_count"]); ps[b["player_id"]][surf].append(b["ace_count"])
        oc[a["player_id"]].append(b["ace_count"]); oc[b["player_id"]].append(a["ace_count"])

    bins = defaultdict(lambda: [0, 0])
    for pred, act in recs:
        if pred <= 0:
            continue
        for line in range(1, 26):
            b = round((line / pred) * 20) / 20
            bins[b][0] += 1 if act >= line else 0
            bins[b][1] += 1
    curve = [(b, round(w / n, 4)) for b, (w, n) in sorted(bins.items())
             if n >= 200 and 0.3 <= b <= 1.6]
    print(f"# built from {len(recs)} paired matches")
    print("CALIBRATION_CURVE =", curve)
    return curve


if __name__ == "__main__":
    build_curve()
