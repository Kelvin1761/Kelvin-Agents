#!/usr/bin/env python3
"""EXP-20261101-34 診斷：G（準咗嘅速度分）喺排名度郁咗邊啲馬、點解冇變成 Gold／Good。只量度。

    python3 au_l600_g_swap_dig_20261101.py --arms ARMS_DIR --cand G --out OUT.json

比較 base 同候選嘅頭 4 名：被推入（候選頭 4、base 唔係）vs 被擠走（相反）。
SP 只用嚟做外部參照（市場點睇呢匹馬），唔入任何分數。
"""
from __future__ import annotations

import argparse
import json
import statistics as st
from collections import defaultdict
from pathlib import Path


def sp(x):
    try:
        v = float(str(x).replace("$", ""))
        return v if v > 1 else None
    except (TypeError, ValueError):
        return None


def ranks(rows, key):
    order = sorted(range(len(rows)), key=lambda i: (-key(rows[i]), rows[i]["n"]))
    out = [0] * len(rows)
    for r, i in enumerate(order):
        out[i] = r + 1
    return out


def summarise(items):
    if not items:
        return {"n": 0}
    sps = [sp(x["sp"]) for x in items if sp(x["sp"])]
    return {
        "n": len(items),
        "placed_rate": round(sum(x["placed"] for x in items) / len(items), 4),
        "market_implied_place": round(st.mean(min(1.0, 3.0 / s) for s in sps), 4) if sps else None,
        "median_sp": round(st.median(sps), 2) if sps else None,
        "form_rank_median": st.median(x["form_rank"] for x in items),
        "speed_rank_base_median": st.median(x["speed_rank_base"] for x in items),
        "speed_rank_cand_median": st.median(x["speed_rank_cand"] for x in items),
        "speed_shift_mean": round(st.mean(x["speed_shift"] for x in items), 2),
        "rating_rank_median": st.median(x["rating_rank"] for x in items),
        "market_rank_median": st.median(x["market_rank"] for x in items if x["market_rank"]),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", required=True)
    ap.add_argument("--cand", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    arms = Path(args.arms)
    base = {(r["meeting"], r["race"]): r for r in json.loads((arms / "base.json").read_text())["races"]}
    cand = {(r["meeting"], r["race"]): r for r in json.loads((arms / f"{args.cand}.json").read_text())["races"]}
    promoted, demoted = [], []
    agree = defaultdict(lambda: [0, 0])
    for k, b in base.items():
        if b["date"] < "2026-08-05" or sum(x["pos"] <= 3 for x in b["rows"]) < 3:
            continue
        c = cand[k]
        rows_b, rows_c = b["rows"], c["rows"]
        rb = ranks(rows_b, lambda x: x["ability"])
        rc = ranks(rows_c, lambda x: x["ability"])
        fq = ranks(rows_b, lambda x: x["features"]["form_quality_score"])
        rt = ranks(rows_b, lambda x: x["features"]["rating_score"])
        sb = ranks(rows_b, lambda x: x["features"]["pace_figure_score"])
        sc = ranks(rows_c, lambda x: x["features"]["pace_figure_score"])
        mk = ranks(rows_b, lambda x: -(sp(x["sp"]) or 999))
        for i, x in enumerate(rows_b):
            item = {"placed": x["pos"] <= 3, "sp": x["sp"], "form_rank": fq[i], "rating_rank": rt[i],
                    "speed_rank_base": sb[i], "speed_rank_cand": sc[i],
                    "speed_shift": rows_c[i]["features"]["pace_figure_score"] - x["features"]["pace_figure_score"],
                    "market_rank": mk[i] if sp(x["sp"]) else None}
            if rc[i] <= 4 < rb[i]:
                promoted.append(item)
            elif rb[i] <= 4 < rc[i]:
                demoted.append(item)
            # 速度分同狀態排名嘅一致：速度分頭 3 而狀態唔係頭 3 嘅馬（速度分獨有嘅推介）
            for arm, sr in (("base", sb[i]), ("cand", sc[i])):
                if sr <= 3 and fq[i] > 3:
                    agree[f"{arm}_speed_top3_form_not"][0] += 1
                    agree[f"{arm}_speed_top3_form_not"][1] += x["pos"] <= 3
                if sr <= 3 and fq[i] <= 3:
                    agree[f"{arm}_speed_top3_form_top3"][0] += 1
                    agree[f"{arm}_speed_top3_form_top3"][1] += x["pos"] <= 3
    out = {"promoted": summarise(promoted), "demoted": summarise(demoted),
           "speed_vs_form": {k: {"n": v[0], "placed_rate": round(v[1] / v[0], 4)} for k, v in agree.items()}}
    print(json.dumps(out, indent=1))
    Path(args.out).write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
