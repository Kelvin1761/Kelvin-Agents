#!/usr/bin/env python3
"""EXP-20261016-18：官方評分對位六項。規格見 protocol —— 唔准喺度改。

    run --dump cls.json --outdir D   → describe.json + 候選 arm（base、R1x、R2x、R3x、R4x、R5a、R5b、R6x）
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / ".agents/skills/au_racing/au_wong_choi_auto/scripts"))
sys.path.insert(0, str(HERE))
import au_jt_audit_eval_20261016 as ev  # noqa: E402
from au_racing_engine.engine_core import METRO_VENUE_TOKENS, clip_score, parse_placing  # noqa: E402
from au_racing_engine.scoring import CLASS_MICRO_WEIGHTS as W  # noqa: E402

METRO_R6 = METRO_VENUE_TOKENS + ("morphettville", "ascot", "belmont", "the valley")


def tier(venue, tokens):
    text = " ".join(str(venue or "").split()).lower()
    return "metro" if any(t in text for t in tokens) else ("provincial" if text else "")


def placed_flags(c, relative):
    place = parse_placing(c["latest_placing"])
    n = c.get("latest_field_size")
    if relative and place is not None and n and n >= 2 and place <= n:
        pct = (place - 1) / (n - 1)
        return pct <= 0.25, pct > 0.5, place
    return (place is not None and place <= 3), (place is not None and place >= 6), place


def class_score(c, tokens=METRO_VENUE_TOKENS, relative=False, drop_bonus=False):
    score = 60.0
    starts = c["career_starts"]
    good, poor, place = placed_flags(c, relative)
    if starts == 0:
        score = W["career0_base"]
        rc = str(c["race_class"] or "").lower()
        if "2-y-o" in rc or "2yo" in rc:
            score += W["career0_2yo_bonus"]
    elif starts <= 5:
        score += W["career5_placed_bonus"] if good else W["career5_unplaced_pen"]
    elif starts >= 15:
        if c["race_bucket"] == "maiden":
            score += W["career15_maiden_pen"]
        elif poor:
            score += W["career15_unplaced_pen"]
        elif good:
            score += W["career15_placed_bonus"]
    if "降班" in str(c["class_move"] or "") and not drop_bonus:
        score += W["class_drop_bonus"]
    if tier(c["today_venue"], tokens) == "metro" and tier(c["latest_venue"], tokens) == "provincial":
        rt = c["latest_rt"]
        if not (rt is not None and rt >= 68):
            score += W["metro_prov_pen"]
    return clip_score(score)


def rating_score(c, cls, mixed_weight_only=False, no_bucket=False, no_top3=False):
    rating, rated = c["rating"], int(c["rated_count"] or 0)
    if rating is None or rated < 2:
        wp = c["weight_proxy"]
        if mixed_weight_only and rating is None and rated >= 2 and wp is not None:
            return clip_score(wp), "proxy_weight_only"
        if wp is None:
            return clip_score(cls), "proxy"
        return clip_score(0.5 * clip_score(cls) + 0.5 * wp), "proxy_class_weight"
    adj = 0.0
    avg, sd, top3 = c["avg_rating"], c["rating_stdev"] or 0.0, c["top3_cutoff"]
    if avg is not None:
        d = rating - avg
        adj += max(-12.0, min(12.0, d / sd * 6.0)) if sd >= 0.5 else max(-6.0, min(6.0, d * 1.5))
    if top3 is not None and not no_top3:
        if rating >= top3:
            adj += 1.5
        elif rating + 1.0 < top3:
            adj -= 1.0
    if not no_bucket:
        if c["race_bucket"] in {"bm58", "bm72", "bm88"}:
            adj *= 0.9
        elif c["race_bucket"] == "maiden":
            adj *= 0.8
    return clip_score(60.0 + adj), "official"


def rows_of(race, **kw):
    from au_racing_engine.scoring import MATRIX_WEIGHTS
    from au_walkforward_refit import exact_score
    out = []
    for x in race["rows"]:
        c = x["cls"]
        cs = class_score(c, tokens=kw.get("tokens", METRO_VENUE_TOKENS), relative=kw.get("relative", False),
                         drop_bonus=kw.get("drop_bonus", False))
        rs, src = rating_score(c, cs, kw.get("mixed_weight_only", False), kw.get("no_bucket", False), kw.get("no_top3", False))
        feats = {**x["features"], "class_score": round(cs, 6), "rating_score": round(rs, 6)}
        dim_feats = dict(feats)
        if kw.get("class_once") and src.startswith("proxy"):
            dim_feats["class_score"] = 60.0
        r = {k: x[k] for k in ("n", "name", "pos", "sp", "wet", "proven_class", "full_time")}
        r["features"] = feats
        r["ability"] = exact_score({**r, "features": dim_feats}, MATRIX_WEIGHTS)
        r["_src"] = src
        out.append(r)
    return out


def boot(cells, reps=2000):
    def stat(sample):
        a = defaultdict(lambda: [0, 0.0])
        for race in sample:
            for k, e in race:
                a[k][0] += 1; a[k][1] += e
        return {k: v[1] / v[0] for k, v in a.items() if v[0]}, a
    point, a = stat(cells)
    return point, a


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True); ap.add_argument("--outdir", required=True)
    args = ap.parse_args()
    out = Path(args.outdir); out.mkdir(parents=True, exist_ok=True)
    dump = json.loads(Path(args.dump).read_text(encoding="utf-8"))
    clean = [r for r in dump["races"] if r["date"] >= ev.CUT and sum(x["pos"] <= 3 for x in r["rows"]) >= 3
             and any(x["pos"] == 1 for x in r["rows"])]
    # 1. replica check
    gaps = {"class": 0.0, "rating": 0.0, "ability": 0.0}
    for r in clean:
        for x, y in zip(r["rows"], rows_of(r)):
            gaps["class"] = max(gaps["class"], abs(y["features"]["class_score"] - x["features"]["class_score"]))
            gaps["rating"] = max(gaps["rating"], abs(y["features"]["rating_score"] - x["features"]["rating_score"]))
            gaps["ability"] = max(gaps["ability"], abs(y["ability"] - x["ability"]))
    print("replica gaps", gaps)
    if max(gaps.values()) > 1e-3:
        raise SystemExit("replica does not reproduce the engine — stop")
    desc = {"races": len(clean), "replica_gaps": gaps}
    # R1 mixed races: proxy vs official horses, by rating_score band
    band = lambda s: "<56" if s < 56 else "56-60" if s < 60 else "60-64" if s < 64 else "64+"  # noqa: E731
    cells = defaultdict(lambda: [0, 0.0]); mixed_races = 0
    for r in clean:
        rated = int(r["rows"][0]["cls"]["rated_count"] or 0)
        has_unrated = any(x["cls"]["rating"] is None for x in r["rows"])
        if rated >= 2 and has_unrated:
            mixed_races += 1
            for x in r["rows"]:
                src = "official" if x["cls"]["rating"] is not None else "proxy"
                k = f"{src}|{band(x['features']['rating_score'])}"
                cells[k][0] += 1; cells[k][1] += ev.excess(x, len(r["rows"]))
    desc["R1"] = {"mixed_races": mixed_races,
                  "cells": {k: {"n": v[0], "excess": round(v[1] / v[0], 4)} for k, v in sorted(cells.items())}}
    # R2 share of proxy horses
    srcs = defaultdict(int)
    for r in clean:
        for x in r["rows"]:
            c = x["cls"]; srcs["official" if (c["rating"] is not None and int(c["rated_count"] or 0) >= 2) else "proxy"] += 1
    desc["R2"] = dict(srcs)
    # R3 class drop trigger by month + direction
    by = defaultdict(lambda: [0, 0]); trig = [0, 0.0]; nott = [0, 0.0]; prize_have = defaultdict(lambda: [0, 0])
    for r in clean:
        m = r["date"][:7] if r["date"] < "2026-10-02" else "live 10-02→"
        for x in r["rows"]:
            t = "降班" in str(x["cls"]["class_move"] or "")
            by[m][0] += 1; by[m][1] += t
            prize_have[m][0] += 1; prize_have[m][1] += bool(x["cls"]["today_prize"])
            e = ev.excess(x, len(r["rows"]))
            (trig if t else nott)[0] += 1; (trig if t else nott)[1] += e
    desc["R3"] = {"trigger_rate": {k: round(v[1] / v[0], 4) for k, v in sorted(by.items())},
                  "today_prize_coverage": {k: round(v[1] / v[0], 4) for k, v in sorted(prize_have.items())},
                  "triggered": {"n": trig[0], "excess": round(trig[1] / max(1, trig[0]), 4)},
                  "not": {"n": nott[0], "excess": round(nott[1] / nott[0], 4)}}
    # R4 how many class flags change with relative placing
    ch = sum(1 for r in clean for x in r["rows"]
             if placed_flags(x["cls"], True)[:2] != placed_flags(x["cls"], False)[:2] and x["cls"]["career_starts"] and
             (x["cls"]["career_starts"] <= 5 or x["cls"]["career_starts"] >= 15))
    desc["R4"] = {"runners_flag_changed": ch}
    # R5 trigger shares
    desc["R5"] = {"bucket": dict(sorted(defaultdict(int, {}).items()))}
    bk = defaultdict(int)
    for r in clean:
        for x in r["rows"]:
            if x["cls"]["rating"] is not None and int(x["cls"]["rated_count"] or 0) >= 2:
                bk[x["cls"]["race_bucket"] or "other"] += 1
    desc["R5"] = {"official_runners_by_bucket": dict(bk)}
    # R6 venues
    tiers = defaultdict(int); prov_names = defaultdict(int); pen = [0, 0]
    for r in clean:
        for x in r["rows"]:
            c = x["cls"]
            for v in (c["today_venue"], c["latest_venue"]):
                t = tier(v, METRO_VENUE_TOKENS); tiers[t or "blank"] += 1
                if t == "provincial":
                    prov_names[" ".join(str(v).split()).lower()] += 1
            old = tier(c["today_venue"], METRO_VENUE_TOKENS) == "metro" and tier(c["latest_venue"], METRO_VENUE_TOKENS) == "provincial"
            new = tier(c["today_venue"], METRO_R6) == "metro" and tier(c["latest_venue"], METRO_R6) == "provincial"
            pen[0] += old; pen[1] += new
    desc["R6"] = {"tiers": dict(tiers), "top_provincial": sorted(prov_names.items(), key=lambda kv: -kv[1])[:25],
                  "metro_prov_condition_old": pen[0], "metro_prov_condition_new": pen[1]}
    (out / "describe.json").write_text(json.dumps(desc, ensure_ascii=False, indent=1))
    print(json.dumps(desc, ensure_ascii=False, indent=1))

    arms = {"base": {}, "R1x": {"mixed_weight_only": True}, "R2x": {"class_once": True},
            "R3x": {"drop_bonus": True}, "R4x": {"relative": True}, "R5a": {"no_bucket": True},
            "R5b": {"no_top3": True}, "R6x": {"tokens": METRO_R6}}
    for name, kw in arms.items():
        races = [{**{k: v for k, v in r.items() if k != "rows"}, "rows": [{k: v for k, v in y.items() if k != "_src"} for y in rows_of(r, **kw)]}
                 for r in dump["races"]]
        (out / f"{name}.json").write_text(json.dumps({"races": races}))
        print("built", name, flush=True)


if __name__ == "__main__":
    main()
