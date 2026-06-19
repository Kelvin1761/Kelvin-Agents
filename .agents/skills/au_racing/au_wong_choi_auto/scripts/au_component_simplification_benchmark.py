#!/usr/bin/env python3
from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[4]

sys.path.append(str(SCRIPT_DIR))
sys.path.append(str(SCRIPT_DIR / "racing_engine"))

from au_noise_fix_shadow_test import _archive_runtime_races, _target_runtime_races  # type: ignore
from au_pace_profile_shadow_test import DEFAULT_TARGET_MEETINGS, load_archive_meetings, load_target_meetings  # type: ignore
from au_sip_tester import delta_report, evaluate_races, report_summary  # type: ignore

import engine_core  # type: ignore
import matrix_mapper  # type: ignore
from engine_core import RacingEngine  # type: ignore


OUTPUT_MD = PROJECT_ROOT / "2026-05-31 AU Component Simplification Benchmark（港式中文）.md"

VARIANTS = {
    "new_mainline": {
        "label": "建議主線",
        "summary": "移除 confidence ranking 作用，並保留 health_score 作為現行備戰/健康分。",
    },
    "experimental_health_live": {
        "label": "實驗版 health 入分",
        "summary": "如 engine 提供實驗版 health_score，則正式入分檢查會唔會比現行 health_score 更好。",
        "experimental_health": True,
    },
    "new_mainline_no_named_db": {
        "label": "建議主線 + 關閉 named DB",
        "summary": "喺建議主線基礎上，停用大場 named jockey/trainer ratings。",
        "disable_named_db": True,
    },
    "health_off": {
        "label": "建議主線 + 關閉 health",
        "summary": "保留建議主線其他改動，但 track matrix 只用 track_score。",
        "health_off": True,
    },
    "jt_no_combo": {
        "label": "建議主線 + 移除 combo 組件",
        "summary": "人馬配搭只保留 familiarity + signals，移除場館騎練 combo / trainer-track component。",
        "jt_component_weights": {"familiarity": 1.0, "combo": 0.0, "signals": 1.0},
    },
    "jt_no_signals": {
        "label": "建議主線 + 移除 signals 組件",
        "summary": "人馬配搭只保留 familiarity + combo，移除換騎訊號 / stage / apprentice component。",
        "jt_component_weights": {"familiarity": 1.0, "combo": 1.0, "signals": 0.0},
    },
    "jt_core_only": {
        "label": "建議主線 + 只留 familiarity",
        "summary": "人馬配搭只保留 horse-jockey familiarity / trial continuity / best-rider history core。",
        "jt_component_weights": {"familiarity": 1.0, "combo": 0.0, "signals": 0.0},
    },
}


@contextmanager
def patched_variant(config: dict):
    saved_named = engine_core.should_use_named_jt_ratings
    saved_method = RacingEngine._jockey_horse_fit_component_weights
    saved_health = RacingEngine._health_score
    saved_formulas = deepcopy(matrix_mapper.MATRIX_FORMULAS)
    try:
        if config.get("disable_named_db"):
            engine_core.should_use_named_jt_ratings = lambda race_context: False

        if config.get("experimental_health") and hasattr(RacingEngine, "_experimental_health_score"):
            RacingEngine._health_score = RacingEngine._experimental_health_score

        if config.get("jt_component_weights"):
            weights = dict(config["jt_component_weights"])

            def _component_weights(self, payload=weights):
                return dict(payload)

            RacingEngine._jockey_horse_fit_component_weights = _component_weights

        if config.get("health_off"):
            matrix_mapper.MATRIX_FORMULAS["track"] = (("track_score", 1.0),)

        yield
    finally:
        engine_core.should_use_named_jt_ratings = saved_named
        RacingEngine._jockey_horse_fit_component_weights = saved_method
        RacingEngine._health_score = saved_health
        matrix_mapper.MATRIX_FORMULAS.clear()
        matrix_mapper.MATRIX_FORMULAS.update(saved_formulas)


def _summary_block(title: str, summary: dict, delta_vs_stored: dict | None = None, delta_vs_mainline: dict | None = None) -> list[str]:
    lines = [
        f"## {title}",
        "",
        f"- Races: `{summary['races']}`",
        f"- Champion: `{summary['champion']}`",
        f"- Gold: `{summary['gold']}`",
        f"- Good: `{summary['good']}`",
        f"- Pass: `{summary['pass']}`",
        f"- Top3 Place: `{summary['top3_place']}`",
        f"- 0-hit: `{summary['0hit']}`",
        f"- 1-hit: `{summary['1hit']}`",
    ]
    if delta_vs_stored:
        lines.append(
            f"- 對 stored baseline: gold `{delta_vs_stored['gold_delta']:+.1f}`, good `{delta_vs_stored['good_delta']:+.1f}`, "
            f"pass `{delta_vs_stored['pass_delta']:+.1f}`, place `{delta_vs_stored['place_delta']:+.1f}`, "
            f"0-hit `{delta_vs_stored['0hit_delta']:+d}`, 1-hit `{delta_vs_stored['1hit_delta']:+d}`"
        )
    if delta_vs_mainline:
        lines.append(
            f"- 對新主線: gold `{delta_vs_mainline['gold_delta']:+.1f}`, good `{delta_vs_mainline['good_delta']:+.1f}`, "
            f"pass `{delta_vs_mainline['pass_delta']:+.1f}`, place `{delta_vs_mainline['place_delta']:+.1f}`, "
            f"0-hit `{delta_vs_mainline['0hit_delta']:+d}`, 1-hit `{delta_vs_mainline['1hit_delta']:+d}`"
        )
    lines.append("")
    return lines


def _run_runtime_variant(config: dict) -> tuple[list[dict], list[dict]]:
    with patched_variant(config):
        archive_races = _archive_runtime_races()
        target_races = _target_runtime_races(DEFAULT_TARGET_MEETINGS)
    return archive_races, target_races


def main() -> int:
    parser = argparse.ArgumentParser(description="AU component simplification benchmark")
    parser.add_argument("--output-md", default=str(OUTPUT_MD))
    args = parser.parse_args()

    stored_archive = load_archive_meetings()
    stored_target = load_target_meetings(DEFAULT_TARGET_MEETINGS)
    stored_archive_bucket, _, _, _ = evaluate_races(stored_archive, "stored_archive")
    stored_target_bucket, _, _, _ = evaluate_races(stored_target, "stored_target")
    stored_archive_summary = report_summary(stored_archive_bucket, "stored_archive")
    stored_target_summary = report_summary(stored_target_bucket, "stored_target")

    runtime_results: dict[str, dict] = {}
    for name, config in VARIANTS.items():
        archive_runtime, target_runtime = _run_runtime_variant(config)
        archive_bucket, _, _, _ = evaluate_races(archive_runtime, name)
        target_bucket, _, _, _ = evaluate_races(target_runtime, name)
        runtime_results[name] = {
            "config": config,
            "archive_bucket": archive_bucket,
            "archive_summary": report_summary(archive_bucket, name),
            "target_bucket": target_bucket,
            "target_summary": report_summary(target_bucket, name),
        }

    mainline_archive = runtime_results["new_mainline"]["archive_bucket"]
    mainline_target = runtime_results["new_mainline"]["target_bucket"]

    lines = [
        "# AU Component Simplification Benchmark（港式中文）",
        "",
        "目的：驗證 `confidence_score` 退出 ranking、`health_score` schema 對齊、以及 `jockey_horse_fit_score` 拆件後，喺 archive 同 `2026-05-30` 三個 meetings 是否有改善。",
        "",
        "## Stored Baseline",
        "",
        "### Archive",
        "",
        *_summary_block("Archive stored python_auto", stored_archive_summary),
        "### 2026-05-30 三場合併",
        "",
        *_summary_block("05-30 stored python_auto", stored_target_summary),
    ]

    for name, payload in runtime_results.items():
        config = payload["config"]
        lines.extend(
            [
                f"## Variant: {config['label']}",
                "",
                config["summary"],
                "",
                "### Archive",
                "",
            ]
        )
        lines.extend(
            _summary_block(
                f"{config['label']} / Archive",
                payload["archive_summary"],
                delta_vs_stored=delta_report(stored_archive_bucket, payload["archive_bucket"]),
                delta_vs_mainline=None if name == "new_mainline" else delta_report(mainline_archive, payload["archive_bucket"]),
            )
        )
        lines.extend(
            [
                "### 2026-05-30 三場合併",
                "",
            ]
        )
        lines.extend(
            _summary_block(
                f"{config['label']} / 05-30",
                payload["target_summary"],
                delta_vs_stored=delta_report(stored_target_bucket, payload["target_bucket"]),
                delta_vs_mainline=None if name == "new_mainline" else delta_report(mainline_target, payload["target_bucket"]),
            )
        )

    lines.extend(
        [
            "## 初步閱讀框架",
            "",
            "- `new_mainline` 代表你而家要求嘅核心結構修正有冇整體提升。",
            "- `experimental_health_live` 用嚟驗證實驗版 health 真係幫到手，定只會增加 noise。",
            "- `health_off` 用嚟驗證 health layer 有冇存在價值；如果關掉後更好，代表 track matrix 可再簡化。",
            "- `jt_no_combo` / `jt_no_signals` / `jt_core_only` 用嚟答『人馬配搭邊一層真係值得留』。",
            "- `new_mainline_no_named_db` 用嚟答『named jockey/trainer DB 係咪值得為咗少量 edge 保留複雜度』。",
            "",
        ]
    )

    output_path = Path(args.output_md)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
