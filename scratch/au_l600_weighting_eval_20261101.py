#!/usr/bin/env python3
"""EXP-20261101-30 離線 replica 同 arm 產生器。規格見 protocol —— 唔准喺度改。

    python3 au_l600_weighting_eval_20261101.py --dump dump_base.json --outdir ARMS

1. replica：baseline 重算 `pace_figure_score` 同綜合分，同引擎差 > 1e-3／0.005 即停。
2. leaf 診斷（只報告）：場內配對 AUC，賽日 bootstrap；Trend 斜率診斷。
3. 寫 arm：base、R、P、RP。每場加 `tags` 畀分層用。
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SCRIPTS))
from au_racing_engine.scoring import MATRIX_WEIGHTS, clip_score  # noqa: E402
from au_walkforward_refit import exact_score  # noqa: E402

SEC_PER_LENGTH = 0.17   # engine_core._SEC_PER_LENGTH
DECAY = 0.8             # EXP-20261016-01 D3c
DIST_TAU = 0.25         # full_time_speed.aggregate
CUT = "2026-08-05"
BOOT, SEED = 2000, 7


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def run_weights(runs, arm, today):
    """runs newest first. → list of weights（同 runs 對齊）。"""
    out = []
    for k, run in enumerate(runs):
        w = 1.0
        if "R" in arm:
            w *= DECAY ** k
        if "P" in arm:
            d = _num(run.get("distance"))
            if d and d > 0 and today and today > 0:
                w *= math.exp(-abs(math.log(d / today)) / DIST_TAU)
        out.append(w)
    return out


def horse_values(runs, arm, today):
    """→ (own_x, race_x)，同 engine `_pf_aggregates` 一樣捨入到 3dp。"""
    runs = sorted(runs, key=lambda r: str(r.get("run_date") or ""), reverse=True)
    ws = run_weights(runs, arm, today)
    own, race = [], []
    for run, w in zip(runs, ws):
        base, margin = _num(run.get("l600_delta")), _num(run.get("margin"))
        if base is None:
            continue
        race.append((w, base))
        # 冇標記 source 嘅行跟馬匹整體 source（engine `_pf_aggregates`）；dump 入面只有
        # sportsbet 或者空，冇 mixed，所以空 = sportsbet。replica 會驗證。
        if run.get("source") in ("sportsbet_race_context", None) and margin is not None:
            own.append((w, round(base + margin * SEC_PER_LENGTH, 4)))

    def agg(pairs):
        tw = sum(w for w, _ in pairs)
        return round(sum(w * v for w, v in pairs) / tw, 3) if pairs and tw > 0 else None
    return agg(own), agg(race)


def field_pf(race, arm):
    """→ {horse_number: score or None(=engine 60 neutral)}，母體 = Logic 全部馬。"""
    today = None
    for x in race["rows"]:
        today = _num((x.get("pf") or {}).get("today_distance")) or today
    vals = {n: horse_values(runs, arm, today) for n, runs in race["pf_field"].items()}
    own_field = [o for o, _ in vals.values() if o is not None]
    race_field = [r for _, r in vals.values() if r is not None]

    def stats(values):
        m = sum(values) / len(values) if values else 0.0
        sd = (sum((v - m) ** 2 for v in values) / len(values)) ** 0.5 if len(values) > 1 else 0.0
        return m, sd
    om, osd = stats(own_field)
    rm, rsd = stats(race_field)
    out = {}
    for n, (own, rc) in vals.items():
        if own is not None and len(own_field) >= 3:
            v, m, sd = own, om, osd
        elif rc is not None and len(race_field) >= 3:
            v, m, sd = rc, rm, rsd
        else:
            out[n] = 60.0
            continue
        out[n] = 60.0 if sd <= 0 else clip_score(60 - (v - m) / sd * 20.0)
    return out


def build(race, arm):
    scores = field_pf(race, arm)
    rows = []
    for x in race["rows"]:
        feats = dict(x["features"])
        s = scores.get(str(x["n"]))
        if s is not None:
            feats["pace_figure_score"] = round(float(s), 6)
        r = {k: x[k] for k in ("n", "name", "pos", "sp", "wet", "proven_class", "full_time")}
        r["features"] = feats
        r["ability"] = exact_score(r, MATRIX_WEIGHTS)
        rows.append(r)
    top = min(range(len(rows)), key=lambda i: (-race["rows"][i]["ability"], race["rows"][i]["n"]))
    top_runs = len(race["pf_field"].get(str(race["rows"][top]["n"])) or [])
    today = _num((race["rows"][0].get("pf") or {}).get("today_distance"))
    tags = {"top_pf_runs": "0" if top_runs == 0 else "1-2" if top_runs <= 2 else "3-5" if top_runs <= 5 else "6+",
            "distance": None if not today else "<=1200" if today <= 1200 else "1201-1600" if today <= 1600 else ">1600"}
    return {**{k: v for k, v in race.items() if k not in ("rows", "pf_field", "fq_field")}, "tags": tags, "rows": rows}


def clean(races):
    return [r for r in races if r["date"] >= CUT and sum(x["pos"] <= 3 for x in r["rows"]) >= 3
            and any(x["pos"] == 1 for x in r["rows"])]


# ── leaf 診斷 ──────────────────────────────────────────────────────────────
def day_auc_parts(races, score_fn):
    days = {}
    for r in races:
        sc = score_fn(r)
        ok = [(sc[str(x["n"])], x["pos"] <= 3) for x in r["rows"]
              if str(x["n"]) in sc and sc[str(x["n"])] is not None]
        hit = tot = 0.0
        for a, pa in ok:
            for b, pb in ok:
                if pa and not pb:
                    tot += 1
                    hit += 1.0 if a > b else 0.5 if a == b else 0.0
        h, t = days.get(r["date"], (0.0, 0.0))
        days[r["date"]] = (h + hit, t + tot)
    return days


def paired(base, cand):
    days = sorted(set(base) & set(cand))
    def delta(ds):
        bh = sum(base[d][0] for d in ds); bt = sum(base[d][1] for d in ds)
        ch = sum(cand[d][0] for d in ds); ct = sum(cand[d][1] for d in ds)
        return ch / ct - bh / bt
    rng = random.Random(SEED)
    boots = sorted(delta([days[rng.randrange(len(days))] for _ in days]) for _ in range(BOOT))
    point = delta(days)
    p = 2 * min(sum(b <= 0 for b in boots), sum(b >= 0 for b in boots)) / BOOT
    return {"delta": round(point, 5), "ci": [round(boots[int(.025 * BOOT)], 5), round(boots[int(.975 * BOOT)], 5)],
            "p": round(min(1.0, p), 4)}


def leaf_scores_only_pf(race, arm):
    """Leaf AUC 只計有 PF 值嘅馬（同 EXP-20261016-01 診斷一致）。"""
    sc = field_pf(race, arm)
    return {n: (s if race["pf_field"].get(n) else None) for n, s in sc.items()}


def trend_scores(race):
    out = {}
    for n, runs in race["pf_field"].items():
        runs = sorted(runs, key=lambda r: str(r.get("run_date") or ""), reverse=True)
        vals = [(k, _num(r["l600_delta"]) + _num(r["margin"]) * SEC_PER_LENGTH) for k, r in enumerate(runs)
                if _num(r.get("l600_delta")) is not None and _num(r.get("margin")) is not None
                and r.get("source") in ("sportsbet_race_context", None)]
        if len(vals) < 3:
            out[n] = None
            continue
        mk = sum(k for k, _ in vals) / len(vals); mv = sum(v for _, v in vals) / len(vals)
        slope = sum((k - mk) * (v - mv) for k, v in vals) / sum((k - mk) ** 2 for k, _ in vals)
        out[n] = slope   # 正 = 越近越細（越快）= 改善
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    dump = json.loads(Path(args.dump).read_text(encoding="utf-8"))

    gaps = {"pace_figure_score": 0.0, "ability": 0.0, "rows_gt_1e-3": 0, "rows": 0}
    worst = None
    for r in clean(dump["races"]):
        b = build(r, "")
        for x, y in zip(r["rows"], b["rows"]):
            g = abs(y["features"]["pace_figure_score"] - x["features"]["pace_figure_score"])
            if g > gaps["pace_figure_score"]:
                gaps["pace_figure_score"], worst = g, (r["meeting"], r["race"], x["n"], x["features"]["pace_figure_score"],
                                                     y["features"]["pace_figure_score"], x.get("pf"))
            gaps["ability"] = max(gaps["ability"], abs(y["ability"] - x["ability"]))
            gaps["rows_gt_1e-3"] += g > 1e-3
            gaps["rows"] += 1
    print("replica gaps", gaps, "worst", worst, flush=True)
    if gaps["pace_figure_score"] > 1e-3 or gaps["ability"] > 0.005:
        raise SystemExit("replica does not reproduce the engine — stop")

    races = clean(dump["races"])
    base_leaf = day_auc_parts(races, lambda r: leaf_scores_only_pf(r, ""))
    diag = {"replica_gaps": gaps, "races": len(races), "leaf_auc": {}}
    for arm in ("R", "P", "RP"):
        diag["leaf_auc"][arm] = paired(base_leaf, day_auc_parts(races, lambda r, a=arm: leaf_scores_only_pf(r, a)))
    th = sum(h for h, _ in base_leaf.values()); tt = sum(t for _, t in base_leaf.values())
    diag["leaf_auc"]["base_level"] = round(th / tt, 5)
    tr = day_auc_parts(races, trend_scores)
    diag["trend_slope_auc"] = round(sum(h for h, _ in tr.values()) / max(1, sum(t for _, t in tr.values())), 5)
    diag["trend_coverage"] = round(sum(v is not None for r in races for v in trend_scores(r).values())
                                   / max(1, sum(len(r["pf_field"]) for r in races)), 4)
    changed = {}
    for arm in ("R", "P", "RP"):
        n = 0
        for r in races:
            b, c = build(r, ""), build(r, arm)
            ob = sorted(range(len(b["rows"])), key=lambda i: (-b["rows"][i]["ability"], b["rows"][i]["n"]))[:3]
            oc = sorted(range(len(c["rows"])), key=lambda i: (-c["rows"][i]["ability"], c["rows"][i]["n"]))[:3]
            n += ob != oc
        changed[arm] = n
    diag["races_top3_order_changed"] = changed
    print(json.dumps(diag, indent=1), flush=True)
    (out / "describe.json").write_text(json.dumps(diag, ensure_ascii=False, indent=1))
    for arm in ("base", "R", "P", "RP"):
        built = [build(r, "" if arm == "base" else arm) for r in dump["races"]]
        (out / f"{arm}.json").write_text(json.dumps({"races": built}))
        print("built", arm, flush=True)


if __name__ == "__main__":
    main()
