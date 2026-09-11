import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared_wong_choi.contracts import Domain
from shared_wong_choi.domain_evidence import record_prediction_decision
from shared_wong_choi.evidence import DecisionState, EvidenceRecord, EvidenceStore, RecordKind
from shared_wong_choi.research_index import _hash
from shared_wong_choi.research_nba_feature_provenance import (
    inspect_nba_feature_provenance,
    verify_nba_feature_provenance_report,
)


EVENT = "2026-10-21"
TAG = "BOS_LAL"
CUTOFF = "2026-10-21T08:00:00+00:00"
AS_OF = datetime(2026, 10, 21, 9, tzinfo=timezone.utc)
FAMILIES = ("market", "player_form", "team_context", "schedule_context", "injury_context")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture(tmp_path, mode="valid"):
    evidence = tmp_path / "evidence"
    store = EvidenceStore(evidence)
    store.append(EvidenceRecord(
        "wc:nba:model-release:feature", RecordKind.MODEL_RELEASE, Domain.NBA,
        "2026-08-29T00:00:00+00:00",
        {"release_stage": "shadow", "code_commit": "a" * 40,
         "evaluation_contract_version": "nba-v1"},
    ))
    snapshot = tmp_path / "archive" / EVENT / "_prediction_snapshots" / "feature"
    snapshot.mkdir(parents=True)
    odds = snapshot / f"Sportsbet_Odds_{TAG}.json"
    odds.write_text(json.dumps({"matchup": TAG, "markets": []}) + "\n")
    game = snapshot / f"nba_game_data_{TAG}.json"
    game.write_text(json.dumps({"game": TAG, "players": [], "teams": []}) + "\n")
    report = snapshot / f"Game_{TAG}_Full_Analysis.md"
    report.write_text("# NBA analysis\n", encoding="utf-8")
    projection = snapshot / f"NBA_Feature_Evidence_{EVENT}.json"

    def source(path, field):
        return {"artifact": path.name, "sha256": digest(path),
                "available_at": CUTOFF, "field": field}

    families = {
        "market": {"status": "available", "derivation": "sportsbet.market/v1",
                   "sources": [source(odds, "markets")]},
        "player_form": {"status": "available", "derivation": "nba.player_l10/v1",
                        "sources": [source(game, "players")]},
        "team_context": {"status": "available", "derivation": "nba.team_context/v1",
                         "sources": [source(game, "teams")]},
        "schedule_context": {"status": "available", "derivation": "nba.schedule/v1",
                             "sources": [source(game, "game")]},
        "injury_context": {"status": "unavailable", "reason": "source_not_configured",
                           "sources": []},
    }
    if mode == "family":
        families.pop("schedule_context")
    elif mode == "future":
        families["market"]["sources"][0]["available_at"] = "2026-10-21T08:00:01+00:00"
    elif mode == "digest":
        families["market"]["sources"][0]["sha256"] = "f" * 64
    elif mode == "output":
        families["market"]["sources"][0].update(
            artifact=report.name, sha256=digest(report), field="analysis")
    elif mode == "fake_injury":
        families["injury_context"] = {"status": "available", "derivation": "nba.injury/v1",
                                      "sources": []}
    rows = [{"game_tag": "NYK_MIA" if mode == "wrong_tag" else TAG,
             "feature_contract_id": "nba-pregame-feature-v1", "families": families}]
    projection.write_text(json.dumps({
        "schema_version": "wong-choi-nba-feature-evidence/v1",
        "event_id": EVENT, "generated_at": CUTOFF, "rows": rows,
    }, sort_keys=True) + "\n")
    files = [odds, game, report, projection]
    manifest = snapshot / "manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": "wong-choi-prediction-snapshot/v1", "append_only": True,
        "domain": "nba", "event_id": EVENT, "created_at": CUTOFF,
        "files": [{"name": path.name, "bytes": path.stat().st_size, "sha256": digest(path)}
                  for path in files],
    }) + "\n")
    record_prediction_decision(
        domain=Domain.NBA, event_id=EVENT, snapshot=snapshot, evidence_root=evidence,
        decision_state=DecisionState.SHADOW,
        recommendations=[{"event_id": TAG, "status": "analysis_snapshot_available"}],
        model_release_id="wc:nba:model-release:feature", created_at=AS_OF,
        source_cutoff_at=CUTOFF,
    )
    return evidence, snapshot


def inspect(evidence):
    return inspect_nba_feature_provenance(root=evidence, as_of=AS_OF)


def test_nba_five_family_projection_verifies_inputs_but_not_sample(tmp_path):
    report = inspect(fixture(tmp_path)[0])
    assert (report["games"], report["verified_games"],
            report["available_families"], report["unavailable_families"]) == (1, 1, 4, 1)
    assert report["feature_availability_verified"] is True
    assert report["verified_monitoring_samples"] is None
    assert report["model_promotion_allowed"] is False


@pytest.mark.parametrize(
    ("mode", "blocker"),
    [("wrong_tag", "game_tag_set_mismatch"),
     ("family", "feature_family_contract_incomplete"),
     ("future", "feature_source_after_cutoff"),
     ("digest", "feature_source_digest_mismatch"),
     ("output", "feature_source_is_prediction_output"),
     ("fake_injury", "feature_family_contract_invalid")],
)
def test_invalid_nba_feature_projection_is_blocked(tmp_path, mode, blocker):
    report = inspect(fixture(tmp_path, mode)[0])
    assert blocker in report["records"][0]["blockers"]
    assert report["verified_games"] == 0


def test_mutated_nba_projection_loses_bundle_authority(tmp_path):
    evidence, snapshot = fixture(tmp_path)
    (snapshot / f"NBA_Feature_Evidence_{EVENT}.json").write_text("{}\n")
    report = inspect(evidence)
    assert report["records"][0]["blockers"] == ["prediction_bundle_unverified"]


def test_nba_verifier_rejects_forged_sample_authority(tmp_path):
    evidence = fixture(tmp_path)[0]
    report = inspect(evidence)
    report["verified_monitoring_samples"] = 1
    report["content_hash"] = _hash({key: value for key, value in report.items()
                                    if key != "content_hash"})
    with pytest.raises((ValueError, RuntimeError)):
        verify_nba_feature_provenance_report(report, root=evidence, as_of=AS_OF,
                                             relocation_roots=())


def test_no_nba_prediction_is_not_feature_ready(tmp_path):
    evidence = tmp_path / "evidence"
    EvidenceStore(evidence).append(EvidenceRecord(
        "wc:nba:model-release:feature", RecordKind.MODEL_RELEASE, Domain.NBA,
        "2026-08-29T00:00:00+00:00",
        {"release_stage": "shadow", "code_commit": "a" * 40,
         "evaluation_contract_version": "nba-v1"},
    ))
    report = inspect(evidence)
    assert report["records_seen"] == 0
    assert report["feature_availability_verified"] is False
