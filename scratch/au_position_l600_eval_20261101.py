#!/usr/bin/env python3
"""EXP-20261101-40 arm 產生器（base／P）+ RQ holdout 準確度。規格見 protocol —— 唔准喺度改。

    python3 au_position_l600_eval_20261101.py --dump dump_pos.json --training training.json --outdir ARMS
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SCRIPTS))
from au_racing_engine import speed  # noqa: E402
from au_racing_engine.scoring import MATRIX_WEIGHTS  # noqa: E402
from au_walkforward_refit import exact_score  # noqa: E402

MIN_TRAIN = 2000
KEEP = ("n", "name", "pos", "sp", "wet", "proven_class", "full_time")


def features(r):
    n = r.get("starters"); fin = r.get("finish"); m = r.get("margin")
    if m is None or not n or n < 2 or not fin:
        return None
    m = float(m)
    p4 = (r["pos_400"] - 1) / (n - 1) if r.get("pos_400") else 0.5
    p8 = (r["pos_800"] - 1) / (n - 1) if r.get("pos_800") else 0.5
    return [1.0, m, m * m, p4, p8, p4 * m, (fin - 1) / (n - 1), float(r.get("pos_400") is None)]


def fit(rows):
    A = np.array([features(r) for r in rows]); y = np.array([r["y"] for r in rows])
    return np.linalg.lstsq(A, y, rcond=None)[0]


def horse_values(runs, horse_source, beta):
    ordered = sorted(runs, key=lambda run: str(run.get("run_date") or ""), reverse=True)
    own, race = [], []
    for k, run in enumerate(ordered):
        w = speed.RECENCY_DECAY ** k
        o, r = speed.run_values(run, horse_source)
        if o is not None and beta is not None:
            x = features(run)
            if x is not None:
                o = round(r + float(np.array(x) @ beta), 4)
        if o is not None:
            own.append((w, o))
        if r is not None:
            race.append((w, r))
    return speed.HorseSpeed(speed.weighted_mean(own), speed.weighted_mean(race), len(runs))


CLEAN = "2026-08-05"


def build(race, beta):
    # 2026-08-05 之前係 Racenet 年代（馬匹整體 source 唔係 Sportsbet，dump 冇帶），判決窗亦唔用 ——
    # 兩個 arm 都原封用引擎分數（harness 修正，唔係候選改動）。
    clean = race["date"] >= CLEAN
    if clean:
        field = {n: horse_values(runs, speed.SPORTSBET, beta) for n, runs in race["pf_field"].items()}
        scores = speed.field_scores(field)
    rows = []
    for x in race["rows"]:
        r = {k: x[k] for k in KEEP}
        pf = round(scores[str(x["n"])].score, 6) if clean else x["features"]["pace_figure_score"]
        r["features"] = {**x["features"], "pace_figure_score": pf}
        r["ability"] = exact_score(r, MATRIX_WEIGHTS)
        rows.append(r)
    d = race["rows"][0].get("distance")
    try:
        d = float(str(d).rstrip("m"))
    except (TypeError, ValueError):
        d = None
    top = min(range(len(race["rows"])), key=lambda i: (-race["rows"][i]["ability"], race["rows"][i]["n"]))
    style = str(race["rows"][top].get("style") or "")[:2] or "?"
    tags = {"distance": None if not d else "<=1200" if d <= 1200 else "1201-1600" if d <= 1600 else ">1600",
            "fallback_share": 0.0, "top_style": style}
    return {**{k: v for k, v in race.items() if k not in ("rows", "pf_field", "fq_field")}, "tags": tags, "rows": rows}


def main():
    ap = argparse.ArgumentParser()
    for a in ("--dump", "--training", "--outdir"):
        ap.add_argument(a, required=True)
    args = ap.parse_args()
    out = Path(args.outdir); out.mkdir(parents=True, exist_ok=True)
    dump = json.loads(Path(args.dump).read_text())["races"]
    train = [r for r in json.loads(Path(args.training).read_text()) if features(r) is not None]

    # replica：beta=None → 現行公式；必須同引擎一致（own 只用 Sportsbet 來源，同 A/A 一樣）
    gaps = 0
    for race in dump:
        b = build(race, None)
        gaps += sum(abs(y["features"]["pace_figure_score"] - x["features"]["pace_figure_score"]) > 1e-6
                    for x, y in zip(race["rows"], b["rows"]))
    print("replica rows off:", gaps, flush=True)
    if gaps:
        raise SystemExit("replica does not reproduce the engine — stop")

    betas, fallback = {}, 0
    for date in sorted({r["date"] for r in dump}):
        prior = [r for r in train if r["date"] < date]
        betas[date] = fit(prior) if len(prior) >= MIN_TRAIN else None
        fallback += betas[date] is None
    print("dates", len(betas), "fallback dates (<2000 train rows)", fallback, flush=True)

    arms = {"base": [build(r, None) for r in dump], "P": [build(r, betas[r["date"]]) for r in dump]}
    for name, built in arms.items():
        (out / f"{name}.json").write_text(json.dumps({"races": built}))
    changed = sum(1 for a, b in zip(arms["base"], arms["P"]) if [x["ability"] for x in a["rows"]] != [x["ability"] for x in b["rows"]])
    print("races changed", changed, flush=True)

    # RQ holdout：每個目標日只用之前數據 fit，量場內 Spearman（現行 vs P）
    by_race = defaultdict(list)
    for r in train:
        by_race[(r["date"], r["race"])].append(r)
    cur_s, new_s = [], []
    cache = {}
    for (date, _), rs in by_race.items():
        if len(rs) < 4 or date < "2026-01-01":
            continue
        if date not in cache:
            prior = [r for r in train if r["date"] < date]
            cache[date] = fit(prior) if len(prior) >= MIN_TRAIN else None
        beta = cache[date]
        if beta is None:
            continue
        truth = np.argsort(np.argsort([r["true"] for r in rs]))
        for est, acc in ((lambda r: r["raw"] + 0.17 * r["margin"], cur_s),
                         (lambda r, b=beta: r["raw"] + float(np.array(features(r)) @ b), new_s)):
            e = np.argsort(np.argsort([est(r) for r in rs]))
            if e.std() > 0 and truth.std() > 0:
                acc.append(float(np.corrcoef(e, truth)[0, 1]))
    desc = {"rq_holdout_races": len(new_s), "rq_spearman_current": round(st.mean(cur_s), 4),
            "rq_spearman_position": round(st.mean(new_s), 4), "fallback_dates": fallback, "races_changed": changed,
            "final_beta": dict(zip(["const", "margin", "margin2", "p400", "p800", "p400xm", "finish", "no_pos"],
                                   [round(float(v), 4) for v in fit(train)]))}
    print(json.dumps(desc, indent=1), flush=True)
    (out / "describe.json").write_text(json.dumps(desc, indent=1))


if __name__ == "__main__":
    main()
