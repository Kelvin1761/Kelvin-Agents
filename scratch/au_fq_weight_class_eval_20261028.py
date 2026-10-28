#!/usr/bin/env python3
"""EXP-20261028-11／-12／-13 離線 replica 同 arm 產生器。規格見三份 protocol —— 唔准喺度改。

    python3 au_fq_weight_class_eval_20261028.py --dump dump_base.json --outdir ARMS

1. replica 檢查：baseline 重算近績質素分、級數分、rating 分同綜合分，同引擎差 > 1e-3 即停。
2. 估 A1／A3 嘅 μ、k（只用 run_date < 2026-08-05 嘅逐仗值，冇賽果）。
3. 描述統計（describe.json）。
4. 寫 arm：base、A1、A2、A3、B1、B2、C0、C1–C5。每場加 `tags` 畀分層用。
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HERE))
import au_jt_audit_eval_20261016 as ev  # noqa: E402
from au_racing_engine import engine_core as ec  # noqa: E402
from au_racing_engine.dimensions import CLASS_SCORE_LIVE, CLASS_SCORE_LIVE_WEIGHT, RATING_SCORE_SHARE  # noqa: E402
from au_racing_engine.scoring import CLASS_MICRO_WEIGHTS as CW, MATRIX_WEIGHTS, clip_score, parse_float, parse_placing  # noqa: E402
from au_walkforward_refit import exact_score  # noqa: E402

# 量度時嘅 live 值（EXP-13 C3 之後 production 已剷走 career15_*）。寫死，令 replica 可以重現。
CW = {**CW, "career15_maiden_pen": -6.79, "career15_unplaced_pen": -1.4, "career15_placed_bonus": 5.42}

RW = ec.FORM_QUALITY_RECENCY_WEIGHTS
Z_PLACE_MAX = 0.5 / ec.FORM_QUALITY_SD_PCT       # ±1.567（EXP-11 A2 封頂）
CUT = "2026-08-05"


# ── EXP-11 近績質素分 ───────────────────────────────────────────────────────
def run_value(run, cap=False):
    f, s = int(run["finish_pos"]), int(run["starters"])
    zp = (0.5 - (f - 1) / (s - 1)) / ec.FORM_QUALITY_SD_PCT
    zq = (math.log10(float(run["prize"])) - ec.FORM_QUALITY_MU_LOG_PRIZE) / ec.FORM_QUALITY_SD_LOG_PRIZE
    if cap:
        zq = max(-Z_PLACE_MAX, min(Z_PLACE_MAX, zq))
    return (zp + zq) / 2


def fq_raw(runs, cap=False, shrink=None):
    vals = [run_value(r, cap) for r in runs]
    if len(vals) < 2:
        return None
    w = RW[: len(vals)]
    raw = sum(v * x for v, x in zip(vals, w)) / sum(w)
    if shrink:
        mu, k = shrink
        W = sum(w)
        raw = mu + (raw - mu) * W / (W + k)
    return raw


def fq_scores(race, cap=False, shrink=None):
    field = [fq_raw(runs, cap, shrink) for runs in race["fq_field"]]
    field = [v for v in field if v is not None]
    n = len(field)
    mean = sum(field) / n if n else None
    sd = (sum((v - mean) ** 2 for v in field) / n) ** 0.5 if n >= 2 else 0.0
    out = []
    for x in race["rows"]:
        fq = x["fq"]
        if fq.get("fallback") or fq.get("raw") is None:
            out.append(x["features"]["form_quality_score"])   # fallback 組合分唔受候選影響
            continue
        raw = fq_raw(fq["runs"], cap, shrink)
        if raw is None or n < 3 or mean is None or sd <= 0:
            out.append(x["features"]["form_quality_score"])
            continue
        score = clip_score(60.0 + 20.0 * (raw - mean) / sd)
        last = parse_float((fq["runs"][0] or {}).get("distance")) if fq["runs"] else None
        today = fq.get("today_distance")
        if last and today and abs(today - last) >= ec.FORM_QUALITY_TRIP_CHANGE_M:
            score = clip_score(score + ec.FORM_QUALITY_TRIP_CHANGE_PEN)
        out.append(score)
    return out


def estimate_shrink(dump, cap):
    """μ、k：run_date < CUT 嘅逐仗值（去重：馬名＋日期），只計 ≥2 仗嘅馬。冇用賽果。"""
    per = defaultdict(dict)
    for race in dump["races"]:
        for x in race["rows"]:
            for r in x["fq"].get("runs") or []:
                if str(r.get("date") or "") < CUT and r.get("finish_pos") and r.get("starters") and r.get("prize"):
                    per[x["name"].lower()][r["date"]] = run_value(r, cap)
    allv = [v for d in per.values() for v in d.values()]
    mu = sum(allv) / len(allv)
    groups = [list(d.values()) for d in per.values() if len(d) >= 2]
    within_num = sum(sum((v - sum(g) / len(g)) ** 2 for v in g) for g in groups)
    within_df = sum(len(g) - 1 for g in groups)
    s2w = within_num / within_df
    means = [sum(g) / len(g) for g in groups]
    mm = sum(means) / len(means)
    var_means = sum((m - mm) ** 2 for m in means) / (len(means) - 1)
    s2b = var_means - s2w * sum(1 / len(g) for g in groups) / len(groups)
    return {"mu": mu, "k": s2w / s2b, "sigma2_within": s2w, "sigma2_between": s2b,
            "horses": len(groups), "runs": len(allv)}


# ── EXP-12／-13 官方評分對位 ───────────────────────────────────────────────
def weight_proxy(c):
    w, avg = parse_float(c["weight"]), parse_float(c["avg_weight"])
    sd, n = parse_float(c["weight_stdev"]) or 0.0, int(c["weighted_count"] or 0)
    if w is None or not avg or n < 4 or sd < 0.3:
        return None
    return clip_score(60.0 + max(-12.0, min(12.0, (w - avg) / sd * 6.0)))


def class_score(c, drop=()):
    starts = c["career_starts"] or 0
    place = parse_placing(c["latest_placing"])
    n = c.get("latest_field_size")
    if place is not None and n and n >= 2 and place <= n:
        pct = (place - 1) / (n - 1)
        good, poor = pct <= 0.25, pct > 0.5
    else:
        good, poor = place is not None and place <= 3, place is not None and place >= 6
    score = 60.0
    if starts == 0:
        if "G0" not in drop:
            score = CW["career0_base"]
            rc = str(c["title"] or "").lower()
            if "2-y-o" in rc or "2yo" in rc:
                score += CW["career0_2yo_bonus"]
    elif starts <= 5:
        if "G5" not in drop:
            score += CW["career5_placed_bonus"] if good else CW["career5_unplaced_pen"]
    elif starts >= 15 and "G15" not in drop:
        if c["race_bucket"] == "maiden":
            score += CW["career15_maiden_pen"]
        elif poor:
            score += CW["career15_unplaced_pen"]
        elif good:
            score += CW["career15_placed_bonus"]
    if "降班" in str(c["class_move"] or "") and "GD" not in drop:
        score += CW["class_drop_bonus"]
    if c["today_tier"] == "metro" and c["latest_tier"] == "provincial" and "GM" not in drop:
        rt = c["latest_rt"]
        if not (rt is not None and rt >= 68):
            score += CW["metro_prov_pen"]
    return clip_score(score)


def class_groups(c):
    """邊幾組規則有郁到呢匹馬（描述／分層用）。"""
    base = class_score(c)
    return [g for g in ("G0", "G5", "G15", "GD", "GM") if abs(class_score(c, (g,)) - base) > 1e-9]


def rating_score(c, cls, wp_allowed, no_class=False):
    rating, rated = c["rating"], int(c["rated_count"] or 0)
    if rating is None or rated < 2:
        wp = weight_proxy(c) if wp_allowed else None
        if no_class:   # EXP-13 C0：代理只用負磅，冇就 60
            return (wp if wp is not None else 60.0), "proxy_c0"
        class_proxy = clip_score(cls)
        class_once = (CLASS_SCORE_LIVE_WEIGHT / RATING_SCORE_SHARE) * (class_proxy - 60.0) if CLASS_SCORE_LIVE else 0.0
        if rating is None and rated >= 2 and wp is not None:
            return clip_score(wp - class_once), "proxy_weight_only"
        if wp is None:
            return clip_score(class_proxy - class_once), "proxy"
        return clip_score(0.5 * class_proxy + 0.5 * wp - class_once), "proxy_class_weight"
    avg, sd = parse_float(c["avg_rating"]), parse_float(c["rating_stdev"]) or 0.0
    adj = 0.0
    if avg is not None:
        d = rating - avg
        adj = max(-12.0, min(12.0, d / sd * 6.0)) if sd >= 0.5 else max(-6.0, min(6.0, d * 1.5))
    return clip_score(60.0 + adj), "official"


def wp_rule(c, rule):
    if rule == "base":
        return not c["engine_is_sw"]
    if rule == "B1":
        return c["title_class"] == "handicap"
    if rule == "B2":
        return not c["engine_is_sw"] and c["title_class"] != "set_weight"
    raise ValueError(rule)


# ── arm 組裝 ───────────────────────────────────────────────────────────────
ARMS = {
    "base": {}, "A1": {"shrink": "A1"}, "A2": {"cap": True}, "A3": {"cap": True, "shrink": "A3"},
    "B1": {"wp": "B1"}, "B2": {"wp": "B2"},
    "C0": {"no_class": True}, "C1": {"drop": ("G0",)}, "C2": {"drop": ("G5",)}, "C3": {"drop": ("G15",)},
    "C4": {"drop": ("GD",)}, "C5": {"drop": ("GM",)},
}


def build(race, shrinks, cap=False, shrink=None, wp="base", no_class=False, drop=()):
    fqs = fq_scores(race, cap, shrinks.get(shrink) if shrink else None)
    rows, proxy_race = [], False
    for x, fq in zip(race["rows"], fqs):
        c = x["cls"]
        cs = 60.0 if no_class else class_score(c, drop)
        rs, src = rating_score(c, cs, wp_rule(c, wp), no_class)
        proxy_race |= src != "official"
        feats = {**x["features"], "form_quality_score": round(fq, 6),
                 "class_score": round(cs, 6), "rating_score": round(rs, 6)}
        r = {k: x[k] for k in ("n", "name", "pos", "sp", "wet", "proven_class", "full_time")}
        r["features"] = feats
        r["ability"] = exact_score(r, MATRIX_WEIGHTS)
        rows.append(r)
    tags = {"proxy_race": proxy_race,
            "title_class": race["rows"][0]["cls"]["title_class"],
            "fq_runs": [len(x["fq"].get("runs") or []) for x in race["rows"]],
            "class_groups": [class_groups(x["cls"]) for x in race["rows"]]}
    return {**{k: v for k, v in race.items() if k not in ("rows", "fq_field")}, "tags": tags, "rows": rows}


def clean(races):
    return [r for r in races if r["date"] >= CUT and sum(x["pos"] <= 3 for x in r["rows"]) >= 3
            and any(x["pos"] == 1 for x in r["rows"])]


def describe(dump, shrinks, sh):
    races = clean(dump["races"])
    out = {"races": len(races), "shrink": shrinks}
    # A：場數組分佈 + 名次層內剩餘超額
    def rank_layer(i):
        return "1-3" if i < 3 else "4-6" if i < 6 else "7+"
    for arm, kw in (("base", {}), ("A1", {"shrink": "A1"}), ("A2", {"cap": True}), ("A3", {"cap": True, "shrink": "A3"})):
        dist = defaultdict(list)
        for r in races:
            for x, s in zip(r["rows"], fq_scores(r, kw.get("cap", False), sh.get(kw.get("shrink")) if kw.get("shrink") else None)):
                if x["fq"].get("fallback") or x["fq"].get("raw") is None:
                    continue
                dist[min(len(x["fq"]["runs"]), 6)].append(s)
        out[f"fq_dist_{arm}"] = {n: {"n": len(v), "mean": round(sum(v) / len(v), 2),
                                     "sd": round((sum((s - sum(v) / len(v)) ** 2 for s in v) / len(v)) ** 0.5, 2),
                                     "ge85": round(sum(s >= 85 for s in v) / len(v), 3),
                                     "le35": round(sum(s <= 35 for s in v) / len(v), 3)} for n, v in sorted(dist.items())}
    cells = defaultdict(lambda: [0, 0.0])
    for r in races:
        order = sorted(r["rows"], key=lambda x: (-x["ability"], x["n"]))
        for i, x in enumerate(order):
            k = "fallback" if (x["fq"].get("fallback") or x["fq"].get("raw") is None) else str(min(len(x["fq"]["runs"]), 6))
            cells[(rank_layer(i), k)][0] += 1
            cells[(rank_layer(i), k)][1] += ev.excess(x, len(r["rows"]))
    out["A_residual_excess_by_rank_layer_and_runs"] = {f"{a}|{b}": {"n": v[0], "excess": round(v[1] / v[0], 4)}
                                                      for (a, b), v in sorted(cells.items())}
    # B：賽事名分類 × 代理來源
    tc = defaultdict(lambda: defaultdict(int))
    for r in races:
        for x in r["rows"]:
            c = x["cls"]
            tc[c["title_class"]][f"engine_sw={c['engine_is_sw']}|src={c['rating_source']}"] += 1
    out["B_title_class_x_source"] = {k: dict(v) for k, v in tc.items()}
    sample = defaultdict(list)
    for r in races:
        c = r["rows"][0]["cls"]
        if len(sample[c["title_class"]]) < 25:
            sample[c["title_class"]].append(c["title"])
    out["B_title_samples"] = dict(sample)
    # B 診斷：B1 判定為定磅、而 baseline 有用負磅代理嘅場，負磅／年齡／性別嘅場內配對 AUC
    def pair_auc(races_, key):
        hit = tot = 0.0
        for r in races_:
            rows = [x for x in r["rows"] if key(x) is not None]
            for a in rows:
                for b in rows:
                    if a["pos"] <= 3 < b["pos"]:
                        ka, kb = key(a), key(b)
                        tot += 1
                        hit += 1.0 if ka > kb else 0.5 if ka == kb else 0.0
        return {"pairs": int(tot), "auc": round(hit / tot, 4) if tot else None}
    sw_proxy = [r for r in races if r["rows"][0]["cls"]["title_class"] != "handicap"
                and any(weight_proxy(x["cls"]) is not None and not x["cls"]["engine_is_sw"]
                        and (x["cls"]["rating"] is None or int(x["cls"]["rated_count"] or 0) < 2) for x in r["rows"])]
    male = {"G", "C", "H", "R"}
    out["B_diag_nonhandicap_proxy_races"] = {
        "races": len(sw_proxy),
        "weight_proxy": pair_auc(sw_proxy, lambda x: weight_proxy(x["cls"])),
        "age": pair_auc(sw_proxy, lambda x: x["cls"]["age"]),
        "male": pair_auc(sw_proxy, lambda x: None if not x["cls"]["sex"] else float(x["cls"]["sex"] in male)),
        "class_score": pair_auc(sw_proxy, lambda x: x["features"]["class_score"]),
    }
    # C：每組觸發馬喺名次層內嘅剩餘超額（觸發 vs 冇觸發）
    gc = defaultdict(lambda: [0, 0.0])
    for r in races:
        order = sorted(r["rows"], key=lambda x: (-x["ability"], x["n"]))
        for i, x in enumerate(order):
            fired = class_groups(x["cls"])
            for g in ("G0", "G5", "G15", "GD", "GM"):
                d = class_score(x["cls"]) - class_score(x["cls"], (g,))
                tag = "none" if g not in fired else ("plus" if d > 0 else "minus")
                gc[(g, rank_layer(i), tag)][0] += 1
                gc[(g, rank_layer(i), tag)][1] += ev.excess(x, len(r["rows"]))
    out["C_residual_excess"] = {f"{g}|{l}|{t}": {"n": v[0], "excess": round(v[1] / v[0], 4)}
                                for (g, l, t), v in sorted(gc.items())}
    out["C_class_score_auc"] = pair_auc(races, lambda x: x["features"]["class_score"])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    dump = json.loads(Path(args.dump).read_text(encoding="utf-8"))
    # 用 dump script 最新嘅 classify_title 重新分類（截斷修正，見 EXP-12 protocol 附註）。
    from au_fq_weight_class_dump_20261028 import classify_title
    for race in dump["races"]:
        for x in race["rows"]:
            x["cls"]["title_class"] = classify_title(x["cls"]["title"])

    gaps = defaultdict(float)
    for r in clean(dump["races"]):
        b = build(r, {})
        for x, y in zip(r["rows"], b["rows"]):
            for k in ("form_quality_score", "class_score", "rating_score"):
                gaps[k] = max(gaps[k], abs(y["features"][k] - x["features"][k]))
            gaps["ability"] = max(gaps["ability"], abs(y["ability"] - x["ability"]))
            gaps["ability_rows_gt_1e-3"] += abs(y["ability"] - x["ability"]) > 1e-3
    print("replica gaps", dict(gaps), flush=True)
    # leaf 要 ≤ 1e-3。綜合分容差 0.005：dump 將 leaf 存到 6dp，維度分再捨入到 2dp，
    # 啱啱跨捨入邊界（20.974991 vs 20.975006）會差 0.01 × 係數 ≈ 0.0037。
    if max(gaps[k] for k in ("form_quality_score", "class_score", "rating_score")) > 1e-3 or gaps["ability"] > 0.005:
        raise SystemExit("replica does not reproduce the engine — stop")

    shrinks = {"A1": estimate_shrink(dump, cap=False), "A3": estimate_shrink(dump, cap=True)}
    print("shrink", json.dumps(shrinks), flush=True)
    sh = {k: (v["mu"], v["k"]) for k, v in shrinks.items()}
    desc = describe(dump, shrinks, sh)
    desc["replica_gaps"] = dict(gaps)
    (out / "describe.json").write_text(json.dumps(desc, ensure_ascii=False, indent=1))
    for name, kw in ARMS.items():
        races = [build(r, sh, **kw) for r in dump["races"]]
        (out / f"{name}.json").write_text(json.dumps({"races": races}))
        print("built", name, flush=True)


if __name__ == "__main__":
    main()
