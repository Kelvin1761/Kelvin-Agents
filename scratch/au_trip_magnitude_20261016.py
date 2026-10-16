#!/usr/bin/env python3
"""EXP-20261016-73：大幅轉程扣分幅度。dev 揀、confirm 一次。規格見 protocol。

    select  --base x_none.json --dist none.json            → dev 窗全部設定嘅 Gold／Good，揀一個
    build   --base x_none.json --dist none.json --ks K --ki K --out arm.json
"""
from __future__ import annotations

import argparse
import itertools
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
for p in (SCRIPTS, SCRIPTS.parents[2] / "shared_racing"):
    sys.path.insert(0, str(p))
DEV_END = "2026-09-04"
KS = (3, 5, 8, 12, 16)


def dist(v):
    m = re.search(r"(\d{3,4})", str(v or ""))
    return float(m.group(1)) if m else None


def changes(dist_dump):
    """{(meeting, race, n): +1 增程 / -1 縮程} for |Δ| ≥ 400."""
    out = {}
    for r in json.loads(Path(dist_dump).read_text(encoding="utf-8"))["races"]:
        today = dist(r["rows"][0]["dist"]["today"])
        for x in r["rows"]:
            runs = x["dist"]["fq_runs"]
            last = dist(runs[0].get("distance")) if runs else None
            if today and last and abs(today - last) >= 400:
                out[(r["meeting"], r["race"], x["n"])] = 1 if today > last else -1
    return out


def arm(base, ch, ks, ki):
    from au_racing_engine.engine_core import clip_score
    from au_racing_engine.scoring import MATRIX_WEIGHTS
    from au_walkforward_refit import exact_score
    races = []
    for r in base:
        rows = []
        for x in r["rows"]:
            y = json.loads(json.dumps(x))
            c = ch.get((r["meeting"], r["race"], x["n"]))
            if c:
                y["features"]["form_quality_score"] = clip_score(y["features"]["form_quality_score"] - (ki if c > 0 else ks))
                y["ability"] = exact_score(y, MATRIX_WEIGHTS)
            rows.append(y)
        races.append({**{k: v for k, v in r.items() if k != "rows"}, "rows": rows})
    return races


def clean(races, lo=None, hi=None):
    return [r for r in races if r["date"] >= "2026-08-05" and (lo is None or r["date"] >= lo)
            and (hi is None or r["date"] <= hi) and sum(x["pos"] <= 3 for x in r["rows"]) >= 3
            and any(x["pos"] == 1 for x in r["rows"])]


def cmd_select(args):
    from au_eval import _counts
    base = json.loads(Path(args.base).read_text(encoding="utf-8"))["races"]
    ch = changes(args.dist)
    dev_base = clean(base, hi=DEV_END)
    score = lambda r: r["ability"]  # noqa: E731
    rows = []
    for ks, ki in itertools.product(KS, KS):
        c = _counts(clean(arm(dev_base, ch, ks, ki)), score)
        rows.append({"ks": ks, "ki": ki, "symmetric": ks == ki, "gold": round(c["gold"], 3),
                     "good": round(c["good_positional"], 3), "sum": round(c["gold"] + c["good_positional"], 3)})
    best = sorted(rows, key=lambda r: (-r["sum"], r["ks"] + r["ki"]))[0]
    out = {"dev_races": len(dev_base), "triggered": len(ch), "grid": rows, "chosen": best,
           "current_minus5": next(r for r in rows if r["ks"] == 5 and r["ki"] == 5)}
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1))
    for r in sorted(rows, key=lambda r: -r["sum"])[:8]:
        print(r)
    print("current -5/-5:", out["current_minus5"]); print("CHOSEN:", best)


def cmd_build(args):
    base = json.loads(Path(args.base).read_text(encoding="utf-8"))["races"]
    Path(args.out).write_text(json.dumps({"races": arm(base, changes(args.dist), args.ks, args.ki)}))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("select"); s.add_argument("--base", required=True); s.add_argument("--dist", required=True)
    s.add_argument("--out", required=True)
    b = sub.add_parser("build"); b.add_argument("--base", required=True); b.add_argument("--dist", required=True)
    b.add_argument("--ks", type=float, required=True); b.add_argument("--ki", type=float, required=True)
    b.add_argument("--out", required=True)
    args = ap.parse_args()
    {"select": cmd_select, "build": cmd_build}[args.cmd](args)


if __name__ == "__main__":
    main()
