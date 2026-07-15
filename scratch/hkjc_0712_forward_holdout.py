#!/usr/bin/env python3
"""Apply pre-declared market-free structural candidates to 2026-07-12 only.

The candidate definitions came from the April-May discovery archive.  This
script does not tune any parameter on the July result.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
HARNESS_PATH = ROOT / "scratch/hkjc_structural_signal_research.py"
TRAIN_PATH = ROOT / ".agents/skills/hkjc_racing/hkjc_reflector/artifacts/hkjc_ranking_dataset.csv"
TEST_PATH = ROOT / "scratch/hkjc_2026-07-12_ranking_dataset.csv"
OUTPUT_PATH = ROOT / "scratch/hkjc_2026-07-12_forward_holdout.json"


def load_harness():
    spec = importlib.util.spec_from_file_location("hkjc_structural_signal_research", HARNESS_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def main() -> int:
    h = load_harness()
    train_raw = pd.read_csv(TRAIN_PATH, encoding="utf-8-sig")
    test_raw = pd.read_csv(TEST_PATH, encoding="utf-8-sig")
    train_raw["__split"] = "train"
    test_raw["__split"] = "test"
    prepared, blocks = h.prepare(pd.concat([train_raw, test_raw], ignore_index=True))
    train = prepared[prepared["__split"] == "train"].copy()
    test = prepared[prepared["__split"] == "test"].copy()

    test["score__baseline"] = pd.to_numeric(test[h.BASELINE], errors="coerce")
    rows = {"baseline": h.race_rows(test, "score__baseline", "baseline")}

    direct_specs = {
        "distance_course_record": blocks["distance_course_record"],
        "clean_variant_sectional": blocks["clean_variant_sectional"],
    }
    for name, columns in direct_specs.items():
        test[f"score__{name}"] = h.predict_block(train, test, columns)
        rows[name] = h.race_rows(test, f"score__{name}", name)

    support_specs = {
        "support_trackwork_trial_20": {"trackwork_trial": 0.20},
        "support_variant_sectional_10": {"variant_sectional": 0.10},
        "support_tw20_variant10": {"trackwork_trial": 0.20, "variant_sectional": 0.10},
        "support_tw20_variant10_distance10": {
            "trackwork_trial": 0.20,
            "variant_sectional": 0.10,
            "distance_course_record": 0.10,
        },
        "support_tw20_variant10_prior10_rail10": {
            "trackwork_trial": 0.20,
            "variant_sectional": 0.10,
            "historical_professional_priors": 0.10,
            "rail_draw_condition": 0.10,
        },
        "support_clean_trackwork_20": {"clean_trackwork_trial": 0.20},
        "support_clean_variant_10": {"clean_variant_sectional": 0.10},
        "support_clean_tw20_variant10": {
            "clean_trackwork_trial": 0.20,
            "clean_variant_sectional": 0.10,
        },
    }
    required = sorted({block for spec in support_specs.values() for block in spec})
    support_scores = {block: h.predict_support(train, test, blocks[block]) for block in required}
    baseline_z = h._race_z(pd.to_numeric(test[h.BASELINE], errors="coerce"), test["race_key"])
    for name, spec in support_specs.items():
        score = baseline_z.copy()
        for block, strength in spec.items():
            score = score + strength * support_scores[block]
        test[f"score__{name}"] = score
        rows[name] = h.race_rows(test, f"score__{name}", name)

    frames = {name: pd.DataFrame(value) for name, value in rows.items()}
    baseline = frames["baseline"]
    report = {
        "research_only": True,
        "market_features_used": [],
        "parameter_tuning_on_2026_07_12": False,
        "train": {
            "meetings": int(train["date"].nunique()),
            "races": int(train["race_key"].nunique()),
            "rows": int(len(train)),
            "date_range": [str(train["date"].min()), str(train["date"].max())],
        },
        "test": {
            "meetings": 1,
            "races": int(test["race_key"].nunique()),
            "rows": int(len(test)),
            "date": "2026-07-12",
        },
        "models": {},
    }
    for name, frame in frames.items():
        entry = {
            "summary": h.summary(frame),
            "race_rows": frame.to_dict(orient="records"),
        }
        if name != "baseline":
            entry["vs_baseline"] = h.compare(baseline, frame)
        report["models"][name] = entry

    OUTPUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({name: entry["summary"] for name, entry in report["models"].items()}, ensure_ascii=False, indent=2))
    print(f"Report: {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
