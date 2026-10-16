#!/usr/bin/env python3
"""EXP-20261016-75 描述：P1／P2 觸發改變、P4 備戰階段、P5 試閘速度覆蓋、P6 條件化方向。規格見 protocol。

    --dir D（入面有 base.json、P1.json、P2.json…）--out describe.json
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import au_jt_audit_eval_20261016 as ev  # noqa: E402


def prep_state(x):
    v = round(x["features"]["preparation_score"], 2)
    return "ok+T1" if v >= 64.0 else "ok" if v > 60.0 else "none"


def stratum(c):
    return "0" if not c else "1-5" if c <= 5 else "6+"


def stage(x):
    p = x["prep"]
    if not p["career"] or p["cycle"] in {"First-up", "久休復出"}:
        return "debut/first-up"
    if p["cycle"] in {"Second-up", "二出"}:
        return "second-up"
    return "later"


def boot_diff(races, key, a, b, strat, reps=2000):
    def stat(sample):
        acc = defaultdict(lambda: [0, 0.0, 0, 0.0])
        for race in sample:
            n = len(race["rows"])
            for x in race["rows"]:
                k = key(x); s = strat(x); e = ev.excess(x, n)
                if k == a:
                    acc[s][0] += 1; acc[s][1] += e
                elif k in b:
                    acc[s][2] += 1; acc[s][3] += e
        num = den = 0.0; per = {}
        for s, (na, ea, nb, eb) in acc.items():
            if na and nb:
                d = ea / na - eb / nb
                per[s] = {"a_n": na, "a_excess": round(ea / na, 4), "b_n": nb, "b_excess": round(eb / nb, 4), "diff": round(d, 4)}
                num += na * d; den += na
        return (num / den if den else float("nan")), per
    point, per = stat(races)
    rng = random.Random(7)
    s = sorted(stat([races[rng.randrange(len(races))] for _ in races])[0] for _ in range(reps))
    return {"weighted_diff": round(point, 4), "ci": [round(s[50], 4), round(s[reps - 51], 4)], "per_stratum": per}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True); ap.add_argument("--out", required=True)
    args = ap.parse_args()
    d = Path(args.dir)
    base = ev.load(d / "base.json")
    rows = [x for r in base for x in r["rows"]]
    out = {"races": len(base), "runners": len(rows),
           "prep_state": {k: sum(prep_state(x) == k for x in rows) for k in ("none", "ok", "ok+T1")}}
    # P6 direction
    out["P6_trial_ok_vs_none"] = boot_diff(base, prep_state, "ok", {"none"}, lambda x: stratum(x["prep"]["career"]))
    out["P6_T1_among_ok"] = boot_diff(base, prep_state, "ok+T1", {"ok"}, lambda x: stratum(x["prep"]["career"]))
    # P4 stage
    cells = defaultdict(lambda: [0, 0.0])
    for r in base:
        n = len(r["rows"])
        for x in r["rows"]:
            k = f"{stage(x)} | {'trial ok' if prep_state(x) != 'none' else 'no'}"
            cells[k][0] += 1; cells[k][1] += ev.excess(x, n)
    out["P4"] = {k: {"n": v[0], "excess": round(v[1] / v[0], 4)} for k, v in sorted(cells.items())}
    # P5 coverage
    with_trials = [x for x in rows if (x["prep"]["trial_count"] or 0) > 0]
    out["P5"] = {"runners_with_trials": len(with_trials),
                 "with_trial_speed": sum(1 for x in with_trials if x["prep"]["trial_speed"] not in (None, "", 0)),
                 "coverage": round(sum(1 for x in with_trials if x["prep"]["trial_speed"] not in (None, "", 0)) / max(1, len(with_trials)), 4)}
    # P1/P2 how many runners change trial-ok state
    for v in ("P1", "P2", "P3", "P4", "P6a", "P6b"):
        p = d / f"{v}.json"
        if not p.exists():
            continue
        other = {(r["meeting"], r["race"], x["n"]): prep_state(x) for r in ev.load(p) for x in r["rows"]}
        changed = defaultdict(int)
        for r in base:
            for x in r["rows"]:
                o = other.get((r["meeting"], r["race"], x["n"]))
                if o and o != prep_state(x):
                    changed[f"{prep_state(x)}→{o}"] += 1
        out[f"changes_{v}"] = dict(changed)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
