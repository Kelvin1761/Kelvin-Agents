"""Frozen metric and actual harness integration tests; all data is synthetic."""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared_wong_choi.contracts import Domain
from shared_wong_choi.evaluation_rulers import load_evaluation_ruler
from shared_wong_choi.research_harness import run_research_harness
from shared_wong_choi.research_postflight import SafetyEvidence
from shared_wong_choi.research_safety import ResearchSafetyError
from test_research_safety import encoded, fixture_inputs, source_record


METRICS = {
    "gold", "good_positional", "top3_capture_at5", "mean_top3_model_rank",
    "competitive_recall_at5", "ndcg_at5", "top5_pairwise_auc",
}


def completed(scores, positions, withdrawn=()):
    predictions = [{"entity_id": str(i), "score": score}
                   for i, score in enumerate(scores, 1)]
    labels = {"positions": {str(i): pos for i, pos in enumerate(positions, 1)
                            if str(i) not in withdrawn}, "withdrawn": list(withdrawn)}
    context = {"cohorts": {}, "prices": {r["entity_id"]: {} for r in predictions}}
    return predictions, labels, context


# Captured from unmodified9848 au_eval._stage4_metric_rows before extraction.
@pytest.mark.parametrize("scores,positions,mean,ndcg,auc,gold,good,capture", [
    ([60, 50, 40, 30, 20, 10], [1, 2, 4, 3, 5, 6], 7 / 3,
     0.992619504174702, 8 / 9, True, True, 1.0),
    ([60, 40, 40, 30, 20, 10], [1, 2, 4, 3, 5, 6], 7 / 3,
     0.992619504174702, 7.5 / 9, True, True, 1.0),
    ([80, 70, 60, 50, 40, 30, 20, 10], [1, 4, 5, 6, 7, 2, 3, 8], 14 / 3,
     0.7452525342261976, 5 / 13, False, False, 1 / 3),
    ([60, 50, 40, 30, 20, 10], [1, 2, 3, 3, 5, 6], 2.5,
     1.0, 1.0, True, True, 1.0),
])
def test_matches_pre_edit_native_seven_metric_reference(scores, positions, mean, ndcg, auc, gold, good, capture):
    from shared_wong_choi.research_racing_measurement import measure_racing_prediction
    args = completed(scores, positions)
    original = deepcopy(args)
    result = measure_racing_prediction(*args)
    assert result == pytest.approx({"gold": gold, "good_positional": good,
        "top3_capture_at5": capture, "mean_top3_model_rank": mean,
        "competitive_recall_at5": capture, "ndcg_at5": ndcg, "top5_pairwise_auc": auc})
    assert args == original


def test_explicit_withdrawal_is_excluded_only_during_measurement():
    from shared_wong_choi.research_racing_measurement import measure_racing_prediction
    args = completed([60, 50, 40, 30, 20, 10], [1, 2, 0, 3, 4, 5], withdrawn=("3",))
    result = measure_racing_prediction(*args)
    assert result == {"gold": True, "good_positional": True, "top3_capture_at5": 1.0,
        "mean_top3_model_rank": 2.0, "competitive_recall_at5": 1.0,
        "ndcg_at5": 1.0, "top5_pairwise_auc": 1.0}


@pytest.mark.parametrize("fault", ["missing_finish", "unknown_finish", "missing_prediction",
    "duplicate_prediction", "unknown_prediction", "dropped_from_both", "boolean_score",
    "infinite_score", "boolean_finish", "impossible_places", "unknown_withdrawal",
    "duplicate_withdrawal", "self_reported_metrics", "no_comparable_pairs"])
def test_incomplete_or_invalid_measurement_never_becomes_zero(fault):
    from shared_wong_choi.research_racing_measurement import measure_racing_prediction
    predictions, label, context = completed([60, 50, 40, 30, 20, 10], [1, 2, 4, 3, 5, 6])
    if fault == "missing_finish": del label["positions"]["6"]
    elif fault == "unknown_finish": label["positions"]["unknown"] = label["positions"].pop("6")
    elif fault == "missing_prediction": predictions.pop()
    elif fault == "duplicate_prediction": predictions.append(deepcopy(predictions[0]))
    elif fault == "unknown_prediction": predictions[-1]["entity_id"] = "unknown"
    elif fault == "dropped_from_both": predictions.pop(); del label["positions"]["6"]
    elif fault == "boolean_score": predictions[0]["score"] = True
    elif fault == "infinite_score": predictions[0]["score"] = float("inf")
    elif fault == "boolean_finish": label["positions"]["1"] = True
    elif fault == "impossible_places": label["positions"]["1"] = 2
    elif fault == "unknown_withdrawal": label["withdrawn"] = ["unknown"]
    elif fault == "duplicate_withdrawal": label["withdrawn"] = ["3", "3"]; del label["positions"]["3"]
    elif fault == "self_reported_metrics": predictions = [{"gold": True}]
    elif fault == "no_comparable_pairs":
        predictions, label, context = completed([3, 2, 1], [1, 2, 3])
    with pytest.raises(ResearchSafetyError):
        measure_racing_prediction(predictions, label, context)


def harness_inputs(tmp_path, domain, *, missing_finish=False, different_field=False, distinct_ids=False):
    ruler = load_evaluation_ruler(domain)
    names = tuple(m["name"] for m in ruler.metrics)
    postflight = {"schema_version": "wong-choi-research-postflight-protocol/v1",
        "spec_id": f"wc:{domain.value}:experiment-spec:safety-inputs", "domain": domain.value,
        "label_field": "winner", "harness_digest": hashlib.sha256(
            (Path(__file__).resolve().parents[1] / "research_harness.py").read_bytes()).hexdigest(),
        "components": ["a", "b"],
        "variants": {"empty": [], "a": ["a"], "b": ["b"], "full": ["a", "b"]},
        "negative_control": {"kind": "development_label_rotation", "max_gain": {n: 0.001 for n in names}},
        "power": {"method": "paired_t_design", "target": 0.8, "min_dev_units": 2,
            "unit": "race", "minimum_effects": {n: 0.1 for n in names},
            "sd_floor": {n: 0.001 for n in names}}}
    postflight_path = tmp_path / "postflight.json"
    postflight_path.write_bytes(encoded(postflight))

    def amend(protocol, rows, records):
        protocol["postflight_protocol_digest"] = hashlib.sha256(postflight_path.read_bytes()).hexdigest()
        for i, row in enumerate(rows):
            event = datetime.fromisoformat(row["event_at"])
            for entity in map(str, range(3, 7)):
                value = 70 + i + int(entity)
                feature = source_record(i, entity, event, value)
                price = source_record(i, entity, event, 2.0 + int(entity) / 10, price=True)
                records.extend([feature, price])
                row["payload"]["research_inputs"]["entities"].append({"entity_id": entity,
                    "features": {"rating": {"source_id": "prerace-feed", "record_id": feature["record_id"], "value": value}},
                    "prices": [{"source_id": "prerace-feed", "record_id": price["record_id"], "market_id": "moneyline"}]})
            positions = [1, 2, 4, 3, 5, 6] if i % 2 == 0 else [6, 5, 3, 4, 2, 1]
            row["payload"]["winner"] = {"positions": dict(zip(map(str, range(1, 7)), positions)), "withdrawn": []}
        if different_field:
            extra = source_record(3, "7", datetime.fromisoformat(rows[3]["event_at"]), 80)
            price = source_record(3, "7", datetime.fromisoformat(rows[3]["event_at"]), 3.0, price=True)
            records.extend([extra, price])
            rows[3]["payload"]["research_inputs"]["entities"].append({"entity_id": "7",
                "features": {"rating": {"source_id": "prerace-feed", "record_id": extra["record_id"], "value": 80}},
                "prices": [{"source_id": "prerace-feed", "record_id": price["record_id"], "market_id": "moneyline"}]})
            rows[3]["payload"]["winner"]["positions"]["7"] = 7
        if distinct_ids:
            for i, row in enumerate(rows):
                for entity in row["payload"]["research_inputs"]["entities"]:
                    entity["entity_id"] = f"race-{i}-horse-{entity['entity_id']}"
                positions = row["payload"]["winner"]["positions"]
                row["payload"]["winner"]["positions"] = {f"race-{i}-horse-{k}": v for k, v in positions.items()}
            for record in records:
                i = record["event_id"].split("-")[-1]
                record["entity_id"] = f"race-{i}-horse-{record['entity_id']}"
        if missing_finish: del rows[-1]["payload"]["winner"]["positions"]["6"]

    spec, inputs = fixture_inputs(tmp_path, amend, domain=domain)
    evidence = SafetyEvidence(inputs["protocol_path"], postflight_path, inputs["source_paths"])
    return spec, inputs, evidence


@pytest.mark.parametrize("domain", [Domain.AU, Domain.HKJC])
def test_actual_harness_defaults_to_canonical_measurement_and_keeps_labels_separate(tmp_path, domain):
    spec, inputs, evidence = harness_inputs(tmp_path, domain)
    seen = []

    def scorer(case, components):
        assert "winner" not in case and "split" not in case
        assert all(e["prices"] == {} and set(e["features"]) == {"rating"} for e in case["entities"])
        assert all(r["inputs"]["event_id"] != case["event_id"] for r in case["training_rows"])
        seen.append(case["event_id"])
        return [{"entity_id": e["entity_id"], "score": e["features"]["rating"] + len(components)}
                for e in case["entities"]]

    output = tmp_path / "output"
    sidecar = run_research_harness(spec, dataset_snapshot=inputs["dataset_snapshot"],
        registry=inputs["registry"], evidence=evidence, role="candidate", scorer=scorer, output_dir=output)
    metrics = json.loads((output / "metrics.json").read_text())
    assert len(metrics["observations"]) == 6
    assert all(set(r["metrics"]) == METRICS for r in metrics["observations"])
    assert len(sidecar["trace"]) == 6 and len(seen) == 12
    assert set(sidecar["control"]["label_sources"]) == {"row-2", "row-3"}
    assert set(sidecar["ablations"]) == {"empty", "a", "b", "full"}
    assert sidecar["control"]["observations"][0]["metrics"] != metrics["observations"][2]["metrics"]


def test_actual_harness_does_not_publish_partial_metrics_for_missing_finish(tmp_path):
    spec, inputs, evidence = harness_inputs(tmp_path, Domain.AU, missing_finish=True)
    output = tmp_path / "output"
    def scorer(case, components):
        return [{"entity_id": e["entity_id"], "score": e["features"]["rating"]} for e in case["entities"]]
    with pytest.raises(ResearchSafetyError):
        run_research_harness(spec, dataset_snapshot=inputs["dataset_snapshot"],
            registry=inputs["registry"], evidence=evidence, role="baseline", scorer=scorer, output_dir=output)
    assert not output.exists()


@pytest.mark.parametrize("fault", ["different_field", "distinct_ids", "missing_finish"])
def test_incompatible_canonical_labels_block_before_any_scorer_call(tmp_path, fault):
    spec, inputs, evidence = harness_inputs(tmp_path, Domain.AU, **{fault: True})
    calls = []
    def scorer(case, components):
        calls.append(case["event_id"])
        return [{"entity_id": e["entity_id"], "score": e["features"]["rating"]} for e in case["entities"]]
    output = tmp_path / "output"
    with pytest.raises(ResearchSafetyError):
        run_research_harness(spec, dataset_snapshot=inputs["dataset_snapshot"],
            registry=inputs["registry"], evidence=evidence, role="candidate", scorer=scorer, output_dir=output)
    assert calls == [], "known-invalid measurement/control must block before model execution"
    assert not output.exists()


@pytest.mark.parametrize("fault", ["domain", "ruler", "missing_metric", "duplicate_metric"])
def test_default_selection_rejects_unfrozen_measurement_contract(tmp_path, fault):
    from dataclasses import replace
    from shared_wong_choi.research_racing_measurement import racing_measurement_for
    spec, _, _ = harness_inputs(tmp_path, Domain.AU)
    if fault == "domain": spec = replace(spec, domain=Domain.TENNIS)
    elif fault == "ruler": spec = replace(spec, evaluation_ruler_id="au-v3")
    elif fault == "missing_metric": spec = replace(spec, preregistered_metrics=spec.preregistered_metrics[:-1])
    else: spec = replace(spec, preregistered_metrics=(*spec.preregistered_metrics[:-1], spec.preregistered_metrics[0]))
    with pytest.raises(ResearchSafetyError):
        racing_measurement_for(spec)


@pytest.mark.parametrize("fault", ["no_prices", "empty_prices", "blank_id", "huge_score"])
def test_measurement_requires_audited_identity_and_finite_scores(fault):
    from shared_wong_choi.research_racing_measurement import measure_racing_prediction
    predictions, label, context = completed([60, 50, 40, 30, 20, 10], [1, 2, 4, 3, 5, 6])
    if fault == "no_prices": del context["prices"]
    elif fault == "empty_prices": context["prices"] = {}
    elif fault == "blank_id": context["prices"][" "] = context["prices"].pop("6")
    else: predictions[0]["score"] = 10 ** 400
    with pytest.raises(ResearchSafetyError):
        measure_racing_prediction(predictions, label, context)


def test_native_ranking_tie_order_is_preserved_without_resorting_entities():
    from shared_wong_choi.research_racing_measurement import measure_racing_prediction
    predictions, label, context = completed([60, 50, 40, 40, 40, 10], [1, 2, 4, 5, 3, 6])
    first = measure_racing_prediction(predictions, label, context)
    reordered = predictions[:2] + [predictions[4], predictions[2], predictions[3]] + predictions[5:]
    second = measure_racing_prediction(reordered, label, context)
    assert first["gold"] is False and second["gold"] is True
    assert first["top5_pairwise_auc"] == second["top5_pairwise_auc"]
