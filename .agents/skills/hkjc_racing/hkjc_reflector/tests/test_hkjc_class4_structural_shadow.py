from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "hkjc_class4_structural_shadow.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("hkjc_class4_structural_shadow", SCRIPT)
SHADOW = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(SHADOW)


def sample_record(*, top2_delta: int = 1, revision_source: str = "test") -> dict:
    baseline = {
        "top1_win": 0, "top2_hits": 1, "both_top2_place": 0,
        "top3_hits": 1, "top4_hits": 1, "top4_all": 0,
        "top5_hits": 1, "top5_all": 0, "winner_mrr": 0.25,
    }
    candidate = dict(baseline)
    candidate["top2_hits"] += top2_delta
    candidate["both_top2_place"] = int(candidate["top2_hits"] == 2)
    return {
        "model_version": "v-test", "phase": "prospective", "source": revision_source,
        "event_key": "2026-07-15|沙田|1", "date": "2026-07-15",
        "meeting_name": "2026-07-15_ShaTin", "race_number": 1,
        "venue": "沙田", "track": "Turf", "course": "A", "distance_num": 1200,
        "race_class": "Class 4", "is_target_class": True, "field_size": 12,
        "actual_top3": [1, 2, 3],
        "models": {
            "baseline": baseline,
            "primary_full_support": candidate,
            "challenger_trackwork_variant": candidate,
        },
    }


class ShadowLedgerTests(unittest.TestCase):
    def test_market_feature_guard(self) -> None:
        SHADOW.assert_market_free(["raw_l400", "prior_combo_place_rate"])
        with self.assertRaises(ValueError):
            SHADOW.assert_market_free(["market_rank"])

    def test_append_is_idempotent_and_revisions_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.jsonl"
            original = sample_record()
            first = SHADOW.append_ledger(ledger, [original])
            second = SHADOW.append_ledger(ledger, [original])
            changed = sample_record(top2_delta=0, revision_source="corrected")
            third = SHADOW.append_ledger(ledger, [changed])
            self.assertEqual(first, {"appended": 1, "unchanged": 0, "revised": 0})
            self.assertEqual(second, {"appended": 0, "unchanged": 1, "revised": 0})
            self.assertEqual(third, {"appended": 1, "unchanged": 0, "revised": 1})
            rows = SHADOW._read_ledger(ledger)
            self.assertEqual([row["revision"] for row in rows], [1, 2])

    def test_report_section_is_replaced_not_duplicated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "report.md"
            report.write_text("# Reflector\n", encoding="utf-8")
            record = sample_record()
            payload = {
                "summaries": {
                    name: SHADOW._summarize([record], name)
                    for name in ("baseline", "primary_full_support", "challenger_trackwork_variant")
                }
            }
            tracker = {
                "prospective": {"races": 1},
                "promotion": {"primary_full_support": {"eligible_for_manual_review": False}},
            }
            SHADOW.append_to_reflector_report(report, payload, tracker)
            SHADOW.append_to_reflector_report(report, payload, tracker)
            text = report.read_text(encoding="utf-8")
            self.assertEqual(text.count(SHADOW.REPORT_START), 1)
            self.assertEqual(text.count(SHADOW.REPORT_END), 1)


if __name__ == "__main__":
    unittest.main()
