#!/usr/bin/env python3
"""兩件事：

A. 每個 leaf 嘅**實際影響力** = 有效權重 × 場內標準差。
   權重高但分佈窄嘅 leaf 係浪費咗嘅容量（例：jockey_horse_fit 權重 0.1009 但 SD 3.76）。
   用場內 SD（而唔係全體 SD）因為排名只喺場內比較。

B. **Benbulben 型** cohort：模型前三推介，但佢嘅計分近仗其實係
   「場內後半段位置」或「輸一大截」而現行 base 仍然 ≥60。
   量佢們實際命中率 vs 基線，睇呢類馬有幾多、蝕幾多。

唯讀，本地 cache。
"""
from __future__ import annotations

import csv
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR / "racing_engine"))

from au_archive_calibrator import (  # noqa: E402
    HISTORICAL_RESULTS_CSV,
    normalize_horse_name,
    normalize_track_name,
    parse_int,
)
from matrix_mapper import MATRIX_FORMULAS  # noqa: E402
from scoring import MATRIX_WEIGHTS  # noqa: E402

HERE = Path(__file__).resolve().parent
DIST = re.compile(r"(\d+)")
MARGIN_L = re.compile(r"([-+]?\d+(?:\.\d+)?)\s*L")


def eff_weights():
    eff = {}
    for mk, comps in MATRIX_FORMULAS.items():
        for leaf, w in comps:
            eff[leaf] = eff.get(leaf, 0.0) + MATRIX_WEIGHTS[mk] * w
    return eff


def load_results():
    field = Counter()
    margin = {}
    with HISTORICAL_RESULTS_CSV.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            race = parse_int(row.get("Race"))
            pos = parse_int(row.get("Pos"))
            if not race or not pos:
                continue
            k3 = (str(row.get("Date") or "").strip(),
                  normalize_track_name(row.get("Track") or ""), race)
            field[k3] += 1
            m = MARGIN_L.search(str(row.get("Margin") or ""))
            margin[k3 + (normalize_horse_name(row.get("Horse") or ""),)] = (
                abs(float(m.group(1))) if m else (0.0 if pos == 1 else None))
    return field, margin


def main():
    eff = eff_weights()
    leaf_cache = json.loads((HERE / "au_leaf_cache.json").read_text(encoding="utf-8"))
    races = leaf_cache["races"]

    # ---------- A. 實際影響力 ----------
    within = defaultdict(list)
    for race in races:
        for leaf in eff:
            vals = [h["features"].get(leaf, 60.0) for h in race["rows"]]
            if len(vals) >= 3:
                within[leaf].append(statistics.pstdev(vals))
    print(f"{'leaf':26}{'有效權重':>10}{'場內 SD':>9}{'影響力=w×SD':>14}{'佔總影響':>10}")
    infl = {k: eff[k] * statistics.mean(v) for k, v in within.items() if v}
    total = sum(infl.values())
    for leaf, val in sorted(infl.items(), key=lambda kv: -kv[1]):
        print(f"{leaf:26}{eff[leaf]:>10.4f}"
              f"{statistics.mean(within[leaf]):>9.2f}{val:>14.4f}"
              f"{100*val/total:>9.1f}%")

    # ---------- B. Benbulben 型 cohort ----------
    field_truth, margin_truth = load_results()
    stab = json.loads((HERE / "au_stability_cache.json").read_text(encoding="utf-8"))
    lastfin = json.loads((HERE / "au_lastfinish_cache.json").read_text(encoding="utf-8"))
    runs_index = {}
    for race in stab["races"]:
        for h in race["rows"]:
            lf = lastfin.get(f"{race['meeting']}|{race['race']}|{h['n']}")
            hslug = normalize_horse_name(h["name"] or "")
            for run in h["runs"]:
                run["_field"] = run["_margin"] = None
                place = run.get("place")
                if not place:
                    continue
                vslug = normalize_track_name(run.get("venue") or "")
                k3 = (run["date"], vslug, run.get("race_no"))
                f = field_truth.get(k3)
                if f and f >= 2 and place <= f:
                    run["_field"] = f
                elif lf:
                    dm = DIST.search(str(run.get("distance") or ""))
                    dist = int(dm.group(1)) if dm else None
                    if (lf["place"] == place and dist == lf["distance"]
                            and normalize_track_name(lf["venue"]) == vslug
                            and lf["field"] >= 2 and place <= lf["field"]):
                        run["_field"] = lf["field"]
                run["_margin"] = (run.get("margin")
                                  if run.get("margin") is not None
                                  else margin_truth.get(k3 + (hslug,)))
            runs_index[(race["meeting"], race["race"], h["n"])] = h["runs"]

    def flatter_runs(h, runs):
        """現行 base ≥60 但實際係後半位置 / 輸 >5L 嘅計分場次數。"""
        bad = 0
        for i, row in enumerate(h.get("form_rows_detail") or []):
            if i >= len(runs):
                break
            run = runs[i]
            if run.get("place") != row.get("place") or int(row["base"]) < 60:
                continue
            f, mg = run.get("_field"), run.get("_margin")
            pct = ((run["place"] - 1) / (f - 1)) if f and f > 1 else None
            if (pct is not None and pct > 0.5) or (mg is not None and mg > 5.0):
                bad += 1
        return bad

    stats = defaultdict(lambda: {"n": 0, "top3": 0, "win": 0, "bot": 0, "sp": 0.0, "spn": 0})
    examples = []
    for race in races:
        field_n = race["field"]
        ranked = sorted(race["rows"], key=lambda h: (-(h["ability"] or 0), h["n"]))
        for rank, h in enumerate(ranked[:3], 1):
            runs = runs_index.get((race["meeting"], race["race"], h["n"]), [])
            bad = flatter_runs(h, runs)
            bucket = "flattered" if bad >= 1 else "clean"
            for key in (bucket, "ALL"):
                e = stats[key]
                e["n"] += 1
                e["top3"] += 1 if h["pos"] <= 3 else 0
                e["win"] += 1 if h["pos"] == 1 else 0
                e["bot"] += 1 if h["pos"] > field_n * 2 / 3 else 0
                if h["sp"]:
                    e["sp"] += float(h["sp"])
                    e["spn"] += 1
            if bad >= 2 and h["pos"] > field_n * 2 / 3:
                examples.append({"meeting": race["meeting"], "race": race["race"],
                                 "horse": h["name"], "model_rank": rank,
                                 "pos": h["pos"], "field": field_n, "sp": h["sp"],
                                 "flattered_runs": bad,
                                 "stability_leaves": {
                                     "form": h["features"]["form_score"],
                                     "cons": h["features"]["consistency_score"]}})

    print(f"\n{'cohort':12}{'n':>6}{'勝%':>7}{'前三%':>8}{'尾三分一%':>11}{'平均SP':>8}")
    for key in ("clean", "flattered", "ALL"):
        e = stats[key]
        if not e["n"]:
            continue
        print(f"{key:12}{e['n']:>6}{100*e['win']/e['n']:>7.1f}{100*e['top3']/e['n']:>8.1f}"
              f"{100*e['bot']/e['n']:>11.1f}"
              f"{e['sp']/e['spn'] if e['spn'] else 0:>8.1f}")

    print(f"\nBenbulben 型（≥2 場被抬高 且 跑落尾三分一）共 {len(examples)} 個前三推介：")
    for ex in sorted(examples, key=lambda x: -(x["sp"] or 0))[:18]:
        print(f"  {ex['meeting'][:30]:30} R{ex['race']:<2} #{ex['model_rank']} "
              f"{ex['horse'][:19]:19} {ex['pos']:>2}/{ex['field']:<2} SP {str(ex['sp']):>6} "
              f"抬高{ex['flattered_runs']}場 form {ex['stability_leaves']['form']:.0f}"
              f" cons {ex['stability_leaves']['cons']:.0f}")


if __name__ == "__main__":
    main()
