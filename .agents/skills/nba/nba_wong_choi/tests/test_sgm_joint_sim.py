"""N1 shadow: seeded MC and same-simulation SGM joint probability."""
from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import monte_carlo_nba as mc  # noqa: E402

META = {"date": "2026-10-22", "away": {"abbr": "BOS"}, "home": {"abbr": "LAL"}}


def _card(name, team, category, avg, sd, lines, min_avg=34.0):
    return {
        "name": name, "team": team, "category": category, "avg": avg, "sd": sd,
        "cov": sd / avg, "min_avg": min_avg,
        "line_analysis": {
            str(line): {"line": float(line), "line_display": f"{line}+", "odds": "1.9",
                        "implied_prob": 52.6, "hit_l10": 60.0, "estimated_prob": 60.0}
            for line in lines
        },
    }


CARDS = [
    _card("Jayson Tatum", "BOS", "points", 27.0, 6.0, [25]),
    _card("Jaylen Brown", "BOS", "points", 23.0, 5.5, [20]),
    _card("Jayson Tatum", "BOS", "rebounds", 8.0, 2.5, [8]),
    _card("LeBron James", "LAL", "assists", 8.0, 2.5, [8]),
]


def _leg(player, team, category, line):
    return {"market_type": "PLAYER_MILESTONE", "player": player, "team": team,
            "category": category, "line_val": float(line)}


COMBOS = {
    "1": [_leg("Jayson Tatum", "BOS", "PTS", 25), _leg("Jaylen Brown", "BOS", "PTS", 20)],
    "2": [_leg("Jayson Tatum", "BOS", "PTS", 25), _leg("Jayson Tatum", "BOS", "REB", 8)],
    "3": [],
    "X": [{"market_type": "TEAM_MARKET", "player": "TEAM_BOS_LAL", "team": "TEAM",
           "category": "TEAM", "line_val": 0}],
}


def test_seeded_card_mc_is_reproducible_and_order_independent():
    first = mc.run_monte_carlo_for_cards(CARDS, meta=META, n=2000, seed=123)
    again = mc.run_monte_carlo_for_cards(CARDS, meta=META, n=2000, seed=123)
    assert [r["mc_prob"] for r in first] == [r["mc_prob"] for r in again]
    reordered = mc.run_monte_carlo_for_cards(list(reversed(CARDS)), meta=META, n=2000, seed=123)
    by_key = {(r["player"], r["category"], r["line"]): r["mc_prob"] for r in first}
    assert all(by_key[(r["player"], r["category"], r["line"])] == r["mc_prob"] for r in reordered)


def test_seeded_mc_does_not_reseed_the_global_rng():
    random.seed(7)
    expected = random.random()
    random.seed(7)
    mc.monte_carlo_player_prop(avg=20, sd=5, line=20, n=200, seed=42)
    assert random.random() == expected


def test_seeded_run_matches_the_old_global_seed_stream():
    # Private RNG with the same seed reproduces the old random.seed(seed) output.
    new = mc.monte_carlo_player_prop(avg=20, sd=5, line=20, n=2000, seed=42)
    random.seed(42)
    old = mc.monte_carlo_player_prop(avg=20, sd=5, line=20, n=2000, rng=random)
    assert new["mc_prob"] == old["mc_prob"]


def test_joint_sim_is_deterministic_and_counts_joint_hits_in_one_game():
    first = mc.simulate_sgm_joint(COMBOS, CARDS, spread="-3.5", meta=META, n=4000, seed=99)
    again = mc.simulate_sgm_joint(COMBOS, CARDS, spread="-3.5", meta=META, n=4000, seed=99)
    assert first == again
    teammates = first["1"]
    assert teammates["sim_status"] == "ok"
    assert 0 < teammates["sim_joint_prob"] <= min(teammates["sim_leg_marginals"])
    # Shared team scoring / pace / margin make teammates' overs co-move.
    assert teammates["sim_correlation_lift"] > 1.0
    # Same player across two markets shares the role factor too.
    assert first["2"]["sim_correlation_lift"] > 1.0
    assert "3" not in first  # empty combo
    assert first["X"]["sim_status"] == "unsupported_leg"


def test_joint_sim_marginals_track_the_single_leg_mc():
    sim = mc.simulate_sgm_joint({"1": [_leg("LeBron James", "LAL", "AST", 8)]}, CARDS,
                                meta=META, n=20000, seed=5)
    single = mc.run_monte_carlo_for_cards([CARDS[3]], meta=META, n=20000, seed=5)[0]
    assert abs(sim["1"]["sim_joint_prob"] * 100 - single["mc_prob"]) < 2.0
