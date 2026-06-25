#!/usr/bin/env python3
from __future__ import annotations

import itertools
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[4]
import sys as _sys; _sys.path.insert(0, str(PROJECT_ROOT))
from wongchoi_paths import AU_RACING
AUTO_DIR = PROJECT_ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts"
sys.path.insert(0, str(AUTO_DIR))
sys.path.insert(0, str(AUTO_DIR / "racing_engine"))

from au_market_free_ablation import (  # noqa: E402
    FORMULA_PRESETS,
    PLACE_MODES,
    apply_variant,
    delta_report,
    evaluate_races,
    load_all_races,
    metric_score,
    report_summary,
)


OUTPUT_MD = AU_RACING / "AU_BM58_GoodFirm_Search.md"

FOCUS_FORMULAS = (
    "jt_fit_tempered",
    "class_weight_class_only",
    "class_weight_80_20",
    "track_pure",
    "formline_purer",
    "race_shape_light_track",
)

PLACE_SCALE_MAP = {
    "place_live": 1.0,
    "place_085": 0.85,
    "place_070": 0.70,
    "place_half": 0.50,
    "place_off": 0.0,
}


def evaluate_variant_scaled(races: list[dict], formula_names: tuple[str, ...], place_scale: float):
    def adjust(horses, race):
        place_mode = "place_live"
        original = PLACE_MODES["place_live"]
        PLACE_MODES["place_live"] = place_scale
        try:
            return apply_variant(horses, race, formula_names, place_mode)
        finally:
            PLACE_MODES["place_live"] = original

    return evaluate_races(races, "variant", adjust)


def subset_races(races: list[dict], *, condition: str, race_class: str) -> list[dict]:
    return [
        race
        for race in races
        if race.get("condition_bucket") == condition and race.get("race_class_bucket") == race_class
    ]


def candidate_rows(full_races: list[dict], core_races: list[dict]) -> list[dict]:
    baseline_full, _, _, _ = evaluate_races(full_races, "baseline")
    baseline_core, _, _, _ = evaluate_races(core_races, "baseline")

    rows = []
    formula_sets = [()]
    for combo_size in (1, 2, 3, 4):
        formula_sets.extend(itertools.combinations(FOCUS_FORMULAS, combo_size))

    for formula_names in formula_sets:
        for place_label, place_scale in PLACE_SCALE_MAP.items():
            if not formula_names and place_scale == 1.0:
                continue
            overall, _, _, _ = evaluate_variant_scaled(full_races, formula_names, place_scale)
            core, _, _, _ = evaluate_variant_scaled(core_races, formula_names, place_scale)
            rows.append(
                {
                    "formula": "+".join(formula_names) or "baseline_formula",
                    "place_label": place_label,
                    "place_scale": place_scale,
                    "overall": overall,
                    "core": core,
                    "overall_summary": report_summary(overall, "overall"),
                    "core_summary": report_summary(core, "core"),
                    "overall_delta": delta_report(baseline_full, overall),
                    "core_delta": delta_report(baseline_core, core),
                    "promotion_like": (
                        core["good"] >= baseline_core["good"]
                        and core["minimum"] > baseline_core["minimum"]
                        and overall["good"] >= baseline_full["good"] - 1
                    ),
                }
            )
    return baseline_full, baseline_core, rows


def row_sort_key(row: dict):
    core = row["core"]
    overall = row["overall"]
    return (
        core["good"] / (core["races"] or 1),
        core["minimum"] / (core["races"] or 1),
        -(core["hit_distribution"][0] / (core["races"] or 1)),
        overall["good"] / (overall["races"] or 1),
        overall["minimum"] / (overall["races"] or 1),
        metric_score(core),
        metric_score(overall),
    )


def pct(value: str) -> str:
    return value


def main() -> int:
    races = load_all_races()
    core_races = subset_races(races, condition="Good/Firm", race_class="BM58-70")
    baseline_full, baseline_core, rows = candidate_rows(races, core_races)
    rows.sort(key=row_sort_key, reverse=True)

    promotion_like = [row for row in rows if row["promotion_like"]]
    top_rows = rows[:20]

    lines = [
        "# AU BM58-70 Good/Firm Targeted Search",
        "",
        "- Focus bucket: `Good/Firm + BM58-70`",
        f"- Full races: **{baseline_full['races']}**",
        f"- Core races: **{baseline_core['races']}**",
        "",
        "## Baseline",
        "",
        f"- Full: Good **{report_summary(baseline_full, 'full')['good']}**, Pass **{report_summary(baseline_full, 'full')['pass']}**, 0-hit **{report_summary(baseline_full, 'full')['0hit']}**",
        f"- Core: Good **{report_summary(baseline_core, 'core')['good']}**, Pass **{report_summary(baseline_core, 'core')['pass']}**, 0-hit **{report_summary(baseline_core, 'core')['0hit']}**",
        "",
        "## Promotion-Like Candidates",
        "",
        "Definition: core `Good` flat or better, core `Pass` higher, full-sample `Good` no worse than -1 race.",
        "",
    ]

    if promotion_like:
        lines.extend(
            [
                "| Rank | Candidate | Core Good | Core Pass | Core 0H | Full Good | Full Pass | Core Delta | Full Delta |",
                "|---:|---|---:|---:|---:|---:|---:|---|---|",
            ]
        )
        for idx, row in enumerate(promotion_like[:10], 1):
            core = row["core_summary"]
            overall = row["overall_summary"]
            cd = row["core_delta"]
            od = row["overall_delta"]
            lines.append(
                f"| {idx} | {row['formula']} / {row['place_label']} | {core['good']} | {core['pass']} | {core['0hit']} | "
                f"{overall['good']} | {overall['pass']} | "
                f"G {cd['good_delta']:+.1f} / P {cd['pass_delta']:+.1f} / 0H {cd['0hit_delta']:+d} | "
                f"G {od['good_delta']:+.1f} / P {od['pass_delta']:+.1f} / 0H {od['0hit_delta']:+d} |"
            )
    else:
        lines.append("No candidate passed the promotion-like filter.")

    lines.extend(
        [
            "",
            "## Top Core Candidates",
            "",
            "| Rank | Candidate | Core Good | Core Pass | Core 0H | Full Good | Full Pass | Core Delta | Full Delta |",
            "|---:|---|---:|---:|---:|---:|---:|---|---|",
        ]
    )
    for idx, row in enumerate(top_rows, 1):
        core = row["core_summary"]
        overall = row["overall_summary"]
        cd = row["core_delta"]
        od = row["overall_delta"]
        lines.append(
            f"| {idx} | {row['formula']} / {row['place_label']} | {core['good']} | {core['pass']} | {core['0hit']} | "
            f"{overall['good']} | {overall['pass']} | "
            f"G {cd['good_delta']:+.1f} / P {cd['pass_delta']:+.1f} / 0H {cd['0hit_delta']:+d} | "
            f"G {od['good_delta']:+.1f} / P {od['pass_delta']:+.1f} / 0H {od['0hit_delta']:+d} |"
        )

    OUTPUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUTPUT_MD}")
    print(f"Core races: {baseline_core['races']} | Full races: {baseline_full['races']}")
    print(f"Promotion-like candidates: {len(promotion_like)}")
    if top_rows:
        best = top_rows[0]
        print("Top core candidate:", best["formula"], best["place_label"], best["core_delta"], best["overall_delta"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
