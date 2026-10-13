"""Advisory distribution diagnostics for stored AU/HKJC feature scores.

Reads pre-race features only. No outcome, odds, ranking or model mutation.
Sparse cohorts are reported as insufficient; drift never blocks publication.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys

os.environ["DO_NOT_TRACK"] = "1"
os.environ["ITERATIVE_DO_NOT_TRACK"] = "1"
REPO = Path(__file__).resolve().parents[4]
SCRIPTS = REPO / ".agents/skills/shared_racing/scripts"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(SCRIPTS))

FEATURES = (
    "form_score", "performance_quality_score", "pace_figure_score",
    "trial_score", "pace_map_score", "jockey_score", "trainer_score",
    "track_score",
)
MIN_REF = 100
MIN_CURRENT = 50
THRESHOLD = 0.1


def read_rows(paths):
    """Return explicit missing values, cohort metadata and content provenance."""
    rows, manifest = [], []
    seen = set()
    for path in sorted(map(Path, paths)):
        raw = path.read_bytes()  # unreadable files must not silently shrink corpus
        data = json.loads(raw)
        name = path.parent.name
        match = re.match(r"^(\d{4}-\d{2}-\d{2})[ _](.+)", name)
        if not match:
            raise ValueError(f"Meeting has no dated identity: {path}")
        day, venue = match.groups()
        venue = re.split(r"[ _]Race\b|_Race_", venue)[0].replace("_", " ").strip()
        race = data.get("race_analysis") or {}
        distance = re.search(r"\d+", str(race.get("distance", "")))
        distance_band = "unknown" if not distance else (
            "sprint" if int(distance[0]) <= 1400 else
            "mile" if int(distance[0]) <= 1800 else "staying"
        )
        horses = data.get("horses") or {}
        if not horses:
            raise ValueError(f"No horses: {path}")
        bucket = "<=8" if len(horses) <= 8 else "9-10" if len(horses) <= 10 else "11-12" if len(horses) <= 12 else "13+"
        identity = (name, path.name)
        if identity in seen:
            raise ValueError(f"Duplicate race: {identity}")
        seen.add(identity)
        manifest.append({"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()})
        for number, horse in horses.items():
            auto = horse.get("python_auto") or {}
            features = auto.get("feature_scores") or {}
            if not features:
                raise ValueError(f"Unscored horse {number}: {path}")
            going = str(race.get("going") or (auto.get("race_context") or {}).get("going") or "unknown").lower()
            family = next((g for g in ("good", "soft", "heavy", "firm", "yielding", "standard") if g in going), "unknown")
            row = {"date": day, "race": f"{name}/{path.name}", "venue": venue,
                   "distance_band": distance_band, "going_family": family,
                   "field_bucket": bucket, "score_version": auto.get("version", "unknown")}
            for key in FEATURES:
                value = features.get(key)
                if value is not None:
                    value = float(value)
                    if not math.isfinite(value):
                        value = None
                row[key] = value
            rows.append(row)
    return rows, manifest


def compare(reference, current, html=None):
    """Evidently ignores nulls in drift; report null coverage separately."""
    import pandas as pd
    from evidently import Report
    from evidently.metrics import ValueDrift

    ref, cur = pd.DataFrame(reference), pd.DataFrame(current)
    metrics, fields = [], {}
    for field in FEATURES:
        r, c = ref[field].dropna(), cur[field].dropna()
        fields[field] = {"reference_non_null": len(r), "current_non_null": len(c),
                         "reference_missing_rate": float(ref[field].isna().mean()),
                         "current_missing_rate": float(cur[field].isna().mean())}
        if len(r) < MIN_REF or len(c) < MIN_CURRENT:
            fields[field]["status"] = "insufficient_data"
        elif r.nunique() < 2:
            fields[field]["status"] = "constant_reference"
        else:
            metrics.append(ValueDrift(column=field, method="wasserstein", threshold=THRESHOLD))
    if metrics:
        result = Report(metrics).run(cur[list(FEATURES)], ref[list(FEATURES)])
        payload = result.dict()
        for metric in payload["metrics"]:
            config = metric["config"]
            column = config["column"]
            score = float(metric["value"])
            fields[column].update(score=score, status="drift" if score >= THRESHOLD else "stable")
        if html:
            result.save_html(str(html))
    return fields


def cohort_report(reference, current):
    keys = ("venue", "distance_band", "going_family", "field_bucket")
    groups = {}
    for row in current:
        key = tuple(row[k] for k in keys)
        groups.setdefault(key, []).append(row)
    results = []
    for key, cur in sorted(groups.items()):
        ref = [r for r in reference if tuple(r[k] for k in keys) == key]
        entry = {"cohort": dict(zip(keys, key)), "reference_horses": len(ref), "current_horses": len(cur)}
        if "unknown" in key or len(ref) < MIN_REF or len(cur) < MIN_CURRENT:
            entry["status"] = "insufficient_data"
        else:
            entry.update(status="evaluated", fields=compare(ref, cur))
        results.append(entry)
    return results


def main(argv=None):
    from corpus_paths import logic_files
    from data_contract import engine_fingerprint, resolve_root

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=("au", "hkjc"), required=True)
    parser.add_argument("--meeting", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    match = re.match(r"\d{4}-\d{2}-\d{2}", args.meeting.name)
    if not match:
        raise ValueError("Meeting must start with YYYY-MM-DD")
    current_date = date.fromisoformat(match[0])
    first = (current_date - timedelta(days=28)).isoformat()
    root = resolve_root(args.platform)
    if root is None:
        raise ValueError("No corpus root configured")
    paths = [p for p in logic_files(root) if first <= Path(p).parent.name[:10] < match[0]]
    reference, ref_manifest = read_rows(paths)
    current, current_manifest = read_rows(args.meeting.glob("Race_*_Logic.json"))
    if not current:
        raise ValueError("No current scored races")
    cohorts = cohort_report(reference, current)
    # The pooled plot is exploratory because composition and model versions can change.
    pooled = compare(reference, current, args.out / "pooled_exploratory.html") if reference else {}
    report = {"platform": args.platform, "mode": "advisory", "engine_fingerprint": engine_fingerprint(args.platform),
              "method": "wasserstein", "threshold": THRESHOLD,
              "reference_dates": [first, (current_date - timedelta(days=1)).isoformat()],
              "reference_horses": len(reference), "current_horses": len(current),
              "cohorts": cohorts, "pooled_exploratory": pooled,
              "limitations": ["Drift is not proof of a pipeline incident or model degradation.",
                              "Stored scores may span model changes; score version is not an engine hash.",
                              "Insufficient cohorts give no assurance; missing rates require existing health checks."],
              "inputs": ref_manifest + current_manifest}
    (args.out / "drift.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    evaluated = sum(c["status"] == "evaluated" for c in cohorts)
    alarms = sum(f["status"] == "drift" for c in cohorts for f in c.get("fields", {}).values())
    print(f"Drift advisory {args.platform}: {evaluated}/{len(cohorts)} cohorts evaluated; {alarms} unverified shifts. {args.out / 'drift.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
