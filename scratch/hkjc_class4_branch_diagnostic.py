#!/usr/bin/env python3
"""Research-only diagnostic for a Class 4 condition-specific support branch.

This does not alter HKJC Wong Choi production scoring.  It reuses previously
generated race-level shadow predictions and applies the complete support matrix
only to Class 4 races; every other race retains the frozen baseline prediction.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
FORWARD_REPORT = ROOT / "scratch/hkjc_top2_forward_validation.json"
DISCOVERY_REPORT = ROOT / "scratch/hkjc_structural_signal_research_corrected.json"
OUTPUT = ROOT / "scratch/hkjc_class4_branch_diagnostic.json"
HELPER_PATH = ROOT / "scratch/hkjc_structural_signal_research.py"
SUPPORT_MODEL = "support_tw20_variant10_prior10_rail10"
FORWARD_MODEL = "candidate_b_trackwork_variant_prior_rail"


def _load_helper():
    spec = importlib.util.spec_from_file_location("hkjc_structural_signal_research", HELPER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load helper module: {HELPER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows).sort_values("race_key").reset_index(drop=True)


def _hybrid(base: pd.DataFrame, support: pd.DataFrame) -> pd.DataFrame:
    base_i = base.set_index("race_key").copy()
    support_i = support.set_index("race_key").copy()
    if set(base_i.index) != set(support_i.index):
        raise ValueError("Baseline and support predictions do not cover identical races")
    support_i = support_i.loc[base_i.index]
    class4 = base_i["race_class"].astype(str).str.strip().eq("Class 4")
    metric_columns = [
        "model",
        "top1_win",
        "top2_hits",
        "both_top2_place",
        "top3_hits",
        "top4_hits",
        "top4_all",
        "top5_hits",
        "top5_all",
        "winner_rank",
        "winner_mrr",
        "pick1_finish",
    ]
    base_i.loc[class4, metric_columns] = support_i.loc[class4, metric_columns]
    base_i["model"] = "class4_condition_specific_support_branch"
    return base_i.reset_index()


def _evaluate(helper, base: pd.DataFrame, support: pd.DataFrame) -> dict:
    hybrid = _hybrid(base, support)
    class4_mask = base["race_class"].astype(str).str.strip().eq("Class 4")
    return {
        "class4_races": int(class4_mask.sum()),
        "baseline": helper.summary(base),
        "hybrid": helper.summary(hybrid),
        "vs_baseline": helper.compare(base, hybrid),
        "class4_only_baseline": helper.summary(base.loc[class4_mask].copy()),
        "class4_only_support": helper.summary(support.loc[class4_mask].copy()),
        "class4_only_vs_baseline": helper.compare(
            base.loc[class4_mask].copy(), support.loc[class4_mask].copy()
        ),
        "hybrid_meeting_summary": {
            str(name): helper.summary(group)
            for name, group in hybrid.groupby("meeting_name", sort=True)
        },
        "race_rows": hybrid.to_dict(orient="records"),
    }


def main() -> None:
    helper = _load_helper()
    forward = json.loads(FORWARD_REPORT.read_text(encoding="utf-8"))
    discovery = json.loads(DISCOVERY_REPORT.read_text(encoding="utf-8"))

    scopes: dict[str, dict] = {}
    frames: dict[str, tuple[pd.DataFrame, pd.DataFrame]] = {}

    for scope in ["untouched_102_races", "full_113_races"]:
        base = _frame(forward["scopes"][scope]["baseline"]["race_rows"])
        support = _frame(forward["scopes"][scope][FORWARD_MODEL]["race_rows"])
        frames[scope] = (base, support)
        scopes[scope] = _evaluate(helper, base, support)

    discovery_base = _frame(discovery["models"]["baseline"]["race_rows"])
    discovery_support = _frame(discovery["models"][SUPPORT_MODEL]["race_rows"])
    scopes["rolling_discovery_80_races"] = _evaluate(helper, discovery_base, discovery_support)

    combined_base = pd.concat(
        [discovery_base, frames["full_113_races"][0]], ignore_index=True
    )
    combined_support = pd.concat(
        [discovery_support, frames["full_113_races"][1]], ignore_index=True
    )
    if combined_base["race_key"].duplicated().any():
        raise ValueError("Combined periods contain duplicate race keys")
    scopes["combined_193_races"] = _evaluate(helper, combined_base, combined_support)

    payload = {
        "research_only": True,
        "production_matrix_changed": False,
        "market_features_used": False,
        "status": "post_hoc_hypothesis_generation_not_independent_confirmation",
        "structural_rule": (
            "Use the full support matrix only for Class 4 races; use the frozen baseline "
            "for every other race."
        ),
        "selection_warning": (
            "The Class 4 branch was selected after inspecting condition slices. Results "
            "are suitable for shadow-test prioritisation, not production promotion."
        ),
        "scopes": scopes,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: {"class4_races": v["class4_races"], "baseline": v["baseline"], "hybrid": v["hybrid"], "vs_baseline": v["vs_baseline"]} for k, v in scopes.items()}, ensure_ascii=False, indent=2))
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
