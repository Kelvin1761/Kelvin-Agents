#!/usr/bin/env python3
"""HKJC Wong Choi failure-cohort localization and error attribution.

HKJC localization of the AU 2026-07-17 Phase-4 cohort analysis
(.agents/skills/au_racing/au_wong_choi_auto/scripts/au_failure_cohorts.py).

Slices the archived HKJC races (production ranking = stored
python_auto.ability_score) by venue / month / class / field size /
score-gap tightness / feature coverage, ranks underperforming cohorts
(n>=30 flagged as powered), then attributes error per matrix dimension via
leave-one-dimension-out + ±10/20% weight perturbation, plus winner-vs-top2
matrix deltas in zero-hit races.

Research-only: reads Logic files + results JSON, writes report files, never
touches Logic files or live weights. HKJC going/draw are NOT race-level
inputs here (going is post-race only; draw feeds race_shape) — no going slice.

Usage:
    python3 scratch/hkjc_failure_cohorts.py [--min-races 30] [--report-date YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "shared_racing"))
ENGINE = ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_wong_choi_auto" / "scripts" / "racing_engine"
sys.path.insert(0, str(ENGINE))

from wongchoi_paths import HK_RACING  # noqa: E402
from eval_metrics import race_metrics, summarize_races  # noqa: E402
from scoring import MATRIX_WEIGHTS  # noqa: E402

MATRIX_KEYS = ("stability", "sectional", "race_shape", "trainer_signal",
               "horse_health", "form_line", "class_advantage")
FEATURE_KEYS = ("form_score", "speed_score", "class_score", "jockey_score",
                "trainer_score", "draw_score", "distance_score", "track_going_score",
                "weight_score", "consistency_score", "risk_score", "confidence_score")
KPI_KEYS = ("good_positional", "winner_in_top3", "top3_precision", "miss")


def as_float(value, default=60.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def find_results_json(meeting: Path):
    files = sorted(meeting.glob("*全日賽果.json"))
    return files[0] if files else None


def load_results(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for race_key, race_data in data.items():
        try:
            rn = int(race_key)
        except (TypeError, ValueError):
            continue
        pos = {}
        for row in race_data.get("results", []):
            try:
                pos[int(row["horse_no"])] = int(row["pos"])
            except (KeyError, TypeError, ValueError):
                continue
        if pos:
            out[rn] = pos
    return out


def class_family(value: str) -> str:
    t = str(value or "").strip()
    if not t:
        return "Unknown"
    if "一級" in t or "G1" in t:
        return "Group/Listed"
    if "二級" in t or "三級" in t or "G2" in t or "G3" in t or "上市" in t or "讓賽錦標" in t:
        return "Group/Listed"
    for cls, label in (("一", "Class1"), ("二", "Class2"), ("三", "Class3"),
                       ("四", "Class4"), ("五", "Class5")):
        if f"第{cls}班" in t:
            return label
    if "新馬" in t or t.upper().startswith("GR") or "組別未" in t:
        return "Griffin/Maiden"
    return "Other"


def field_band(n: int) -> str:
    if n <= 8:
        return "<=8"
    if n <= 11:
        return "9-11"
    return "12+"


def coverage_band(race: list[dict]) -> str:
    defaults = []
    for row in race:
        fs = row["features"]
        vals = [as_float(fs.get(k), 60.0) for k in FEATURE_KEYS]
        defaults.append(sum(1 for v in vals if abs(v - 60.0) < 1e-9) / len(vals))
    avg = mean(defaults) if defaults else 0.0
    if avg < 0.15:
        return "rich (<15% default)"
    if avg < 0.35:
        return "medium (15-35% default)"
    return "thin (>=35% default)"


def score_gap_band(race: list[dict]) -> str:
    ranked = sorted((row["ability"] for row in race), reverse=True)
    gap = ranked[0] - ranked[2] if len(ranked) >= 3 else 0.0
    if gap < 2.0:
        return "tight (top1-top3 < 2)"
    if gap < 5.0:
        return "medium (2-5)"
    return "clear (>=5)"


def load_races() -> list[dict]:
    """One record per archived HKJC race with per-horse matrix + feature scores."""
    races = []
    for meeting in sorted(HK_RACING.iterdir()):
        if not meeting.is_dir() or "(" in meeting.name or not meeting.name.startswith("2026"):
            continue
        results_path = find_results_json(meeting)
        if results_path is None or not list(meeting.glob("Race_*_Logic.json")):
            continue
        actual = load_results(results_path)
        venue = "HappyValley" if "Happy" in meeting.name else "ShaTin"
        month = meeting.name[:7]
        for logic_path in sorted(meeting.glob("Race_*_Logic.json")):
            m = re.search(r"Race_(\d+)_Logic\.json$", logic_path.name)
            rn = int(m.group(1)) if m else 0
            if rn not in actual:
                continue
            logic = json.loads(logic_path.read_text(encoding="utf-8"))
            race_class = (logic.get("race_analysis") or {}).get("race_class", "")
            rows = []
            for hn_text, horse in logic.get("horses", {}).items():
                try:
                    hn = int(hn_text)
                except ValueError:
                    continue
                auto = horse.get("python_auto", {})
                if not auto.get("feature_scores"):
                    continue
                pos = actual[rn].get(hn)
                rows.append({
                    "horse": hn,
                    "ability": as_float(auto.get("ability_score"), 60.0),
                    "matrix": {k: as_float((auto.get("matrix_scores") or {}).get(k), 60.0) for k in MATRIX_KEYS},
                    "features": auto.get("feature_scores", {}),
                    "actual_pos": pos if pos is not None else 99,
                })
            if len(rows) < 4:
                continue
            pos_map = actual[rn]
            top3 = [h for h, p in pos_map.items() if p <= 3]
            if sum(1 for p in pos_map.values() if p <= 3) < 3 or not top3:
                continue
            races.append({
                "meeting": meeting.name, "venue": venue, "month": month,
                "race": rn, "class_family": class_family(race_class),
                "field": len(rows), "rows": rows,
                "pos_map": pos_map, "top3": top3,
            })
    return races


def eval_race(race: dict, weights=None) -> dict:
    rows = race["rows"]
    if weights is None:
        ranked = sorted(rows, key=lambda r: (-r["ability"], r["horse"]))
    else:
        total = sum(weights.values()) or 1.0
        scale = sum(MATRIX_WEIGHTS.values()) / total
        scored = [(r["horse"], scale * sum(weights.get(k, 0.0) * r["matrix"][k] for k in MATRIX_KEYS))
                  for r in rows]
        order = {h: s for h, s in scored}
        ranked = sorted(rows, key=lambda r: (-order[r["horse"]], r["horse"]))
    picks = [r["horse"] for r in ranked]
    return race_metrics(picks, race["top3"], actual_pos=race["pos_map"])


def summarize(races: list[dict], weights=None) -> dict:
    return summarize_races([eval_race(r, weights) for r in races])


SLICERS = {
    "venue": lambda r: r["venue"],
    "month": lambda r: r["month"],
    "class": lambda r: r["class_family"],
    "field_size": lambda r: field_band(r["field"]),
    "score_gap": lambda r: score_gap_band(r["rows"]),
    "feature_coverage": lambda r: coverage_band(r["rows"]),
}


def cohort_table(races: list[dict], min_races: int) -> list[dict]:
    overall = summarize(races)
    o_r = overall["rates"]
    o_prec = overall["top3_precision"]
    rows = []
    for name, slicer in SLICERS.items():
        groups = defaultdict(list)
        for r in races:
            groups[slicer(r)].append(r)
        for value, members in groups.items():
            s = summarize(members)
            n = s["races"]
            rows.append({
                "slice": name, "cohort": value, "races": n,
                "underpowered": n < min_races,
                "good_positional_rate": s["rates"]["good_positional"],
                "good_any2_rate": s["rates"]["good_any2"],
                "winner_in_top3": s["rates"]["winner_in_top3"],
                "top3_precision": s["top3_precision"],
                "miss_rate": s["exclusive_labels"].get("Miss", 0) / max(1, n),
                "delta_good_positional": s["rates"]["good_positional"] - o_r["good_positional"],
                "delta_winner_in_top3": s["rates"]["winner_in_top3"] - o_r["winner_in_top3"],
                "delta_top3_precision": s["top3_precision"] - o_prec,
            })
    rows.sort(key=lambda row: (row["underpowered"], row["delta_top3_precision"]))
    return rows


def attribution(races: list[dict], cohorts: dict[str, list[dict]]) -> dict:
    baseline = {name: summarize(members, dict(MATRIX_WEIGHTS)) for name, members in cohorts.items()}
    out = {"baseline": baseline, "dimensions": {}, "reconstruction_error": {}}
    # fidelity check: reconstructed vs stored ranking agreement
    for name, members in cohorts.items():
        stored = summarize(members)
        recon = baseline[name]
        out["reconstruction_error"][name] = {
            "stored_good_pos": stored["counts"]["good_positional"],
            "recon_good_pos": recon["counts"]["good_positional"],
        }
    for key in MATRIX_KEYS:
        w = MATRIX_WEIGHTS.get(key, 0.0)
        variants = {"drop": 0.0, "-20%": w * 0.8, "-10%": w * 0.9, "+10%": w * 1.1, "+20%": w * 1.2}
        out["dimensions"][key] = {}
        for label, nw in variants.items():
            weights = dict(MATRIX_WEIGHTS)
            weights[key] = nw
            out["dimensions"][key][label] = {
                name: summarize(members, weights) for name, members in cohorts.items()
            }
    return out


def zero_hit_winner_deltas(races: list[dict]) -> dict:
    deltas = defaultdict(list)
    count = 0
    for race in races:
        ranked = sorted(race["rows"], key=lambda r: (-r["ability"], r["horse"]))
        top3_picks = ranked[:3]
        if any(r["actual_pos"] <= 3 for r in top3_picks):
            continue
        winner = next((r for r in race["rows"] if r["actual_pos"] == 1), None)
        if winner is None:
            continue
        count += 1
        top2 = ranked[:2]
        for key in MATRIX_KEYS:
            top2_avg = mean(r["matrix"][key] for r in top2)
            deltas[key].append(winner["matrix"][key] - top2_avg)
    return {"zero_hit_races": count,
            "winner_minus_top2_avg": {k: round(mean(v), 3) for k, v in deltas.items() if v}}


def pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-races", type=int, default=30)
    ap.add_argument("--report-date", default=date.today().isoformat())
    args = ap.parse_args()

    races = load_races()
    overall = summarize(races)
    table = cohort_table(races, args.min_races)

    cohorts = {
        "ALL": races,
        "HappyValley": [r for r in races if r["venue"] == "HappyValley"],
        "ShaTin": [r for r in races if r["venue"] == "ShaTin"],
        "field 12+": [r for r in races if field_band(r["field"]) == "12+"],
        "tight gap": [r for r in races if score_gap_band(r["rows"]) == "tight (top1-top3 < 2)"],
    }
    attr = attribution(races, cohorts)
    zero_hit = zero_hit_winner_deltas(races)

    lines = [
        f"# HKJC Wong Choi Failure Cohorts & Error Attribution ({args.report_date})",
        "",
        f"> Archived HKJC races (n={overall['races']}), production ranking = stored "
        f"`python_auto.ability_score`, canonical ruler. Cohorts under {args.min_races} "
        f"races marked underpowered. Going is NOT a slice (post-race only; not a race-level input).",
        "",
        f"Overall: Good-pos {pct(overall['rates']['good_positional'])} · "
        f"any-2 {pct(overall['rates']['good_any2'])} · "
        f"W-in-T3 {pct(overall['rates']['winner_in_top3'])} · "
        f"Top1 {pct(overall['rates']['champion'])} · "
        f"Top3-prec {pct(overall['top3_precision'])} · Gold {overall['counts']['gold']}",
        "",
        "## Ranked cohort table (worst Top3-precision delta first)",
        "",
        "| Slice | Cohort | Races | Good pos | any-2 | W-in-T3 | Top3 prec | Miss | ΔGood pos | ΔW-in-T3 | ΔTop3 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in table:
        mark = " *(underpowered)*" if row["underpowered"] else ""
        lines.append(
            f"| {row['slice']} | {row['cohort']}{mark} | {row['races']} | "
            f"{pct(row['good_positional_rate'])} | {pct(row['good_any2_rate'])} | "
            f"{pct(row['winner_in_top3'])} | {pct(row['top3_precision'])} | "
            f"{pct(row['miss_rate'])} | {pct(row['delta_good_positional'])} | "
            f"{pct(row['delta_winner_in_top3'])} | {pct(row['delta_top3_precision'])} |"
        )

    lines += [
        "",
        "## Matrix-dimension attribution (reconstructed weights baseline)",
        "",
        "Values: Top3 precision (Good-positional rate) per cohort. Baseline reconstructs "
        "`ability_score` from stored `matrix_scores` × live weights.",
        "",
        "| Dimension | Variant | " + " | ".join(cohorts.keys()) + " |",
        "|---|---|" + "---|" * len(cohorts),
    ]
    base = attr["baseline"]
    lines.append("| _baseline_ | live weights | " + " | ".join(
        f"{pct(base[n]['top3_precision'])} ({pct(base[n]['rates']['good_positional'])})" for n in cohorts) + " |")
    for key, variants in attr["dimensions"].items():
        for label, per_cohort in variants.items():
            lines.append(
                f"| {key} (w={MATRIX_WEIGHTS.get(key, 0.0):.3f}) | {label} | " + " | ".join(
                    f"{pct(per_cohort[n]['top3_precision'])} ({pct(per_cohort[n]['rates']['good_positional'])})"
                    for n in cohorts) + " |")

    lines += [
        "",
        "## Zero-hit races: winner vs model top-2 matrix deltas",
        "",
        f"Zero-hit races with a matched winner: **{zero_hit['zero_hit_races']}**. "
        "Positive = winner beat the model's top 2 on that dimension (signal existed but was outweighed).",
        "",
        "| Dimension | Winner − top2 avg |",
        "|---|---:|",
    ]
    for key, delta in sorted(zero_hit["winner_minus_top2_avg"].items(), key=lambda kv: -kv[1]):
        lines.append(f"| {key} | {delta:+.2f} |")
    lines.append("")

    out_md = ROOT / f"{args.report_date} HKJC Failure Cohorts and Attribution.md"
    out_json = ROOT / "scratch" / "hkjc_failure_cohorts.json"
    out_md.write_text("\n".join(lines), encoding="utf-8")
    out_json.write_text(json.dumps(
        {"report_date": args.report_date, "overall": overall, "cohort_table": table,
         "attribution": attr, "zero_hit": zero_hit}, ensure_ascii=False, indent=1, default=str),
        encoding="utf-8")
    print(f"Wrote {out_md}")
    print(f"Wrote {out_json}")
    print(f"races={overall['races']} zero_hit={zero_hit['zero_hit_races']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
