from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".agents" / "skills"))

from shared_wong_choi.research_tennis_settlement_source import _outcomes
from tennis_wc.research_evidence import build_settlement_artifacts


EVENT = "2026-09-01"
CUTOFF = datetime(2026, 8, 31, 23, tzinfo=timezone.utc)
SETTLED = datetime(2026, 9, 2, tzinfo=timezone.utc)
RAW_RESPONSE = json.dumps(
    {"winner_name": "Player A", "loser_name": "Player B"},
    sort_keys=True,
    separators=(",", ":"),
)


def _outcome(**changes: object) -> dict:
    value = {
        "prediction_id": 101,
        "match_id": 501,
        "match_date": EVENT,
        "prediction_created_at": "2026-08-31T22:55:00+00:00",
        "player_a_id": 11,
        "player_b_id": 22,
        "player_a_name": "Player A",
        "player_b_name": "Player B",
        "selection_player_id": 11,
        "model_probability": 0.62,
        "no_vig_market_probability": 0.54,
        "winner_player_id": 11,
        "result_source_provider": "tennismylife",
        "result_raw_response_id": 990,
        "result_created_at": "2026-09-01T18:00:00+00:00",
    }
    value.update(changes)
    return value


def _raw(**changes: object) -> dict:
    value = {
        "id": 990,
        "provider_name": "tennismylife",
        "response_json": RAW_RESPONSE,
        "fetched_at": "2026-09-01T17:59:00+00:00",
        "created_at": "2026-09-01T17:59:01+00:00",
    }
    value.update(changes)
    return value


def test_settlement_artifacts_pass_existing_central_consumer() -> None:
    artifacts = build_settlement_artifacts(
        event_id=EVENT,
        source_cutoff_at=CUTOFF,
        settled_at=SETTLED,
        outcomes=[_outcome()],
        raw_responses={990: _raw()},
    )
    outcome_name = f"Tennis_Settlement_Evidence_{EVENT}.json"
    raw_name = next(name for name in artifacts if name.startswith("Tennis_Settlement_Raw_"))
    payload = json.loads(artifacts[outcome_name])
    row = payload["rows"][0]
    response_sha = hashlib.sha256(RAW_RESPONSE.encode("utf-8")).hexdigest()

    assert row["result_raw_artifact"] == raw_name
    assert row["result_raw_response_sha256"] == response_sha
    assert json.loads(artifacts[raw_name])["response_json"] == RAW_RESPONSE
    verified, valid = _outcomes(
        artifacts[outcome_name],
        event_id=EVENT,
        cutoff=CUTOFF,
        settled_at=SETTLED,
        recommendation_ids={101},
        raw_artifacts={raw_name: artifacts[raw_name]},
    )
    assert (verified, valid) == (1, True)


def test_settlement_artifacts_are_deterministic() -> None:
    kwargs = {
        "event_id": EVENT,
        "source_cutoff_at": CUTOFF,
        "settled_at": SETTLED,
        "outcomes": [_outcome()],
        "raw_responses": {990: _raw()},
    }
    assert build_settlement_artifacts(**kwargs) == build_settlement_artifacts(**kwargs)


@pytest.mark.parametrize(
    ("outcome_changes", "raw_changes", "message"),
    [
        ({"winner_player_id": 22}, {}, "does not confirm winner"),
        ({}, {"provider_name": "wrong"}, "provenance mismatch"),
        ({}, {"fetched_at": "2026-08-31T22:59:59+00:00"}, "before source cutoff"),
        ({}, {"created_at": "2026-09-01T18:00:01+00:00"}, "after result"),
        ({"selection_player_id": 33}, {}, "participant"),
    ],
)
def test_unverifiable_settlement_fails_closed(
    outcome_changes: dict,
    raw_changes: dict,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        build_settlement_artifacts(
            event_id=EVENT,
            source_cutoff_at=CUTOFF,
            settled_at=SETTLED,
            outcomes=[_outcome(**outcome_changes)],
            raw_responses={990: _raw(**raw_changes)},
        )


def test_missing_raw_or_duplicate_prediction_fails_closed() -> None:
    with pytest.raises(ValueError, match="missing Tennis result raw response"):
        build_settlement_artifacts(
            event_id=EVENT,
            source_cutoff_at=CUTOFF,
            settled_at=SETTLED,
            outcomes=[_outcome()],
            raw_responses={},
        )
    with pytest.raises(ValueError, match="duplicate Tennis settlement prediction"):
        build_settlement_artifacts(
            event_id=EVENT,
            source_cutoff_at=CUTOFF,
            settled_at=SETTLED,
            outcomes=[_outcome(), _outcome()],
            raw_responses={990: _raw()},
        )
