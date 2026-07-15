#!/usr/bin/env python3
"""Top2-first forward validation on post-discovery HKJC meetings.

Primary candidate definitions are frozen from the 2026-07-13 research report.
No forward result is used for feature or weight selection.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "scratch/hkjc_structural_signal_research.py"
TRAIN = ROOT / "scratch/hkjc_discovery_20260412_20260524_dataset.csv"
TEST = ROOT / "scratch/hkjc_forward_20260527_20260712_dataset.csv"
OUTPUT = ROOT / "scratch/hkjc_top2_forward_validation.json"


PRIMARY_SPECS = {
    "candidate_a_trackwork_20": {"trackwork_trial": 0.20},
    "candidate_b_trackwork_variant_prior_rail": {
        "trackwork_trial": 0.20,
        "variant_sectional": 0.10,
        "historical_professional_priors": 0.10,
        "rail_draw_condition": 0.10,
    },
}

DIAGNOSTIC_SPECS = {
    "ablation_trackwork_variant": {
        "trackwork_trial": 0.20,
        "variant_sectional": 0.10,
    },
}


def load_harness():
    spec = importlib.util.spec_from_file_location("hkjc_structural_signal_research", HARNESS)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def evaluate_scope(h, frames: dict[str, pd.DataFrame], scope_dates: pd.Series) -> dict:
    scoped = {name: frame.loc[scope_dates.loc[frame.index]].copy() for name, frame in frames.items()}
    baseline = scoped["baseline"]
    output = {}
    for name, frame in scoped.items():
        entry = {
            "summary": h.summary(frame),
            "slices": h.slice_summary(frame),
            "meeting_summary": {
                meeting: h.summary(group)
                for meeting, group in frame.groupby("meeting_name", sort=True)
            },
            "race_rows": frame.to_dict(orient="records"),
        }
        if name != "baseline":
            entry["vs_baseline"] = h.compare(baseline, frame)
        output[name] = entry
    return output


def gate(candidate: dict, baseline: dict) -> dict:
    c = candidate["summary"]
    b = baseline["summary"]
    top1_delta = c["top1_rate"] - b["top1_rate"]
    top2_delta = c["top2_individual_place_rate"] - b["top2_individual_place_rate"]
    both_delta = c["both_top2_place_rate"] - b["both_top2_place_rate"]
    top4_delta = c["avg_top4_hits"] - b["avg_top4_hits"]
    top4_stats = candidate["vs_baseline"]["top4_hits"]
    checks = {
        "top1_no_regression": top1_delta >= -0.01,
        "top2_gain_at_least_2pp": top2_delta >= 0.02,
        "both_top2_not_down": both_delta >= 0.0,
        "top4_not_down": top4_delta >= 0.0,
        "top4_statistically_confirmed": (
            top4_stats["wilcoxon_p_value"] < 0.05
            and top4_stats["bootstrap_95_ci"][0] > 0
        ),
    }
    return {
        "deltas": {
            "top1_rate": round(top1_delta, 4),
            "top2_individual_place_rate": round(top2_delta, 4),
            "both_top2_place_rate": round(both_delta, 4),
            "avg_top4_hits": round(top4_delta, 4),
        },
        "checks": checks,
        "passes_directional_gate": all(
            checks[key]
            for key in (
                "top1_no_regression",
                "top2_gain_at_least_2pp",
                "both_top2_not_down",
                "top4_not_down",
            )
        ),
        "passes_production_evidence_gate": all(checks.values()),
    }


def main() -> int:
    h = load_harness()
    train_raw = pd.read_csv(TRAIN, encoding="utf-8-sig")
    test_raw = pd.read_csv(TEST, encoding="utf-8-sig")
    train_raw["__split"] = "train"
    test_raw["__split"] = "test"
    prepared, blocks = h.prepare(pd.concat([train_raw, test_raw], ignore_index=True))
    train = prepared[prepared["__split"] == "train"].copy()
    test = prepared[prepared["__split"] == "test"].copy()

    test["score__baseline"] = pd.to_numeric(test[h.BASELINE], errors="coerce")
    race_frames = {
        "baseline": pd.DataFrame(h.race_rows(test, "score__baseline", "baseline"))
    }
    specs = {**PRIMARY_SPECS, **DIAGNOSTIC_SPECS}
    needed = sorted({block for item in specs.values() for block in item})
    support = {block: h.predict_support(train, test, blocks[block]) for block in needed}
    baseline_z = h._race_z(pd.to_numeric(test[h.BASELINE], errors="coerce"), test["race_key"])
    for name, item in specs.items():
        score = baseline_z.copy()
        for block, strength in item.items():
            score = score + strength * support[block]
        test[f"score__{name}"] = score
        race_frames[name] = pd.DataFrame(h.race_rows(test, f"score__{name}", name))

    row_dates = race_frames["baseline"]["date"]
    untouched_mask = row_dates < "2026-07-12"
    full_mask = pd.Series(True, index=row_dates.index)
    scopes = {
        "untouched_102_races": evaluate_scope(h, race_frames, untouched_mask),
        "full_113_races": evaluate_scope(h, race_frames, full_mask),
    }
    for scope in scopes.values():
        baseline = scope["baseline"]
        for name in PRIMARY_SPECS:
            scope[name]["top2_first_gate"] = gate(scope[name], baseline)

    report = {
        "research_only": True,
        "market_features_used": [],
        "forward_results_used_for_tuning": False,
        "priority_order": [
            "top2_individual_place_rate",
            "both_top2_place_rate",
            "top1_no_regression",
            "top4_coverage",
        ],
        "train": {
            "meetings": int(train["date"].nunique()),
            "races": int(train["race_key"].nunique()),
            "rows": int(len(train)),
            "date_range": [str(train["date"].min()), str(train["date"].max())],
        },
        "test": {
            "meetings": int(test["date"].nunique()),
            "races": int(test["race_key"].nunique()),
            "rows": int(len(test)),
            "date_range": [str(test["date"].min()), str(test["date"].max())],
        },
        "primary_specs": PRIMARY_SPECS,
        "diagnostic_specs": DIAGNOSTIC_SPECS,
        "scopes": scopes,
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    concise = {
        scope_name: {
            model: {
                "summary": values["summary"],
                "gate": values.get("top2_first_gate"),
            }
            for model, values in scope.items()
        }
        for scope_name, scope in scopes.items()
    }
    print(json.dumps(concise, ensure_ascii=False, indent=2))
    print(f"report={OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
