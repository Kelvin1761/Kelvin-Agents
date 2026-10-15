#!/usr/bin/env python3
"""EXP-20261016-08：砌 L600 候選 dump（P1–P6）同跑包尾指標。規格見 protocol —— 唔准喺度改。

    build  --dump base.json --asb asb.json --outdir D   → D/{A0r,P1..P6}.json
    flops  --base X.json --cand Y.json                    → 跑包尾指標 Δ（賽日 bootstrap）
"""
from __future__ import annotations

import argparse
import json
import random
import re
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
for p in (SCRIPTS, HERE):
    sys.path.insert(0, str(p))

CUT = "2026-08-05"


# ── replica PF（同 production `_pace_figure_score`：own 優先、場內 ≥3、否則 race-level、60 − 20z）──
def runner_values(runs, spl=0.17, keep=None):
    runs = [r for r in runs if keep is None or keep(r)]
    own = [float(r["l600_delta"]) + float(r["margin"]) * spl for r in runs
           if r.get("source") == "sportsbet_race_context" and r.get("l600_delta") is not None
           and r.get("margin") is not None]
    race = [float(r["l600_delta"]) for r in runs if r.get("l600_delta") is not None]
    return (statistics.mean(own) if own else None), (statistics.mean(race) if race else None), len(own) or len(race)


def replica_pf(rows, spl=0.17, keep=None, shrink=False):
    vals = [runner_values(r.get("pf_run_list") or [], spl, keep) for r in rows]
    own_f = [o for o, _, _ in vals if o is not None]
    race_f = [x for _, x, _ in vals if x is not None]
    out = []
    for own, race, n in vals:
        if own is not None and len(own_f) >= 3:
            v, f = own, own_f
        elif race is not None and len(race_f) >= 3:
            v, f = race, race_f
        else:
            out.append(60.0)
            continue
        mu, sd = statistics.mean(f), statistics.pstdev(f)
        if sd <= 0:
            out.append(60.0)
            continue
        score = max(0.0, min(100.0, 60 - 20 * (v - mu) / sd))
        if shrink:
            score = 60 + (score - 60) * n / (n + 3)
        out.append(score)
    return out


def competitive(run):
    m = run.get("margin")
    f, n = run.get("finish"), run.get("starters")
    pct_ok = bool(f and n and n >= 2 and (f - 1) / (n - 1) <= 0.5)
    return (m is not None and float(m) <= 4.0) or pct_ok


def zscores(values):
    obs = [v for v in values if v is not None]
    if len(obs) < 2 or statistics.pstdev(obs) == 0:
        return [0.0] * len(values)
    mu, sd = statistics.mean(obs), statistics.pstdev(obs)
    return [max(-3.0, min(3.0, (v - mu) / sd)) if v is not None else 0.0 for v in values]


def cmd_build(args):
    from au_racing_engine.scoring import MATRIX_WEIGHTS
    from au_walkforward_refit import exact_score
    dump = json.loads(Path(args.dump).read_text(encoding="utf-8"))
    asb = json.loads(Path(args.asb).read_text(encoding="utf-8"))["asb"]
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)

    def arm(name, fn):
        races = []
        for race in dump["races"]:
            new_pf = fn(race)
            rows = []
            for row, pf in zip(race["rows"], new_pf):
                feats = dict(row["features"])
                feats["pace_figure_score"] = round(pf, 6)
                r = {**row, "features": feats}
                r["ability"] = exact_score(r, MATRIX_WEIGHTS)
                rows.append(r)
            races.append({**race, "rows": rows})
        (out / f"{name}.json").write_text(json.dumps({"races": races}))
        print("built", name, flush=True)

    engine_pf = lambda race: [r["features"]["pace_figure_score"] for r in race["rows"]]  # noqa: E731
    arm("A0", engine_pf)                                         # engine baseline, ability re-derived
    arm("A0r", lambda race: replica_pf(race["rows"]))
    arm("P1", lambda race: [60.0] * len(race["rows"]))
    arm("P2", lambda race: replica_pf(race["rows"], spl=0.34))
    arm("P3", lambda race: replica_pf(race["rows"], keep=competitive))
    arm("P4", lambda race: [pf if pf <= 60 else 60 + min(pf - 60, max(0.0, r["features"]["form_quality_score"] - 60))
                            for pf, r in zip(engine_pf(race), race["rows"])])

    def p5(race):
        raws = []
        for r in race["rows"]:
            d = asb.get(f"{race['date']}|{race['meeting']}|{race['race']}|{r['n']}")
            raws.append(d["raw"] if d and d["raw"] is not None else None)
        return [60 + 10 * z for z in zscores(raws)]
    arm("P5", p5)
    arm("P6", lambda race: replica_pf(race["rows"], shrink=True))


# ── 跑包尾指標 ───────────────────────────────────────────────────────────
def sp(row):
    try:
        return float(str(row.get("sp")).replace("$", ""))
    except (TypeError, ValueError):
        return None


def flop_rows(races):
    """{date: [(top2_bottom, longshot_top2_bottom, top1_bottom)]} per race."""
    out = {}
    for race in races:
        n = len(race["rows"])
        ranked = sorted(race["rows"], key=lambda x: (-x["ability"], x["n"]))
        bottom = lambda x: x["pos"] > n - n // 3  # noqa: E731
        t2 = sum(bottom(x) for x in ranked[:2]) / 2
        ls = sum(bottom(x) and (sp(x) or 0) >= 15 for x in ranked[:2])
        t1 = float(bottom(ranked[0]))
        out.setdefault(race["date"], []).append((t2, ls, t1))
    return out


def load(path):
    races = [r for r in json.loads(Path(path).read_text(encoding="utf-8"))["races"]
             if r["date"] >= CUT and sum(x["pos"] <= 3 for x in r["rows"]) >= 3
             and any(x["pos"] == 1 for x in r["rows"])]
    return {(r["meeting"], r["race"]): r for r in races}


def cmd_flops(args):
    base, cand = load(args.base), load(args.cand)
    keys = sorted(set(base) & set(cand))
    fb = flop_rows([base[k] for k in keys])
    fc = flop_rows([cand[k] for k in keys])
    days = sorted(fb)
    res = {}
    for i, name in enumerate(("top2_bottom_third_rate", "longshot15_top2_bottom_count", "top1_bottom_third_rate")):
        def stat(pick, f):
            vals = [row[i] for d in pick for row in f[d]]
            return sum(vals) if i == 1 else sum(vals) / len(vals)
        point = stat(days, fc) - stat(days, fb)
        rng = random.Random(7)
        s = sorted(stat(p, fc) - stat(p, fb) for p in
                   ([days[rng.randrange(len(days))] for _ in days] for _ in range(2000)))
        pval = min(1.0, 2 * min(sum(x <= 0 for x in s), sum(x >= 0 for x in s)) / len(s))
        res[name] = {"base": round(stat(days, fb), 4), "cand": round(stat(days, fc), 4),
                     "delta": round(point, 4), "ci": [round(s[50], 4), round(s[1949], 4)], "p": pval}
    print(json.dumps({"label": args.label, "races": len(keys), **res}, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--dump", required=True)
    b.add_argument("--asb", required=True)
    b.add_argument("--outdir", required=True)
    f = sub.add_parser("flops")
    f.add_argument("--base", required=True)
    f.add_argument("--cand", required=True)
    f.add_argument("--label", default="")
    args = ap.parse_args()
    {"build": cmd_build, "flops": cmd_flops}[args.cmd](args)


if __name__ == "__main__":
    main()
