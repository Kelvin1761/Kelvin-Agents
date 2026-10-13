"""失手體檢：分類規則、只算失手場、ledger 唔重複、報告段落可以重寫。

背景：EXP-20261013-05 由一場失手追出 `Finished -3/7` 被 regex 丟走；
EXP-20261013-01 證實失手共識唔可以拎嚟調權重。所以呢個工具只做分類。
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "shared_racing" / "scripts"))

import miss_autopsy as ma  # noqa: E402


def _preds(order):
    return [{"horse_no": h, "derived_rank": i} for i, h in enumerate(order, 1)]


def _actual(order):
    return [{"placing": i, "horse_no": h} for i, h in enumerate(order, 1)]


def _logic(*, tier="clear", tied=False, swap=None, pf_alert=False, weak=None):
    weak = weak or {}
    horses = {}
    for h in range(1, 11):
        states = {f"leaf_{k}": ("fallback" if k < weak.get(h, 0) else "observed") for k in range(8)}
        horses[str(h)] = {"python_auto": {"feature_evidence_state": states}}
    return {
        "horses": horses,
        "python_auto_verdict": {
            "confidence_tier": tier, "top_pick_tied": tied, "top1_top3_gap": 6.0,
            "pace_figure_coverage": {"alert": pf_alert, "pct": 70.0 if pf_alert else 100.0},
            "decision_trace": {"thin_evidence_swap": swap},
        },
    }


PREDS = _preds([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
MISS = _actual([7, 8, 9])


class ClassifyTests(unittest.TestCase):
    def test_clean_inputs_clear_margin_is_model_wrong(self):
        self.assertEqual(ma.classify_race(1, _logic(), PREDS, MISS)["bucket"], "model_wrong")

    def test_tight_race_is_crowded(self):
        entry = ma.classify_race(1, _logic(tier="tight"), PREDS, MISS)
        self.assertEqual(entry["bucket"], "crowded")
        self.assertEqual([t["rule"] for t in entry["triggers"]], ["tight"])

    def test_thin_evidence_swap_is_input_anomaly(self):
        entry = ma.classify_race(1, _logic(swap={"demoted": "1", "promoted": "2"}), PREDS, MISS)
        self.assertEqual(entry["bucket"], "input_anomaly")

    def test_input_anomaly_beats_crowded(self):
        entry = ma.classify_race(1, _logic(tier="tight", pf_alert=True), PREDS, MISS)
        self.assertEqual(entry["bucket"], "input_anomaly")
        self.assertEqual({t["rule"] for t in entry["triggers"]}, {"pace_figure_alert", "tight"})

    def test_thin_placegetter_needs_four_weak_leaves(self):
        """≥2 會喺 28% 馬匹觸發（太鬆）；門檻係 4。"""
        three = ma.classify_race(1, _logic(weak={8: 3}), PREDS, MISS)
        four = ma.classify_race(1, _logic(weak={8: 4}), PREDS, MISS)
        self.assertEqual(three["bucket"], "model_wrong")
        self.assertEqual(four["bucket"], "input_anomaly")
        self.assertIn("8", four["triggers"][0]["value"])

    def test_unscored_placegetter_and_dropped_rows(self):
        entry = ma.classify_race(1, _logic(), PREDS, _actual([7, 8, 99]), dropped_rows=1)
        rules = {t["rule"] for t in entry["triggers"]}
        self.assertEqual(rules, {"unscored_placegetter", "dropped_result_rows"})
        self.assertEqual(entry["actual_top3_model_ranks"], [7, 8, None])

    def test_data_health_issue(self):
        entry = ma.classify_race(1, _logic(), PREDS, MISS, health_issues=["MISSING_FACTS"])
        self.assertEqual(entry["bucket"], "input_anomaly")

    def test_missing_verdict_fields_do_not_crash(self):
        """HKJC Logic 冇 evidence state／confidence_tier。"""
        entry = ma.classify_race(1, {"horses": {}}, PREDS, MISS)
        self.assertEqual(entry["bucket"], "model_wrong")


class OutputTests(unittest.TestCase):
    def _result(self, meeting="2026-10-11 Seymour Race 1-10", races=None):
        races = races if races is not None else [
            {"race": 2, "label": "Miss", "bucket": "input_anomaly",
             "triggers": [{"rule": "pace_figure_alert", "value": 70.0}, {"rule": "tied", "value": 0.2}],
             "actual_top3_model_ranks": [1, 4, None]},
        ]
        return {"meeting": meeting, "status": "ok", "evaluated": "snap", "races": races,
                "summary": {"scored_races": 10, "misses": len(races),
                            "buckets": {"input_anomaly": len(races), "crowded": 0, "model_wrong": 0}}}

    def test_ledger_replaces_same_meeting(self):
        with tempfile.TemporaryDirectory() as t:
            ledger = Path(t) / "l.jsonl"
            ma.write_ledger(ledger, self._result())
            ma.write_ledger(ledger, self._result())
            ma.write_ledger(ledger, self._result(meeting="2026-10-12 Tamworth Race 1-8", races=[]))
            rows = [json.loads(l) for l in ledger.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(sum(1 for r in rows if r["kind"] == "race"), 1)
            self.assertEqual(sum(1 for r in rows if r["kind"] == "summary"), 2)
            self.assertEqual(rows[0]["week"], "2026-W41")

    def test_report_section_is_replaced_not_duplicated(self):
        with tempfile.TemporaryDirectory() as t:
            report = Path(t) / "report.md"
            report.write_text("# 覆盤\n\n內容\n", encoding="utf-8")
            block = ma.render_markdown(self._result())
            self.assertTrue(ma.append_report(report, block))
            self.assertTrue(ma.append_report(report, block))
            text = report.read_text(encoding="utf-8")
            self.assertEqual(text.count(ma.REPORT_BEGIN), 1)
            self.assertIn("內容", text)
            self.assertIn("1／4／?", text)

    def test_missing_report_is_not_created(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertFalse(ma.append_report(Path(t) / "nope.md", "x"))


if __name__ == "__main__":
    unittest.main()
