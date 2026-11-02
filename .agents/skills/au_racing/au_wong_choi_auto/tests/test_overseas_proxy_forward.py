"""EXP-20261102-12 forward：反事實「冇代理」近績質素分一定要同引擎關代理時一樣。

2026-11-02 已用 10-17 Caulfield Cup 實測（開／關 `WC_AU_OVERSEAS_RATING_PROXY` 各跑一次）3/3 匹一致；
呢度鎖住三條路徑（場內標準分、後備組合、增程縮程 −5）。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts"))

from au_overseas_proxy_forward import proxy_rank_error, without_proxy_score  # noqa: E402


class WithoutProxyScoreTests(unittest.TestCase):
    def test_field_relative(self) -> None:
        detail = {"raw": 0.8, "run_count": 4, "field_count": 12, "field_mean": 0.5, "field_stdev": 0.3}
        self.assertAlmostEqual(without_proxy_score({}, detail), 80.0)

    def test_composite_fallback_when_too_few_runs(self) -> None:
        detail = {"raw": 0.8, "run_count": 1, "field_count": 12, "field_mean": 0.5, "field_stdev": 0.3}
        features = {"form_score": 70.0, "performance_quality_score": 50.0}
        self.assertAlmostEqual(without_proxy_score(features, detail), 62.0)

    def test_trip_change_penalty(self) -> None:
        detail = {"raw": 0.5, "run_count": 3, "field_count": 8, "field_mean": 0.5, "field_stdev": 0.2,
                  "trip_change": {"today": 3200, "last": 2400, "delta": -5.0}}
        self.assertAlmostEqual(without_proxy_score({}, detail), 55.0)

    def test_rank_error_counts_proxy_horses_only(self) -> None:
        race = {"rows": [{"n": 1, "ability": 80, "pos": 3, "proxy": True},
                         {"n": 2, "ability": 70, "pos": 1, "proxy": False},
                         {"n": 3, "ability": 60, "pos": 2, "proxy": False}]}
        self.assertEqual(proxy_rank_error([race]), (2.0, 1))


if __name__ == "__main__":
    unittest.main()
