"""`_parse_pf_token` 支援 12 個欄位，實際只有 1 個有數據。

2026-08-31 實測 73,806 條 pf_runs（2026-08-05 起，全部 `sportsbet_race_context`）：
`l600_delta` 100%，其餘十個 **0.0%** —— 全部係 Racenet 遺留（2026-08 剷走）。
`_pf_aggregates` 為咗嗰十個欄位計 `_avg` / `_best` / `tempo` / `rt_rating` /
`early pace`，實際上係喺一個場級數字上面空轉。

呢個 suite 唔係要求刪走佢哋（Racenet 格式喺舊歸檔仲讀得到），係要**釘住呢件事
係已知嘅**，唔好再有人（包括我）睇住個欄位清單以為呢個特徵好豐富。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "au_racing"
                      / "au_wong_choi_auto" / "scripts"))

from au_racing_engine.engine_core import (  # noqa: E402
    _PF_SPLIT_KEYS, _parse_pf_token, _pf_aggregates)

# 現行 Sportsbet PF token 得兩樣嘢。
SPORTSBET_TOKEN = "Source: sportsbet_race_context L600 Delta: 0.11"
# Racenet 年代（≤2026-07）先有其餘欄位。
RACENET_TOKEN = ("Last600: 29.28 Runner Time: 64.88 Race Time: 0.29 "
                 "Early Runner Pace: Fast. Early Race Pace: Fast. L600 Delta: 0.38")

DEAD_UNDER_SPORTSBET = (
    "l600_time", "runner_time", "race_time_diff", "l800_delta",
    "l400_delta", "l200_delta", "tempo_qrank", "rt_rating",
    "early_runner_pace", "early_race_pace",
)


class SportsbetTokenTests(unittest.TestCase):
    def test_only_l600_delta_survives_the_sportsbet_feed(self) -> None:
        parsed = _parse_pf_token(SPORTSBET_TOKEN)
        self.assertEqual(parsed["l600_delta"], 0.11)
        for key in DEAD_UNDER_SPORTSBET:
            with self.subTest(key=key):
                self.assertIsNone(parsed[key],
                                  f"{key} 突然有值 —— 上游多咗嘢，值得重新評估")

    def test_racenet_token_still_parses(self) -> None:
        """舊歸檔仲讀得到，所以個 parser 唔可以剷。"""
        parsed = _parse_pf_token(RACENET_TOKEN)
        self.assertEqual(parsed["l600_time"], 29.28)
        self.assertEqual(parsed["runner_time"], 64.88)
        self.assertEqual(parsed["l600_delta"], 0.38)


class AggregateLivenessTests(unittest.TestCase):
    def test_sportsbet_runs_only_produce_two_live_aggregates(self) -> None:
        runs = [_parse_pf_token(SPORTSBET_TOKEN) for _ in range(3)]
        for r in runs:
            r["source"] = "sportsbet_race_context"
            r["margin"] = 1.0
        agg = _pf_aggregates(runs, "sportsbet_race_context")
        live = {k for k in agg if k.endswith(("_avg", "_best"))}
        self.assertEqual(
            live,
            {"l600_delta_avg", "l600_delta_best",
             "own_l600_delta_avg", "own_l600_delta_best"},
            "Sportsbet feed 應該只出 l600_delta 同個體化版；"
            "多咗嘢就係上游變咗，要重新量 coverage",
        )

    def test_split_keys_still_lists_the_dormant_racenet_fields(self) -> None:
        """佢哋留喺度係為咗舊歸檔，唔係因為 live 有數據。"""
        for key in ("l800_delta", "l400_delta", "l200_delta", "runner_time"):
            self.assertIn(key, _PF_SPLIT_KEYS)


if __name__ == "__main__":
    unittest.main()
