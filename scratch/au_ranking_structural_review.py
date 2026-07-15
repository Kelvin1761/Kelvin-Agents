#!/usr/bin/env python3
"""Market-free AU ranking audit focused on Top-2 place and Top-4 trifecta quality.

This is a shadow-only research harness.  It never writes to Logic.json or the
production engine.  Google Drive placeholders are skipped after a short read
timeout and listed in the report so the evaluated sample is explicit.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import re
import signal
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.extend([str(ROOT), str(SCRIPT_DIR), str(SCRIPT_DIR / "racing_engine")])

from au_archive_calibrator import (  # noqa: E402
    ARCHIVE_ROOT,
    HISTORICAL_RESULTS_CSV,
    choose_track_rows,
    detect_meeting_date,
    load_historical_results,
    normalize_horse_name,
    parse_float,
    parse_int,
)
from matrix_mapper import map_features_to_matrix_scores  # noqa: E402
from scoring import FEATURE_KEYS, MATRIX_WEIGHTS  # noqa: E402

REPORT = ARCHIVE_ROOT / "AU_Ranking_Structural_Review_2026-07-13.md"
CACHE = Path("/private/tmp/au_ranking_structural_review_cache.json")
MATRIX_KEYS = tuple(MATRIX_WEIGHTS)


class ReadTimeout(Exception):
    pass


def _timeout(_signum, _frame):
    raise ReadTimeout()


def read_text_bounded(path: Path, seconds: float) -> str:
    old = signal.signal(signal.SIGALRM, _timeout)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        return path.read_text(encoding="utf-8-sig")
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


def meeting_track(path: Path) -> str:
    name = re.sub(r"^\d{4}-\d{2}-\d{2}[ _]", "", path.name)
    return re.sub(r"\s+Race\s+\d+(?:-\d+)?$", "", name, flags=re.I).strip()


def condition_bucket(value: str) -> str:
    text = str(value or "").lower()
    if "heavy" in text:
        return "Heavy"
    if "soft" in text:
        return "Soft"
    if "synthetic" in text or "poly" in text:
        return "Synthetic"
    return "Good/Firm"


def distance_bucket(value) -> str:
    distance = parse_int(value, 0) or 0
    if distance < 1200:
        return "Sprint <1200m"
    if distance <= 1400:
        return "Sprint/Mile 1200-1400m"
    if distance <= 1800:
        return "Middle 1401-1800m"
    return "Staying 1801m+"


def field_bucket(size: int) -> str:
    if size <= 8:
        return "Field <=8"
    if size <= 12:
        return "Field 9-12"
    return "Field 13+"


def parse_scoring(text: str) -> list[dict]:
    rows = []
    for row in csv.DictReader(text.splitlines()):
        number = parse_int(row.get("horse_number"))
        if number is None:
            continue
        features = {key: parse_float(row.get(key), 60.0) or 60.0 for key in FEATURE_KEYS}
        matrices = map_features_to_matrix_scores(features)
        rows.append(
            {
                "horse_number": number,
                "horse_name": str(row.get("horse_name") or "").strip(),
                "horse_slug": normalize_horse_name(row.get("horse_name") or ""),
                "ability": parse_float(row.get("ability_score"), 0.0) or 0.0,
                "features": features,
                "matrices": {key: float(matrices.get(key, 60.0)) for key in MATRIX_KEYS},
            }
        )
    return rows


def build_dataset(timeout_seconds: float) -> tuple[list[dict], list[str]]:
    labels = load_historical_results(HISTORICAL_RESULTS_CSV)
    races, skipped = [], []
    meetings = sorted(path for path in ARCHIVE_ROOT.iterdir() if path.is_dir())
    for index, meeting in enumerate(meetings, 1):
        date = detect_meeting_date(meeting)
        track = meeting_track(meeting)
        if not date or not track:
            continue
        if index == 1 or index % 10 == 0:
            print(f"scan {index}/{len(meetings)} {meeting.name}", flush=True)
        for path in sorted(meeting.glob("Race_*_Auto_Scoring.csv")):
            race_no = parse_int(path.stem)
            if not race_no:
                continue
            try:
                scoring = parse_scoring(read_text_bounded(path, timeout_seconds))
            except (ReadTimeout, OSError, UnicodeError) as exc:
                skipped.append(f"{path.relative_to(ARCHIVE_ROOT)} [{type(exc).__name__}]")
                continue
            result_rows = choose_track_rows(labels.get((date, race_no), []), track)
            lookup = {row["horse_slug"]: row for row in result_rows}
            joined = []
            for horse in scoring:
                actual = lookup.get(horse["horse_slug"])
                if not actual:
                    continue
                joined.append({**horse, "actual_pos": int(actual["pos"])})
            if len(joined) < 4 or sum(1 for horse in joined if horse["actual_pos"] <= 3) < 3:
                continue
            first = result_rows[0]
            races.append(
                {
                    "date": date,
                    "meeting": meeting.name,
                    "track": str(first.get("track") or track),
                    "race": race_no,
                    "condition": condition_bucket(first.get("condition") or ""),
                    "distance": distance_bucket(first.get("distance") or 0),
                    "field": field_bucket(len(joined)),
                    "horses": joined,
                }
            )
    races.sort(key=lambda race: (race["date"], race["meeting"], race["race"]))
    return races, skipped


def save_cache(races: list[dict], skipped: list[str]) -> None:
    CACHE.write_text(json.dumps({"races": races, "skipped": skipped}, ensure_ascii=False), encoding="utf-8")


def load_or_build(rebuild: bool, timeout_seconds: float) -> tuple[list[dict], list[str]]:
    if CACHE.exists() and not rebuild:
        payload = json.loads(CACHE.read_text(encoding="utf-8"))
        races, skipped = payload["races"], payload["skipped"]
        enrich_result_meta(races)
        return races, skipped
    races, skipped = build_dataset(timeout_seconds)
    enrich_result_meta(races)
    save_cache(races, skipped)
    return races, skipped


def enrich_result_meta(races: list[dict]) -> None:
    """Restore distance/condition from the raw result CSV (the shared loader omits distance)."""
    lookup = {}
    with HISTORICAL_RESULTS_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            race_no = parse_int(row.get("Race"))
            if not race_no:
                continue
            key = (str(row.get("Date") or "").strip(), normalize_horse_name(row.get("Track") or ""), race_no)
            lookup.setdefault(key, row)
    for race in races:
        key = (race["date"], normalize_horse_name(race["track"]), int(race["race"]))
        row = lookup.get(key)
        if not row:
            continue
        race["condition"] = condition_bucket(row.get("Condition") or "")
        race["distance"] = distance_bucket(row.get("Distance") or 0)


def fixed_scores(horse: dict) -> dict[str, float]:
    base = float(horse["ability"])
    mx = horse["matrices"]
    ft = horse["features"]
    return {
        "baseline": base,
        # Independent structural tests; every score remains a single pre-rank rating.
        "pace_perf_plus3": base + 0.03 * (mx["pace_perf"] - mx["stability"]),
        "race_shape_plus3": base + 0.03 * (mx["race_shape"] - mx["stability"]),
        "class_weight_to8": base + 0.03465 * (mx["class_weight"] - mx["stability"]),
        "form_line_new5": base + 0.05 * (mx["form_line"] - mx["stability"]),
        "distance_new5": base + 0.05 * (ft["distance_score"] - mx["stability"]),
        "fitness_new5": base + 0.05 * (ft["health_score"] - mx["stability"]),
        "confidence_new5": base + 0.05 * (ft["confidence_score"] - mx["stability"]),
        "balanced_professional": base
        + 0.025 * (mx["class_weight"] - mx["stability"])
        + 0.025 * (ft["distance_score"] - mx["stability"])
        + 0.02 * (mx["pace_perf"] - mx["stability"]),
    }


def rank_race(race: dict, variant: str) -> list[dict]:
    return sorted(race["horses"], key=lambda horse: (-horse["scores"][variant], horse["horse_number"]))


def race_values(ranked: list[dict]) -> dict[str, float]:
    actual_top3 = {horse["horse_number"] for horse in ranked if horse["actual_pos"] <= 3}
    winner_rank = next((idx for idx, horse in enumerate(ranked, 1) if horse["actual_pos"] == 1), len(ranked))
    top2_hits = sum(1 for horse in ranked[:2] if horse["actual_pos"] <= 3)
    top3_hits = sum(1 for horse in ranked[:3] if horse["actual_pos"] <= 3)
    top4_hits = sum(1 for horse in ranked[:4] if horse["horse_number"] in actual_top3)
    top5_hits = sum(1 for horse in ranked[:5] if horse["horse_number"] in actual_top3)
    return {
        "top1_win": float(ranked[0]["actual_pos"] == 1),
        "top1_place": float(ranked[0]["actual_pos"] <= 3),
        "top2_place_strike": top2_hits / 2.0,
        "top2_both_place": float(top2_hits == 2),
        "top3_slot": top3_hits / 3.0,
        "top3_exact": float(top3_hits == 3),
        "top4_trifecta": float(top4_hits == 3),
        "top4_coverage": top4_hits / 3.0,
        "top5_trifecta": float(top5_hits == 3),
        "top5_coverage": top5_hits / 3.0,
        "winner_mrr": 1.0 / winner_rank,
    }


def evaluate(races: list[dict], variant: str) -> tuple[dict, list[dict]]:
    values = [race_values(rank_race(race, variant)) for race in races]
    keys = values[0].keys() if values else ()
    return ({key: mean(row[key] for row in values) for key in keys} | {"races": len(values)}), values


def bootstrap_delta(base: list[dict], candidate: list[dict], key: str, seed: int = 20260713) -> tuple[float, float]:
    rng = random.Random(seed)
    deltas = [candidate[i][key] - base[i][key] for i in range(len(base))]
    if not deltas:
        return 0.0, 0.0
    sims = []
    for _ in range(2500):
        sims.append(mean(deltas[rng.randrange(len(deltas))] for _ in deltas))
    sims.sort()
    return sims[int(0.025 * len(sims))], sims[int(0.975 * len(sims))]


def exact_mcnemar(base: list[dict], candidate: list[dict], key: str) -> float:
    gain = sum(1 for b, c in zip(base, candidate) if not b[key] and c[key])
    loss = sum(1 for b, c in zip(base, candidate) if b[key] and not c[key])
    n = gain + loss
    if not n:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(0, min(gain, loss) + 1)) / (2**n)
    return min(1.0, 2.0 * tail)


def fold_directions(races: list[dict], variant: str, key: str) -> str:
    chunks = [races[i::5] for i in range(5)]
    signs = []
    for chunk in chunks:
        base, _ = evaluate(chunk, "baseline")
        cand, _ = evaluate(chunk, variant)
        delta = cand[key] - base[key]
        signs.append("+" if delta > 1e-12 else "-" if delta < -1e-12 else "=")
    return "".join(signs)


def group_deltas(races: list[dict], variant: str, field: str, key: str) -> list[tuple[str, int, float]]:
    grouped = defaultdict(list)
    for race in races:
        grouped[race[field]].append(race)
    output = []
    for label, rows in grouped.items():
        if len(rows) < 12:
            continue
        base, _ = evaluate(rows, "baseline")
        cand, _ = evaluate(rows, variant)
        output.append((label, len(rows), (cand[key] - base[key]) * 100))
    return sorted(output, key=lambda item: item[2], reverse=True)


def prepare_scores(races: list[dict]) -> None:
    for race in races:
        for horse in race["horses"]:
            horse["scores"] = fixed_scores(horse)


def pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def pp(value: float) -> str:
    return f"{value * 100:+.2f}pp"


def render(races: list[dict], skipped: list[str]) -> str:
    variants = list(races[0]["horses"][0]["scores"]) if races else []
    baseline, base_values = evaluate(races, "baseline")
    lines = [
        "# AU Wong Choi Ranking Structural Review",
        "",
        "## Scope and controls",
        "",
        f"- Evaluated races: **{len(races)}**; runners: **{sum(len(r['horses']) for r in races)}**.",
        f"- Google Drive files skipped after timeout: **{len(skipped)}**.",
        "- No odds, SP, favourite rank, market movement or market ranking is read by any candidate score.",
        "- All candidates produce one structural pre-ranking score; there are no post-7D horse swaps or manual rank rules.",
        "",
        "## Historical baseline",
        "",
        "| KPI | Baseline |",
        "|---|---:|",
    ]
    for key, label in (
        ("top1_win", "Top-1 winner accuracy"),
        ("top1_place", "Top-1 place strike"),
        ("top2_place_strike", "Top-2 place strike per selection"),
        ("top2_both_place", "Both Top-2 placed"),
        ("top3_slot", "Top-3 slot precision"),
        ("top3_exact", "Top-3 contains all trifecta horses"),
        ("top4_trifecta", "Top-4 trifecta coverage"),
        ("top5_trifecta", "Top-5 trifecta coverage"),
        ("winner_mrr", "Winner mean reciprocal rank"),
    ):
        lines.append(f"| {label} | {pct(baseline[key])} |")

    lines.extend([
        "",
        "## Independent structural tests",
        "",
        "| Candidate | Top1 win | Top2 place | Both Top2 | Top4 trifecta | Top5 trifecta | Top2 95% CI delta | Top4 p | Fold signs T2/T4 |",
        "|---|---:|---:|---:|---:|---:|---|---:|---|",
    ])
    evaluations = {}
    for variant in variants:
        metrics, values = evaluate(races, variant)
        evaluations[variant] = (metrics, values)
        if variant == "baseline":
            continue
        ci = bootstrap_delta(base_values, values, "top2_place_strike")
        p_value = exact_mcnemar(base_values, values, "top4_trifecta")
        signs = f"{fold_directions(races, variant, 'top2_place_strike')}/{fold_directions(races, variant, 'top4_trifecta')}"
        lines.append(
            f"| `{variant}` | {pct(metrics['top1_win'])} ({pp(metrics['top1_win']-baseline['top1_win'])}) "
            f"| {pct(metrics['top2_place_strike'])} ({pp(metrics['top2_place_strike']-baseline['top2_place_strike'])}) "
            f"| {pct(metrics['top2_both_place'])} ({pp(metrics['top2_both_place']-baseline['top2_both_place'])}) "
            f"| {pct(metrics['top4_trifecta'])} ({pp(metrics['top4_trifecta']-baseline['top4_trifecta'])}) "
            f"| {pct(metrics['top5_trifecta'])} ({pp(metrics['top5_trifecta']-baseline['top5_trifecta'])}) "
            f"| [{pp(ci[0])}, {pp(ci[1])}] | {p_value:.3f} | {signs} |"
        )

    ranked_candidates = sorted(
        (variant for variant in variants if variant != "baseline"),
        key=lambda name: (
            evaluations[name][0]["top2_place_strike"] - baseline["top2_place_strike"],
            evaluations[name][0]["top4_trifecta"] - baseline["top4_trifecta"],
        ),
        reverse=True,
    )
    lines.extend(["", "## Segment stability of the two best candidates", ""])
    for variant in ranked_candidates[:2]:
        lines.extend([f"### `{variant}`", "", "| Segment | Bucket | Races | Top2 delta | Top4 delta |", "|---|---|---:|---:|---:|"])
        for field in ("condition", "distance", "field", "track"):
            top2 = {name: (n, delta) for name, n, delta in group_deltas(races, variant, field, "top2_place_strike")}
            top4 = {name: (n, delta) for name, n, delta in group_deltas(races, variant, field, "top4_trifecta")}
            for name in sorted(set(top2) & set(top4)):
                n = top2[name][0]
                lines.append(f"| {field} | {name} | {n} | {top2[name][1]:+.2f}pp | {top4[name][1]:+.2f}pp |")
        lines.append("")

    # Combination gate: combine only independently positive candidates; otherwise
    # explicitly keep baseline as the final combination result.
    positive = []
    for variant in ranked_candidates:
        metrics, values = evaluations[variant]
        ci = bootstrap_delta(base_values, values, "top2_place_strike")
        if metrics["top2_place_strike"] > baseline["top2_place_strike"] and metrics["top4_trifecta"] >= baseline["top4_trifecta"] and ci[0] >= 0:
            positive.append(variant)
    lines.extend(["## Final combination gate", ""])
    if len(positive) >= 2:
        a, b = positive[:2]
        combo = "final_combined"
        for race in races:
            for horse in race["horses"]:
                base = horse["scores"]["baseline"]
                horse["scores"][combo] = base + (horse["scores"][a] - base) + (horse["scores"][b] - base)
        metrics, values = evaluate(races, combo)
        ci = bootstrap_delta(base_values, values, "top2_place_strike")
        lines.extend([
            f"- Combined `{a}` + `{b}`.",
            f"- Top1 win: {pct(metrics['top1_win'])} ({pp(metrics['top1_win']-baseline['top1_win'])}).",
            f"- Top2 place: {pct(metrics['top2_place_strike'])} ({pp(metrics['top2_place_strike']-baseline['top2_place_strike'])}); 95% CI [{pp(ci[0])}, {pp(ci[1])}].",
            f"- Top4 trifecta: {pct(metrics['top4_trifecta'])} ({pp(metrics['top4_trifecta']-baseline['top4_trifecta'])}).",
        ])
    else:
        lines.append("- No two independent candidates passed the Top-2 + Top-4 + confidence-interval gate; final combined recommendation is **no production score change**.")

    lines.extend(["", "## Skipped file manifest", ""])
    if skipped:
        lines.extend(f"- `{item}`" for item in skipped[:80])
        if len(skipped) > 80:
            lines.append(f"- ... and {len(skipped)-80} more in cache manifest.")
    else:
        lines.append("- None.")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild-cache", action="store_true")
    parser.add_argument("--timeout", type=float, default=0.35)
    parser.add_argument("--output", type=Path, default=REPORT)
    args = parser.parse_args()
    races, skipped = load_or_build(args.rebuild_cache, args.timeout)
    if not races:
        raise SystemExit("No labelled races available")
    prepare_scores(races)
    args.output.write_text(render(races, skipped), encoding="utf-8")
    print(f"races={len(races)} runners={sum(len(r['horses']) for r in races)} skipped={len(skipped)}")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
