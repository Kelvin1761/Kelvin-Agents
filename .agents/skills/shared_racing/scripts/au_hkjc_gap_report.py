#!/usr/bin/env python3
"""AU vs HKJC Wong Choi canonical gap report — one ruler, both engines.

Evaluates the stored production rankings (`python_auto.ability_score`) of every
archived race on both sides through `shared_racing/eval_metrics`, then reports
every Good definition side by side with bootstrap confidence intervals and
going / venue / field-size context.

Usage:
    python3 .agents/skills/shared_racing/scripts/au_hkjc_gap_report.py \
        [--bootstrap 2000] [--seed 20260717] [--out-md PATH] [--out-json PATH]
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SHARED_ROOT = SCRIPT_DIR.parent
PROJECT_ROOT = SHARED_ROOT.parents[2]
AU_SCRIPTS = PROJECT_ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts"
HKJC_REFLECTOR_SCRIPTS = PROJECT_ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_reflector" / "scripts"

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SHARED_ROOT))
sys.path.insert(0, str(AU_SCRIPTS))
sys.path.insert(0, str(AU_SCRIPTS / "racing_engine"))
sys.path.insert(0, str(HKJC_REFLECTOR_SCRIPTS))

from wongchoi_paths import HK_RACING  # noqa: E402
from eval_metrics import build_manifest, race_metrics, summarize_races  # noqa: E402
from au_archive_calibrator import normalize_condition_bucket  # noqa: E402
from au_cached_walkforward_ml import as_float, group_races, materialize_dataset  # noqa: E402
from walk_forward_auto_backtest import clip_score, find_results_json, load_results  # noqa: E402


def load_au_races() -> list[dict]:
    """One record per archived AU race, production ranking = stored ability_score."""
    races = []
    for race in group_races(materialize_dataset()):
        ranked = sorted(race, key=lambda row: (-as_float(row.get("ability_score"), 60.0), int(row["horse_number"])))
        picks = [int(row["horse_number"]) for row in ranked]
        actual_pos = {int(row["horse_number"]): int(row["actual_pos"]) for row in ranked}
        actual_top3 = [horse for horse, pos in actual_pos.items() if pos <= 3]
        first = race[0]
        races.append(
            {
                "domain": "AU",
                "race_id": (first["meeting"], int(first["race"])),
                "date": str(first["date"]),
                "meeting": first["meeting"],
                "venue": str(first.get("track") or "").strip() or "Unknown",
                "going": str(first.get("condition_bucket") or "Unknown"),
                "going_family": normalize_condition_bucket(str(first.get("condition_bucket") or "")),
                "field": len(race),
                "eval": race_metrics(picks, actual_top3, actual_pos=actual_pos),
            }
        )
    return races


def hkjc_meeting_dirs() -> list[Path]:
    dirs = []
    for path in sorted(HK_RACING.iterdir()):
        if not path.is_dir():
            continue
        if not re.match(r"^\d{4}-\d{2}-\d{2}_", path.name):
            continue
        if "(" in path.name:  # analyst working copies, no canonical Logic files
            continue
        if not list(path.glob("Race_*_Logic.json")) or find_results_json(path) is None:
            continue
        dirs.append(path)
    return dirs


def load_hkjc_races() -> list[dict]:
    """One record per archived HKJC race, production ranking = stored ability_score."""
    races = []
    for meeting_dir in hkjc_meeting_dirs():
        meeting_date = meeting_dir.name[:10]
        venue = meeting_dir.name[11:] or "Unknown"
        actual = load_results(find_results_json(meeting_dir))
        for logic_path in sorted(meeting_dir.glob("Race_*_Logic.json")):
            match = re.search(r"Race_(\d+)_Logic\.json$", logic_path.name)
            race_num = int(match.group(1)) if match else 0
            if race_num not in actual:
                continue
            logic = json.loads(logic_path.read_text(encoding="utf-8"))
            scored = []
            for horse_num_text, horse in logic.get("horses", {}).items():
                try:
                    horse_num = int(horse_num_text)
                except ValueError:
                    continue
                auto = horse.get("python_auto", {})
                if not auto.get("feature_scores"):
                    continue
                scored.append((horse_num, clip_score(auto.get("ability_score", 60.0))))
            if len(scored) < 4:
                continue
            actual_pos = actual[race_num]
            actual_top3 = [horse for horse, pos in actual_pos.items() if pos <= 3]
            if sum(1 for pos in actual_pos.values() if pos <= 3) < 3 or not actual_top3:
                continue
            picks = [horse for horse, _score in sorted(scored, key=lambda item: (-item[1], item[0]))]
            races.append(
                {
                    "domain": "HKJC",
                    "race_id": (meeting_dir.name, race_num),
                    "date": meeting_date,
                    "meeting": meeting_dir.name,
                    "venue": venue,
                    "going": "Unknown",  # not persisted in HKJC Logic files
                    "field": len(scored),
                    "eval": race_metrics(picks, actual_top3, actual_pos=actual_pos),
                }
            )
    return races


def field_band(field: int) -> str:
    if field <= 8:
        return "<=8"
    if field <= 11:
        return "9-11"
    return "12+"


def summarize(records: list[dict]) -> dict:
    return summarize_races([record["eval"] for record in records])


def bootstrap_rate(records: list[dict], key: str, iterations: int, rng: random.Random) -> tuple[float, float]:
    values = [1.0 if record["eval"][key] else 0.0 for record in records]
    n = len(values)
    if n == 0:
        return (0.0, 0.0)
    samples = sorted(sum(rng.choices(values, k=n)) / n for _ in range(iterations))
    return (samples[int(0.025 * iterations)], samples[int(0.975 * iterations)])


def bootstrap_diff(left: list[dict], right: list[dict], key: str, iterations: int, rng: random.Random) -> tuple[float, float]:
    lv = [1.0 if record["eval"][key] else 0.0 for record in left]
    rv = [1.0 if record["eval"][key] else 0.0 for record in right]
    if not lv or not rv:
        return (0.0, 0.0)
    samples = sorted(
        sum(rng.choices(lv, k=len(lv))) / len(lv) - sum(rng.choices(rv, k=len(rv))) / len(rv)
        for _ in range(iterations)
    )
    return (samples[int(0.025 * iterations)], samples[int(0.975 * iterations)])


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def kpi_row(name: str, summary: dict) -> str:
    rates = summary["rates"]
    return (
        f"| {name} | {summary['races']} | {summary['counts']['gold']} ({pct(rates['gold'])}) | "
        f"{summary['counts']['good_positional']} ({pct(rates['good_positional'])}) | "
        f"{summary['counts']['good_any2']} ({pct(rates['good_any2'])}) | "
        f"{summary['counts']['pass_any1']} ({pct(rates['pass_any1'])}) | "
        f"{pct(rates['champion'])} | {pct(rates['winner_in_top3'])} | "
        f"{summary['top3_precision'] * 100:.1f}% | {summary['mrr']:.3f} |"
    )


KPI_HEADER = (
    "| Sample | Races | Gold | Good (positional) | Good (any-2) | Pass (any hit) | Top1 win | W-in-Top3 | Top3 prec | MRR |\n"
    "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
)


def main() -> int:
    parser = argparse.ArgumentParser(description="AU vs HKJC canonical gap report")
    parser.add_argument("--bootstrap", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260717)
    parser.add_argument("--report-date", default=date.today().isoformat())
    parser.add_argument("--out-md", default=None)
    parser.add_argument("--out-json", default=None)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    au = load_au_races()
    hk = load_hkjc_races()
    if not au or not hk:
        print(f"ERROR: empty sample (AU={len(au)}, HKJC={len(hk)})", file=sys.stderr)
        return 1

    au_dates = sorted(record["date"] for record in au)
    hk_dates = sorted(record["date"] for record in hk)
    common_start = max(au_dates[0], hk_dates[0])
    common_end = min(au_dates[-1], hk_dates[-1])
    au_common = [record for record in au if common_start <= record["date"] <= common_end]
    hk_common = [record for record in hk if common_start <= record["date"] <= common_end]

    manifests = {
        "AU": build_manifest(
            [record["race_id"] for record in au],
            dates=[record["date"] for record in au],
            meetings=[record["meeting"] for record in au],
            going_mix=Counter(record["going"] for record in au),
            repo_root=PROJECT_ROOT,
            extra={"ranking": "stored python_auto.ability_score (cached matrix reconstruction)"},
        ),
        "HKJC": build_manifest(
            [record["race_id"] for record in hk],
            dates=[record["date"] for record in hk],
            meetings=[record["meeting"] for record in hk],
            going_mix=Counter(record["venue"] for record in hk),
            repo_root=PROJECT_ROOT,
            extra={"ranking": "stored python_auto.ability_score (live engine outputs)"},
        ),
    }

    slices: dict[str, dict] = {}
    for name, records in (("AU (full archive)", au), ("HKJC (full archive)", hk),
                          (f"AU (common window {common_start}..{common_end})", au_common),
                          (f"HKJC (common window {common_start}..{common_end})", hk_common)):
        slices[name] = summarize(records)

    au_by_going = {going: summarize(records) for going, records in sorted(
        _group(au, lambda r: r["going_family"]).items())}
    au_by_going_detail = {going: summarize(records) for going, records in sorted(
        _group(au, lambda r: r["going"]).items())}
    hk_by_venue = {venue: summarize(records) for venue, records in sorted(
        _group(hk, lambda r: r["venue"]).items())}
    au_by_field = {band: summarize(records) for band, records in sorted(
        _group(au, lambda r: field_band(r["field"])).items())}
    hk_by_field = {band: summarize(records) for band, records in sorted(
        _group(hk, lambda r: field_band(r["field"])).items())}

    cis = {}
    for key in ("good_positional", "good_any2", "winner_in_top3", "champion"):
        cis[key] = {
            "au": bootstrap_rate(au, key, args.bootstrap, rng),
            "hk": bootstrap_rate(hk, key, args.bootstrap, rng),
            "diff_hk_minus_au": bootstrap_diff(hk, au, key, args.bootstrap, rng),
            "diff_common_window": bootstrap_diff(hk_common, au_common, key, args.bootstrap, rng),
        }

    # AU Good/Firm going vs HKJC (HKJC turf is predominantly good-ish going)
    au_goodfirm = _group(au, lambda r: r["going_family"]).get("Good/Firm", [])
    goodfirm_summary = summarize(au_goodfirm) if au_goodfirm else None
    cis["good_positional_goodfirm_vs_hk"] = bootstrap_diff(hk, au_goodfirm, "good_positional", args.bootstrap, rng) if au_goodfirm else None

    lines = [
        f"# AU vs HKJC Wong Choi — Canonical Gap Report ({args.report_date})",
        "",
        "> Both engines evaluated with `shared_racing/eval_metrics` on stored production",
        "> rankings (`python_auto.ability_score`). Every Good definition reported explicitly.",
        "",
        "## Samples",
        "",
    ]
    for side, manifest in manifests.items():
        lines.append(f"- **{side}**: {manifest['race_count']} races / {manifest['meeting_count']} meetings, "
                     f"{manifest['date_range'][0]} → {manifest['date_range'][1]}, engine commit `{manifest['engine_commit']}`, "
                     f"sample hash `{manifest['sample_hash']}`.")
    lines += [
        "",
        "## Headline (one ruler)",
        "",
        KPI_HEADER,
    ]
    for name, summary in slices.items():
        lines.append(kpi_row(name, summary))
    lines += [
        "",
        "## Bootstrap 95% confidence intervals",
        "",
        "| KPI | AU rate [CI] | HKJC rate [CI] | Gap HKJC−AU [CI] | Gap in common window [CI] |",
        "|---|---|---|---|---|",
    ]
    for key, ci in cis.items():
        if key == "good_positional_goodfirm_vs_hk" or ci is None:
            continue
        au_rate = slices["AU (full archive)"]["rates"][key]
        hk_rate = slices["HKJC (full archive)"]["rates"][key]
        lines.append(
            f"| {key} | {pct(au_rate)} [{pct(ci['au'][0])}, {pct(ci['au'][1])}] "
            f"| {pct(hk_rate)} [{pct(ci['hk'][0])}, {pct(ci['hk'][1])}] "
            f"| [{pct(ci['diff_hk_minus_au'][0])}, {pct(ci['diff_hk_minus_au'][1])}] "
            f"| [{pct(ci['diff_common_window'][0])}, {pct(ci['diff_common_window'][1])}] |"
        )
    lines += ["", "## AU by going family", "", KPI_HEADER]
    for going, summary in au_by_going.items():
        lines.append(kpi_row(f"AU {going}", summary))
    lines += ["", "## AU by detailed going", "", KPI_HEADER]
    for going, summary in au_by_going_detail.items():
        lines.append(kpi_row(f"AU {going}", summary))
    if goodfirm_summary and cis.get("good_positional_goodfirm_vs_hk"):
        ci = cis["good_positional_goodfirm_vs_hk"]
        lines += [
            "",
            f"Going-adjusted check: HKJC vs **AU Good/Firm only** positional-Good gap 95% CI "
            f"[{pct(ci[0])}, {pct(ci[1])}] (HKJC going is not persisted in Logic files but HKJC turf "
            f"racing is predominantly Good-ish going; treat as an approximation).",
        ]
    lines += ["", "## HKJC by venue", "", KPI_HEADER]
    for venue, summary in hk_by_venue.items():
        lines.append(kpi_row(f"HKJC {venue}", summary))
    lines += ["", "## By field size", "", KPI_HEADER]
    for band, summary in au_by_field.items():
        lines.append(kpi_row(f"AU field {band}", summary))
    for band, summary in hk_by_field.items():
        lines.append(kpi_row(f"HKJC field {band}", summary))
    lines += [
        "",
        "## Reading guide",
        "",
        "- **Good (positional)** = model picks 1 and 2 both in the actual top 3 — the definition behind",
        "  both the AU \"17.9%\" figure and the HKJC calibration doc's 24/91=26.4%.",
        "- **Good (any-2)** = any 2 of the model top 3 in the actual top 3 (cumulative, includes Gold) —",
        "  the AU cached walk-forward's historical `good`.",
        "- Exclusive reflector labels (Gold/Good/Pass/1 Hit/Miss) remain available per race in the JSON output.",
        "",
    ]
    report = "\n".join(lines)

    out_md = Path(args.out_md) if args.out_md else PROJECT_ROOT / f"{args.report_date} AU vs HKJC Canonical Gap Report.md"
    out_json = Path(args.out_json) if args.out_json else PROJECT_ROOT / "scratch" / "au_hkjc_gap_report.json"
    out_md.write_text(report, encoding="utf-8")
    out_json.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "report_date": args.report_date,
        "manifests": manifests,
        "slices": {name: summary for name, summary in slices.items()},
        "au_by_going": au_by_going,
        "au_by_going_detail": au_by_going_detail,
        "hk_by_venue": hk_by_venue,
        "au_by_field": au_by_field,
        "hk_by_field": hk_by_field,
        "bootstrap_cis": {k: v for k, v in cis.items()},
        "races": [
            {**{k: record[k] for k in ("domain", "date", "meeting", "venue", "going", "field")},
             "race_id": list(record["race_id"]),
             "eval": {k: v for k, v in record["eval"].items() if k != "picks"}}
            for record in au + hk
        ],
    }
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"Wrote {out_md}")
    print(f"Wrote {out_json}")
    print()
    print(report.split("## AU by going")[0])
    return 0


def _group(records: list[dict], key) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        groups[key(record)].append(record)
    return dict(groups)


if __name__ == "__main__":
    raise SystemExit(main())
