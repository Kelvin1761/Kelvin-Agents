#!/usr/bin/env python3
"""EXP-20261016-12／-13：騎練訊號審計同 K2 嘅描述量度 + 候選 arm。規格見 protocol —— 唔准喺度改。

    describe --dump jt.json --out describe.json      J1／J2／J3／J5／J6 描述 + baseline 重算核對
    build    --dump jt.json --outdir D                → D/{base,J1x,J2x-best,J2x-same,J2x-trial,J3x,J5a,J5b,K2}.json
    flops    --base X.json --cand Y.json             頭兩名 $15+ 跑尾三分一（賽日 bootstrap）
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SCRIPTS))

CUT = "2026-08-05"
TRIAL = ("試閘交代密度足夠", "備戰同騎練配置方向一致")
SIGNALS = {"best": "沿用歷來最佳人馬配搭", "same": "沿用上仗騎師，部署連貫", "trial": "試閘手接手，備戰線完整"}
CURRENT = "現役騎師曾策騎此駒"
NO_EVIDENCE = 58.0


def load(path):
    races = [r for r in json.loads(Path(path).read_text(encoding="utf-8"))["races"]
             if r["date"] >= CUT and sum(x["pos"] <= 3 for x in r["rows"]) >= 3
             and any(x["pos"] == 1 for x in r["rows"])]
    return sorted(races, key=lambda r: (r["date"], r["meeting"], r["race"]))


def fit(row, drop=lambda f: False, no_evidence=NO_EVIDENCE, trial_counts=True):
    """人馬配搭分，同引擎次序（修訂 1）：60 + 全部加分（含試閘）或點位 → ≥72 而 class_score<58 −3
    → 減 (preparation − 60) → clip。`trial_counts=False` = 只得試閘證據都當冇證據（J1x／J5）。"""
    pair = [a["delta"] for a in row["jt"]["fit_adjustments"] if a["delta"] and not drop(a["factor"])]
    trial = row["features"]["preparation_score"] - 60.0
    evidence = bool(pair) or (trial_counts and bool(trial))
    raw = max(0.0, min(100.0, 60.0 + sum(pair) + trial)) if evidence else no_evidence
    if raw >= 72 and row["features"]["class_score"] < 58:
        raw -= 3
    if evidence:
        raw -= trial
    return max(0.0, min(100.0, raw))


def paid(n):
    return 3 if n >= 8 else 2


def excess(row, n):
    return float(row["pos"] <= paid(n)) - paid(n) / n


def stratum(rides):
    return "0" if rides == 0 else "1-2" if rides <= 2 else "3+"


# ── describe ──────────────────────────────────────────────────────────────
def boot_diff(cells, key_fn, rng_seed=7, reps=2000):
    """cells: list of races, each a list of (stratum, triggered, excess). Weighted (by triggered n)
    within-stratum difference triggered − not, resampling races."""
    def stat(sample):
        acc = {}
        for race in sample:
            for s, t, e in race:
                a = acc.setdefault(s, [0, 0.0, 0, 0.0])
                if t:
                    a[0] += 1; a[1] += e
                else:
                    a[2] += 1; a[3] += e
        num = den = 0.0
        per = {}
        for s, (nt, et, nn, en) in acc.items():
            if nt and nn:
                d = et / nt - en / nn
                per[s] = {"trig_n": nt, "trig_excess": round(et / nt, 4), "not_n": nn,
                          "not_excess": round(en / nn, 4), "diff": round(d, 4)}
                num += nt * d; den += nt
        return (num / den if den else float("nan")), per
    point, per = stat(cells)
    rng = random.Random(rng_seed)
    samples = sorted(stat([cells[rng.randrange(len(cells))] for _ in cells])[0] for _ in range(reps))
    return {"weighted_diff": round(point, 4), "ci": [round(samples[50], 4), round(samples[reps - 51], 4)],
            "per_stratum": per}


def pair_auc(races, key):
    num = den = 0.0
    for race in races:
        n = len(race["rows"])
        pos = [x for x in race["rows"] if x["pos"] <= paid(n)]
        neg = [x for x in race["rows"] if x["pos"] > paid(n)]
        for a in pos:
            for b in neg:
                d = key(a) - key(b)
                num += 1.0 if d > 0 else 0.5 if d == 0 else 0.0
                den += 1
    return round(num / den, 4) if den else None


def cmd_describe(args):
    races = load(args.dump)
    rows = [x for r in races for x in r["rows"]]
    out = {"races": len(races), "runners": len(rows)}
    gap = max(abs(fit(x) - x["features"]["jockey_horse_fit_score"]) for x in rows)
    out["baseline_fit_recompute_max_gap"] = gap
    if gap > 1e-3:
        raise SystemExit(f"fit recompute does not reproduce the engine (max gap {gap}) — stop")

    has = lambda x, f: any(a["factor"] == f and a["delta"] for a in x["jt"]["fit_adjustments"])  # noqa: E731
    pairless = lambda x: not any(a["delta"] for a in x["jt"]["fit_adjustments"])  # noqa: E731
    trial_only = [excess(x, len(r["rows"])) for r in races for x in r["rows"]
                  if pairless(x) and x["features"]["preparation_score"] != 60.0]
    nothing = [excess(x, len(r["rows"])) for r in races for x in r["rows"]
               if pairless(x) and x["features"]["preparation_score"] == 60.0]
    out["J1"] = {"trial_only_at_60": {"n": len(trial_only), "excess": round(sum(trial_only) / len(trial_only), 4)},
                 "no_evidence_at_58": {"n": len(nothing), "excess": round(sum(nothing) / len(nothing), 4)}}
    out["J2"] = {}
    for key, factor in SIGNALS.items():
        cells = [[(stratum(x["jt"]["cur_rides"]), has(x, factor), excess(x, len(r["rows"]))) for x in r["rows"]]
                 for r in races]
        res = boot_diff(cells, None)
        res["trigger_rate"] = round(sum(has(x, factor) for x in rows) / len(rows), 4)
        lower = sum(1 for v in res["per_stratum"].values() if v["diff"] < 0)
        res["reversed"] = bool(lower >= 2 and res["ci"][1] < 0)
        out["J2"][key] = res
    j3 = {}
    for r in races:
        for x in r["rows"]:
            rides = x["jt"]["cur_rides"]
            if not rides:
                continue
            places = x["jt"]["cur_places"]
            cell = j3.setdefault(f"rides {stratum(rides)} | places {min(places, 3)}{'+' if places >= 3 else ''}", [0, 0.0])
            cell[0] += 1; cell[1] += excess(x, len(r["rows"]))
    out["J3"] = {k: {"n": n, "excess": round(e / n, 4)} for k, (n, e) in sorted(j3.items())}
    ne = [excess(x, len(r["rows"])) for r in races for x in r["rows"] if not any(a["delta"] for a in x["jt"]["fit_adjustments"])]
    ev = [excess(x, len(r["rows"])) for r in races for x in r["rows"] if any(a["delta"] for a in x["jt"]["fit_adjustments"])]
    out["J5"] = {"no_evidence": {"n": len(ne), "excess": round(sum(ne) / len(ne), 4)},
                 "with_evidence": {"n": len(ev), "excess": round(sum(ev) / len(ev), 4)}}
    out["J6"] = {k: pair_auc(races, lambda x, k=k: x["features"][k])
                 for k in ("jockey_score", "trainer_score", "jockey_horse_fit_score")}
    out["J6"]["shares"] = {"jockey_score": 0.333333, "trainer_score": 0.285714, "jockey_horse_fit_score": 0.380952}
    k2_moved = sum(1 for x in rows if abs(x["k2"]["ability"] - x["ability"]) > 1e-6)
    out["K2"] = {"runners_ability_moved": k2_moved,
                 "races_ability_moved": sum(1 for r in races if any(abs(x["k2"]["ability"] - x["ability"]) > 1e-6
                                                                     for x in r["rows"]))}
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))


# ── build arms ────────────────────────────────────────────────────────────
def cmd_build(args):
    from au_racing_engine.scoring import MATRIX_WEIGHTS
    from au_walkforward_refit import exact_score
    dump = json.loads(Path(args.dump).read_text(encoding="utf-8"))
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    keep = ("n", "name", "pos", "sp", "features", "wet", "proven_class", "full_time", "ability",
            "career_starts", "pf_run_list")

    def arm(name, fn):
        races = []
        for race in dump["races"]:
            rows = []
            for row in race["rows"]:
                r = fn({k: row.get(k) for k in keep} | {"jt": row["jt"], "k2": row["k2"]})
                r.pop("jt"); r.pop("k2")
                rows.append(r)
            races.append({**{k: v for k, v in race.items() if k != "rows"}, "rows": rows})
        (out / f"{name}.json").write_text(json.dumps({"races": races}))
        print("built", name, flush=True)

    def with_fit(**kw):
        def fn(row):
            feats = {**row["features"], "jockey_horse_fit_score": round(fit(row, **kw), 6)}
            r = {**row, "features": feats}
            r["ability"] = exact_score(r, MATRIX_WEIGHTS)
            return r
        return fn

    arm("base", with_fit())
    arm("J1x", with_fit(trial_counts=False))
    for key, factor in SIGNALS.items():
        arm(f"J2x-{key}", with_fit(drop=lambda f, factor=factor: f == factor))
    arm("J3x", with_fit(drop=lambda f: f.startswith(CURRENT)))
    arm("J5a", with_fit(no_evidence=60.0, trial_counts=False))
    arm("J5b", with_fit(no_evidence=56.0, trial_counts=False))
    arm("K2", lambda row: {**row, **{k: row["k2"][k] for k in ("features", "wet", "proven_class", "full_time")},
                           "ability": row["k2"]["ability"]})


# ── flops ─────────────────────────────────────────────────────────────────
def sp(row):
    try:
        return float(str(row.get("sp")).replace("$", ""))
    except (TypeError, ValueError):
        return None


def cmd_flops(args):
    base = {(r["meeting"], r["race"]): r for r in load(args.base)}
    cand = {(r["meeting"], r["race"]): r for r in load(args.cand)}
    keys = sorted(set(base) & set(cand))

    def per_day(src):
        out = {}
        for k in keys:
            race = src[k]
            n = len(race["rows"])
            top2 = sorted(race["rows"], key=lambda x: (-x["ability"], x["n"]))[:2]
            out.setdefault(race["date"], []).append(sum((sp(x) or 0) >= 15 and x["pos"] > n - n // 3 for x in top2))
        return out
    fb, fc = per_day(base), per_day(cand)
    days = sorted(fb)
    stat = lambda f, pick: sum(c for d in pick for c in f[d])  # noqa: E731
    rng = random.Random(7)
    s = sorted(stat(fc, p) - stat(fb, p) for p in ([days[rng.randrange(len(days))] for _ in days] for _ in range(2000)))
    print(json.dumps({"label": args.label, "races": len(keys), "base": stat(fb, days), "cand": stat(fc, days),
                      "delta": stat(fc, days) - stat(fb, days), "ci": [s[50], s[1949]]}, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("describe"); d.add_argument("--dump", required=True); d.add_argument("--out", required=True)
    b = sub.add_parser("build"); b.add_argument("--dump", required=True); b.add_argument("--outdir", required=True)
    f = sub.add_parser("flops"); f.add_argument("--base", required=True); f.add_argument("--cand", required=True)
    f.add_argument("--label", default="")
    args = ap.parse_args()
    {"describe": cmd_describe, "build": cmd_build, "flops": cmd_flops}[args.cmd](args)


if __name__ == "__main__":
    main()
