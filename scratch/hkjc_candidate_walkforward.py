#!/usr/bin/env python3
"""HKJC candidate weight test — pre-registered expanding walk-forward gate.

The 2026-07-17 cohort attribution surfaced ONE causal-trigger candidate with
measured in-sample support: shrinking trainer_signal weight (−20% raised
archive-wide Good-positional +1.6pp in-sample; trainer_signal is the 2nd-largest
weight at 0.221). This harness tests weight-multiplier candidates through the
pre-registered gate — the SAME gate used for AU:

  * Good (positional) >= +1.5pp OOS, meeting-grouped expanding walk-forward
  * losses <= 0.5pp on Gold / Top1 / W-in-T3
  * Miss non-regression
  * Top3 fold stability >= 4/5 folds
  * candidate multiplier selected per fold on TRAIN meetings only

Ranking is a pure re-weighting of the stored per-horse matrix_scores
(reconstruction is exact vs stored ability_score), so no Drive re-scoring is
needed. Reported for the full 243-race archive AND the faithful cohort
(schema HKJC_LOGIC_V4_2, i.e. sectional-seeing May-06 onward) so the
sectional-blind April artifact cannot flatter a go-forward weight decision.

Usage:
    python3 scratch/hkjc_candidate_walkforward.py [--folds 5] [--faithful-only]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

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

# Candidate = per-dimension weight multiplier applied to live MATRIX_WEIGHTS.
CANDIDATES = {
    "trainer_signal x0.7": {"trainer_signal": 0.7},
    "trainer_signal x0.8": {"trainer_signal": 0.8},
    "trainer_signal x0.9": {"trainer_signal": 0.9},
}
# Per-fold train-only selection grid for the trainer_signal multiplier.
TRAINER_GRID = [0.7, 0.8, 0.9]


def as_float(v, d=60.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def find_results_json(meeting: Path):
    files = sorted(meeting.glob("*全日賽果.json"))
    return files[0] if files else None


def load_results(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for k, race in data.items():
        try:
            rn = int(k)
        except (TypeError, ValueError):
            continue
        pos = {}
        for row in race.get("results", []):
            try:
                pos[int(row["horse_no"])] = int(row["pos"])
            except (KeyError, TypeError, ValueError):
                continue
        if pos:
            out[rn] = pos
    return out


def load_races():
    races = []
    for meeting in sorted(HK_RACING.iterdir()):
        if not meeting.is_dir() or "(" in meeting.name or not meeting.name.startswith("2026"):
            continue
        rp = find_results_json(meeting)
        if rp is None or not list(meeting.glob("Race_*_Logic.json")):
            continue
        actual = load_results(rp)
        for lp in sorted(meeting.glob("Race_*_Logic.json")):
            m = re.search(r"Race_(\d+)_Logic\.json$", lp.name)
            rn = int(m.group(1)) if m else 0
            if rn not in actual:
                continue
            logic = json.loads(lp.read_text(encoding="utf-8"))
            schema = logic.get("schema_version")
            rows = []
            for hn_text, horse in logic.get("horses", {}).items():
                try:
                    hn = int(hn_text)
                except ValueError:
                    continue
                auto = horse.get("python_auto", {})
                if not auto.get("feature_scores"):
                    continue
                rows.append({
                    "horse": hn,
                    "ability": as_float(auto.get("ability_score"), 60.0),
                    "matrix": {k: as_float((auto.get("matrix_scores") or {}).get(k), 60.0) for k in MATRIX_KEYS},
                })
            if len(rows) < 4:
                continue
            pos = actual[rn]
            top3 = [h for h, p in pos.items() if p <= 3]
            if sum(1 for p in pos.values() if p <= 3) < 3 or not top3:
                continue
            races.append({"meeting": meeting.name, "date": meeting.name[:10],
                          "schema_v4": schema == "HKJC_LOGIC_V4_2",
                          "rows": rows, "pos": pos, "top3": top3})
    return races


def rank_eval(race, mult=None):
    weights = dict(MATRIX_WEIGHTS)
    if mult:
        for k, m in mult.items():
            weights[k] = MATRIX_WEIGHTS[k] * m
    scored = [(r["horse"], sum(weights[k] * r["matrix"][k] for k in MATRIX_KEYS)) for r in race["rows"]]
    order = dict(scored)
    picks = [r["horse"] for r in sorted(race["rows"], key=lambda r: (-order[r["horse"]], r["horse"]))]
    return race_metrics(picks, race["top3"], actual_pos=race["pos"])


def summ(races, mult=None):
    return summarize_races([rank_eval(r, mult) for r in races])


def good_pos_rate(races, mult=None):
    return summ(races, mult)["rates"]["good_positional"]


def walk_forward(races, folds):
    """Expanding meeting-grouped walk-forward with per-fold train-only selection."""
    meetings = sorted({r["meeting"] for r in races})
    n = len(meetings)
    # seed train = first block; remaining split into `folds` contiguous test blocks
    seed = max(1, n // (folds + 1))
    test_meetings = meetings[seed:]
    block = max(1, len(test_meetings) // folds)
    fold_results = []
    for i in range(folds):
        start = i * block
        end = (i + 1) * block if i < folds - 1 else len(test_meetings)
        test_set = set(test_meetings[start:end])
        if not test_set:
            continue
        train_set = set(meetings[:seed + start])
        train_races = [r for r in races if r["meeting"] in train_set]
        test_races = [r for r in races if r["meeting"] in test_set]
        # select trainer multiplier on TRAIN only
        best_mult, best_gp = 1.0, -1.0
        for mv in TRAINER_GRID:
            gp = good_pos_rate(train_races, {"trainer_signal": mv})
            if gp > best_gp:
                best_gp, best_mult = gp, mv
        base = summ(test_races)
        cand = summ(test_races, {"trainer_signal": best_mult})
        fold_results.append({
            "fold": i + 1, "train_meetings": len(train_set), "test_meetings": len(test_set),
            "test_races": base["races"], "selected_mult": best_mult,
            "base": base["rates"], "cand": cand["rates"],
            "base_top3prec": base["top3_precision"], "cand_top3prec": cand["top3_precision"],
            "base_miss": base["exclusive_labels"].get("Miss", 0),
            "cand_miss": cand["exclusive_labels"].get("Miss", 0),
        })
    return fold_results


def aggregate_gate(fold_results):
    import statistics
    def mean_delta(key):
        return statistics.mean(f["cand"][key] - f["base"][key] for f in fold_results)
    good_delta = mean_delta("good_positional")
    gold_delta = mean_delta("gold")
    top1_delta = mean_delta("champion")
    wint3_delta = mean_delta("winner_in_top3")
    miss_delta = statistics.mean(f["cand_miss"] - f["base_miss"] for f in fold_results)
    top3_stable = sum(1 for f in fold_results if f["cand_top3prec"] >= f["base_top3prec"] - 1e-9)
    passed = (
        good_delta >= 0.015
        and gold_delta >= -0.005 and top1_delta >= -0.005 and wint3_delta >= -0.005
        and miss_delta <= 0
        and top3_stable >= 4
    )
    return {
        "good_delta_pp": round(good_delta * 100, 2),
        "gold_delta_pp": round(gold_delta * 100, 2),
        "top1_delta_pp": round(top1_delta * 100, 2),
        "wint3_delta_pp": round(wint3_delta * 100, 2),
        "miss_delta_races_mean": round(miss_delta, 2),
        "top3_fold_stability": f"{top3_stable}/{len(fold_results)}",
        "PASS": passed,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--faithful-only", action="store_true")
    args = ap.parse_args()

    races = load_races()
    faithful = [r for r in races if r["schema_v4"]]
    print(f"Loaded {len(races)} races ({len(faithful)} faithful V4.2 / "
          f"{len(races) - len(faithful)} sectional-blind).")

    report = {"generated": "2026-07-17", "n_all": len(races), "n_faithful": len(faithful),
              "in_sample": {}, "walk_forward": {}}

    # In-sample perturbation snapshot (context, not the gate)
    for label, mult in CANDIDATES.items():
        report["in_sample"][label] = {
            "all_good_pos_pp": round(100 * good_pos_rate(races, mult), 2),
            "faithful_good_pos_pp": round(100 * good_pos_rate(faithful, mult), 2),
        }
    report["in_sample"]["baseline"] = {
        "all_good_pos_pp": round(100 * good_pos_rate(races), 2),
        "faithful_good_pos_pp": round(100 * good_pos_rate(faithful), 2),
    }

    for name, subset in (("all_archive", races), ("faithful_only", faithful)):
        fr = walk_forward(subset, args.folds)
        gate = aggregate_gate(fr)
        report["walk_forward"][name] = {"folds": fr, "gate": gate}
        print(f"\n=== Walk-forward gate: {name} ({len(subset)} races, {args.folds} folds) ===")
        for f in fr:
            print(f"  fold{f['fold']}: train={f['train_meetings']}m test={f['test_meetings']}m/{f['test_races']}r "
                  f"mult={f['selected_mult']} | good {100*f['base']['good_positional']:.1f}→"
                  f"{100*f['cand']['good_positional']:.1f} | top3prec {100*f['base_top3prec']:.1f}→"
                  f"{100*f['cand_top3prec']:.1f}")
        print(f"  GATE: good Δ{gate['good_delta_pp']:+}pp | gold Δ{gate['gold_delta_pp']:+} "
              f"top1 Δ{gate['top1_delta_pp']:+} wint3 Δ{gate['wint3_delta_pp']:+} | "
              f"miss Δ{gate['miss_delta_races_mean']:+} | top3 {gate['top3_fold_stability']} | "
              f"{'PASS' if gate['PASS'] else 'FAIL'}")

    out = ROOT / "scratch" / "hkjc_candidate_walkforward.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
