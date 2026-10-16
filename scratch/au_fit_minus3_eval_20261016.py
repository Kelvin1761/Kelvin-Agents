#!/usr/bin/env python3
"""EXP-20261016-16：「配搭分 ≥72 而 class_score <58 → −3」方向審計。規格見 protocol —— 唔准喺度改。

    run --dump jt.json --outdir D   → D/describe.json、D/base.json、D/no_minus3.json
用 dump 嘅 `k2` 特徵做 production baseline（05dd1b20 起 K2 開）。
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / ".agents/skills/au_racing/au_wong_choi_auto/scripts"))
sys.path.insert(0, str(HERE))
import au_jt_audit_eval_20261016 as ev  # noqa: E402


def pre_fit(row):
    """搬走試閘之前、未行 −3 嘅配搭分（規則睇嘅就係呢個數）。"""
    pair = [a["delta"] for a in row["jt"]["fit_adjustments"] if a["delta"]]
    trial = row["features"]["preparation_score"] - 60.0
    if not pair and not trial:
        return ev.NO_EVIDENCE
    return max(0.0, min(100.0, 60.0 + sum(pair) + trial))


def fit(row, minus3=True):
    pair = [a["delta"] for a in row["jt"]["fit_adjustments"] if a["delta"]]
    trial = row["features"]["preparation_score"] - 60.0
    evidence = bool(pair) or bool(trial)
    raw = pre_fit(row)
    if minus3 and raw >= 72 and row["features"]["class_score"] < 58:
        raw -= 3
    if evidence:
        raw -= trial
    return max(0.0, min(100.0, raw))


def did(races, seed=7, reps=2000):
    def cell(sample):
        acc = {}
        for race in sample:
            n = len(race["rows"])
            for x in race["rows"]:
                f = pre_fit(x)
                band = "hi" if f >= 72 else "near" if f >= 64 else None
                if band is None:
                    continue
                weak = "weak" if x["features"]["class_score"] < 58 else "ok"
                a = acc.setdefault((weak, band), [0, 0.0])
                a[0] += 1; a[1] += ev.excess(x, n)
        m = {k: v[1] / v[0] for k, v in acc.items() if v[0]}
        return acc, (m[("weak", "hi")] - m[("weak", "near")]) - (m[("ok", "hi")] - m[("ok", "near")])
    acc, point = cell(races)
    rng = random.Random(seed)
    s = sorted(cell([races[rng.randrange(len(races))] for _ in races])[1] for _ in range(reps))
    return {"cells": {f"{k[0]}|{k[1]}": {"n": v[0], "excess": round(v[1] / v[0], 4)} for k, v in sorted(acc.items())},
            "did": round(point, 4), "ci": [round(s[50], 4), round(s[reps - 51], 4)]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()
    from au_racing_engine.scoring import MATRIX_WEIGHTS
    from au_walkforward_refit import exact_score
    out = Path(args.outdir); out.mkdir(parents=True, exist_ok=True)
    dump = json.loads(Path(args.dump).read_text(encoding="utf-8"))
    races = []
    for race in dump["races"]:
        rows = [{"n": x["n"], "name": x["name"], "pos": x["pos"], "sp": x["sp"], "jt": x["jt"],
                 **{k: x["k2"][k] for k in ("features", "wet", "proven_class", "full_time", "ability")}}
                for x in race["rows"]]
        races.append({**{k: v for k, v in race.items() if k != "rows"}, "rows": rows})
    clean = [r for r in races if r["date"] >= ev.CUT and sum(x["pos"] <= 3 for x in r["rows"]) >= 3
             and any(x["pos"] == 1 for x in r["rows"])]
    gap = max(abs(fit(x) - x["features"]["jockey_horse_fit_score"]) for r in clean for x in r["rows"])
    abgap = max(abs(exact_score(x, MATRIX_WEIGHTS) - x["ability"]) for r in clean for x in r["rows"])
    if gap > 1e-3 or abgap > 1e-3:
        raise SystemExit(f"recompute mismatch fit {gap} ability {abgap} — stop")
    trig = sum(1 for r in clean for x in r["rows"] if pre_fit(x) >= 72 and x["features"]["class_score"] < 58)
    desc = {"races": len(clean), "fit_gap": gap, "ability_gap": abgap, "triggered": trig, **did(clean)}
    (out / "describe.json").write_text(json.dumps(desc, ensure_ascii=False, indent=1))
    print(json.dumps(desc, ensure_ascii=False, indent=1))

    def arm(name, minus3):
        rs = []
        for race in races:
            rows = []
            for x in race["rows"]:
                r = {k: v for k, v in x.items() if k != "jt"}
                r["features"] = {**x["features"], "jockey_horse_fit_score": round(fit(x, minus3), 6)}
                r["ability"] = exact_score(r, MATRIX_WEIGHTS)
                rows.append(r)
            rs.append({**{k: v for k, v in race.items() if k != "rows"}, "rows": rows})
        (out / f"{name}.json").write_text(json.dumps({"races": rs}))
    arm("base", True)
    arm("no_minus3", False)


if __name__ == "__main__":
    main()
