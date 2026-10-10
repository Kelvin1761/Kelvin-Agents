"""HKJC 三個入分 leaf 唔喺 `feature_scores`，數據合約一定要睇到佢哋。

2026-10-10：`race_shape_context_score`（27.4% 權重）、`formline_strength_score`
（8%）同 `trackwork_trend_score` 存喺 `python_auto.derived_feature_scores`。
閘門只讀 `feature_scores`，所以三個死咗都一樣綠燈發佈 —— 同 AU 2026-08-22
`pace_figure_score` 靜靜死咗 12.2% 權重同一個形狀。
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "shared_racing" / "scripts"))

from data_contract import PLATFORMS, check, observe  # noqa: E402

SCORED_DERIVED = ("race_shape_context_score", "formline_strength_score",
                  "trackwork_trend_score")


def _race(dead: str | None = None, horses: int = 8) -> dict:
    out = {}
    for i in range(1, horses + 1):
        derived = {key: 50.0 + 4 * i for key in SCORED_DERIVED}
        derived["margin_trend_score"] = 60.0          # 展示用，唔應該被收
        if dead:
            derived[dead] = 60.0
        out[str(i)] = {"python_auto": {
            "feature_scores": {"form_score": 40.0 + 5 * i},
            "derived_feature_scores": derived,
        }}
    return {"horses": out}


def _write(tmp: Path, races: list[dict]) -> list[str]:
    paths = []
    for n, payload in enumerate(races, start=1):
        p = tmp / f"Race_{n}_Logic.json"
        p.write_text(json.dumps(payload), encoding="utf-8")
        paths.append(str(p))
    return paths


class HkjcDerivedLeafTests(unittest.TestCase):
    def test_scored_derived_leaves_are_observed_for_hkjc(self):
        with tempfile.TemporaryDirectory() as t:
            fields, *_ = observe(_write(Path(t), [_race()]), "hkjc")
        for key in SCORED_DERIVED:
            self.assertIn(key, fields)
        self.assertNotIn("margin_trend_score", fields)

    def test_au_does_not_pick_up_hkjc_blocks(self):
        with tempfile.TemporaryDirectory() as t:
            fields, *_ = observe(_write(Path(t), [_race()]), "au")
        for key in SCORED_DERIVED:
            self.assertNotIn(key, fields)

    def test_each_dead_derived_leaf_blocks_publishing(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            healthy, *_ = observe(_write(tmp, [_race()] * 3), "hkjc")
        baseline = {"fields": {k: v.summarise() for k, v in healthy.items()}}
        for key in SCORED_DERIVED:
            with self.subTest(key=key), tempfile.TemporaryDirectory() as t:
                violations, _ = check(baseline, _write(Path(t), [_race(dead=key)] * 3), "hkjc")
                errors = [v for v in violations
                          if v.field_name == key and v.check == "dead-field" and v.severity == "error"]
                self.assertTrue(errors, f"{key} 死咗但閘門冇攔：{violations}")

    def test_hkjc_config_lists_only_scored_keys(self):
        blocks = PLATFORMS["hkjc"]["extra_score_blocks"]
        self.assertEqual(tuple(blocks["derived_feature_scores"]), SCORED_DERIVED)


if __name__ == "__main__":
    unittest.main()
