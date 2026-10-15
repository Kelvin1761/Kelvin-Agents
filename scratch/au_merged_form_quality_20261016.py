#!/usr/bin/env python3
"""EXP-20261016-06：近績分 + 表現質素分合併。規格見 protocol —— 唔准喺度改。

    constants  只用 run_date < 2026-08-05 嘅往績計 μ／σ（冇賽果標籤）
    build      砌 4 個候選 dump（form／PQ 設成合併 leaf，production 算術重算 ability）
    leaf       合併 stability vs 而家 stability 嘅場內配對 AUC（Holm 跨 4 候選）
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
for p in (SCRIPTS, SCRIPTS.parents[2] / "shared_racing", HERE):
    sys.path.insert(0, str(p))

CUT = "2026-08-05"
WEIGHTS = {"N4": (1.0, 0.8, 0.6, 0.4), "N6": (1.0, 0.8, 0.6, 0.4, 0.3, 0.2)}
CANDIDATES = ("eq3_N4", "eq3_N6", "eq2_N4", "eq2_N6")


def pct(run):
    f, n = int(run.get("finish_pos") or 0), int(run.get("starters") or 0)
    return (f - 1) / (n - 1) if n >= 2 and 1 <= f <= n else None


def constants(dump):
    seen = {}
    for race in dump["races"]:
        for row in race["rows"]:
            for run in row.get("pq_runs6") or []:
                if run["date"] < CUT and pct(run) is not None:
                    seen[(row["name"], run["date"])] = run
    runs = list(seen.values())
    pcts = [pct(r) for r in runs]
    margins = [min(20.0, abs(float(r["margin"]))) for r in runs]
    prizes = [math.log10(float(r["prize"])) for r in runs]
    return {"runs": len(runs),
            "sd_pct": statistics.pstdev(pcts),
            "mu_m": statistics.mean(margins), "sd_m": statistics.pstdev(margins),
            "mu_p": statistics.mean(prizes), "sd_p": statistics.pstdev(prizes)}


def run_value(run, c, kind):
    p = pct(run)
    if p is None:
        return None
    zp = (0.5 - p) / c["sd_pct"]
    zc = (math.log10(float(run["prize"])) - c["mu_p"]) / c["sd_p"]
    if kind == "eq2":
        return (zp + zc) / 2
    zm = -(min(20.0, abs(float(run["margin"]))) - c["mu_m"]) / c["sd_m"]
    return (zp + zm + zc) / 3


def raw_score(runs, c, kind, n):
    vals = [v for v in (run_value(r, c, kind) for r in runs[:n]) if v is not None]
    if len(vals) < 2:
        return None
    w = WEIGHTS[f"N{n}"][: len(vals)]
    return sum(v * x for v, x in zip(vals, w)) / sum(w)


def current_stability(f):
    return 60 + 0.6 * (f["form_score"] - 60) + 0.4 * (f["performance_quality_score"] - 60)


def merged_leaves(race, c, cand):
    kind, n = cand.split("_N")[0], int(cand.split("_N")[1])
    raws = [raw_score(r.get("pq_runs6") or [], c, kind, n) for r in race["rows"]]
    obs = [v for v in raws if v is not None]
    if len(obs) >= 3 and statistics.pstdev(obs) > 0:
        mu, sd = statistics.mean(obs), statistics.pstdev(obs)
        zs = [None if v is None else max(0.0, min(100.0, 60 + 20 * (v - mu) / sd)) for v in raws]
    else:
        zs = [None] * len(raws)
    return [current_stability(r["features"]) if z is None else z for r, z in zip(race["rows"], zs)], \
           [z is not None for z in zs]


def cmd_build(args):
    from au_racing_engine.scoring import MATRIX_WEIGHTS
    from au_walkforward_refit import exact_score
    dump = json.loads(Path(args.dump).read_text(encoding="utf-8"))
    c = constants(dump)
    Path(args.outdir).mkdir(parents=True, exist_ok=True)
    (Path(args.outdir) / "constants.json").write_text(json.dumps(c, indent=1))
    print("constants", c)
    for cand in CANDIDATES:
        races, covered, total = [], 0, 0
        for race in dump["races"]:
            leaves, mask = merged_leaves(race, c, cand)
            rows = []
            for row, leaf, m in zip(race["rows"], leaves, mask):
                feats = dict(row["features"])
                feats["form_score"] = feats["performance_quality_score"] = round(leaf, 6)
                new = {**row, "features": feats}
                new["ability"] = exact_score(new, MATRIX_WEIGHTS)
                rows.append(new)
                covered += m and race["date"] >= CUT
                total += race["date"] >= CUT
            races.append({**race, "rows": rows})
        (Path(args.outdir) / f"{cand}.json").write_text(json.dumps({"races": races}))
        print(f"{cand}: clean-window merged coverage {covered}/{total} = {covered / max(1, total):.3f}")


def cmd_leaf(args):
    import au_sb_total_speed_gates_20261016 as g
    from model_evaluation_decision import holm_adjust
    dump = json.loads(Path(args.dump).read_text(encoding="utf-8"))
    c = json.loads((Path(args.outdir) / "constants.json").read_text())
    races = [r for r in dump["races"] if r["date"] >= CUT
             and sum(x["pos"] <= 3 for x in r["rows"]) >= 3 and any(x["pos"] == 1 for x in r["rows"])]
    base = g.day_auc([(r["date"], [(current_stability(x["features"]), x["pos"] <= 3) for x in r["rows"]])
                      for r in races])
    out, pvals = {"auc_current_stability": round(g.auc(base), 5)}, {}
    for cand in CANDIDATES:
        items = []
        for r in races:
            leaves, _m = merged_leaves(r, c, cand)
            items.append((r["date"], [(lv, x["pos"] <= 3) for lv, x in zip(leaves, r["rows"])]))
        d = g.day_auc(items)
        lo, hi = g.boot(d, base)
        delta = g.auc(d) - g.auc(base)
        # two-sided bootstrap p from the same resamples
        import random
        days = sorted(d); rng = random.Random(7); s = []
        for _ in range(2000):
            pick = [days[rng.randrange(len(days))] for _ in days]
            s.append(g.auc(d, pick) - g.auc(base, pick))
        p = min(1.0, 2 * min(sum(x <= 0 for x in s), sum(x >= 0 for x in s)) / 2000)
        out[cand] = {"auc": round(g.auc(d), 5), "delta": round(delta, 5), "ci": [round(lo, 5), round(hi, 5)], "p": p}
        pvals[cand] = p
    for k, v in holm_adjust(pvals).items():
        out[k]["p_holm"] = round(v, 4)
    Path(args.out).write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("build", "leaf"):
        s = sub.add_parser(name)
        s.add_argument("--dump", required=True)
        s.add_argument("--outdir", required=True)
        if name == "leaf":
            s.add_argument("--out", required=True)
    args = ap.parse_args()
    {"build": cmd_build, "leaf": cmd_leaf}[args.cmd](args)


if __name__ == "__main__":
    main()
