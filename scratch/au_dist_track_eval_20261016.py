#!/usr/bin/env python3
"""EXP-20261016-71 描述（D1 增減程、D2 往績路程相關度）同 F2 資格判斷。規格見 protocol。

    describe --dump none.json --out describe.json
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import au_jt_audit_eval_20261016 as ev  # noqa: E402


def dist(v):
    m = re.search(r"(\d{3,4})", str(v or ""))
    return float(m.group(1)) if m else None


def band_delta(d):
    if d <= -400: return "≤-400"
    if d <= -200: return "-399..-200"
    if d < 200: return "±199"
    if d < 400: return "+200..+399"
    return "≥+400"


def layer(rank):
    return "rank1-3" if rank <= 3 else "rank4-6" if rank <= 6 else "rank7+"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True); ap.add_argument("--out", required=True)
    args = ap.parse_args()
    races = ev.load(args.dump)
    raw = defaultdict(lambda: [0, 0.0]); lay = defaultdict(lambda: [0, 0.0])
    per_race = []   # [(layer, is_big, excess)] for F2 bootstrap
    for r in races:
        n = len(r["rows"]); today = dist(r["rows"][0]["dist"]["today"])
        ranked = sorted(r["rows"], key=lambda x: (-x["ability"], x["n"]))
        cells = []
        for i, x in enumerate(ranked, 1):
            runs = x["dist"]["fq_runs"]
            if not runs or today is None or dist(runs[0].get("distance")) is None:
                continue
            d = today - dist(runs[0]["distance"]); b = band_delta(d); e = ev.excess(x, n)
            raw[b][0] += 1; raw[b][1] += e
            lay[(layer(i), b)][0] += 1; lay[(layer(i), b)][1] += e
            cells.append((layer(i), abs(d) >= 400, e))
        per_race.append(cells)

    def big_residual(sample):
        tot = defaultdict(lambda: [0, 0.0]); big = defaultdict(lambda: [0, 0.0])
        for cells in sample:
            for l, isbig, e in cells:
                tot[l][0] += 1; tot[l][1] += e
                if isbig:
                    big[l][0] += 1; big[l][1] += e
        num = den = 0.0
        for l, (nb, eb) in big.items():
            mean = tot[l][1] / tot[l][0]
            num += nb * (eb / nb - mean); den += nb
        return num / den if den else float("nan")
    point = big_residual(per_race)
    rng = random.Random(7)
    s = sorted(big_residual([per_race[rng.randrange(len(per_race))] for _ in per_race]) for _ in range(2000))
    d1 = {"raw": {k: {"n": v[0], "excess": round(v[1] / v[0], 4)} for k, v in sorted(raw.items())},
          "within_model_rank": {f"{k[0]}|{k[1]}": {"n": v[0], "excess": round(v[1] / v[0], 4)} for k, v in sorted(lay.items())},
          "big_change_residual": {"point": round(point, 4), "ci": [round(s[50], 4), round(s[1949], 4)]}}
    d1["F2_eligible"] = d1["big_change_residual"]["ci"][1] < 0

    # D2: per band, within-race AUC of the most recent run value in that band (placed vs unplaced)
    def bandgap(g):
        return "≤200" if g <= 200 else "201-400" if g <= 400 else ">400"
    d2 = {}
    for target in ("≤200", "201-400", ">400"):
        num = den = 0.0; cnt = 0
        for r in races:
            n = len(r["rows"]); today = dist(r["rows"][0]["dist"]["today"])
            if today is None: continue
            vals = []
            for x in r["rows"]:
                for run in x["dist"]["fq_runs"]:
                    rd = dist(run.get("distance"))
                    if rd is not None and bandgap(abs(rd - today)) == target and run.get("value") is not None:
                        vals.append((x["pos"] <= ev.paid(n), run["value"])); break
            pos = [v for p, v in vals if p]; neg = [v for p, v in vals if not p]
            cnt += len(vals)
            for a in pos:
                for b in neg:
                    num += 1 if a > b else 0.5 if a == b else 0; den += 1
        d2[target] = {"runners": cnt, "auc": round(num / den, 4) if den else None}
    out = {"races": len(races), "D1": d1, "D2": d2}
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
