"""S_v4 vs S_v2 forward test (EXP-20261026-08): only affected legs, single analysis when due."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import nba_season_rate_v4_forward as f  # noqa: E402


def _write(root, day, rows):
    (root / "ledger").mkdir(exist_ok=True)
    (root / "ledger" / f"{day}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))


def obs(day, player, prev_games, p2, p4, y, status="ok"):
    base = {"target_date": day, "game_tag": "A_B", "player": player, "market": "ast", "line": 4.0, "side": "over",
            "snapshot_id": "s", "snapshot_role": "production", "snapshot_created_at": f"{day}T08:00:00+00:00",
            "post_tip": False, "late_write": False, "tip_unknown": False}
    return [dict(base, row_type="model_obs", season_rate_v4_status=status, season_rate_v2_prob_S=p2,
                 season_rate_v4_prob_S=p4, season_rate_v4_inputs={"previous_games": prev_games,
                                                                  "last_game_date": "2026-10-20"}),
            dict(base, row_type="settlement", y=y, outcome="hit" if y else "miss")]


def test_only_legs_with_previous_season_history_are_compared(tmp_path):
    _write(tmp_path, "2026-10-28", obs("2026-10-28", "a", 8, 0.7, 0.5, 0) + obs("2026-10-28", "b", 0, 0.7, 0.7, 1))
    legs, days = f.collect(tmp_path, f.EPOCH, None)
    assert [l["player"] for l in legs] == ["a"] and days == [("2026-10-28", 1)]
    report = f.analyse(legs, days, "2026-10-29")
    assert report["status"] == "ACCUMULATING" and report["logloss_v4_minus_v2"] < 0


def test_due_after_quiet_days_or_final_date():
    legs = [{"day": "2026-11-0%d" % (i % 9 + 1), "event": f"e{i}", "player": "p", "stat": "ast", "y": i % 2,
             "p2": 0.6, "p4": 0.7 if i % 2 else 0.5, "leak": False} for i in range(150)]
    quiet = [("2026-11-10", 0), ("2026-11-11", 0), ("2026-11-12", 0)]
    assert f.analyse(legs, [("2026-11-09", 5)] + quiet, "2026-11-12")["status"] == "KEEP"
    assert f.analyse(legs[:20], quiet, "2026-11-12")["status"] == "NEEDS_MORE_TESTING"     # < 100 events
    assert f.analyse(legs, [("2026-11-09", 5)], "2026-12-01")["analysis_due"] is True
    legs[0]["leak"] = True
    assert f.analyse(legs, quiet, "2026-11-12")["status"] == "INVALID_DATA"
