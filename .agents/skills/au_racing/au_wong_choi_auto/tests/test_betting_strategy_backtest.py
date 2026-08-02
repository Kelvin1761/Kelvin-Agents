from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = (
    ROOT
    / ".agents"
    / "skills"
    / "au_racing"
    / "au_wong_choi_auto"
    / "scripts"
)
sys.path.insert(0, str(SCRIPTS))

from au_betting_strategy_backtest import (
    Strategy,
    load_market_index,
    load_runtime_dataset_races,
    load_snapshot_races,
    select_bets,
    strategy_metrics,
)


FIELDS = [
    "event_id",
    "menu_hint",
    "event_name",
    "event_dt",
    "selection_id",
    "selection_name",
    "win_lose",
    "bsp",
    "ppwap",
    "morningwap",
    "ppmax",
    "ppmin",
    "ipmax",
    "ipmin",
    "morningtradedvol",
    "pptradedvol",
    "iptradedvol",
]


def write_market(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: row.get(key, "")
                    for key in FIELDS
                }
            )


def market_row(
    number: int,
    name: str,
    *,
    market: str,
    won: bool,
    morning: float,
    bsp: float,
) -> dict:
    return {
        "event_id": "win-event" if market == "win" else "place-event",
        "menu_hint": "Rosehill Gardens (AUS) 1st Jan",
        "event_name": "R1 1400m BM72" if market == "win" else "To Be Placed",
        "event_dt": "01-01-2026 03:15",
        "selection_id": str(1000 + number),
        "selection_name": f"{number}. {name}",
        "win_lose": int(won),
        "bsp": bsp,
        "morningwap": morning,
        "pptradedvol": 100,
    }


class BettingStrategyBacktestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        names = ["Alpha", "Bravo", "Charlie", "Delta"]
        write_market(
            self.root / "dwbfpricesauswin02012026.csv",
            [
                market_row(
                    index,
                    name,
                    market="win",
                    won=index == 1,
                    morning=(1.8, 3.0, 5.0, 9.0)[index - 1],
                    bsp=(10.0, 3.2, 5.5, 8.0)[index - 1],
                )
                for index, name in enumerate(names, 1)
            ],
        )
        write_market(
            self.root / "dwbfpricesausplace02012026.csv",
            [
                market_row(
                    index,
                    name,
                    market="place",
                    won=index <= 3,
                    morning=(1.3, 1.6, 2.0, 3.0)[index - 1],
                    bsp=(1.4, 1.7, 2.1, 3.2)[index - 1],
                )
                for index, name in enumerate(names, 1)
            ],
        )
        score = {
            "2026-01-01 Rosehill Gardens Race 1-1": {
                "1": {
                    str(index): {
                        "name": name,
                        "old_ability": score,
                    }
                    for index, (name, score) in enumerate(
                        zip(names, (70.0, 68.0, 63.0, 59.0)),
                        1,
                    )
                }
            }
        }
        finish = {
            "2026-01-01 Rosehill Gardens Race 1-1": {
                "1": {
                    str(index): {"name": name, "pos": index}
                    for index, name in enumerate(names, 1)
                }
            }
        }
        self.score_path = self.root / "scores.json"
        self.finish_path = self.root / "finishes.json"
        self.score_path.write_text(json.dumps(score), encoding="utf-8")
        self.finish_path.write_text(json.dumps(finish), encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_place_rows_bridge_to_strict_win_race_identity(self) -> None:
        markets, audit = load_market_index(self.root)
        key = ("2026-01-01", "rosehill", 1, "alpha")
        self.assertIn(key, markets["win"])
        self.assertIn(key, markets["place"])
        self.assertEqual(audit["place_unbridged_to_win_race"], 0)

        races, alignment = load_snapshot_races(
            self.score_path,
            self.finish_path,
            markets,
            score_key="old_ability",
        )
        self.assertEqual(len(races), 1)
        self.assertEqual(races[0]["race_type"], "benchmark")
        self.assertEqual(races[0]["top1_top2_gap"], 2.0)
        self.assertEqual(races[0]["selections"][0]["place_bsp"], 1.4)
        self.assertEqual(alignment["win_outcome_mismatch"], 0)

    def test_bsp_never_decides_a_morning_odds_gate(self) -> None:
        markets, _ = load_market_index(self.root)
        races, _ = load_snapshot_races(
            self.score_path,
            self.finish_path,
            markets,
            score_key="old_ability",
        )
        strategy = Strategy(
            market="win",
            ranks="top1",
            execution="bsp",
            min_morning_odds=2.0,
            morning_market_top2=False,
            min_score_gap=None,
        )
        # Alpha later paid BSP 10.0, but morning was only 1.8.
        self.assertEqual(select_bets(races, strategy), [])

    def test_market_commission_is_applied_to_net_event_profit(self) -> None:
        bets = [
            {
                "date": "2026-01-01",
                "venue": "rosehill",
                "race_number": 1,
                "event_dt": "01-01-2026 03:15",
                "market": "win",
                "model_rank": 1,
                "horse_number": 1,
                "horse_name": "Alpha",
                "odds": 3.0,
                "morning_odds": 3.0,
                "won": True,
                "field_size": 10,
                "race_type": "benchmark",
                "score_gap": 1.0,
            },
            {
                "date": "2026-01-01",
                "venue": "rosehill",
                "race_number": 1,
                "event_dt": "01-01-2026 03:15",
                "market": "win",
                "model_rank": 2,
                "horse_number": 2,
                "horse_name": "Bravo",
                "odds": 4.0,
                "morning_odds": 4.0,
                "won": False,
                "field_size": 10,
                "race_type": "benchmark",
                "score_gap": 1.0,
            },
        ]
        metrics = strategy_metrics(bets, commission=0.05)
        # Gross event P&L = +2 - 1 = +1; commission = 0.05.
        self.assertEqual(metrics["pnl"], 0.95)
        self.assertEqual(metrics["roi_pct"], 47.5)
        self.assertEqual(metrics["bets"], 2)
        self.assertEqual(metrics["events"], 1)

    def test_current_runtime_dataset_uses_frozen_scores_before_market_join(
        self,
    ) -> None:
        names = ["Alpha", "Bravo", "Charlie", "Delta"]
        dataset = {
            "design": {"model": "current RacingEngine"},
            "races": [
                {
                    "metadata": {
                        "date": "2026-01-01",
                        "track": "Rosehill Gardens",
                        "race_number": 1,
                        "race_class": "BM72",
                    },
                    "rows": [
                        {
                            "horse_number": index,
                            "horse_name": name,
                            "score": score,
                            "actual_pos": index,
                        }
                        for index, (name, score) in enumerate(
                            zip(names, (70.0, 68.0, 63.0, 59.0)),
                            1,
                        )
                    ],
                }
            ],
        }
        dataset_path = self.root / "runtime_dataset.json"
        dataset_path.write_text(json.dumps(dataset), encoding="utf-8")
        markets, _ = load_market_index(self.root)
        races, alignment = load_runtime_dataset_races(
            dataset_path,
            markets,
        )
        self.assertEqual(len(races), 1)
        self.assertEqual(races[0]["race_type"], "benchmark")
        self.assertEqual(races[0]["selections"][0]["horse_name"], "Alpha")
        self.assertEqual(races[0]["selections"][0]["win_bsp"], 10.0)
        self.assertEqual(alignment["win_outcome_mismatch"], 0)


if __name__ == "__main__":
    unittest.main()
