from __future__ import annotations

import copy
import gzip
import json

import pytest

from tennis_wc import research_diagnostics as diagnostics
from test_stage5_research_evidence import CUTOFF, EVENT, _observation, _raws


def build(observations=None, predictions=None, raws=None):
    return diagnostics.build_research_diagnostics(
        event_id=EVENT, captured_at=CUTOFF,
        predictions=[{"id": 101}] if predictions is None else predictions,
        observations=[_observation()] if observations is None else observations,
        raw_responses=_raws() if raws is None else raws, reason="unresolved warnings",
    )


def test_journal_preserves_effectful_warning_exact_inputs_and_original_raw_text():
    obs = _observation()
    obs["pricing"]["model"]["components"][0]["warnings"] = ["missing_surface"]
    originals = copy.deepcopy((obs, _raws()))
    files, status = build([obs])
    payload = json.loads(gzip.decompress(next(iter(files.values()))))
    assert payload["observations"] == [obs]
    assert payload["raw_responses"] == list(_raws().values())
    assert (obs, _raws()) == originals
    assert status["observation_coverage_complete"] is True
    assert payload["feature_availability_verified"] is False
    assert status["model_promotion_allowed"] is False
    assert not any(name.startswith("Tennis_Feature_Evidence_") for name in files)
    assert build([obs])[0] == files


def test_missing_and_duplicate_observations_remain_visible_and_incomplete():
    obs = _observation()
    files, status = build([obs, obs], [{"id": 101}, {"id": 202}])
    assert status["observation_coverage_complete"] is False
    assert len(json.loads(gzip.decompress(next(iter(files.values()))))["observations"]) == 2
    assert build([], [])[1]["observation_coverage_complete"] is False


def test_raw_metadata_allowlist_never_copies_request_headers_or_settings():
    raw = _raws()
    raw[901]["request_headers"] = {"Authorization": "do-not-copy"}
    files, _ = build(raws=raw)
    decoded = gzip.decompress(next(iter(files.values())))
    assert b"do-not-copy" not in decoded
    assert b"request_headers" not in decoded


@pytest.mark.parametrize("limit", ["MAX_UNCOMPRESSED_BYTES", "MAX_COMPRESSED_BYTES"])
def test_budget_excess_rejects_entire_journal_instead_of_truncating(limit, monkeypatch):
    monkeypatch.setattr(diagnostics, limit, 1)
    with pytest.raises(ValueError, match="byte budget exceeded"):
        build()


def test_nonfinite_observation_is_not_serialized_as_nonstandard_json():
    obs = _observation()
    obs["pricing"]["edge"] = float("nan")
    with pytest.raises(ValueError):
        build([obs])
