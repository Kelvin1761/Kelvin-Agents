from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / ".agents" / "skills"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nba_research_evidence import build_feature_projection, settlement_artifacts
from shared_wong_choi.research_nba_feature_provenance import _projection
from shared_wong_choi.research_nba_settlement_source import _result_chain


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


def test_settlement_selector_requires_exact_verified_chain(tmp_path: Path) -> None:
    folder = tmp_path / f"{EVENT} NBA Analysis"
    folder.mkdir()
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

    selected = settlement_artifacts(folder=folder, event_id=EVENT)
    artifacts = {path.name: path.read_bytes() for path in selected}
    assert [path.name for path in selected] == sorted(artifacts)
    assert _result_chain(EVENT, artifacts) == (1, True)

    verification.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="incomplete NBA settlement result chain"):
        settlement_artifacts(folder=folder, event_id=EVENT)
