"""Complete-day AU walk-forward producer with explicit warm-up/fallback records.

Scoring and fitting adapters are injected; no outcomes for a prediction date are
passed to either adapter. This module does not grant a provenance PASS to inputs.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy

from au_prediction_intake import content_hash, validate_pair, _day, _index, _require, _time


def produce_walk_forward(manifest, *, baseline_profile, candidate_profile,
                         fit, predict_baseline, predict_candidate):
    """Fit once before each complete day; emit every registered evaluation race.

    fit(prefix, profile) receives isolated prior-day input/labels only and returns
    a JSON state, or None for registered no-consensus fallback. Predict adapters
    receive an isolated {race_id,date,prediction_at,input}, state and profile, and
    must return complete ability/ranking (including production tie/safety rules).
    Exceptions propagate; they never silently drop a day or switch to fallback.
    """
    _require(manifest.get("provenance_audit") == "PASS", "provenance_not_passed")
    _require(baseline_profile.get("fitted") is False, "baseline_must_be_locked_fixed_profile")
    _require(candidate_profile.get("fitted") is True, "producer_requires_fitted_profile")
    _require(candidate_profile.get("fallback") == "baseline", "fallback_not_registered")
    _require(isinstance(candidate_profile.get("algorithm"), str), "algorithm_not_registered")
    for name in ("warmup_min_races", "warmup_min_days"):
        _require(type(candidate_profile.get(name)) is int and candidate_profile[name] >= 1,
                 "warmup_not_registered")
    expected = _index(manifest["evaluation_races"], "manifest")
    _require(bool(expected), "empty_evaluation")
    training = _index(manifest.get("training_races", []), "training")
    for key, race in expected.items():
        if key in training:
            _require(training[key] == race, "training_evaluation_identity_conflict")
        training[key] = race
    # Validate evaluation inputs before an adapter can observe them. Temporary
    # zero-score records exercise the same intake boundary, not a second schema.
    preflight_base, preflight_candidate = [], []
    empty_state = {"parameters": None, "fallback_reason": "preflight"}
    empty_fit = {"training_race_ids": [], "training_hash": content_hash([]), "cutoff": None,
                 "state": empty_state, "state_hash": content_hash(empty_state)}
    for race in expected.values():
        record = {k: race[k] for k in ("race_id", "date", "prediction_at")}
        record.update(input_hash=content_hash(race["input"]), ranking=list(race["input"]["runner_ids"]),
                      ability={n: 0.0 for n in race["input"]["runner_ids"]})
        preflight_base.append({**record, "profile_hash": content_hash(baseline_profile), "status": "baseline"})
        preflight_candidate.append({**record, "profile_hash": content_hash(candidate_profile),
                                    "status": "baseline_fallback", "fit": empty_fit})
    validate_pair(manifest, preflight_base, preflight_candidate, baseline_profile=baseline_profile,
                  candidate_profile=candidate_profile)
    for race in training.values():
        _day(race["date"])
    by_day = defaultdict(list)
    for race in expected.values():
        _day(race["date"])
        _require(race["date"] >= "2026-08-05", "outside_au_clean_fit_window")
        by_day[race["date"]].append(race)
    baseline, candidate, fit_days = [], [], []
    original_hash = content_hash(manifest)
    for day, races in sorted(by_day.items()):
        deadline = min(_time(r["prediction_at"]) for r in races)
        prefix = []
        for race in sorted(training.values(), key=lambda r: (r["date"], r["race_id"])):
            if not ("2026-08-05" <= race["date"] < day):
                continue
            _require("results_available_at" in race, "training_label_availability_missing")
            if _time(race["results_available_at"]) >= deadline:
                continue
            _require("labels" in race and race.get("labels_hash") == content_hash(race["labels"]),
                     "training_labels_hash_changed")
            sources = race["input"].get("sources", [])
            _require(bool(sources), "training_source_lineage_missing")
            for source in sources:
                _require(source.get("audit") == "PASS", "training_source_provenance_flag")
                _require(_time(source["available_at"]) <= _time(race["prediction_at"]), "training_future_source")
            prefix.append(race)
        trained_days = len({r["date"] for r in prefix})
        warm = len(prefix) >= candidate_profile["warmup_min_races"] and trained_days >= candidate_profile["warmup_min_days"]
        state = fit(deepcopy(prefix), deepcopy(candidate_profile)) if warm else None
        fallback_reason = None if state is not None else ("no_consensus" if warm else "warmup")
        fitted_state = {"parameters": state, "fallback_reason": fallback_reason}
        training_payload = [{"race_id": r["race_id"], "input_hash": content_hash(r["input"]),
                             "labels_hash": r["labels_hash"]} for r in sorted(prefix, key=lambda r: r["race_id"])]
        fit_record = {"training_race_ids": [r["race_id"] for r in sorted(prefix, key=lambda r: r["race_id"])],
                      "training_hash": content_hash(training_payload),
                      "cutoff": max((r["date"] for r in prefix), default=None),
                      "state": fitted_state, "state_hash": content_hash(fitted_state)}
        fit_days.append({"date": day, "training_races": len(prefix), "training_days": trained_days,
                         "state_hash": fit_record["state_hash"], "fallback_reason": fallback_reason})
        for race in sorted(races, key=lambda r: r["race_id"]):
            safe_input = {k: deepcopy(race[k]) for k in ("race_id", "date", "prediction_at", "input")}
            base = predict_baseline(deepcopy(safe_input), None, deepcopy(baseline_profile))
            cand = deepcopy(base) if fallback_reason else predict_candidate(
                deepcopy(safe_input), deepcopy(state), deepcopy(candidate_profile))
            common = {k: race[k] for k in ("race_id", "date", "prediction_at")}
            common["input_hash"] = content_hash(race["input"])
            baseline.append({**base, **common, "profile_hash": content_hash(baseline_profile), "status": "baseline"})
            candidate.append({**cand, **common, "profile_hash": content_hash(candidate_profile), "fit": deepcopy(fit_record),
                              "status": "baseline_fallback" if fallback_reason else "candidate"})
    _require(content_hash(manifest) == original_hash, "manifest_mutated_by_adapter")
    checked = validate_pair(manifest, baseline, candidate, baseline_profile=baseline_profile,
                            candidate_profile=candidate_profile)
    return {"schema": "au-oos-producer/v1", "manifest_hash": checked["manifest_hash"],
            "baseline_profile": baseline_profile, "candidate_profile": candidate_profile,
            "baseline": baseline, "candidate": candidate, "fit_days": fit_days}
