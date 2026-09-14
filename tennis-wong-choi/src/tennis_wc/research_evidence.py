"""Create compact, immutable Stage 5 evidence from one Tennis pricing run.

The caller supplies the exact in-memory feature snapshots and pricing outputs
used by the run plus the raw API rows they reference.  This module performs no
database query, model calculation, settlement, publication or promotion.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from datetime import datetime, timezone
from typing import Mapping, Sequence


FEATURE_SCHEMA = "wong-choi-tennis-feature-evidence/v3"
SETTLEMENT_SCHEMA = "wong-choi-tennis-settlement-evidence/v2"
SETTLEMENT_RAW_SCHEMA = "wong-choi-tennis-settlement-raw-result/v1"
COMPONENTS = frozenset({
    "surface_elo_edge", "overall_elo_edge", "serve_return_edge",
    "recent_form_edge", "opponent_rank_bucket_edge", "tournament_level_edge",
    "round_performance_edge", "big_match_edge", "pressure_edge",
    "head_to_head_edge", "fatigue_edge",
})
ELO_BACKBONE_COMPONENTS = frozenset({"surface_elo_edge", "overall_elo_edge"})
ZERO_EFFECT_WARNING_COMPONENTS = COMPONENTS - ELO_BACKBONE_COMPONENTS
DECISION_PATHS = {
    "tour": ("match_context", "tour"),
    "tournament_level": ("match_context", "level"),
    "player_a_odds": ("market", "player_a_odds"),
    "player_b_odds": ("market", "player_b_odds"),
}
STATIC_COMPONENT_PATHS = {
    "surface_elo_edge": (("player_a", "surface_elo"), ("player_b", "surface_elo")),
    "overall_elo_edge": (("player_a", "overall_elo"), ("player_b", "overall_elo")),
    "serve_return_edge": (
        ("player_a", "tournament_level_stats", "hold_rate"),
        ("player_a", "tournament_level_stats", "break_rate"),
        ("player_b", "tournament_level_stats", "hold_rate"),
        ("player_b", "tournament_level_stats", "break_rate"),
    ),
    "recent_form_edge": (
        ("player_a", "opponent_rank_buckets", "TOP_100", "shrinked_win_rate"),
        ("player_b", "opponent_rank_buckets", "TOP_100", "shrinked_win_rate"),
    ),
    "tournament_level_edge": (
        ("player_a", "tournament_level_stats", "shrinked_win_rate"),
        ("player_b", "tournament_level_stats", "shrinked_win_rate"),
    ),
    "round_performance_edge": (
        ("match_context", "round"),
        ("player_a", "round_stats", "shrinked_win_rate"),
        ("player_b", "round_stats", "shrinked_win_rate"),
    ),
    "big_match_edge": (
        ("player_a", "big_match_stats", "win_rate"),
        ("player_b", "big_match_stats", "win_rate"),
    ),
    "pressure_edge": (
        ("player_a", "pressure_stats", "pressure_score"),
        ("player_b", "pressure_stats", "pressure_score"),
    ),
    "head_to_head_edge": (
        ("player_a", "head_to_head", "win_rate"),
        ("player_a", "head_to_head", "sample_size"),
        ("player_b", "head_to_head", "win_rate"),
        ("player_b", "head_to_head", "sample_size"),
    ),
    "fatigue_edge": (
        ("player_a", "fatigue", "rest_days"),
        ("player_b", "fatigue", "rest_days"),
    ),
}
SETTLEMENT_INPUT_FIELDS = {
    "prediction_id", "match_id", "match_date", "prediction_created_at",
    "player_a_id", "player_b_id", "player_a_name", "player_b_name",
    "selection_player_id", "model_probability", "no_vig_market_probability",
    "winner_player_id", "result_source_provider", "result_raw_response_id",
    "result_created_at",
}


def _encoded(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _hash(value: object) -> str:
    return hashlib.sha256(_encoded(value)).hexdigest()


def _at(value: object) -> datetime:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid Tennis evidence timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Tennis evidence timestamps must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _number(value: object) -> bool:
    return type(value) in {int, float} and math.isfinite(float(value))


def _value(snapshot: dict, path: Sequence[str]) -> object:
    current: object = snapshot
    for part in path:
        if not isinstance(current, dict) or part not in current:
            raise ValueError(f"missing Tennis feature path: {'.'.join(path)}")
        current = current[part]
    return current


def _input(
    snapshot: dict,
    path: Sequence[str],
    *,
    available_by: datetime,
) -> tuple[dict, dict]:
    point = _value(snapshot, path)
    if not isinstance(point, dict) or set(point) != {"value", "provenance"}:
        raise ValueError(f"invalid Tennis feature point: {'.'.join(path)}")
    provenance = point["provenance"]
    expected = {
        "source_provider", "source_endpoint", "source_timestamp", "calculated_at",
        "raw_response_id", "warnings",
    }
    if (
        not isinstance(provenance, dict)
        or set(provenance) != expected
        or type(provenance.get("raw_response_id")) is not int
        or provenance["raw_response_id"] <= 0
        or provenance.get("warnings") != []
        or not isinstance(provenance.get("source_provider"), str)
        or not provenance["source_provider"].strip()
        or not isinstance(provenance.get("source_endpoint"), str)
        or not provenance["source_endpoint"].strip()
    ):
        raise ValueError(f"unverified Tennis feature point: {'.'.join(path)}")
    source_at = _at(provenance["source_timestamp"])
    calculated_at = _at(provenance["calculated_at"])
    if source_at > calculated_at or calculated_at > available_by:
        raise ValueError(f"future Tennis feature point: {'.'.join(path)}")
    raw_id = provenance["raw_response_id"]
    return {
        "path": list(path),
        "value_sha256": _hash(point["value"]),
        "raw_response_ids": [raw_id],
    }, {
        "raw_response_id": raw_id,
        "source_provider": provenance["source_provider"],
        "source_endpoint": provenance["source_endpoint"],
        "fetched_at": source_at,
        "calculated_at": calculated_at,
    }


def _remember(refs: dict[int, dict], item: dict) -> None:
    raw_id = item["raw_response_id"]
    current = refs.get(raw_id)
    if current is None:
        refs[raw_id] = item
        return
    if any(current[key] != item[key] for key in (
        "source_provider", "source_endpoint", "fetched_at",
    )):
        raise ValueError("one Tennis raw response has conflicting provenance")
    current["calculated_at"] = min(current["calculated_at"], item["calculated_at"])


def _rank_bucket(value: object) -> str:
    if type(value) is not int or value <= 0:
        raise ValueError("verified current rank required for rank-bucket component")
    if value <= 10:
        return "TOP_10"
    if value <= 25:
        return "TOP_25"
    if value <= 50:
        return "TOP_50"
    if value <= 100:
        return "TOP_100"
    if value <= 200:
        return "RANK_101_200"
    return "RANK_201_PLUS"


def _normalised_name(value: object) -> str:
    if not isinstance(value, str):
        return ""
    folded = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return " ".join(re.findall(r"[a-z0-9]+", folded.casefold()))


def _raw_confirms_winner(response: object, outcome: Mapping[str, object]) -> bool:
    if isinstance(response, dict) and isinstance(response.get("parsed_results"), list):
        candidates = response["parsed_results"]
    else:
        candidates = response if isinstance(response, list) else [response]
    expected_pair = {
        _normalised_name(outcome["player_a_name"]),
        _normalised_name(outcome["player_b_name"]),
    }
    winner_name = (
        outcome["player_a_name"]
        if outcome["winner_player_id"] == outcome["player_a_id"]
        else outcome["player_b_name"]
    )
    expected_winner = _normalised_name(winner_name)
    found = confirmed = conflicted = False
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        pairs = []
        if (
            isinstance(candidate.get("winner_name"), str)
            and isinstance(candidate.get("loser_name"), str)
        ):
            pairs.append((
                candidate["winner_name"], candidate["loser_name"],
                candidate["winner_name"],
            ))
        if (
            isinstance(candidate.get("player_name"), str)
            and isinstance(candidate.get("opponent_name"), str)
            and type(candidate.get("won")) in {bool, int}
            and candidate["won"] in {0, 1}
        ):
            pairs.append((
                candidate["player_name"], candidate["opponent_name"],
                candidate["player_name"] if candidate["won"] else candidate["opponent_name"],
            ))
        for left, right, winner in pairs:
            if {_normalised_name(left), _normalised_name(right)} != expected_pair:
                continue
            found = True
            if _normalised_name(winner) == expected_winner:
                confirmed = True
            else:
                conflicted = True
    return found and confirmed and not conflicted


def _component_paths(name: str, snapshot: dict) -> tuple[tuple[str, ...], ...]:
    if name != "opponent_rank_bucket_edge":
        paths = STATIC_COMPONENT_PATHS.get(name)
        if paths is None:
            raise ValueError(f"unknown Tennis component: {name}")
        return paths
    rank_a = _value(snapshot, ("player_a", "current_rank"))
    rank_b = _value(snapshot, ("player_b", "current_rank"))
    if not isinstance(rank_a, dict) or not isinstance(rank_b, dict):
        raise ValueError("invalid Tennis current-rank point")
    bucket_for_a = _rank_bucket(rank_b.get("value"))
    bucket_for_b = _rank_bucket(rank_a.get("value"))
    return (
        ("player_a", "current_rank"),
        ("player_b", "current_rank"),
        ("player_a", "opponent_rank_buckets", bucket_for_a, "shrinked_win_rate"),
        ("player_b", "opponent_rank_buckets", bucket_for_b, "shrinked_win_rate"),
    )


def _components(
    snapshot: dict,
    pricing: dict,
    *,
    available_by: datetime,
) -> tuple[list[dict], dict[int, dict]]:
    model = pricing.get("model")
    raw_components = model.get("components") if isinstance(model, dict) else None
    if not isinstance(raw_components, list):
        raise ValueError("Tennis pricing components missing")
    output, names, raw_refs = [], set(), {}
    required = {"name", "probability", "weight", "active", "reason", "warnings"}
    for component in raw_components:
        if (
            not isinstance(component, dict)
            or set(component) != required
            or component.get("name") in names
            or component.get("name") not in COMPONENTS
            or type(component.get("active")) is not bool
            or not _number(component.get("probability"))
            or not _number(component.get("weight"))
            or not isinstance(component.get("reason"), str)
            or not component["reason"].strip()
            or not isinstance(component.get("warnings"), list)
            or any(not isinstance(item, str) or not item for item in component["warnings"])
            or len(component["warnings"]) != len(set(component["warnings"]))
        ):
            raise ValueError("invalid or unknown Tennis pricing component")
        names.add(component["name"])
        inputs = []
        projected_active = component["active"]
        if projected_active and component["warnings"]:
            if (
                component["name"] in ZERO_EFFECT_WARNING_COMPONENTS
                and float(component["probability"]) == 0.5
            ):
                projected_active = False
            else:
                raise ValueError("active Tennis component has unresolved warnings")
        if projected_active:
            for path in _component_paths(component["name"], snapshot):
                item, raw_ref = _input(snapshot, path, available_by=available_by)
                inputs.append(item)
                _remember(raw_refs, raw_ref)
            if not inputs:
                raise ValueError("active Tennis component has no inputs")
        elif not component["warnings"]:
            raise ValueError("inactive Tennis component needs an explicit warning")
        output.append({
            "name": component["name"],
            "active": projected_active,
            "warnings": list(component["warnings"]),
            "inputs": inputs,
        })
    if names != COMPONENTS or not any(item["active"] for item in output):
        raise ValueError("incomplete Tennis component set")
    return output, raw_refs


def _raw_artifacts(
    *,
    event_id: str,
    raw_refs: Mapping[int, Mapping[str, object]],
    raw_responses: Mapping[int, Mapping[str, object]],
    cutoff: datetime,
) -> tuple[list[dict], dict[str, bytes]]:
    metadata, artifacts = [], {}
    for raw_id in sorted(raw_refs):
        expected = raw_refs[raw_id]
        row = raw_responses.get(raw_id)
        if not isinstance(row, Mapping):
            raise ValueError(f"missing Tennis raw response: {raw_id}")
        try:
            stored_id = row["id"]
            provider = row["provider_name"]
            endpoint = row["endpoint"]
            response_json = row["response_json"]
            fetched_at = _at(row["fetched_at"])
            created_at = _at(row["created_at"])
        except KeyError as exc:
            raise ValueError("incomplete Tennis raw response") from exc
        if (
            stored_id != raw_id
            or not isinstance(provider, str)
            or not provider.strip()
            or not isinstance(endpoint, str)
            or not endpoint.strip()
            or not isinstance(response_json, str)
            or not response_json.strip()
            or fetched_at > created_at
            or created_at > cutoff
            or provider != expected["source_provider"]
            or endpoint != expected["source_endpoint"]
            or fetched_at != expected["fetched_at"]
            or created_at > expected["calculated_at"]
        ):
            raise ValueError("invalid or future Tennis raw response")
        try:
            response = json.loads(response_json)
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid Tennis raw response JSON") from exc
        response_sha256 = _hash(response)
        name = f"Tennis_Raw_Evidence_{event_id}_{raw_id}_{response_sha256[:12]}.json"
        metadata.append({
            "raw_response_id": raw_id,
            "source_provider": provider,
            "source_endpoint": endpoint,
            "fetched_at": fetched_at.isoformat(),
            "created_at": created_at.isoformat(),
            "artifact_name": name,
            "response_sha256": response_sha256,
        })
        artifacts[name] = _encoded(response) + b"\n"
    return metadata, artifacts


def build_prediction_artifacts(
    *,
    event_id: str,
    captured_at: datetime,
    observations: Sequence[Mapping[str, object]],
    raw_responses: Mapping[int, Mapping[str, object]],
) -> dict[str, bytes]:
    """Build feature projection plus raw-source files without side effects."""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", event_id) is None:
        raise ValueError("canonical Tennis event date required")
    cutoff = _at(captured_at)
    if not isinstance(observations, Sequence) or isinstance(observations, (str, bytes)):
        raise ValueError("Tennis observations must be a sequence")
    rows, seen, all_raw_refs = [], set(), {}
    for observation in sorted(observations, key=lambda item: int(item.get("prediction_id", 0))):
        if not isinstance(observation, Mapping) or set(observation) != {
            "prediction_id", "prediction_created_at", "snapshot", "pricing"
        }:
            raise ValueError("invalid Tennis observation contract")
        prediction_id = observation["prediction_id"]
        snapshot, pricing = observation["snapshot"], observation["pricing"]
        if (
            type(prediction_id) is not int
            or prediction_id <= 0
            or prediction_id in seen
            or not isinstance(snapshot, dict)
            or not isinstance(pricing, dict)
        ):
            raise ValueError("invalid Tennis observation identity")
        prediction_at = _at(observation["prediction_created_at"])
        if prediction_at > cutoff:
            raise ValueError("Tennis prediction is after snapshot cutoff")
        selection = pricing.get("selection_player_id")
        numeric = ("model_probability", "no_vig_market_probability", "current_market_odds", "edge")
        if (
            type(selection) is not int
            or selection <= 0
            or any(not _number(pricing.get(name)) for name in numeric)
            or not 0 < pricing["model_probability"] < 1
            or not 0 < pricing["no_vig_market_probability"] < 1
            or pricing["current_market_odds"] <= 1
        ):
            raise ValueError("complete priced prediction required for Tennis evidence")
        participants = {
            _value(snapshot, ("player_a", "id", "value")),
            _value(snapshot, ("player_b", "id", "value")),
        }
        if selection not in participants or len(participants) != 2:
            raise ValueError("Tennis selection is not an exact participant")
        components, component_raw_refs = _components(
            snapshot, pricing, available_by=prediction_at,
        )
        decision_inputs, decision_raw_refs = {}, {}
        for name, path in DECISION_PATHS.items():
            item, raw_ref = _input(snapshot, path, available_by=prediction_at)
            decision_inputs[name] = item
            _remember(decision_raw_refs, raw_ref)
        raw_refs = dict(component_raw_refs)
        for raw_ref in decision_raw_refs.values():
            _remember(raw_refs, dict(raw_ref))
        for raw_ref in raw_refs.values():
            _remember(all_raw_refs, dict(raw_ref))
        rows.append({
            "prediction_id": prediction_id,
            "match_id": _value(snapshot, ("match_id", "value")),
            "feature_set_version": snapshot.get("feature_set_version"),
            "prediction_created_at": prediction_at.isoformat(),
            "selection_player_id": selection,
            "model_probability": pricing["model_probability"],
            "no_vig_market_probability": pricing["no_vig_market_probability"],
            "current_market_odds": pricing["current_market_odds"],
            "edge": pricing["edge"],
            "feature_snapshot": snapshot,
            "feature_snapshot_sha256": _hash(snapshot),
            "components": components,
            "decision_inputs": decision_inputs,
            "raw_input_ids": sorted(raw_refs),
        })
        seen.add(prediction_id)
    if not rows:
        raise ValueError("at least one complete Tennis prediction is required")
    raw_inputs, artifacts = _raw_artifacts(
        event_id=event_id,
        raw_refs=all_raw_refs,
        raw_responses=raw_responses,
        cutoff=cutoff,
    )
    feature_name = f"Tennis_Feature_Evidence_{event_id}.json"
    payload = {
        "schema_version": FEATURE_SCHEMA,
        "event_id": event_id,
        "generated_at": cutoff.isoformat(),
        "raw_inputs": raw_inputs,
        "rows": rows,
    }
    artifacts[feature_name] = _encoded(payload) + b"\n"
    return dict(sorted(artifacts.items()))


def build_settlement_artifacts(
    *,
    event_id: str,
    source_cutoff_at: datetime,
    settled_at: datetime,
    outcomes: Sequence[Mapping[str, object]],
    raw_responses: Mapping[int, Mapping[str, object]],
) -> dict[str, bytes]:
    """Build hash-pinned Tennis result evidence without database or file I/O."""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", event_id) is None:
        raise ValueError("canonical Tennis settlement event date required")
    cutoff, settlement_time = _at(source_cutoff_at), _at(settled_at)
    if cutoff > settlement_time:
        raise ValueError("Tennis settlement precedes source cutoff")
    if not isinstance(outcomes, Sequence) or isinstance(outcomes, (str, bytes)):
        raise ValueError("Tennis outcomes must be a sequence")

    rows, artifacts, seen = [], {}, set()
    for outcome in sorted(outcomes, key=lambda item: int(item.get("prediction_id", 0))):
        if not isinstance(outcome, Mapping) or set(outcome) != SETTLEMENT_INPUT_FIELDS:
            raise ValueError("invalid Tennis settlement outcome contract")
        prediction_id = outcome["prediction_id"]
        if type(prediction_id) is not int or prediction_id <= 0:
            raise ValueError("invalid Tennis settlement prediction identity")
        if prediction_id in seen:
            raise ValueError("duplicate Tennis settlement prediction")
        prediction_at = _at(outcome["prediction_created_at"])
        result_at = _at(outcome["result_created_at"])
        participant_ids = {outcome["player_a_id"], outcome["player_b_id"]}
        if (
            outcome["match_date"] != event_id
            or prediction_at > cutoff
            or result_at > settlement_time
            or any(type(outcome[name]) is not int or outcome[name] <= 0 for name in (
                "match_id", "player_a_id", "player_b_id", "selection_player_id",
                "winner_player_id", "result_raw_response_id",
            ))
            or len(participant_ids) != 2
            or outcome["selection_player_id"] not in participant_ids
            or outcome["winner_player_id"] not in participant_ids
        ):
            raise ValueError("invalid Tennis settlement participant or chronology")
        if (
            not _normalised_name(outcome["player_a_name"])
            or not _normalised_name(outcome["player_b_name"])
            or _normalised_name(outcome["player_a_name"])
            == _normalised_name(outcome["player_b_name"])
            or not isinstance(outcome["result_source_provider"], str)
            or not outcome["result_source_provider"].strip()
            or any(
                not _number(outcome[name]) or not 0 < outcome[name] < 1
                for name in ("model_probability", "no_vig_market_probability")
            )
        ):
            raise ValueError("invalid Tennis settlement outcome values")

        raw_id = outcome["result_raw_response_id"]
        raw = raw_responses.get(raw_id)
        if not isinstance(raw, Mapping):
            raise ValueError(f"missing Tennis result raw response: {raw_id}")
        try:
            response_json = raw["response_json"]
            fetched_at, raw_created_at = _at(raw["fetched_at"]), _at(raw["created_at"])
            response = json.loads(response_json)
        except (KeyError, TypeError, ValueError, UnicodeError) as exc:
            raise ValueError("invalid Tennis result raw response") from exc
        if (
            raw.get("id") != raw_id
            or raw.get("provider_name") != outcome["result_source_provider"]
        ):
            raise ValueError("Tennis result raw provenance mismatch")
        if not isinstance(response_json, str) or not response_json.strip():
            raise ValueError("invalid Tennis result raw response")
        if fetched_at < cutoff:
            raise ValueError("Tennis result raw response is before source cutoff")
        if fetched_at > raw_created_at or raw_created_at > result_at:
            raise ValueError("Tennis result raw response is after result")
        if not _raw_confirms_winner(response, outcome):
            raise ValueError("Tennis result raw response does not confirm winner")

        response_sha = hashlib.sha256(response_json.encode("utf-8")).hexdigest()
        raw_name = (
            f"Tennis_Settlement_Raw_{event_id}_{raw_id}_{response_sha[:12]}.json"
        )
        raw_payload = {
            "schema_version": SETTLEMENT_RAW_SCHEMA,
            "event_id": event_id,
            "raw_response_id": raw_id,
            "source_provider": outcome["result_source_provider"],
            "fetched_at": fetched_at.isoformat(),
            "created_at": raw_created_at.isoformat(),
            "response_sha256": response_sha,
            "response_json": response_json,
        }
        raw_bytes = _encoded(raw_payload) + b"\n"
        previous = artifacts.get(raw_name)
        if previous is not None and previous != raw_bytes:
            raise ValueError("conflicting Tennis result raw response")
        artifacts[raw_name] = raw_bytes
        rows.append({
            "prediction_id": prediction_id,
            "match_id": outcome["match_id"],
            "match_date": outcome["match_date"],
            "prediction_created_at": prediction_at.isoformat(),
            "player_a_id": outcome["player_a_id"],
            "player_b_id": outcome["player_b_id"],
            "player_a_name": outcome["player_a_name"],
            "player_b_name": outcome["player_b_name"],
            "selection_player_id": outcome["selection_player_id"],
            "model_probability": outcome["model_probability"],
            "no_vig_market_probability": outcome["no_vig_market_probability"],
            "winner_player_id": outcome["winner_player_id"],
            "result_source_provider": outcome["result_source_provider"],
            "result_raw_response_id": raw_id,
            "result_raw_artifact": raw_name,
            "result_raw_response_sha256": response_sha,
            "result_raw_fetched_at": fetched_at.isoformat(),
            "result_raw_created_at": raw_created_at.isoformat(),
            "result_created_at": result_at.isoformat(),
        })
        seen.add(prediction_id)
    if not rows:
        raise ValueError("at least one complete Tennis settlement is required")

    outcome_name = f"Tennis_Settlement_Evidence_{event_id}.json"
    artifacts[outcome_name] = _encoded({
        "schema_version": SETTLEMENT_SCHEMA,
        "event_id": event_id,
        "generated_at": settlement_time.isoformat(),
        "rows": rows,
    }) + b"\n"
    return dict(sorted(artifacts.items()))
