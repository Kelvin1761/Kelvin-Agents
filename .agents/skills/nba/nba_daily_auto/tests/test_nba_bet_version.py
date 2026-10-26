"""The 21:00 publication is the version the user bets: evaluated separately, never re-published."""
from __future__ import annotations

import json
import sys
from pathlib import Path

AUTO_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AUTO_DIR))
import nba_combo_roi as roi  # noqa: E402
import nba_daily_schedule as schedule  # noqa: E402
import nba_market_ledger as ledger  # noqa: E402

D = "2026-10-26"


def sgm(role, created, legs, cid="1"):
    return {"row_type": "sgm_obs", "target_date": D, "game_tag": "DET_PHI", "combo_id": cid, "legs": legs,
            "product_of_leg_prices": 2.5, "snapshot_id": f"{role}-{created}", "snapshot_role": role,
            "snapshot_created_at": created, "late_write": False, "post_tip": False, "tip_unknown": False}


def leg(player, market="ast", line=4.0, team="PHI"):
    return {"player": player, "market": market, "line": line, "side": "over", "price": 1.5, "team": team}


def settle(player, outcome, market="ast", line=4.0):
    return {"row_type": "settlement", "target_date": D, "game_tag": "DET_PHI", "player": player,
            "market": market, "line": line, "side": "over", "outcome": outcome}


ROWS = [
    sgm("production", "2026-10-25T21:06:00+11:00", [leg("Jaylen Brown")]),
    sgm("final_refresh", "2026-10-26T06:49:00+11:00", [leg("LeBron James", "pts", 15.0)]),
    settle("Jaylen Brown", "miss"), settle("LeBron James", "hit", "pts", 15.0),
]


def test_bet_view_settles_the_2100_publication_not_the_morning_one():
    latest = roi.settle_combos(ROWS)
    bet = roi.settle_combos(ROWS, "bet")
    assert [c["state"] for c in latest] == ["win"]       # morning version
    assert [c["state"] for c in bet] == ["loss"]         # what the user actually bet


def test_choose_view_snapshot():
    rows = [dict(r, row_type="model_obs") for r in ROWS[:2]]
    assert ledger._choose_view_snapshot(rows, "latest") == "final_refresh-2026-10-26T06:49:00+11:00"
    assert ledger._choose_view_snapshot(rows, "bet") == "production-2026-10-25T21:06:00+11:00"
    assert ledger._choose_view_snapshot([dict(ROWS[1], row_type="model_obs")], "bet") is None


def _ledger(tmp_path, rows):
    (tmp_path / "ledger").mkdir()
    (tmp_path / "ledger" / f"{D}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))


def test_morning_alert_names_published_players_now_out_or_doubtful(tmp_path):
    _ledger(tmp_path, ROWS)
    folder = tmp_path / "game"; folder.mkdir()
    game = {"injuries": {"PHI": {}},
            "official_injuries": {"PHI": {"status": "available", "players": {
                "jaylenbrown": {"player": "Brown,Jaylen", "status": "Questionable", "level": "dtd", "reason": ""}}}}}
    (folder / "nba_game_data_DET_PHI.json").write_text(json.dumps(game))
    text = schedule.published_leg_availability_alert(folder, D, root=tmp_path)
    assert "Jaylen Brown" in text and "Questionable" in text and "LeBron" not in text   # only the bet version
    game["official_injuries"]["PHI"]["players"] = {}
    (folder / "nba_game_data_DET_PHI.json").write_text(json.dumps(game))
    assert schedule.published_leg_availability_alert(folder, D, root=tmp_path) is None
    assert schedule.published_leg_availability_alert(tmp_path / "missing", D, root=tmp_path / "nope") is None


def test_banker_shadow_bet_version_runs_across_days(tmp_path):
    # regression: the parameter once shared a name with a local list and broke on day two
    for day in ("2026-10-25", "2026-10-26"):
        (tmp_path / "ledger").mkdir(exist_ok=True)
        (tmp_path / "ledger" / f"{day}.jsonl").write_text("")
    out = roi.banker_shadow("2026-10-26", tmp_path, model_id="m", version="bet")
    assert out["view"] == "bet" and out["arms"]["B2"]["combos"] == 0
