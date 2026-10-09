from __future__ import annotations

import hashlib
import json
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / ".agents" / "skills"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from nba_research_evidence import (
    build_feature_projection, build_recommendation_projection,
    freeze_settlement_artifacts, settlement_artifacts,
)
from shared_wong_choi.research_nba_feature_provenance import _projection
from shared_wong_choi.research_nba_settlement_source import _result_chain
from shared_wong_choi.research_nba_monitoring_samples import _recommendations


EVENT = "2026-10-21"
TAG = "BOS_NYK"
CUTOFF = datetime(2026, 10, 21, 8, tzinfo=timezone.utc)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sources(folder: Path, *, injuries: bool = True) -> tuple[Path, Path]:
    odds = folder / f"Sportsbet_Odds_{TAG}.json"
    odds.write_text(json.dumps({
        "source": "Sportsbet",
        "target_analysis_date": EVENT,
        "matchup": "Boston Celtics @ New York Knicks",
        "game_lines": {"spread": {"home": -2.5}},
        "player_props": {"points": [{"player": "Player A", "line": 20.5}]},
    }), encoding="utf-8")
    game = folder / f"nba_game_data_{TAG}.json"
    payload = {
        "meta": {
            "game": "Boston Celtics at New York Knicks",
            "date": "2026-10-21T23:00:00Z",
            "season_phase": "EARLY_REGULAR",
            "away": {"name": "Boston Celtics", "abbr": "BOS"},
            "home": {"name": "New York Knicks", "abbr": "NYK"},
        },
        "players": {
            "BOS": [{"name": "Player A", "l10": [20, 21, 22]}],
            "NYK": [{"name": "Player B", "l10": [18, 19, 20]}],
        },
        "team_stats": {"BOS": {"pace": 99.1}, "NYK": {"pace": 98.2}},
        "team_dvp": {"BOS": {"PG": 24.1}, "NYK": {"PG": 23.8}},
    }
    if injuries:
        payload["injuries"] = {"BOS": {}, "NYK": {"Player C": "Out"}}
    game.write_text(json.dumps(payload), encoding="utf-8")
    return odds, game


def test_feature_projection_passes_existing_central_consumer(tmp_path: Path) -> None:
    folder = tmp_path / f"{EVENT} NBA Analysis"
    folder.mkdir()
    odds, game = _sources(folder)
    raw = build_feature_projection(
        folder=folder,
        event_id=EVENT,
        game_tags=[TAG],
        source_cutoff_at=CUTOFF,
    )
    rows, blockers = _projection(
        raw,
        event_id=EVENT,
        cutoff=CUTOFF,
        game_tags={TAG},
        files={odds.name: _digest(odds), game.name: _digest(game)},
    )

    assert blockers == set()
    assert rows == [{
        "game_tag": TAG,
        "available_families": 5,
        "unavailable_families": 0,
        "verified": True,
        "blockers": [],
    }]
    assert build_feature_projection(
        folder=folder,
        event_id=EVENT,
        game_tags=[TAG],
        source_cutoff_at=CUTOFF,
    ) == raw


def test_missing_injury_source_is_explicitly_unavailable(tmp_path: Path) -> None:
    folder = tmp_path / f"{EVENT} NBA Analysis"
    folder.mkdir()
    _sources(folder, injuries=False)
    payload = json.loads(build_feature_projection(
        folder=folder,
        event_id=EVENT,
        game_tags=[TAG],
        source_cutoff_at=CUTOFF,
    ))
    assert payload["rows"][0]["families"]["injury_context"] == {
        "status": "unavailable",
        "reason": "source_not_present",
        "sources": [],
    }


def _scheduled_sources(folder: Path) -> datetime:
    _sources(folder)
    game = folder / f"nba_game_data_{TAG}.json"
    value = json.loads(game.read_text())
    value["meta"]["date"] = "2026-10-21T12:00:00Z"
    game.write_text(json.dumps(value))
    return datetime(2026, 10, 21, 12, tzinfo=timezone.utc)


def test_projection_uses_frozen_bytes_not_changed_live_source(tmp_path: Path) -> None:
    folder = tmp_path / f"{EVENT} NBA Analysis"
    folder.mkdir()
    start = _scheduled_sources(folder)
    captured = tmp_path / "captured"
    shutil.copytree(folder, captured)
    game = folder / f"nba_game_data_{TAG}.json"
    game.write_text("{}")
    raw = build_feature_projection(
        folder=folder, source_folder=captured, event_id=EVENT,
        game_tags=[TAG], source_cutoff_at=CUTOFF, event_starts={TAG: start},
    )
    files = {item.name: _digest(item) for item in captured.iterdir()}
    rows, blockers = _projection(
        raw, event_id=EVENT, cutoff=CUTOFF, game_tags={TAG}, files=files,
    )
    assert not blockers
    assert rows[0]["verified"]
    assert files[game.name] != _digest(game)


@pytest.mark.parametrize("fault", ["late", "wrong_time", "wrong_tag", "missing", "naive"])
def test_official_schedule_validation_fails_closed(tmp_path: Path, fault: str) -> None:
    folder = tmp_path / f"{EVENT} NBA Analysis"
    folder.mkdir()
    start = _scheduled_sources(folder)
    events, cutoff = {TAG: start}, CUTOFF
    if fault == "late":
        cutoff = start
    elif fault == "missing":
        events = {}
    elif fault == "naive":
        events = {TAG: start.replace(tzinfo=None)}
    else:
        game = folder / f"nba_game_data_{TAG}.json"
        value = json.loads(game.read_text())
        if fault == "wrong_time":
            value["meta"]["date"] = "2026-10-21T13:00:00Z"
        else:
            value["meta"]["away"]["abbr"] = "LAL"
        game.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        build_feature_projection(
            folder=folder, event_id=EVENT, game_tags=[TAG],
            source_cutoff_at=cutoff, event_starts=events,
        )


def test_scheduler_snapshot_attaches_verified_projection(tmp_path: Path) -> None:
    import nba_daily_schedule as schedule

    folder = tmp_path / f"{EVENT} NBA Analysis"
    folder.mkdir()
    start = _scheduled_sources(folder)
    (folder / f"Game_{TAG}_Full_Analysis.md").write_text(
        "### 🛡️ Combo 1\nLeg 1: Player Alpha PTS 20+ @1.85\n" + "A" * 2500
    )
    (folder / "NBA_All_SGM_Report.txt").write_text("SGM")
    (folder / "NBA_Banker_Report.txt").write_text("BANKER")
    with mock.patch.object(schedule, "datetime") as clock:
        clock.now.return_value = CUTOFF
        snapshot = schedule.create_prediction_snapshot(
            folder, EVENT, [TAG], event_starts={TAG: start},
        )
    manifest = json.loads((snapshot / "manifest.json").read_bytes())
    assert manifest["domain"] == "nba"
    assert manifest["event_id"] == EVENT
    assert manifest["created_at"] == CUTOFF.isoformat()
    assert manifest["research_evidence"] == {
        "status": "pregame_verified", "monitoring_status": "settlement_pending",
    }
    files = {item["name"]: item for item in manifest["files"]}
    assert set(files) == {item.name for item in snapshot.iterdir()} - {"manifest.json"}
    for name, item in files.items():
        assert set(item) == {"name", "sha256", "bytes"}
        assert item["sha256"] == _digest(snapshot / name)
        assert item["bytes"] == (snapshot / name).stat().st_size
    raw = (snapshot / f"NBA_Feature_Evidence_{EVENT}.json").read_bytes()
    rows, blockers = _projection(
        raw, event_id=EVENT, cutoff=CUTOFF, game_tags={TAG},
        files={name: item["sha256"] for name, item in files.items()},
    )
    assert not blockers and rows[0]["verified"]
    recommendations, error = _recommendations(
        (snapshot / f"NBA_Recommendation_Evidence_{EVENT}.json").read_bytes(),
        event_id=EVENT, cutoff=CUTOFF, game_tags={TAG},
    )
    assert error is None and len(recommendations) == 1
    # Exercise the real writer and Central reader, not only private parsers.
    from shared_wong_choi.contracts import Domain
    from shared_wong_choi.domain_evidence import record_prediction_decision
    from shared_wong_choi.evidence import DecisionState, ReleaseStage
    from shared_wong_choi.model_registry import ModelRegistry, ModelReleaseRequest
    from shared_wong_choi.research_prediction_artifacts import inspect_prediction_artifacts
    from shared_wong_choi.research_nba_feature_provenance import inspect_nba_feature_provenance

    evidence = tmp_path / "evidence"
    model = ModelRegistry(evidence).register(ModelReleaseRequest(
        domain=Domain.NBA, model_id="fixture-nba", code_commit="a" * 40,
        evaluation_contract_version="fixture-only", target_stage=ReleaseStage.RESEARCH,
        evaluation_verdict="BASELINE_MIGRATION",
        created_at=(CUTOFF - timedelta(hours=1)).isoformat(),
    ))["record_id"]
    recorded = record_prediction_decision(
        domain=Domain.NBA, event_id=EVENT, snapshot=snapshot, evidence_root=evidence,
        decision_state=DecisionState.SHADOW, model_release_id=model, created_at=CUTOFF,
    )
    assert recorded["status"] == "created"
    inventory = inspect_prediction_artifacts(
        root=evidence, domain=Domain.NBA, as_of=CUTOFF + timedelta(hours=1),
    )
    assert inventory["verified_bundles"] == 1
    assert inventory["records"][0]["manifest_consistent"]
    assert inventory["model_promotion_allowed"] is False
    provenance = inspect_nba_feature_provenance(
        root=evidence, as_of=CUTOFF + timedelta(hours=1),
    )
    assert provenance["feature_availability_verified"]
    assert provenance["verified_games"] == 1
    assert provenance["source_coverage_complete"] is False
    assert provenance["model_promotion_allowed"] is False
    from shared_wong_choi.domain_evidence import record_settlement_for_event
    from shared_wong_choi.research_nba_monitoring_samples import inspect_nba_monitoring_samples

    _results, verification, _summary = _settlement_sources(folder)
    value = json.loads(verification.read_bytes())
    value["legs"][0].update({"player": "Player Alpha", "stat": "PTS", "line": 20.0})
    verification.write_text(json.dumps(value))
    frozen = freeze_settlement_artifacts(folder=folder, event_id=EVENT)
    settled = CUTOFF + timedelta(days=1)
    arguments = dict(
        domain=Domain.NBA, event_id=EVENT, evidence_root=evidence,
        summary={"fixture_only": True}, artifacts=frozen, settled_at=settled,
    )
    assert record_settlement_for_event(**arguments)["status"] == "created"
    assert record_settlement_for_event(**arguments)["status"] == "duplicate"
    samples = inspect_nba_monitoring_samples(root=evidence, as_of=settled + timedelta(hours=1))
    assert samples["qualified_recommendations"] == 1
    assert samples["model_promotion_allowed"] is False
    # Native archive edits cannot mutate linked settlement evidence.
    verification.write_text("{}")
    assert inspect_nba_monitoring_samples(
        root=evidence, as_of=settled + timedelta(hours=1),
    )["content_hash"] == samples["content_hash"]
    # Preserve native duplicate keys; never normalize them into acceptance.
    value["legs"].append(dict(value["legs"][0]))
    value["summary"].update({"total_legs": 2, "hits": 2})
    verification.write_text(json.dumps(value))
    duplicate_keys = freeze_settlement_artifacts(folder=folder, event_id=EVENT)
    record_settlement_for_event(**{**arguments, "artifacts": duplicate_keys})
    blocked = inspect_nba_monitoring_samples(root=evidence, as_of=settled + timedelta(hours=1))
    assert blocked["blocked_settlements"] == 1
    assert blocked["source_coverage_complete"] is False
    assert any("recommendation_result_mismatch" in item["blockers"] for item in blocked["candidates"])
    # Subsequent live refresh cannot rewrite the frozen source or its provenance.
    (folder / f"nba_game_data_{TAG}.json").write_text("{}")
    assert _digest(snapshot / f"nba_game_data_{TAG}.json") == files[f"nba_game_data_{TAG}.json"]["sha256"]


def test_native_repeated_combo_legs_have_one_monitoring_identity(tmp_path: Path) -> None:
    report = tmp_path / f"Game_{TAG}_Full_Analysis.md"
    report.write_text(
        "### 🛡️ Combo 1\nLeg 1: Player Alpha PTS 20+ @1.85\n"
        "### 🔥 Combo 2\nLeg 1: Player Alpha PTS 20+ @1.85\n"
    )
    before = report.read_bytes()
    raw = build_recommendation_projection(
        source_folder=tmp_path, event_id=EVENT, game_tags=[TAG], source_cutoff_at=CUTOFF,
    )
    rows, error = _recommendations(raw, event_id=EVENT, cutoff=CUTOFF, game_tags={TAG})
    assert error is None and len(rows) == 1
    assert rows[0]["stat"] == "PTS" and rows[0]["side"] == "over"
    assert report.read_bytes() == before
    assert raw == build_recommendation_projection(
        source_folder=tmp_path, event_id=EVENT, game_tags=[TAG], source_cutoff_at=CUTOFF,
    )


def test_empty_report_does_not_invent_recommendations(tmp_path: Path) -> None:
    (tmp_path / f"Game_{TAG}_Full_Analysis.md").write_text("No props")
    with pytest.raises(ValueError, match="no verified recommendation"):
        build_recommendation_projection(
            source_folder=tmp_path, event_id=EVENT, game_tags=[TAG], source_cutoff_at=CUTOFF,
        )


@pytest.mark.parametrize(
    ("fault", "message"),
    [
        ("missing_odds", "missing NBA source artifact"),
        ("empty_market", "NBA market source has no market data"),
        ("empty_players", "NBA player-form source is empty"),
        ("empty_teams", "NBA team-context source is empty"),
        ("wrong_event", "NBA odds event mismatch"),
        ("wrong_source", "NBA odds event mismatch"),
    ],
)
def test_incomplete_feature_family_fails_closed(
    tmp_path: Path,
    fault: str,
    message: str,
) -> None:
    folder = tmp_path / f"{EVENT} NBA Analysis"
    folder.mkdir()
    odds, game = _sources(folder)
    if fault == "missing_odds":
        odds.unlink()
    else:
        target = odds if fault in {"empty_market", "wrong_event", "wrong_source"} else game
        payload = json.loads(target.read_text())
        if fault == "empty_market":
            payload["game_lines"] = {}
            payload["player_props"] = {}
        elif fault == "empty_players":
            payload["players"] = {"BOS": [], "NYK": []}
        elif fault == "empty_teams":
            payload["team_stats"] = {"BOS": {}, "NYK": {}}
            payload["team_dvp"] = {"BOS": {}, "NYK": {}}
        else:
            if fault == "wrong_event":
                payload["target_analysis_date"] = "2026-10-22"
            else:
                payload["source"] = "unverified"
        target.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        build_feature_projection(
            folder=folder,
            event_id=EVENT,
            game_tags=[TAG],
            source_cutoff_at=CUTOFF,
        )


def _settlement_sources(folder: Path) -> tuple[Path, Path, Path]:
    us_date = "2026-10-20"
    results = folder / f"Results_Brief_{us_date}.json"
    results.write_text(json.dumps({
        "_version": "RESULTS_BRIEF_V1",
        "date": us_date,
        "total_games": 1,
        "games": [{"home": {"team": "NYK"}, "away": {"team": "BOS"}}],
    }), encoding="utf-8")
    verification = folder / f"Props_Verification_{us_date}.json"
    verification.write_text(json.dumps({
        "_version": "PROPS_VERIFICATION_V1",
        "summary": {"total_legs": 1, "hits": 1, "misses": 0,
                    "voids": 0, "unverified": 0},
        "legs": [{"outcome": "hit", "cleared": True, "actual": 21.0,
                  "line": 20.5}],
    }), encoding="utf-8")
    summary = folder / f"Reflector_Run_Summary_{EVENT}.json"
    summary.write_text(json.dumps({
        "analysis_date": EVENT,
        "us_game_date": us_date,
        "results_path": f"/old/{results.name}",
        "verification_path": f"/old/{verification.name}",
        "rows_recorded": 1,
    }), encoding="utf-8")
    return results, verification, summary


def test_settlement_selector_requires_exact_verified_chain(tmp_path: Path) -> None:
    folder = tmp_path / f"{EVENT} NBA Analysis"
    folder.mkdir()
    _results, verification, _summary = _settlement_sources(folder)

    selected = settlement_artifacts(folder=folder, event_id=EVENT)
    artifacts = {path.name: path.read_bytes() for path in selected}
    assert [path.name for path in selected] == sorted(artifacts)
    assert _result_chain(EVENT, artifacts) == (1, True)

    verification.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="incomplete NBA settlement result chain"):
        settlement_artifacts(folder=folder, event_id=EVENT)


def test_settlement_capture_is_exact_immutable_and_idempotent(tmp_path: Path) -> None:
    folder = tmp_path / f"{EVENT} NBA Analysis"
    folder.mkdir()
    sources = _settlement_sources(folder)
    (folder / "Unrelated.json").write_text("{}")
    original = {path.name: path.read_bytes() for path in sources}
    frozen = freeze_settlement_artifacts(folder=folder, event_id=EVENT)
    assert {path.name: path.read_bytes() for path in frozen} == original
    assert all("_research_settlements" in path.parts for path in frozen)
    assert freeze_settlement_artifacts(folder=folder, event_id=EVENT) == frozen
    assert _result_chain(EVENT, {path.name: path.read_bytes() for path in frozen}) == (1, True)
    verification = sources[1]
    value = json.loads(verification.read_bytes())
    value["legs"][0]["actual"] = 22.0
    verification.write_text(json.dumps(value))
    refreshed = freeze_settlement_artifacts(folder=folder, event_id=EVENT)
    assert refreshed != frozen
    assert {path.name: path.read_bytes() for path in frozen} == original
    assert (folder / "Unrelated.json").read_text() == "{}"


def test_corrupt_immutable_settlement_is_not_overwritten(tmp_path: Path) -> None:
    folder = tmp_path / f"{EVENT} NBA Analysis"
    folder.mkdir()
    _settlement_sources(folder)
    frozen = freeze_settlement_artifacts(folder=folder, event_id=EVENT)
    frozen[0].write_text("tampered")
    with pytest.raises(ValueError, match="immutable settlement bytes differ"):
        freeze_settlement_artifacts(folder=folder, event_id=EVENT)
    assert frozen[0].read_text() == "tampered"


def test_settlement_revalidates_captured_chain_after_source_change(tmp_path: Path) -> None:
    import nba_research_evidence as producer

    folder = tmp_path / f"{EVENT} NBA Analysis"
    folder.mkdir()
    _results, verification, _summary = _settlement_sources(folder)
    original = producer.settlement_artifacts

    def select_then_mutate(**kwargs):
        paths = original(**kwargs)
        if kwargs["folder"] == folder:
            verification.write_text("{}")
        return paths

    with mock.patch.object(producer, "settlement_artifacts", side_effect=select_then_mutate):
        with pytest.raises(ValueError, match="incomplete NBA settlement result chain"):
            producer.freeze_settlement_artifacts(folder=folder, event_id=EVENT)
    assert not list((folder / "_research_settlements").iterdir())
