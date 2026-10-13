"""逐週欄位健康：重演幾單真事故，確認趨勢判斷捉得到。

- 2026-08-22：`pace_figure_score` 十個場次全部中性 60、場內 SD 0.00，佔 12.2%
  權重，九個 suite 全綠。（歸檔 Logic 當日已被修正版覆蓋，真語料回溯唔到，
  所以要喺度用 fixture 重演。）
- 結果 CSV `Time` 由 ~100% 跌到 0%；`Margin` 由 2026-W35 起 0%。
- engine 自己講 exact 60 唔可靠：一個 leaf 可以全部 fallback 但分數唔係 60。
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "shared_racing" / "scripts"))

import field_health as fh  # noqa: E402

# 2026-W30 … W35 嘅星期一
WEEK_DAYS = ["2026-07-20", "2026-07-27", "2026-08-03", "2026-08-10", "2026-08-17", "2026-08-24"]
TODAY = dt.date(2026, 8, 31)  # W36 星期一 → 最近完整週係 W35


def _race(n_horses: int, pf_dead: bool = False, sectional_fallback: bool = False) -> dict:
    horses = {}
    for i in range(1, n_horses + 1):
        horses[str(i)] = {"python_auto": {
            "feature_scores": {
                "form_score": 50.0 + i,
                "pace_figure_score": 60.0 if pf_dead else 55.0 + i,
                "sectional_score": 52.0 + i,
            },
            "feature_evidence_state": {
                "form_score": "observed",
                "sectional_score": "fallback" if sectional_fallback else "observed",
            },
            "score_provenance": {"form_score": "recent_form"},
        }}
    return {"horses": horses}


def _corpus(tmp: Path, *, dead_week: str | None = None, fallback_week: str | None = None) -> Path:
    """每週 3 個場次 × 8 場 × 10 匹 = 240 匹（過 MIN_HORSES）。"""
    root = tmp / "AU_Racing"
    for day in WEEK_DAYS:
        week = fh.iso_week(day)
        for venue in ("Alpha", "Beta", "Gamma"):
            meeting = root / f"{day} {venue} Race 1-8"
            meeting.mkdir(parents=True)
            for race in range(1, 9):
                payload = _race(10, pf_dead=(week == dead_week),
                                sectional_fallback=(week == fallback_week))
                (meeting / f"Race_{race}_Logic.json").write_text(json.dumps(payload), encoding="utf-8")
    return root


def _results_csv(path: Path, *, time_dead_from: str | None = None) -> Path:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["Date", "Track", "Race", *fh.RESULTS_COLUMNS])
        writer.writeheader()
        for day in WEEK_DAYS:
            for i in range(250):
                dead = time_dead_from and day >= time_dead_from
                writer.writerow({"Date": day, "Track": "X", "Race": 1, "Distance": 1200,
                                 "Condition": "Good 4", "Pos": i % 10 + 1, "Horse": f"H{i}",
                                 "Barrier": 1, "Weight": "58kg", "Jockey": "J", "Trainer": "T",
                                 "Margin": "1.2L", "SP": "$3.00",
                                 "Time": "" if dead else "01:10.000"})
    return path


class RecordTests(unittest.TestCase):
    def test_record_is_idempotent(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            root = _corpus(tmp)
            ledger = tmp / "ledger.jsonl"
            csv_path = _results_csv(tmp / "results.csv")
            fh.record("au", root, "2026-07-01", ledger, csv_path)
            first = ledger.read_text(encoding="utf-8").splitlines()
            fh.record("au", root, "2026-07-01", ledger, csv_path)
            second = ledger.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(first), len(second))
            keys = [(json.loads(l)["week"], json.loads(l)["source"], json.loads(l)["field"]) for l in second]
            self.assertEqual(len(keys), len(set(keys)), "同一個 (week, source, field) 只可以有一行")

    def test_record_covers_all_four_sources(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            rows = fh.record("au", _corpus(tmp), "2026-07-01", tmp / "l.jsonl",
                             _results_csv(tmp / "results.csv"))
            self.assertEqual({r["source"] for r in rows}, set(fh.SOURCES))


class TrendTests(unittest.TestCase):
    def _findings(self, **corpus_kwargs):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            csv_kwargs = corpus_kwargs.pop("csv", {})
            ledger = tmp / "l.jsonl"
            fh.record("au", _corpus(tmp, **corpus_kwargs), "2026-07-01", ledger,
                      _results_csv(tmp / "results.csv", **csv_kwargs))
            return fh.trend(fh.read_ledger(ledger), today=TODAY)

    def test_healthy_corpus_is_quiet(self):
        week, findings = self._findings()
        self.assertEqual(week, "2026-W35")
        self.assertEqual(findings, [])

    def test_pace_figure_going_dead_is_caught(self):
        """2026-08-22 重演：成週 pace_figure_score 全部 60、SD 0。"""
        _week, findings = self._findings(dead_week="2026-W35")
        hits = {(f["source"], f["field"], f["status"]) for f in findings}
        self.assertIn(("leaf", "pace_figure_score", "dead"), hits)

    def test_fallback_without_sixty_is_caught(self):
        """分數照樣散開、唔係 60，但 evidence 全部 fallback —— neutral_rate 睇唔到。"""
        _week, findings = self._findings(fallback_week="2026-W35")
        hits = {(f["source"], f["field"]) for f in findings}
        self.assertIn(("evidence", "sectional_score"), hits)
        self.assertNotIn(("leaf", "sectional_score"), hits)

    def test_results_csv_column_dying_is_caught_and_dated(self):
        _week, findings = self._findings(csv={"time_dead_from": "2026-08-17"})
        time = [f for f in findings if f["source"] == "results_csv" and f["field"] == "Time"]
        self.assertEqual(len(time), 1)
        self.assertEqual(time[0]["status"], "dead")
        self.assertEqual(time[0]["since"], "2026-W34")

    def test_current_partial_week_is_not_the_default_target(self):
        """今個星期未完、CSV 樣本未夠，判咗只會漏報 —— 預設要揀上一個完整週。"""
        rows = [{"week": w, "source": "leaf", "field": "x", "n": 500, "neutral_rate": 0.0, "spread": 5.0}
                for w in ("2026-W33", "2026-W34", "2026-W35", "2026-W36")]
        self.assertEqual(fh.latest_week(rows, TODAY), "2026-W35")

    def test_field_vanishing_is_reported_missing(self):
        rows = []
        for w in ("2026-W32", "2026-W33", "2026-W34"):
            rows.append({"week": w, "source": "leaf", "field": "gone", "n": 500, "neutral_rate": 0.0, "spread": 5.0})
        for w in ("2026-W32", "2026-W33", "2026-W34", "2026-W35"):
            rows.append({"week": w, "source": "leaf", "field": "kept", "n": 500, "neutral_rate": 0.0, "spread": 5.0})
        _week, findings = fh.trend(rows, "2026-W35")
        self.assertEqual([(f["field"], f["status"]) for f in findings], [("gone", "missing")])

    def test_thin_week_is_not_judged(self):
        rows = [{"week": w, "source": "results_csv", "field": "Time", "n": 500, "fill_rate": 1.0}
                for w in ("2026-W32", "2026-W33", "2026-W34")]
        rows.append({"week": "2026-W35", "source": "results_csv", "field": "Time", "n": 50, "fill_rate": 0.0})
        _week, findings = fh.trend(rows, "2026-W35")
        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
