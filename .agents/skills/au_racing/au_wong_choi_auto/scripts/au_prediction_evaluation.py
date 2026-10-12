"""AU artifact evaluation: canonical v3 plus preregistered power/cohort/Holm.

No fitting or candidate selection happens here. Registration timestamps are
content-bound declarations; the audit must independently verify registration.
"""
from __future__ import annotations

import math
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parents[2] / "shared_racing"))
from eval_metrics import race_metrics  # noqa: E402
from model_evaluation_decision import (  # noqa: E402
    METRIC_DIRECTIONS, PRIMARY_KEYS, RANKING_KEYS, _full_record_metric,
    evaluate_full_record, holm_adjust,
)
from au_prediction_intake import content_hash, validate_pair, _require, _time  # noqa: E402


def metric_row(race, prediction):
    """Consume production ordering, then join complete official finish labels."""
    positions = race.get("labels", {})
    roster = set(race["input"]["runner_ids"])
    _require(set(positions) == roster, "finish_label_roster_changed")
    _require(race.get("labels_hash") == content_hash(positions), "finish_labels_hash_changed")
    _require(all(type(p) is int and 1 <= p <= len(roster) for p in positions.values()),
             "unknown_or_invalid_finish_labels")
    top3 = {horse for horse, pos in positions.items() if pos <= 3}
    _require(len(top3) >= 3 and 1 in positions.values(), "incomplete_placing_labels")
    ranking = prediction["ranking"]
    result = race_metrics(ranking, top3, actual_pos=positions, field_size=len(roster))
    # AU canonical AUC: placed vs unplaced pairs, at least one model top-five;
    # score ties count half. Only the top-five boundary follows final production
    # ranking. Do not assign fabricated scores or positions to unknown runners.
    rank = {horse: i for i, horse in enumerate(ranking, 1)}
    scores = prediction["ability"]
    comparable = concordant = 0
    for placed in top3:
        for other in roster - top3:
            if rank[placed] > 5 and rank[other] > 5:
                continue
            comparable += 1
            concordant += 1 if scores[placed] > scores[other] else (.5 if scores[placed] == scores[other] else 0)
    result["mean_top3_model_rank"] = result["top3_mean_model_rank"]
    result["top5_pairwise_auc"] = concordant / comparable if comparable else None
    return result


def _evidence(base, cand, dates, metric):
    return _full_record_metric([r[metric] for r in base], [r[metric] for r in cand], dates,
                               higher_is_better=METRIC_DIRECTIONS[metric], blocks=6, bootstrap=2000, seed=7)


def evaluate_family(manifest, baseline, candidates, *, baseline_profile, candidate_profiles,
                    registration, power_record):
    """Evaluate every registered arm with immutable profile and sample binding.

    Holm hypotheses are the entire preregistered arm × metric grid, including
    ineligible/nonwinning arms. Non-informative ranking hypotheses receive p=1,
    never shrink the family. Both family and power record predate evaluation.
    A historical WIN remains PENDING_FORWARD, never a release authorization.
    """
    _require(registration.get("schema") == "au-evaluation-family/v1", "family_schema_missing")
    _require(registration.get("holm_unit") == "arm_metric", "holm_family_not_registered")
    _require(registration.get("manifest_hash") == content_hash(manifest), "family_sample_hash_changed")
    _require(registration.get("baseline_profile_hash") == content_hash(baseline_profile), "family_baseline_changed")
    _require(registration.get("power_hash") == content_hash(power_record), "power_record_hash_changed")
    registered_at = _time(registration["registered_at"])
    _require(_time(power_record["prepared_at"]) <= registered_at < _time(registration["evaluation_started_at"]),
             "power_or_family_registered_after_evaluation")
    arms = registration["arms"]
    _require(bool(arms) and set(arms) == set(candidates) == set(candidate_profiles) == set(power_record["arms"]),
             "registered_arm_set_changed")
    ranking = tuple(registration["ranking_metrics"])
    _require(bool(ranking) and len(set(ranking)) == len(ranking) and set(ranking) <= RANKING_KEYS,
             "unregistered_ranking_metric")
    cohorts = registration["cohorts"]
    _require(bool(cohorts) and len({c["name"] for c in cohorts}) == len(cohorts), "cohorts_not_registered")
    for cohort in cohorts:
        _require(cohort["key"] in ("field_size", "venue", "going"), "market_or_unknown_cohort")
        _require(isinstance(cohort.get("values"), list) and bool(cohort["values"]), "cohort_values_not_registered")
        _require(type(cohort["min_races"]) is int and cohort["min_races"] > 0 and
                 type(cohort["min_days"]) is int and cohort["min_days"] > 0, "cohort_power_not_registered")
    metrics = tuple(PRIMARY_KEYS["au"]) + ranking
    records, p_values = {}, {}
    for arm in sorted(arms):
        profile = candidate_profiles[arm]
        _require(arms[arm]["profile_hash"] == content_hash(profile), "registered_profile_changed")
        checked = validate_pair(manifest, baseline, candidates[arm], baseline_profile=baseline_profile,
                                candidate_profile=profile)
        pairs = checked["pairs"]
        dates = [race["date"] for race, _, _ in pairs]
        base = [metric_row(race, prediction) for race, prediction, _ in pairs]
        cand = [metric_row(race, prediction) for race, _, prediction in pairs]
        power = power_record["arms"][arm]
        _require(set(power) == set(ranking), "power_metric_set_changed")
        informative = []
        for metric, item in power.items():
            budget, mde = item["component_budget"], item["mde"]
            _require(all(type(v) in (int, float) and math.isfinite(v) and v >= 0 for v in (budget, mde)),
                     "invalid_power_evidence")
            if budget >= mde:
                informative.append(metric)
        evidence = {metric: _evidence(base, cand, dates, metric) for metric in metrics}
        decision = evaluate_full_record(domain="au", mode=checked["mode"], dates=dates,
                                        baseline_rows=base, candidate_rows=cand, leakage_audit_passed=True,
                                        ranking_metrics=tuple(m for m in ranking if m in informative))
        cohort_results, harmful, sparse = {}, [], []
        for cohort in cohorts:
            indices = []
            for i, (race, _, _) in enumerate(pairs):
                value = len(race["input"]["runner_ids"]) if cohort["key"] == "field_size" else race.get("cohorts", {}).get(cohort["key"])
                _require(value is not None, "cohort_metadata_missing")
                if value in cohort["values"]:
                    indices.append(i)
            day_count = len({dates[i] for i in indices})
            if not indices:
                cohort_results[cohort["name"]] = {"status": "NO_SAMPLE", "races": 0, "days": 0}
                continue
            ce = {m: _evidence([base[i] for i in indices], [cand[i] for i in indices],
                               [dates[i] for i in indices], m) for m in PRIMARY_KEYS["au"]}
            status = "NO_DETECTED_HARM"
            if any(e.favourable().ci_high < 0 for e in ce.values()):
                harmful.append(cohort["name"])
                status = "HARM"
            elif len(indices) < cohort["min_races"] or day_count < cohort["min_days"]:
                sparse.append(cohort["name"])
                status = "UNRESOLVABLE"
            cohort_results[cohort["name"]] = {"status": status, "races": len(indices), "days": day_count,
                                             "primary": {m: vars(e) for m, e in ce.items()}}
        # Contract primary/safety rejection takes precedence over a low-power
        # ranking fallback. A/A must reject even if its budget is zero.
        aa = all(b["ability"] == c["ability"] and b["ranking"] == c["ranking"] for _, b, c in pairs)
        if aa:
            decision = {"verdict": "REJECT", "reason": "identical_predictions"}
        elif harmful:
            decision = {"verdict": "REJECT", "reason": "cohort_regression", "cohorts": harmful}
        elif decision["verdict"] != "REJECT" and (sparse or len(set(dates)) < 6):
            decision = {"verdict": "UNRESOLVABLE", "reason": "insufficient_cohort_or_time_block_power", "cohorts": sparse}
        elif not informative and decision.get("reason") == "ranking_evidence_too_weak":
            decision = {"verdict": "UNRESOLVABLE", "reason": "all_registered_ranking_metrics_noninformative"}
        for metric, item in evidence.items():
            p_values[f"{arm}::{metric}"] = item.p_value if metric in PRIMARY_KEYS["au"] or metric in informative else 1.0
        records[arm] = {"raw_decision": decision, "evidence": {m: vars(e) for m, e in evidence.items()},
                        "informative_ranking": informative, "cohorts": cohort_results, "mode": checked["mode"]}
    adjusted = holm_adjust(p_values)
    for arm, record in records.items():
        decision = dict(record["raw_decision"])
        if decision["verdict"] in ("PRIMARY_WIN", "RANKING_WIN"):
            keys = decision["detail"]["winning_metrics"] if decision["verdict"] == "PRIMARY_WIN" else decision["detail"]["ci_supported_metrics"]
            if not any(adjusted[f"{arm}::{metric}"] <= .05 for metric in keys):
                decision = {"verdict": "REJECT", "reason": "family_holm_not_significant"}
        record["decision"] = decision
        record["forward_status"] = "PENDING_FORWARD" if decision["verdict"] in ("PRIMARY_WIN", "RANKING_WIN") else "NOT_PROMOTED"
    return {"schema": "au-family-evaluation/v1", "manifest_hash": content_hash(manifest),
            "registration_hash": content_hash(registration), "power_hash": content_hash(power_record),
            "holm_raw_p": p_values, "holm_adjusted_p": adjusted, "arms": records,
            "release_authorized": False}
