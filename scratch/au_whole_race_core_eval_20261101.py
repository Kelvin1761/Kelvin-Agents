#!/usr/bin/env python3
"""EXP-20261101-41 arm 產生器（base／W／W_keep／S2_ref）。規格見 protocol —— 唔准喺度改。

    python3 au_whole_race_core_eval_20261101.py --dump dump_pos.json --outdir ARMS

只讀 2026-08-05 → 2026-10-16（10-17 起係 EXP-20261016-03 S2 forward 窗，arm 入面一場都冇）。
A_sb 由 `au_sb_total_speed_20261016.compute_asb` 計（EXP-02 原構造）。
"""
from __future__ import annotations

import argparse
import copy
import json
import statistics as st
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HERE))
from au_racing_engine.scoring import MATRIX_WEIGHTS  # noqa: E402
from au_walkforward_refit import exact_score  # noqa: E402
import au_sb_total_speed_20261016 as sb  # noqa: E402

START, END = "2026-08-05", "2026-10-16"
KEEP = ("n", "name", "pos", "sp", "wet", "proven_class", "full_time", "style")


def leaf_auc(races, key):
    """場內配對 AUC：上名（1–3）vs 唔上名。"""
    wins = total = 0.0
    for race in races:
        rows = [x for x in race["rows"] if key(x) is not None]
        pos = [key(x) for x in rows if x["pos"] <= 3]
        neg = [key(x) for x in rows if x["pos"] > 3]
        for p in pos:
            for q in neg:
                wins += 1.0 if p > q else 0.5 if p == q else 0.0
                total += 1
    return round(wins / total, 4) if total else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()
    out = Path(args.outdir); out.mkdir(parents=True, exist_ok=True)
    races = [r for r in json.loads(Path(args.dump).read_text())["races"] if START <= r["date"] <= END]
    assert max(r["date"] for r in races) <= END
    print("races in window", len(races), flush=True)

    # replica：dump 入面 ability 一定要等於由欄位重算
    off = sum(abs(exact_score(x, MATRIX_WEIGHTS) - x["ability"]) > 1e-3 for r in races for x in r["rows"])
    print("replica rows off:", off, flush=True)
    if off:
        raise SystemExit("replica does not reproduce the engine — stop")

    root = Path(open(HERE.parent / ".wongchoi_au_data_root").read().strip())
    events, histories, audit = sb.parse_corpus(root)
    print("G0 audit", dict(audit), flush=True)
    asb = sb.compute_asb({"races": races}, events, histories)

    arms = {name: [] for name in ("base", "W", "W_keep", "S2_ref")}
    cover = changed = 0
    auc_rows = []
    for race in races:
        details = [asb.get(f"{race['date']}|{race['meeting']}|{race['race']}|{x['n']}") for x in race["rows"]]
        has = [d is not None and d["raw"] is not None for d in details]
        cover += sum(has)
        enough = sum(has) >= 3
        if enough:
            vals = [d["raw"] for d, h in zip(details, has) if h]
            mu, sd = st.mean(vals), st.pstdev(vals)
        for name in arms:
            built = []
            for x, d, h in zip(race["rows"], details, has):
                r = {k: x.get(k) for k in KEEP}
                pf = x["features"]["pace_figure_score"]
                if name in ("W", "W_keep") and enough:
                    z = (d["raw"] - mu) / sd if h and sd > 0 else 0.0
                    pf = round(min(100.0, max(0.0, 60 + 20 * z)), 6)
                if name == "S2_ref":
                    z = d["z"] if h else 0.0
                    pf = round(0.5 * pf + 0.5 * (60 + 10 * z), 6)
                if name == "W" and enough:
                    r["full_time"] = 0.0
                r["features"] = {**x["features"], "pace_figure_score": pf}
                r["ability"] = exact_score(r, MATRIX_WEIGHTS)
                built.append(r)
            arms[name].append({**{k: v for k, v in race.items() if k not in ("rows", "pf_field", "fq_field")},
                               "rows": built, "tags": tags(race, built)})
        auc_rows.append({"rows": [{"pos": x["pos"], "pf": x["features"]["pace_figure_score"],
                                   "asb": d["raw"] if h else None} for x, d, h in zip(race["rows"], details, has)]})
        changed += [x["ability"] for x in arms["base"][-1]["rows"]] != [x["ability"] for x in arms["W"][-1]["rows"]]

    both = [{"rows": [x for x in r["rows"] if x["asb"] is not None]} for r in auc_rows]
    desc = {"races": len(races), "runners": sum(len(r["rows"]) for r in races), "asb_coverage": cover,
            "races_changed_W": changed, "g0_audit": dict(audit),
            "auc_same_horses": {"pace_figure": leaf_auc(both, lambda x: x["pf"]),
                                "asb": leaf_auc(both, lambda x: x["asb"])}}
    print(json.dumps(desc, indent=1), flush=True)
    (out / "describe.json").write_text(json.dumps(desc, indent=1))
    for name, built in arms.items():
        (out / f"{name}.json").write_text(json.dumps({"races": built}))


def tags(race, rows):
    d = race["rows"][0].get("distance")
    try:
        d = float(str(d).rstrip("m"))
    except (TypeError, ValueError):
        d = None
    top = min(range(len(rows)), key=lambda i: (-rows[i]["ability"], rows[i]["n"]))
    return {"distance": None if not d else "<=1200" if d <= 1200 else "1201-1600" if d <= 1600 else ">1600",
            "fallback_share": 0.0, "top_style": str(rows[top].get("style") or "")[:2] or "?"}


if __name__ == "__main__":
    main()
