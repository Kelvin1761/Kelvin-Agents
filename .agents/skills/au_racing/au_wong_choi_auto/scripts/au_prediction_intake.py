"""Validate AU paired predictions against an independently locked corpus manifest.

This is an intake boundary, not a leakage audit or an OOS producer. Source
availability assertions must be established by the separate provenance audit.
No verdict is granted by a caller's mode string. Explicit final rankings include
production tie breaks and safety swaps; intake never reconstructs them from scores.
"""
from __future__ import annotations

from datetime import date, datetime
import hashlib
import json
import math


class PredictionValidationError(ValueError):
    """An artifact cannot support a paired AU evaluation."""


def content_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _require(condition, reason):
    if not condition:
        raise PredictionValidationError(reason)


def _day(value):
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise PredictionValidationError("invalid_date") from exc
    _require(parsed.isoformat() == value, "noncanonical_date")
    return parsed


def _time(value):
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise PredictionValidationError("invalid_available_at") from exc
    _require(parsed.tzinfo is not None, "availability_timezone_missing")
    return parsed


def _index(rows, label):
    result = {}
    for row in rows:
        key = row.get("race_id")
        _require(isinstance(key, str) and bool(key), label + "_race_id_missing")
        _require(key not in result, label + "_duplicate_race_id")
        result[key] = row
    return result


def validate_pair(manifest, baseline, candidate, *, baseline_profile, candidate_profile):
    """Return pairs in locked chronological order, or fail closed.

    Manifest contains *all* evaluation races and allowed training races. Every
    manifest input contains runner_ids and source entries {available_at, audit:
    PASS}; prediction input_hash is derived from that input. Training payloads
    bind IDs and input hashes, preventing an unverified fit_cutoff assertion.
    Labels live outside inputs. The manifest/profile must be frozen before any
    arm is evaluated. Omitted predictions, including fallback days, are errors.
    """
    _require(manifest.get("schema") == "au-paired-predictions/v1", "unsupported_schema")
    _require(manifest.get("provenance_audit") == "PASS", "provenance_not_passed")
    expected = _index(manifest["evaluation_races"], "manifest")
    training = _index(manifest.get("training_races", []), "training")
    for key, row in expected.items():
        if key in training:
            _require(training[key] == row, "training_evaluation_identity_conflict")
        training[key] = row
    bases, candidates = _index(baseline, "baseline"), _index(candidate, "candidate")
    _require(bool(expected), "empty_evaluation")
    _require(set(expected) == set(bases) == set(candidates), "race_identity_changed")
    profiles = (baseline_profile, candidate_profile)
    _require(all(type(p.get("fitted")) is bool for p in profiles), "profile_fitted_missing")
    profile_hashes = tuple(content_hash(p) for p in profiles)
    mode = "walk_forward_oos" if candidate_profile["fitted"] else "fixed_rule"
    pairs = []
    for key, race in sorted(expected.items(), key=lambda item: (item[1]["date"], item[0])):
        day = _day(race["date"])
        if mode == "walk_forward_oos":
            _require(day >= date(2026, 8, 5), "outside_au_clean_fit_window")
        deadline = _time(race["prediction_at"])
        _require(deadline.date() == day, "prediction_day_mismatch")
        roster = race["input"]["runner_ids"]
        _require(len(roster) >= 4 and len(set(roster)) == len(roster), "invalid_runner_roster")
        _require(all(isinstance(n, str) and n for n in roster), "invalid_runner_id")
        sources = race["input"].get("sources", [])
        _require(bool(sources), "source_lineage_missing")
        for source in sources:
            _require(source.get("audit") == "PASS", "source_provenance_flag")
            _require(_time(source["available_at"]) <= deadline, "future_source")
        input_hash = content_hash(race["input"])
        for record, profile, profile_hash in zip((bases[key], candidates[key]), profiles, profile_hashes):
            _require(record.get("date") == race["date"], "prediction_date_changed")
            _require(record.get("input_hash") == input_hash, "input_hash_changed")
            _require(record.get("profile_hash") == profile_hash, "profile_hash_changed")
            _require(record.get("prediction_at") == race["prediction_at"], "prediction_cutoff_changed")
            ranking = record.get("ranking", [])
            _require(len(ranking) == len(roster) and set(ranking) == set(roster), "runner_roster_changed")
            scores = record.get("ability", {})
            _require(set(scores) == set(roster), "ability_roster_changed")
            _require(all(type(v) in (float, int) and math.isfinite(v) for v in scores.values()),
                     "nonfinite_ability")
            _require(record.get("status") in ("candidate", "baseline", "baseline_fallback"),
                     "prediction_status_missing")
            if record["status"] == "baseline_fallback":
                _require(profile.get("fallback") == "baseline", "fallback_not_registered")
                _require(record["ability"] == bases[key]["ability"] and ranking == bases[key]["ranking"],
                         "fallback_differs_from_baseline")
            fitted = profile["fitted"]
            fit = record.get("fit")
            if not fitted:
                _require(fit is None, "fixed_rule_contains_fit")
                continue
            _require(isinstance(fit, dict), "fitted_candidate_needs_walk_forward_predictions")
            ids = fit.get("training_race_ids", [])
            _require(len(set(ids)) == len(ids), "duplicate_training_race")
            payload = []
            for train_id in sorted(ids):
                _require(train_id in training, "unknown_training_race")
                train = training[train_id]
                train_day = _day(train["date"])
                _require(date(2026, 8, 5) <= train_day < day, "training_not_strictly_before_prediction")
                train_sources = train["input"].get("sources", [])
                _require(bool(train_sources), "training_source_lineage_missing")
                for source in train_sources:
                    _require(source.get("audit") == "PASS", "training_source_provenance_flag")
                    _require(_time(source["available_at"]) <= _time(train["prediction_at"]), "training_future_source")
                _require(_time(train["results_available_at"]) < deadline, "training_labels_not_available")
                labels_hash = train.get("labels_hash")
                _require(isinstance(labels_hash, str) and len(labels_hash) == 64, "training_labels_hash_missing")
                _require("labels" in train and content_hash(train["labels"]) == labels_hash,
                         "training_labels_hash_changed")
                payload.append({"race_id": train_id, "input_hash": content_hash(train["input"]),
                                "labels_hash": labels_hash})
            _require(fit.get("training_hash") == content_hash(payload), "training_hash_changed")
            cutoff = max((training[n]["date"] for n in ids), default=None)
            _require(fit.get("cutoff") == cutoff, "fit_cutoff_changed")
            if not ids:
                _require(record["status"] == "baseline_fallback", "empty_training_without_fallback")
            _require("state" in fit and fit.get("state_hash") == content_hash(fit["state"]),
                     "fit_state_hash_changed")
        pairs.append((race, bases[key], candidates[key]))
    return {"mode": mode, "manifest_hash": content_hash(manifest), "pairs": pairs,
            "baseline_profile_hash": profile_hashes[0], "candidate_profile_hash": profile_hashes[1]}
