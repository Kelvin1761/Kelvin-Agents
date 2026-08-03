#!/usr/bin/env python3
"""Research gate for structured local-HKJC running-position evidence.

The official horse profile exposes each historical race's in-running positions.
This script fetches those local-only profiles, applies a strict point-in-time
cutoff for every archived card, and tests race-relative position-conversion
signals by rebuilding a matrix dimension.  It never uses odds or post-race
information from the race being predicted.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
HQ_GATE = ROOT / "scratch" / "hkjc_high_quality_dimension_gate.py"
ARCHIVE = ROOT / "scratch" / "hkjc_ranking_dataset_current.csv"
EXTERNAL = ROOT / "scratch" / "hkjc_ranking_dataset_2026_07_15_current.csv"
CACHE = ROOT / "scratch" / "hkjc_local_position_profile_cache.json"
JSON_OUT = ROOT / "scratch" / "hkjc_local_position_conversion_gate.json"
REPORT_OUT = ROOT / "scratch" / "hkjc_local_position_conversion_gate_report.md"
PROFILE_URL = "https://racing.hkjc.com/zh-hk/local/information/horse?HorseNo={}"


_spec = importlib.util.spec_from_file_location("hkjc_hq_gate", HQ_GATE)
hq = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(hq)

_thread_local = threading.local()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--fetch-only", action="store_true")
    parser.add_argument(
        "--refresh-rich",
        action="store_true",
        help="Refetch cached profiles that predate declared-weight fields.",
    )
    parser.add_argument("--limit", type=int, default=0)
    return parser.parse_args()


def _session() -> requests.Session:
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = requests.Session()
        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 Chrome/126.0 Safari/537.36"
            ),
            "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.7",
        })
        _thread_local.session = session
    return session


def _positions(value: str) -> list[int]:
    output = []
    for token in str(value or "").split():
        match = re.match(r"(\d+)", token)
        if match:
            output.append(int(match.group(1)))
    return output


def _profile_rows(html: str) -> list[dict]:
    """Keep only stable, non-market fields from the official profile table."""
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 19 or cells[0].get("colspan"):
            continue
        if not {"htable_text", "htable_eng_text"}.intersection(cells[0].get("class", [])):
            continue
        link = cells[0].find("a")
        href = link.get("href", "") if link else ""
        date_match = re.search(r"racedate=(\d{4}/\d{2}/\d{2})", href)
        placing_text = cells[1].get_text(strip=True)
        if not date_match or not placing_text.isdigit():
            continue
        rows.append({
            "date": date_match.group(1).replace("/", "-"),
            "placing": int(placing_text),
            "distance": int(cells[4].get_text(strip=True))
            if cells[4].get_text(strip=True).isdigit() else None,
            "class": cells[6].get_text(strip=True),
            "venue_track": cells[3].get_text(strip=True),
            "rating": int(cells[8].get_text(strip=True))
            if cells[8].get_text(strip=True).isdigit() else None,
            "positions": _positions(cells[14].get_text(" ", strip=True)),
            "declared_weight": int(cells[16].get_text(strip=True))
            if cells[16].get_text(strip=True).isdigit() else None,
            "gear": cells[17].get_text(strip=True),
        })
    return rows


def _fetch_one(horse_id: str) -> tuple[str, dict]:
    try:
        response = _session().get(PROFILE_URL.format(horse_id), timeout=20)
        response.raise_for_status()
        rows = _profile_rows(response.text)
        return horse_id, {"status": "ok", "entries": rows}
    except Exception as exc:  # research cache records the failure explicitly
        return horse_id, {"status": "error", "error": str(exc), "entries": []}


def _load_cache() -> dict:
    if not CACHE.exists():
        return {"source": "HKJC local horse profile", "profiles": {}}
    return json.loads(CACHE.read_text(encoding="utf-8"))


def _save_cache(cache: dict) -> None:
    cache["updated_at"] = datetime.now(timezone.utc).isoformat()
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_profiles(
    horse_ids: list[str], workers: int, refresh_rich: bool = False
) -> dict:
    cache = _load_cache()
    profiles = cache.setdefault("profiles", {})
    missing = [
        horse_id for horse_id in horse_ids
        if horse_id not in profiles
        or profiles.get(horse_id, {}).get("status") != "ok"
        or (
            refresh_rich
            and profiles.get(horse_id, {}).get("entries")
            and "declared_weight" not in profiles[horse_id]["entries"][0]
        )
    ]
    print(f"profiles cached={len(horse_ids) - len(missing)} missing={len(missing)}")
    if not missing:
        return cache
    completed = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(_fetch_one, horse_id): horse_id for horse_id in missing}
        for future in as_completed(futures):
            horse_id, payload = future.result()
            profiles[horse_id] = payload
            completed += 1
            if completed % 50 == 0 or completed == len(missing):
                print(f"fetched {completed}/{len(missing)}", flush=True)
                _save_cache(cache)
    return cache


def _clip(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _weighted_mean(values: list[float], decay: float = 0.78) -> float | None:
    if not values:
        return None
    weights = [decay ** index for index in range(len(values))]
    return sum(value * weight for value, weight in zip(values, weights)) / sum(weights)


def position_features(profile: dict, as_of: str) -> dict[str, float | int | None]:
    entries = [
        entry for entry in profile.get("entries", [])
        if str(entry.get("date") or "") < as_of
        and isinstance(entry.get("positions"), list)
        and len(entry["positions"]) >= 2
        and int(entry.get("placing") or 0) > 0
    ]
    entries.sort(key=lambda entry: str(entry.get("date") or ""), reverse=True)
    entries = entries[:6]
    gain_scores = []
    conversion_scores = []
    hidden_close_scores = []
    sustainable_scores = []
    for entry in entries:
        positions = [int(value) for value in entry["positions"] if int(value) > 0]
        if len(positions) < 2:
            continue
        finish = int(entry["placing"])
        early = positions[0]
        bend = positions[-2]
        total_gain = early - finish
        late_gain = bend - finish
        finish_quality = _clip((8.0 - finish) / 7.0)
        total_gain_quality = _clip(0.5 + total_gain / 10.0)
        late_gain_quality = _clip(0.5 + late_gain / 8.0)
        gain_scores.append(100.0 * (0.60 * total_gain_quality + 0.40 * late_gain_quality))
        conversion_scores.append(100.0 * (
            0.45 * finish_quality
            + 0.35 * total_gain_quality
            + 0.20 * late_gain_quality
        ))
        hidden_close_scores.append(100.0 if (
            finish > 5 and (total_gain >= 3 or late_gain >= 2)
        ) else 50.0)
        front_sustain = early <= 3 and finish <= 4
        closer_convert = early >= 6 and finish <= 5 and total_gain >= 2
        sustainable_scores.append(100.0 if (front_sustain or closer_convert) else 50.0)
    samples = len(conversion_scores)
    return {
        "position_samples": samples,
        "position_gain_raw": _weighted_mean(gain_scores),
        "position_conversion_raw": _weighted_mean(conversion_scores),
        "position_hidden_close_raw": _weighted_mean(hidden_close_scores),
        "position_sustainable_raw": _weighted_mean(sustainable_scores),
    }


def prepare(cache: dict) -> pd.DataFrame:
    data = hq.prepare()
    archive = pd.read_csv(ARCHIVE)
    archive["dataset"] = "archive"
    external = pd.read_csv(EXTERNAL)
    external["dataset"] = "external"
    # The independent 2026-07-15 dataset was built from Logic snapshots whose
    # temporary meeting folder did not contain racecard markdown, so horse_id
    # is blank there.  Resolve repeat runners by the frozen archive's exact
    # Chinese name; genuinely new runners stay missing and therefore neutral.
    archive_name_to_id = (
        archive.dropna(subset=["horse_id"])
        .drop_duplicates("horse_name")
        .set_index("horse_name")["horse_id"]
        .to_dict()
    )
    external["horse_id"] = external["horse_id"].where(
        external["horse_id"].notna(),
        external["horse_name"].map(archive_name_to_id),
    )
    raw = pd.concat([archive, external], ignore_index=True)
    keys = ["dataset", "meeting_name", "race_number", "horse_number"]
    data = data.merge(
        raw[keys + ["horse_id"]], on=keys, how="left", validate="one_to_one"
    )
    profiles = cache.get("profiles", {})
    features = []
    for row in data.itertuples():
        horse_id = str(row.horse_id or "").strip()
        profile = profiles.get(horse_id, {})
        features.append(position_features(profile, str(row.date)))
    feature_frame = pd.DataFrame(features, index=data.index)
    return pd.concat([data, feature_frame], axis=1)


def _attach_relative_signals(data: pd.DataFrame) -> pd.DataFrame:
    output = data.copy()
    signal_map = {
        "gain": "position_gain_raw",
        "conversion": "position_conversion_raw",
        "hidden_close": "position_hidden_close_raw",
        "sustainable": "position_sustainable_raw",
    }
    for signal in signal_map:
        output[f"_signal_{signal}"] = math.nan
    for _, rows in output.groupby(["meeting_name", "race_number"], sort=False):
        samples = pd.to_numeric(rows["position_samples"], errors="coerce").fillna(0.0)
        reliability = samples / (samples + 2.0)
        for signal, column in signal_map.items():
            values = pd.to_numeric(rows[column], errors="coerce")
            relative = values.rank(pct=True, method="average")
            evidence = 45.0 + 30.0 * relative
            shrunk = 60.0 + reliability * (evidence - 60.0)
            output.loc[rows.index, f"_signal_{signal}"] = shrunk.where(values.notna())
    return output


def specs() -> dict[str, tuple[str, str, float, bool, str | None, int, bool]]:
    output = {}
    for alpha in (0.025, 0.05, 0.075, 0.10):
        suffix = f"{alpha:.3f}".rstrip("0").rstrip(".")
        output[f"gain_to_race_shape_{suffix}"] = (
            "race_shape", "gain", alpha, False, None, 1, False
        )
        output[f"conversion_to_race_shape_{suffix}"] = (
            "race_shape", "conversion", alpha, False, None, 1, False
        )
        output[f"conversion_to_formline_{suffix}"] = (
            "form_line", "conversion", alpha, False, None, 1, False
        )
        output[f"sustainable_to_race_shape_{suffix}"] = (
            "race_shape", "sustainable", alpha, False, None, 1, False
        )
        output[f"hidden_close_to_race_shape_{suffix}"] = (
            "race_shape", "hidden_close", alpha, True, None, 1, False
        )
    # A closing-position pattern is only promoted when the existing form-line
    # dimension independently confirms that the horse is at least competitive
    # with the field.  This is a dimension-level evidence rule, not a Rank 2/3
    # boundary swap.  Uplift-only also prevents a merely positive profile score
    # from lowering an already stronger race-shape assessment.
    for alpha in (0.015, 0.025, 0.04, 0.05, 0.075):
        suffix = f"{alpha:.3f}".rstrip("0").rstrip(".")
        output[f"hidden_close_formline_confirmed_uplift_{suffix}"] = (
            "race_shape", "hidden_close", alpha, True, "formline_median", 3, True
        )
        output[f"gain_formline_confirmed_uplift_{suffix}"] = (
            "race_shape", "gain", alpha, True, "formline_median", 3, True
        )
        output[f"conversion_formline_confirmed_uplift_{suffix}"] = (
            "race_shape", "conversion", alpha, True, "formline_median", 3, True
        )
        output[f"sustainable_formline_confirmed_uplift_{suffix}"] = (
            "race_shape", "sustainable", alpha, True, "formline_median", 3, True
        )
    return output


def score_race(
    rows: pd.DataFrame,
    spec: tuple[str, str, float, bool, str | None, int, bool] | None,
) -> list[dict]:
    formline_median = float(
        pd.to_numeric(rows["matrix_form_line"], errors="coerce").fillna(60.0).median()
    )
    ranked = []
    for record in rows.to_dict("records"):
        matrices = {
            name: float(record.get(f"matrix_{name}", 60.0) or 60.0)
            for name in hq.MATRIX_WEIGHTS
        }
        if spec:
            (
                dimension,
                signal,
                alpha,
                positive_only,
                confirmation,
                min_samples,
                uplift_only,
            ) = spec
            evidence = record.get(f"_signal_{signal}")
            confirmed = (
                confirmation is None
                or (
                    confirmation == "formline_median"
                    and float(record.get("matrix_form_line", 60.0) or 60.0)
                    >= formline_median
                )
            )
            if evidence is not None and not pd.isna(evidence) and (
                not positive_only or float(evidence) > 60.0
            ) and int(record.get("position_samples", 0) or 0) >= min_samples and confirmed and (
                not uplift_only or float(evidence) > matrices[dimension]
            ):
                matrices[dimension] = (
                    (1.0 - alpha) * matrices[dimension] + alpha * float(evidence)
                )
        ability = sum(
            matrices[name] * weight for name, weight in hq.MATRIX_WEIGHTS.items()
        )
        ranked.append({**record, "_ability": ability})
    return sorted(ranked, key=lambda row: (-row["_ability"], int(row["horse_number"])))


def evaluate(groups: list[pd.DataFrame], spec) -> tuple[dict, dict]:
    metric_rows = []
    details = {}
    for rows in groups:
        ranked = score_race(rows, spec)
        picks = [int(row["horse_number"]) for row in ranked]
        positions = {int(row["horse_number"]): int(row["finish_pos"]) for row in ranked}
        actual = [horse for horse, position in positions.items() if position <= 3]
        metric = hq.race_metrics(picks, actual, actual_pos=positions, field_size=len(rows))
        metric_rows.append(metric)
        key = (ranked[0]["meeting_name"], int(ranked[0]["race_number"]))
        details[key] = {
            "top2_hits": metric["top2_hits"],
            "top2": picks[:2],
            "rank3": picks[2] if len(picks) >= 3 else None,
            "actual": actual,
            "names": {
                int(row["horse_number"]): str(row.get("horse_name") or "")
                for row in ranked
            },
        }
    summary = hq.summarize_races(metric_rows)
    distribution = pd.Series([row["top2_hits"] for row in metric_rows]).value_counts()
    comp = summary["competitiveness"]
    return {
        "races": len(metric_rows),
        "zero_hit": int(distribution.get(0, 0)),
        "one_hit": int(distribution.get(1, 0)),
        "two_hit": int(distribution.get(2, 0)),
        "top2_total_hits": int(sum(row["top2_hits"] for row in metric_rows)),
        "top3_capture_at5": comp["mean_top3_capture_at5"],
        "competitive_recall_at5": comp["mean_competitive_recall_at5"],
        "ndcg_at5": comp["mean_ndcg_at5"],
        "winner_in_top5": summary["rates"]["winner_in_top5"],
        "mrr": summary["mrr"],
    }, details


def _delta(candidate: dict, baseline: dict) -> dict:
    return {key: candidate[key] - baseline[key] for key in candidate if key != "races"}


def run_gate(data: pd.DataFrame) -> dict:
    archive = data[data["dataset"].eq("archive")].copy()
    external = data[data["dataset"].eq("external")].copy()
    dates = sorted(archive["date"].astype(str).unique())
    cut = max(1, math.floor(len(dates) * 0.70))
    annotations = pd.read_csv(hq.ANNOTATIONS, encoding="utf-8-sig")
    abnormal = {
        (row.meeting, int(row.race_number))
        for row in annotations.itertuples()
        if any(bool(getattr(row, flag)) for flag in (
            "extreme_outsider", "major_incident", "interference", "injury", "abnormal"
        ))
    }

    def groups(frame: pd.DataFrame) -> list[pd.DataFrame]:
        return [rows.copy() for _, rows in frame.groupby(
            ["meeting_name", "race_number"], sort=True
        )]

    frames = {
        "development": archive[archive["date"].astype(str).isin(dates[:cut])],
        "temporal_holdout": archive[archive["date"].astype(str).isin(dates[cut:])],
        "all": archive,
        "all_adjusted": archive[~archive.apply(
            lambda row: (row["meeting_name"], int(row["race_number"])) in abnormal,
            axis=1,
        )],
        "external": external,
    }
    split_groups = {name: groups(frame) for name, frame in frames.items()}
    baseline = {}
    baseline_details = {}
    for split, race_groups in split_groups.items():
        baseline[split], baseline_details[split] = evaluate(race_groups, None)
    weak_keys = {
        key for key, detail in baseline_details["all"].items()
        if detail["top2_hits"] <= 1
    }
    split_groups["weak_zero_one"] = [
        rows for rows in split_groups["all"]
        if (rows.iloc[0]["meeting_name"], int(rows.iloc[0]["race_number"])) in weak_keys
    ]
    baseline["weak_zero_one"], baseline_details["weak_zero_one"] = evaluate(
        split_groups["weak_zero_one"], None
    )

    results = {}
    for name, spec in specs().items():
        result = {}
        candidate_details = {}
        for split, race_groups in split_groups.items():
            metrics, details = evaluate(race_groups, spec)
            result[split] = {"candidate": metrics, "delta": _delta(metrics, baseline[split])}
            candidate_details[split] = details
        helped = harmed = rescues = 0
        for key, before in baseline_details["all"].items():
            after = candidate_details["all"][key]
            helped += after["top2_hits"] > before["top2_hits"]
            harmed += after["top2_hits"] < before["top2_hits"]
            rescues += before["rank3"] in before["actual"] and before["rank3"] in after["top2"]
        result["comparison"] = {
            "helped": helped, "harmed": harmed, "rank3_rescues": rescues
        }
        result["race_changes"] = [
            {
                "meeting": key[0],
                "race": key[1],
                "before_hits": before["top2_hits"],
                "after_hits": candidate_details["all"][key]["top2_hits"],
                "before_top2": [
                    {"horse": horse, "name": before["names"].get(horse, "")}
                    for horse in before["top2"]
                ],
                "after_top2": [
                    {"horse": horse, "name": before["names"].get(horse, "")}
                    for horse in candidate_details["all"][key]["top2"]
                ],
                "actual_top3": [
                    {"horse": horse, "name": before["names"].get(horse, "")}
                    for horse in before["actual"]
                ],
                "baseline_rank3": {
                    "horse": before["rank3"],
                    "name": before["names"].get(before["rank3"], ""),
                },
            }
            for key, before in baseline_details["all"].items()
            if candidate_details["all"][key]["top2_hits"] != before["top2_hits"]
            or (
                before["rank3"] in before["actual"]
                and before["rank3"] in candidate_details["all"][key]["top2"]
            )
        ]
        results[name] = result

    ranked = sorted(results, key=lambda name: (
        -results[name]["temporal_holdout"]["delta"]["top2_total_hits"],
        -results[name]["all_adjusted"]["delta"]["ndcg_at5"],
        -results[name]["weak_zero_one"]["delta"]["top2_total_hits"],
    ))
    gates = {}
    for name, result in results.items():
        hold = result["temporal_holdout"]["delta"]
        adjusted = result["all_adjusted"]["delta"]
        external_delta = result["external"]["delta"]
        comp = result["comparison"]
        gates[name] = bool(
            hold["top2_total_hits"] >= 0
            and hold["ndcg_at5"] >= -0.0005
            and adjusted["ndcg_at5"] > 0.0
            and result["all"]["delta"]["zero_hit"] <= 0
            and result["weak_zero_one"]["delta"]["top2_total_hits"] > 0
            and external_delta["ndcg_at5"] >= -0.001
            and external_delta["top2_total_hits"] >= 0
            and comp["helped"] > comp["harmed"]
            and comp["rank3_rescues"] > 0
        )
    passing = [name for name in ranked if gates[name]]
    return {
        "method": {
            "source": "HKJC local horse profile in-running positions",
            "point_in_time": "entries strictly earlier than card date",
            "odds": False,
            "full_field_rerank": True,
        },
        "coverage": {
            "archive_meetings": int(archive["meeting_name"].nunique()),
            "archive_races": int(archive.groupby(["meeting_name", "race_number"]).ngroups),
            "archive_runners": int(len(archive)),
            "position_runners": int(archive["position_samples"].gt(0).sum()),
            "position_samples": int(archive["position_samples"].sum()),
            "external_races": int(external["race_number"].nunique()),
            "external_position_runners": int(external["position_samples"].gt(0).sum()),
            "weak_zero_one_races": len(weak_keys),
        },
        "baseline": baseline,
        "results": results,
        "ranked_candidates": ranked,
        "gates": gates,
        "passing_candidates": passing,
        "recommendation": passing[0] if passing else "HOLD_ALL",
    }


def write_report(payload: dict) -> None:
    lines = [
        "# HKJC Local Position-Conversion Gate",
        "",
        f"- Coverage: {payload['coverage']}",
        "- Official local horse-profile positions only; strict pre-race cutoff.",
        "- Full-field matrix rerank; no odds, swaps, or micro tie-breaks.",
        f"- Passing candidates: {payload['passing_candidates'] or ['NONE']}",
        "",
        "| candidate | pass | all 0hit Δ | all top2 Δ | adjusted NDCG Δ | holdout top2 Δ | holdout NDCG Δ | weak top2 Δ | external NDCG Δ | help/harm | R3 rescues |",
        "|---|:---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in payload["ranked_candidates"]:
        result = payload["results"][name]
        all_delta = result["all"]["delta"]
        adjusted = result["all_adjusted"]["delta"]
        hold = result["temporal_holdout"]["delta"]
        weak = result["weak_zero_one"]["delta"]
        external = result["external"]["delta"]
        comp = result["comparison"]
        lines.append(
            f"| {name} | {'PASS' if payload['gates'][name] else 'FAIL'} | "
            f"{all_delta['zero_hit']:+.0f} | {all_delta['top2_total_hits']:+.0f} | "
            f"{adjusted['ndcg_at5']:+.4f} | {hold['top2_total_hits']:+.0f} | "
            f"{hold['ndcg_at5']:+.4f} | {weak['top2_total_hits']:+.0f} | "
            f"{external['ndcg_at5']:+.4f} | {comp['helped']}/{comp['harmed']} | "
            f"{comp['rank3_rescues']} |"
        )
    REPORT_OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    raw = pd.concat([
        pd.read_csv(ARCHIVE, usecols=["horse_id"]),
        pd.read_csv(EXTERNAL, usecols=["horse_id"]),
    ], ignore_index=True)
    horse_ids = sorted({str(value).strip() for value in raw["horse_id"].dropna() if str(value).strip()})
    if args.limit:
        horse_ids = horse_ids[:args.limit]
    cache = fetch_profiles(horse_ids, args.workers, refresh_rich=args.refresh_rich)
    if args.fetch_only:
        return 0
    data = _attach_relative_signals(prepare(cache))
    payload = run_gate(data)
    JSON_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(payload)
    print(REPORT_OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
