#!/usr/bin/env python3
"""EXP-20261101-35 診斷：點解準咗嘅速度分（G）喺頭 2 換入嘅馬跑得差。只量度。

    python3 au_l600_top2_dig_20261101.py --root AU_ROOT --dump dump_shipped.json --races races.json \
        --arms ARMS_DIR --cand G --out OUT.json

對每個邊界（頭 2、頭 5）逐匹列出換入／換走嘅馬嘅屬性，同埋屬性分組內嘅上名率。
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / ".agents/skills/au_racing/au_wong_choi_auto/scripts"))
sys.path.insert(0, str(HERE))
from au_l600_pit_standard_eval_20261101 import build_index, match  # noqa: E402
from au_l600_standard_dig_20261101 import horse_runs  # noqa: E402


def sp(x):
    try:
        v = float(str(x).replace("$", ""))
        return v if v > 1 else None
    except (TypeError, ValueError):
        return None


def order(rows):
    return sorted(range(len(rows)), key=lambda i: (-rows[i]["ability"], rows[i]["n"]))


def rank_of(rows, key):
    o = sorted(range(len(rows)), key=lambda i: (-key(rows[i]), rows[i]["n"]))
    out = [0] * len(rows)
    for r, i in enumerate(o):
        out[i] = r + 1
    return out


def main():
    ap = argparse.ArgumentParser()
    for a in ("--root", "--dump", "--races", "--arms", "--cand", "--out"):
        ap.add_argument(a, required=True)
    args = ap.parse_args()
    dump = {(r["meeting"], r["race"]): r for r in json.loads(Path(args.dump).read_text())["races"]}
    races = json.loads(Path(args.races).read_text())
    idx = build_index(races)
    prize = defaultdict(list)
    for hr in horse_runs(args.root, races):
        prize[hr["key"]].append(hr["prize"])
    key_prize = {k: st.median(v) for k, v in prize.items()}
    base = {(r["meeting"], r["race"]): r for r in json.loads((Path(args.arms) / "base.json").read_text())["races"]}
    cand = {(r["meeting"], r["race"]): r for r in json.loads((Path(args.arms) / f"{args.cand}.json").read_text())["races"]}

    recs = []
    for k, b in base.items():
        if b["date"] < "2026-08-05" or sum(x["pos"] <= 3 for x in b["rows"]) < 3:
            continue
        c, d = cand[k], dump[k]
        drow = {x["n"]: x for x in d["rows"]}
        ob, oc = order(b["rows"]), order(c["rows"])
        rb = {i: r + 1 for r, i in enumerate(ob)}
        rc = {i: r + 1 for r, i in enumerate(oc)}
        abil_sorted = sorted((x["ability"] for x in b["rows"]), reverse=True)
        fq = rank_of(b["rows"], lambda x: x["features"]["form_quality_score"])
        mk = rank_of(b["rows"], lambda x: -(sp(x["sp"]) or 999))
        today_prizes = []
        for i, x in enumerate(b["rows"]):
            dx = drow.get(x["n"], {})
            runs = d["pf_field"].get(str(x["n"])) or []
            keys = [match(run, idx) for run in runs]
            ps = [key_prize[kk] for kk in keys if kk in key_prize]
            today_prizes.append(st.median(ps) if ps else None)
        field_prize = st.median([p for p in today_prizes if p]) if any(today_prizes) else None
        for i, x in enumerate(b["rows"]):
            dx = drow.get(x["n"], {})
            for K in (2, 5):
                tag = "in" if rc[i] <= K < rb[i] else "out" if rb[i] <= K < rc[i] else None
                if not tag:
                    continue
                cls = dx.get("cls") or {}
                recs.append({
                    "K": K, "tag": tag, "placed": x["pos"] <= 3, "won": x["pos"] == 1,
                    "base_rank": rb[i], "gap_to_K": abil_sorted[K - 1] - x["ability"],
                    "speed_base": x["features"]["pace_figure_score"],
                    "speed_cand": c["rows"][i]["features"]["pace_figure_score"],
                    "form_rank": fq[i], "market_rank": mk[i] if sp(x["sp"]) else None,
                    "pf_runs": len(d["pf_field"].get(str(x["n"])) or []),
                    "career": dx.get("career_starts"), "days": dx.get("days_since_last"),
                    "style": (dx.get("style") or "")[:12], "class_move": str(cls.get("class_move") or ""),
                    "past_prize_vs_field": (today_prizes[i] / field_prize) if today_prizes[i] and field_prize else None,
                    "field_n": len(b["rows"]),
                })

    def summ(rows):
        if not rows:
            return {}
        def med(key):
            v = [r[key] for r in rows if r[key] is not None]
            return round(st.median(v), 3) if v else None
        return {"n": len(rows), "placed": round(st.mean(r["placed"] for r in rows), 3),
                "won": round(st.mean(r["won"] for r in rows), 3),
                "speed_base": med("speed_base"), "speed_cand": med("speed_cand"), "form_rank": med("form_rank"),
                "market_rank": med("market_rank"), "pf_runs": med("pf_runs"), "career": med("career"),
                "days": med("days"), "past_prize_vs_field": med("past_prize_vs_field"), "gap_to_K": med("gap_to_K")}

    out = {}
    for K in (2, 5):
        for tag in ("in", "out"):
            out[f"top{K}_{tag}"] = summ([r for r in recs if r["K"] == K and r["tag"] == tag])
    # 頭 2 換入馬分組
    for K in (2, 5):
        groups = {}
        ins = [r for r in recs if r["K"] == K and r["tag"] == "in"]
        outs = [r for r in recs if r["K"] == K and r["tag"] == "out"]
        _splits(groups, ins, outs)
        out[f"top{K}_groups"] = groups
    print(json.dumps(out, indent=1, ensure_ascii=False))
    Path(args.out).write_text(json.dumps(out, indent=1, ensure_ascii=False))


def _splits(groups, ins, outs):
    def split(name, fn):
        for lab in sorted({fn(r) for r in ins + outs}, key=str):
            a = [r for r in ins if fn(r) == lab]
            b_ = [r for r in outs if fn(r) == lab]
            groups[f"{name}={lab}"] = {"in_n": len(a), "in_placed": round(st.mean(r["placed"] for r in a), 3) if a else None,
                                       "out_n": len(b_), "out_placed": round(st.mean(r["placed"] for r in b_), 3) if b_ else None}
    split("pf_runs", lambda r: "1-2" if r["pf_runs"] <= 2 else "3-5" if r["pf_runs"] <= 5 else "6+")
    split("form_rank", lambda r: "1-2" if r["form_rank"] <= 2 else "3-4" if r["form_rank"] <= 4 else "5+")
    split("market_rank", lambda r: None if r["market_rank"] is None else "1-2" if r["market_rank"] <= 2 else "3-4" if r["market_rank"] <= 4 else "5+")
    split("past_prize_vs_field", lambda r: None if r["past_prize_vs_field"] is None else "lower" if r["past_prize_vs_field"] < 0.8 else "similar" if r["past_prize_vs_field"] <= 1.25 else "higher")
    split("speed_jump", lambda r: "big(>15)" if r["speed_cand"] - r["speed_base"] > 15 else "small" if abs(r["speed_cand"] - r["speed_base"]) <= 15 else "drop")
    split("days", lambda r: None if r["days"] is None else "<=21" if r["days"] <= 21 else "22-60" if r["days"] <= 60 else "61+")
    split("class_move", lambda r: "降班" if "降" in r["class_move"] else "升班" if "升" in r["class_move"] else "same/unknown")
    split("style", lambda r: r["style"][:2] or "?")


if __name__ == "__main__":
    main()
