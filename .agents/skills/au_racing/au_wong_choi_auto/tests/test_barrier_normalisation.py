"""實際出閘檔位 —— 退出馬之後閘位會重編。

守住三樣：乾淨場次係 no-op、污染場次真係修正、唔安全嘅輸入唔動。
再加一個實測性質嘅回歸：分桶會由外向內移，唔會反方向。
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "scripts"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from au_racing_engine.engine_core import normalise_field_barriers  # noqa: E402


def field(barriers):
    return {"horses": {str(i + 1): {"barrier": b} for i, b in enumerate(barriers)}}


def barriers_of(logic):
    return [logic["horses"][k]["barrier"] for k in sorted(logic["horses"], key=int)]


class TestBarrierNormalisation(unittest.TestCase):
    def test_clean_field_is_a_noop(self):
        """冇退出馬（檔位 1..N 連續）—— 一個都唔應該改。"""
        logic = field([3, 1, 5, 2, 4])
        self.assertEqual(normalise_field_barriers(logic), 0)
        self.assertEqual(barriers_of(logic), [3, 1, 5, 2, 4])

    def test_scratched_field_is_renumbered(self):
        """原始抽籤 2/5/9/13，四匹出賽 → 實際出閘 1/2/3/4。"""
        logic = field([2, 5, 9, 13])
        self.assertEqual(normalise_field_barriers(logic), 4)
        self.assertEqual(barriers_of(logic), [1, 2, 3, 4])

    def test_order_is_preserved(self):
        """保序：重編之後嘅相對次序一定同原本一樣。"""
        raw = [11, 2, 14, 7, 3]
        logic = field(raw)
        normalise_field_barriers(logic)
        got = barriers_of(logic)
        self.assertEqual(
            [i for i, _ in sorted(enumerate(raw), key=lambda t: t[1])],
            [i for i, _ in sorted(enumerate(got), key=lambda t: t[1])],
        )

    def test_buckets_only_move_inward(self):
        """實測性質：修正只會令馬由外向內，唔會反方向。"""
        logic = field([2, 6, 10, 15])
        normalise_field_barriers(logic)
        for raw, got in zip([2, 6, 10, 15], barriers_of(logic)):
            self.assertLessEqual(got, raw)

    def test_idempotent(self):
        logic = field([2, 5, 9, 13])
        normalise_field_barriers(logic)
        self.assertEqual(normalise_field_barriers(logic), 0)

    def test_missing_or_duplicate_barriers_are_left_alone(self):
        for barriers in ([1, None, 3], [1, 2, 2], [1, 0, 3]):
            logic = field(barriers)
            self.assertEqual(normalise_field_barriers(logic), 0)
            self.assertEqual(barriers_of(logic), barriers)

    def test_tactical_plan_is_rebuilt_for_changed_horses(self):
        """敘述會引用檔位號，所以改咗檔位就一定要重建 —— 唔然報告會講錯。"""
        logic = field([4, 9, 14])
        for h in logic["horses"].values():
            h["_data"] = {"facts_section": ""}
            h["tactical_plan"] = {"expected_position": "STALE", "race_scenario": "STALE"}
        self.assertEqual(normalise_field_barriers(logic), 3)
        for h in logic["horses"].values():
            self.assertNotEqual(h["tactical_plan"]["race_scenario"], "STALE")

    def test_single_runner_and_empty_field(self):
        for logic in ({"horses": {}}, {"horses": {"1": {"barrier": 7}}}, {}):
            self.assertEqual(normalise_field_barriers(logic), 0)


if __name__ == "__main__":
    unittest.main()
