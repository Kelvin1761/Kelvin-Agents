"""Train/serve parity: live feature construction must equal the training builder.

Builds features for the same player/stat/line through
``build_nba_ml_dataset.extract_game_data`` (training) and
``MLPropPredictor.build_features`` (live) and asserts they match.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO / ".agents" / "scripts" / "nba_ml"))
sys.path.insert(0, str(REPO))
import build_nba_ml_dataset as builder
import nba_ml_predictor as predictor

FEATURES = ['l10_avg', 'l10_sd', 'l10_cov', 'l10_med', 'l5_avg', 'l3_avg', 'min_avg',
            'pace_projected', 'usg_pct', 'ts_pct', 'def_rtg', 'opp_def_rating',
            'opp_def_rank', 'opp_pace', 'defender_pm', 'usg_bonus_pct', 'b2b_flag',
            'b2b_ppg_diff_pct', 'rest_days', 'is_home', 'home_ppg', 'away_ppg',
            'hit_rate_l10', 'hit_rate_l5', 'hit_rate_l3', 'amc', 'line_value']

PTS = [28, 31, 25, 33, 29, 27, 30, 26, 34, 28]  # newest first


def stats(arr):
    n = len(arr)
    avg = sum(arr) / n
    sd = (sum((x - avg) ** 2 for x in arr) / n) ** 0.5
    s = sorted(arr)
    return {"avg": round(avg, 1), "med": (s[4] + s[5]) / 2, "sd": round(sd, 2), "cov": round(sd / avg, 3)}


def payload(with_x5_lines=True):
    player = {
        "name": "Test Star", "position": "G",
        "advanced": {"USG_PCT": 29.1, "TS_PCT": 61.2, "DEF_RATING": 110.4, "MIN": 33.0},
        "splits": {"Home_PPG": 30.1, "Road_PPG": 27.4},
        "gamelog": {"PTS": PTS, "PTS_stats": stats(PTS), "MIN": [34] * 10, "MIN_stats": {"avg": 34.0}},
        "fatigue": {"is_b2b": True, "normal_ppg": 29.0, "b2b_ppg": 26.0, "rest_days": 0},
        "prop_analytics": {},
    }
    if with_x5_lines:
        # What the extractor writes: x.5 lines, `>` convention.
        player["prop_analytics"]["PTS"] = {
            "pace_projected": 29.9,  # extractor's 100-based number
            "sportsbet_lines": [{"line": 24.5, "hit_rate_L10": 90, "hit_rate_L5": 100, "hit_rate_L3": 100, "AMC": 4.0}],
        }
    return {
        "meta": {"date": "2026-10-21T00:00Z", "away": {"abbr": "BOS"}, "home": {"abbr": "DET"}},
        "team_stats": {"BOS": {"DEF_RATING": 111.7, "DEF_RANK": 4, "PACE": 95.58},
                       "DET": {"DEF_RATING": 108.9, "DEF_RANK": 2, "PACE": 99.88}},
        "key_defenders": {"BOS": [{"PCT_PLUSMINUS": -0.031}, {"PCT_PLUSMINUS": 0.02}, {"PCT_PLUSMINUS": 0.05}],
                          "DET": [{"PCT_PLUSMINUS": 0.044}, {"PCT_PLUSMINUS": -0.01}]},
        "usage_redistribution": {"DET": {"Test Star": {"bonus_USG": 3.4}}},
        "players": {"BOS": [], "DET": [player]},
    }, player


def training_row(data, line):
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "nba_game_data_BOS_DET.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        rows = builder.extract_game_data(str(path))
    match = [r for r in rows if r["player"] == "Test Star" and r["stat_category"] == "PTS" and r["line_value"] == line]
    assert len(match) == 1
    return match[0]


def live_features(player, line):
    """Live path. The opp_* arguments are what the TRAINING builder resolves for
    this DET (home) player, i.e. DET's own stats -- see
    test_training_builder_resolves_opponent_to_own_team -- so every other
    feature can be compared like for like."""
    p = predictor.MLPropPredictor.__new__(predictor.MLPropPredictor)  # no model needed
    return p.build_features(
        player, "PTS", line, 1, "BOS",
        opp_def_rating=108.9, opp_def_rank=2, opp_pace=99.88,
        defender_pm=0.044,       # TOP defender, as training does
        usg_bonus_pct=3.4)       # live nonzero; training is always 0


class ParityTests(unittest.TestCase):
    def test_features_equal_for_every_milestone_line(self):
        for with_lines in (True, False):
            data, player = payload(with_lines)
            for line in builder.SPORTSBET_LINES["PTS"]:
                train = training_row(data, line)
                live = live_features(player, line)
                for f in FEATURES:
                    self.assertEqual(float(train[f]), float(live[f]),
                                     f"{f} differs at line {line} (x5 lines={with_lines}): "
                                     f"train={train[f]} live={live[f]}")

    def test_hit_rates_not_zero_when_player_clears_line(self):
        _, player = payload(True)
        live = live_features(player, 30)
        self.assertEqual(live["hit_rate_l10"], 40.0)   # 31,33,30,34 of 10 games >= 30
        self.assertGreater(live["hit_rate_l3"], 0)
        self.assertGreater(live["amc"], 0)

    def test_pace_baseline_is_training_baseline(self):
        _, player = payload(True)
        live = live_features(player, 25)
        self.assertEqual(live["pace_projected"],
                         predictor.training_pace_projected(stats(PTS)["avg"], 99.88))
        self.assertNotEqual(live["pace_projected"], 29.9)

    def test_training_builder_resolves_opponent_to_own_team(self):
        """KNOWN TRAINING DEFECT (documented, not fixed here: no retraining).

        build_nba_ml_dataset.extract_game_data sets
        ``opp_abbr = home_abbr if is_home else away_abbr``, which is the
        player's OWN team, so opp_def_rating / opp_def_rank / opp_pace /
        defender_pm in the training set are own-team values. Live passes the
        true opponent. If this test starts failing the builder was fixed:
        revisit docs/experiments EXP-20261021-01 before retraining.
        """
        data, _ = payload(True)
        row = training_row(data, 10)
        self.assertEqual(row["team"], "DET")
        self.assertEqual(row["opponent"], "DET")
        self.assertEqual(row["opp_pace"], 99.88)


if __name__ == "__main__":
    unittest.main()
