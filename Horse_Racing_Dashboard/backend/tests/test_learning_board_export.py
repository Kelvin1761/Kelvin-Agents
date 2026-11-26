"""自學面板匯出：抄檔唔重計、精簡、冇檔照列。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from services.learning_board_export import export_learning_board  # noqa: E402


def test_export(tmp_path):
    r = tmp_path / "reviews" / "hkjc"
    r.mkdir(parents=True)
    rv = {"date": "2026-11-25", "summary": {"races": 9, "slots": 27, "model_top3_hits": 12}, "reconciliation": {"ok": True},
          "cohorts": [{"label": "A", "today_n": 5, "today_hits": 3, "today_resid_pp": 10, "trail_model_ci_pp": [1, 2],
                       "reading": "跨日同方向"}, {"label": "B", "today_n": 5, "trail_model_ci_pp": None}],
          "meetings": [{"meeting": "2026-11-25_HappyValley", "labels": {"Miss": 1}, "races": [
              {"race": 2, "label": "Miss", "over": [{"name": "X", "rank": 1, "pos": 9, "why": ["a"], "incident": {"labels": ["受阻"]}}],
               "under": []}, {"race": 3, "label": "Good", "over": [], "under": []}]}]}
    (r / "2026-11-25.json").write_text(json.dumps(rv, ensure_ascii=False), encoding="utf-8")
    (r / "2026-11-25.ai.json").write_text(json.dumps({"status": "ok", "narrative": "今晚…", "dropped_sentences": ["x"],
                                                      "hypotheses": [{"title": "T", "cohort": ["tag:A"], "direction": "model_under",
                                                                      "review": {"leak": False, "worth": True}}]}, ensure_ascii=False))
    (tmp_path / "learning").mkdir()
    (tmp_path / "learning" / "hypotheses.jsonl").write_text(json.dumps({"id": "H", "domain": "hkjc", "state": "watching"}) + "\n")
    (tmp_path / "learning" / "gap_report.json").write_text(json.dumps({"date": "2026-11-26", "domains": {"au": {"gaps": [{"field": "Time"}] * 20, "gaps_total": 20}}}))
    b = export_learning_board(tmp_path)
    day = b["domains"]["hkjc"]["days"][0]
    assert [c["label"] for c in day["cohorts"]] == ["A"]                 # 冇 CI 嘅唔帶
    assert day["misses"][0]["over"][0]["incident"] == ["受阻"] and len(day["misses"]) == 1
    assert day["ai"]["hypotheses"][0]["verdict"] == "值得驗證" and day["ai"]["dropped"] == 1
    assert b["domains"]["au"]["days"] == [] and b["hypotheses"][0]["id"] == "H"
    assert len(b["gap_report"]["domains"]["au"]["gaps"]) == 8 and b["health_sweep"] is None
