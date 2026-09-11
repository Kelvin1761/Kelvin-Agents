import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared_wong_choi.contracts import Domain
from shared_wong_choi.domain_evidence import record_prediction_decision, record_settlement_for_event
from shared_wong_choi.evidence import DecisionState, EvidenceRecord, EvidenceStore, RecordKind
from shared_wong_choi.research_index import _hash
from shared_wong_choi.research_nba_settlement_source import (
    inspect_nba_settlement_candidates,
    verify_nba_settlement_candidate_report,
)


EVENT = "2026-10-21"
US_DATE = "2026-10-20"
NOW = datetime(2026, 10, 21, 5, tzinfo=timezone.utc)
END = NOW + timedelta(hours=4)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prediction_fixture(tmp_path, *, research_projection=False):
    evidence = tmp_path / "evidence"
    store = EvidenceStore(evidence)
    store.append(EvidenceRecord(
        "wc:nba:model-release:test", RecordKind.MODEL_RELEASE, Domain.NBA,
        "2026-10-01T00:00:00+00:00",
        {"release_stage": "shadow", "code_commit": "a" * 40,
         "evaluation_contract_version": "nba-v1"},
    ))
    day = tmp_path / "archive" / f"{EVENT} NBA Analysis"
    snapshot = day / "_prediction_snapshots" / "20261021T000000Z-test"
    snapshot.mkdir(parents=True)
    report = snapshot / "Game_BOS_NYK_Full_Analysis.md"
    report.write_text("# immutable pre-game recommendation\n", encoding="utf-8")
    files = [report]
    recommendations = None
    if research_projection:
        tag = "BOS_NYK"
        odds = snapshot / f"Sportsbet_Odds_{tag}.json"
        odds.write_text(json.dumps({"matchup": tag, "markets": []}) + "\n")
        game = snapshot / f"nba_game_data_{tag}.json"
        game.write_text(json.dumps({"game": tag, "players": [], "teams": []}) + "\n")
        feature = snapshot / f"NBA_Feature_Evidence_{EVENT}.json"
        source = lambda path, field: {
            "artifact": path.name, "sha256": digest(path),
            "available_at": "2026-10-21T00:00:00+00:00", "field": field,
        }
        feature.write_text(json.dumps({
            "schema_version": "wong-choi-nba-feature-evidence/v1",
            "event_id": EVENT,
            "generated_at": "2026-10-21T00:00:00+00:00",
            "rows": [{
                "game_tag": tag,
                "feature_contract_id": "nba-pregame-feature-v1",
                "families": {
                    "market": {"status": "available", "derivation": "market/v1",
                               "sources": [source(odds, "markets")]},
                    "player_form": {"status": "available", "derivation": "player/v1",
                                    "sources": [source(game, "players")]},
                    "team_context": {"status": "available", "derivation": "team/v1",
                                     "sources": [source(game, "teams")]},
                    "schedule_context": {"status": "available", "derivation": "schedule/v1",
                                         "sources": [source(game, "game")]},
                    "injury_context": {"status": "unavailable",
                                       "reason": "source_not_configured", "sources": []},
                },
            }],
        }, sort_keys=True) + "\n")
        files.extend([odds, game, feature])
        if research_projection != "missing":
            projection = snapshot / f"NBA_Recommendation_Evidence_{EVENT}.json"
            projection.write_text(json.dumps({
                "schema_version": "wong-choi-nba-recommendation-evidence/v1",
                "event_id": EVENT,
                "generated_at": "2026-10-21T00:00:00+00:00",
                "recommendations": [{
                    "recommendation_id": "bos-nyk-player-a-points-20-over",
                    "game_tag": tag, "player": "Player A", "stat": "points",
                    "line": 20.0, "side": "over",
                }],
            }, sort_keys=True) + "\n")
            files.append(projection)
        recommendations = [{"event_id": tag, "status": "analysis_snapshot_available"}]
    manifest = snapshot / "manifest.json"
    manifest.write_text(json.dumps({
        "append_only": True,
        "created_at": "2026-10-21T00:00:00+00:00",
        "domain": "nba",
        "event_id": EVENT,
        "files": [{"name": path.name, "bytes": path.stat().st_size,
                   "sha256": digest(path)} for path in files],
    }) + "\n", encoding="utf-8")
    record_prediction_decision(
        domain=Domain.NBA, event_id=EVENT, snapshot=snapshot, evidence_root=evidence,
        decision_state=DecisionState.SHADOW,
        recommendations=recommendations,
        model_release_id="wc:nba:model-release:test", created_at=NOW,
        source_cutoff_at="2026-10-21T00:00:00+00:00",
    )
    return evidence, day, snapshot


def result_artifacts(day, *, fault=None):
    results = day / f"Results_Brief_{US_DATE}.json"
    results.write_text(json.dumps({
        "_version": "RESULTS_BRIEF_V1", "date": US_DATE, "total_games": 1,
        "games": [{"home": {"team": "NYK"}, "away": {"team": "BOS"},
                   "final_score": "BOS 101 - NYK 99"}],
    }) + "\n", encoding="utf-8")
    verification = day / f"Props_Verification_{US_DATE}.json"
    unverified = 1 if fault == "unverified" else 0
    line = 21.0 if fault == "different_line" else 20.0
    actual = 22.0 if fault == "different_line" else 21.0
    legs = [{"player": "Player A", "stat": "points", "line": line,
             "actual": None if unverified else actual,
             "margin": None if unverified else actual - line,
             "cleared": None if unverified else True,
             "status": "PLAYER_NOT_FOUND" if unverified else "HIT"}]
    if fault == "extra":
        legs.append({**legs[0], "player": "Player B"})
    verification.write_text(json.dumps({
        "_version": "PROPS_VERIFICATION_V1",
        "summary": {"total_legs": len(legs), "hits": 0 if unverified else len(legs),
                    "misses": 0, "voids": 0, "unverified": unverified,
                    "hit_rate_pct": 0 if unverified else 100.0,
                    "by_combo": {}, "by_stat": {}},
        "legs": legs,
    }) + "\n", encoding="utf-8")
    summary = day / f"Reflector_Run_Summary_{EVENT}.json"
    summary.write_text(json.dumps({
        "analysis_date": EVENT, "us_game_date": US_DATE,
        "target_dir": f"/old/live/{EVENT} NBA Analysis",
        "db_path": "/old/live/nba_reflector.db",
        "results_path": f"/old/live/{results.name}",
        "verification_path": f"/old/live/{verification.name}",
        "pbp_path": None, "rows_recorded": 1,
        "training_snapshot": f"/old/live/Reflector_Training_Snapshot_{EVENT}.csv",
        "ml_summary": None,
    }) + "\n", encoding="utf-8")
    return results, verification, summary


def settled_fixture(tmp_path, *, evidence_verification=True, fault=None,
                    research_projection=False):
    evidence, day, snapshot = prediction_fixture(
        tmp_path, research_projection=research_projection,
    )
    results, verification, summary = result_artifacts(day, fault=fault)
    artifacts = [results, summary]
    if evidence_verification:
        artifacts.append(verification)
    record_settlement_for_event(
        domain=Domain.NBA, event_id=EVENT, evidence_root=evidence,
        summary={"archive_status": "archived", "archive_path": str(day)},
        artifacts=artifacts, settled_at=NOW + timedelta(hours=2), required=True,
    )
    return evidence, day, snapshot, verification


def inspect(evidence):
    return inspect_nba_settlement_candidates(root=evidence, as_of=END)


def test_hash_pinned_results_summary_and_complete_verification_prove_labels_only(tmp_path):
    report = inspect(settled_fixture(tmp_path)[0])
    candidate = report["candidates"][0]
    assert (report["settlements_seen"], report["label_verified_settlements"],
            report["verified_legs"]) == (1, 1, 1)
    assert candidate["blockers"] == ["feature_availability_unverified"]
    assert candidate["label_source_verified"] is True
    assert report["verified_monitoring_samples"] is None
    assert report["model_promotion_allowed"] is False


def test_adjacent_verification_not_in_settlement_is_not_evidence(tmp_path):
    report = inspect(settled_fixture(tmp_path, evidence_verification=False)[0])
    candidate = report["candidates"][0]
    assert candidate["adjacent_unreferenced_verification"] is True
    assert candidate["blockers"] == [
        "verification_artifact_not_evidenced", "feature_availability_unverified",
    ]
    assert report["label_verified_settlements"] == 0


def test_unverified_legs_make_result_chain_incomplete(tmp_path):
    report = inspect(settled_fixture(tmp_path, fault="unverified")[0])
    assert report["candidates"][0]["blockers"] == [
        "result_chain_incomplete", "feature_availability_unverified",
    ]
    assert report["verified_legs"] == 0


def test_mutated_evidenced_verification_fails_closed(tmp_path):
    evidence, _day, _snapshot, verification = settled_fixture(tmp_path)
    verification.write_text("{}\n", encoding="utf-8")
    with pytest.raises((ValueError, RuntimeError)):
        inspect(evidence)


def test_summary_cannot_redirect_to_unrelated_result_basename(tmp_path):
    evidence, day, _snapshot, _verification = settled_fixture(tmp_path)
    summary = day / f"Reflector_Run_Summary_{EVENT}.json"
    payload = json.loads(summary.read_text())
    payload["results_path"] = "/other/Results_Brief_2099-01-01.json"
    summary.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    with pytest.raises((ValueError, RuntimeError)):
        inspect(evidence)


def test_missing_prediction_bundle_blocks_otherwise_complete_labels(tmp_path):
    evidence, _day, snapshot, _verification = settled_fixture(tmp_path)
    (snapshot / "Game_BOS_NYK_Full_Analysis.md").unlink()
    report = inspect(evidence)
    assert report["candidates"][0]["blockers"] == [
        "prediction_bundle_unverified", "feature_availability_unverified",
    ]


def test_verifier_rejects_forged_sample_authority(tmp_path):
    evidence = settled_fixture(tmp_path)[0]
    report = inspect(evidence)
    report["verified_monitoring_samples"] = 1
    report["content_hash"] = _hash({key: value for key, value in report.items()
                                    if key != "content_hash"})
    with pytest.raises((ValueError, RuntimeError)):
        verify_nba_settlement_candidate_report(report, root=evidence, as_of=END,
                                               relocation_roots=())


def test_no_settlement_is_not_complete_or_sample_ready(tmp_path):
    evidence, _day, _snapshot = prediction_fixture(tmp_path)
    report = inspect(evidence)
    assert report["settlements_seen"] == 0
    assert report["label_source_verified"] is False
    assert report["verified_monitoring_samples"] is None
