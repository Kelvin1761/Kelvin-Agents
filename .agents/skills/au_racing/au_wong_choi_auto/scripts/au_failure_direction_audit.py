#!/usr/bin/env python3
"""Audit the two AU ranking errors that matter most without scoring from SP.

SP and actual position enter only after the stored pre-race score has fixed the
model rank.  They label retrospective failure cohorts; they are never inputs to
the model score in this script.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
PROJECT_ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(PROJECT_ROOT / ".agents/skills/au_racing/"
                      "au_wong_choi_auto/scripts"))
from au_racing_engine.scoring import MATRIX_WEIGHTS as ENGINE_MATRIX_WEIGHTS  # noqa: E402


# 2026-09-04：呢個清單以前係手抄嘅，凍結咗喺 2026-08 之前嘅引擎（16 個 leaf / 7 個維度，仲有已退役嘅 race_shape 同 form_line）。
# 由引擎攞，唔好再抄 —— 抄咗嘅版本唔會報錯，只會靜靜咁少計幾個 leaf，
# 然後你會攞住個結論話「呢個維度冇貢獻」。
MATRIX_KEYS = tuple(ENGINE_MATRIX_WEIGHTS)


def _ranked(rows: list[dict]) -> list[dict]:
    """Rank only by the frozen pre-race model score."""
    return sorted(
        rows,
        key=lambda row: (-float(row["score"]), int(row["horse_number"])),
    )


def _field_means(rows: list[dict], container: str) -> dict[str, float]:
    keys = set().union(*(row.get(container, {}) for row in rows))
    return {
        key: mean(float(row.get(container, {}).get(key, 60.0)) for row in rows)
        for key in keys
    }


def _drivers(
    row: dict,
    means: dict[str, float],
    container: str,
    *,
    high: bool,
    limit: int,
) -> list[dict]:
    values = []
    for key, field_mean in means.items():
        value = float(row.get(container, {}).get(key, 60.0))
        values.append({
            "signal": key,
            "score": round(value, 2),
            "field_delta": round(value - field_mean, 2),
        })
    values.sort(key=lambda item: item["field_delta"], reverse=high)
    values = [
        item for item in values
        if (item["field_delta"] > 0 if high else item["field_delta"] < 0)
    ]
    return values[:limit]


def _evidence_gaps(row: dict) -> list[str]:
    return sorted(
        key for key, state in (row.get("feature_evidence_state") or {}).items()
        if state in {"missing", "fallback"}
    )


def _record(
    race: dict,
    row: dict,
    rank: int,
    matrix_means: dict[str, float],
    feature_means: dict[str, float],
    *,
    high: bool,
) -> dict:
    meta = race.get("metadata") or {}
    return {
        "race_id": (
            f"{meta.get('date')}|{meta.get('track')}|R{meta.get('race_number')}"
        ),
        "date": meta.get("date"),
        "track": meta.get("track"),
        "going": meta.get("going"),
        "distance": meta.get("distance"),
        "field_size": meta.get("field_size") or len(race["rows"]),
        "horse_number": row.get("horse_number"),
        "horse_name": row.get("horse_name"),
        "model_rank": rank,
        "score": row.get("score"),
        "actual_pos": row.get("actual_pos"),
        "sp": row.get("result_sp_label"),
        "matrix_drivers": _drivers(
            row, matrix_means, "matrix_scores", high=high, limit=4,
        ),
        "feature_drivers": _drivers(
            row, feature_means, "feature_scores", high=high, limit=6,
        ),
        "evidence_gaps": _evidence_gaps(row),
        "risk_flags": row.get("risk_flags") or [],
    }


def analyze_races(
    races: list[dict],
    *,
    big_odds: float = 21.0,
    model_top: int = 3,
    low_rank: int = 5,
    low_price: float = 4.0,
) -> dict:
    cold_last = []
    cold_tail_two = []
    favourite_missed = []
    low_price_missed = []
    race_count = 0

    for race in races:
        rows = [
            row for row in race.get("rows", [])
            if row.get("actual_pos") is not None and row.get("score") is not None
        ]
        if not rows:
            continue
        race_count += 1
        ranked = _ranked(rows)
        ranks = {int(row["horse_number"]): rank for rank, row in enumerate(ranked, 1)}
        last_position = max(int(row["actual_pos"]) for row in rows)
        matrix_means = _field_means(rows, "matrix_scores")
        feature_means = _field_means(rows, "feature_scores")

        priced = [row for row in rows if row.get("result_sp_label") is not None]
        favourite_sp = min(
            (float(row["result_sp_label"]) for row in priced),
            default=None,
        )
        for row in rows:
            rank = ranks[int(row["horse_number"])]
            sp = row.get("result_sp_label")
            actual = int(row["actual_pos"])
            if sp is not None and rank <= model_top and float(sp) >= big_odds:
                if actual == last_position:
                    cold_last.append(_record(
                        race, row, rank, matrix_means, feature_means, high=True,
                    ))
                if actual >= max(1, last_position - 1):
                    cold_tail_two.append(_record(
                        race, row, rank, matrix_means, feature_means, high=True,
                    ))
            if actual <= 3 and rank >= low_rank and sp is not None:
                if favourite_sp is not None and float(sp) == favourite_sp:
                    favourite_missed.append(_record(
                        race, row, rank, matrix_means, feature_means, high=False,
                    ))
                if float(sp) <= low_price:
                    low_price_missed.append(_record(
                        race, row, rank, matrix_means, feature_means, high=False,
                    ))

    return {
        "design": {
            "ranking_input": "stored pre-race score only",
            "sp_role": "post-score retrospective cohort label only",
            "actual_position_role": "post-score outcome label only",
            "big_odds_threshold": big_odds,
            "model_top_cutoff": model_top,
            "low_model_rank_cutoff": low_rank,
            "low_price_threshold": low_price,
        },
        "races": race_count,
        "cohorts": {
            "model_top_big_odds_finished_last": cold_last,
            "model_top_big_odds_finished_tail_two": cold_tail_two,
            "market_favourite_top3_but_model_low": favourite_missed,
            "sp_at_most_4_top3_but_model_low": low_price_missed,
        },
    }


def _counter(records: list[dict], key: str) -> list[tuple[str, int]]:
    return Counter(
        item["signal"]
        for record in records
        for item in record[key][:3]
    ).most_common()


def _gap_counter(records: list[dict]) -> list[tuple[str, int]]:
    return Counter(
        gap for record in records for gap in record["evidence_gaps"]
    ).most_common()


def _cohort_counter(records: list[dict], key: str) -> list[tuple[str, int]]:
    return Counter(str(record.get(key) or "Unknown") for record in records).most_common()


def summarize(report: dict) -> dict:
    output = {}
    for name, records in report["cohorts"].items():
        output[name] = {
            "count": len(records),
            "recurring_matrix_drivers": _counter(records, "matrix_drivers"),
            "recurring_feature_drivers": _counter(records, "feature_drivers"),
            "missing_or_fallback_evidence": _gap_counter(records),
            "tracks": _cohort_counter(records, "track"),
            "goings": _cohort_counter(records, "going"),
            "field_sizes": _cohort_counter(records, "field_size"),
        }
    return output


def render_markdown(report: dict) -> str:
    report["summary"] = summarize(report)
    summary = report["summary"]
    labels = {
        "model_top_big_odds_finished_last": "Model Top 3 + SP≥21 + 實際包尾",
        "model_top_big_odds_finished_tail_two": "Model Top 3 + SP≥21 + 實際尾二",
        "market_favourite_top3_but_model_low": "市場頭馬入前三，Model 排第 5+",
        "sp_at_most_4_top3_but_model_low": "SP≤4 入前三，Model 排第 5+",
    }
    lines = [
        "# AU Failure Direction Audit",
        "",
        f"- Fixed current-runtime races: **{report['races']}**",
        "- Model rank 先只由 pre-race score 固定；SP 同實際名次只作賽後錯誤標籤。",
        "- 呢份 audit 唔會用賠率重排，亦唔會更改 scoring matrix。",
        "",
        "## Cohort summary",
        "",
        "| Cohort | Cases | Recurring matrices | Recurring missing/fallback |",
        "|---|---:|---|---|",
    ]
    for name, item in summary.items():
        matrices = ", ".join(
            f"{key}={count}" for key, count in item["recurring_matrix_drivers"][:5]
        ) or "—"
        gaps = ", ".join(
            f"{key}={count}" for key, count in item["missing_or_fallback_evidence"][:6]
        ) or "—"
        lines.append(f"| {labels[name]} | {item['count']} | {matrices} | {gaps} |")

    for name in (
        "model_top_big_odds_finished_last",
        "market_favourite_top3_but_model_low",
    ):
        lines.extend(["", f"## {labels[name]}", ""])
        records = report["cohorts"][name]
        if not records:
            lines.append("呢個版本沒有命中定義後個案。")
            continue
        lines.extend([
            "| Race | Horse | Model | SP | Result | Main matrix evidence |",
            "|---|---|---:|---:|---:|---|",
        ])
        for record in records:
            drivers = ", ".join(
                f"{item['signal']} {item['field_delta']:+.1f}"
                for item in record["matrix_drivers"][:3]
            ) or "—"
            lines.append(
                f"| {record['race_id']} | {record['horse_name']} | "
                f"{record['model_rank']} | {record['sp']} | {record['actual_pos']} | "
                f"{drivers} |"
            )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--big-odds", type=float, default=21.0)
    parser.add_argument("--model-top", type=int, default=3)
    parser.add_argument("--low-rank", type=int, default=5)
    parser.add_argument("--low-price", type=float, default=4.0)
    parser.add_argument(
        "--output-json", type=Path,
        default=Path("/private/tmp/au_failure_direction_audit.json"),
    )
    parser.add_argument(
        "--output-md", type=Path,
        default=Path("/private/tmp/au_failure_direction_audit.md"),
    )
    args = parser.parse_args()
    document = json.loads(args.dataset.read_text(encoding="utf-8"))
    report = analyze_races(
        document["races"],
        big_odds=args.big_odds,
        model_top=args.model_top,
        low_rank=args.low_rank,
        low_price=args.low_price,
    )
    report["summary"] = summarize(report)
    args.output_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.output_md.write_text(render_markdown(report), encoding="utf-8")
    print(
        f"Audited {report['races']} races; cold-last="
        f"{len(report['cohorts']['model_top_big_odds_finished_last'])}; "
        f"favourite-missed="
        f"{len(report['cohorts']['market_favourite_top3_but_model_low'])}"
    )
    print(args.output_json)
    print(args.output_md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
