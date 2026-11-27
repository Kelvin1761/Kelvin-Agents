"""Forward 測試總板匯出：重用 shared_wong_choi.forward_board，passthrough missing／stale。"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from services.forward_board_export import export_forward_board  # noqa: E402


def test_export_forward_board(tmp_path, monkeypatch):
    monkeypatch.setenv("WC_FORWARD_BOARD_ROOT", str(tmp_path))
    now = datetime.now(timezone.utc)
    (tmp_path / "au.json").write_text(json.dumps({
        "domain": "au",
        "updated_at": (now - timedelta(hours=1)).isoformat(),
        "tests": [
            {"key": "s2_shadow", "label": "S2 速度（shadow）", "experiment": "EXP-20261016-03",
             "count": 120, "minimum": 300, "unit": "場", "status": "collecting", "note": "",
             "roi": -0.085, "ci": [-0.21, 0.04]},
            {"key": "wt_blind", "label": "WinningTime 速度盲測", "experiment": "EXP-20260927-02",
             "count": 2044, "minimum": 2000, "unit": "場", "status": "decided", "note": "已達標"},
        ],
    }, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "hkjc.json").write_text(json.dumps({
        "domain": "hkjc",
        "updated_at": (now - timedelta(days=10)).isoformat(),
        "tests": [
            {"key": "hk_ready", "label": "沙田檔位前向", "experiment": "EXP-20261001-01",
             "count": 25, "minimum": 20, "unit": "場", "status": "ready", "note": "夠數待判"},
        ],
    }, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "nba.json").write_text(json.dumps({
        "domain": "nba",
        "updated_at": (now - timedelta(hours=2)).isoformat(),
        "tests": [
            {"key": "nba_ou", "label": "NBA 大細盤前向", "experiment": "EXP-20261109-04",
             "count": 45, "minimum": 200, "unit": "注", "status": "collecting", "note": ""},
        ],
    }, ensure_ascii=False), encoding="utf-8")
    # tennis.json 故意唔寫，測 missing domain passthrough

    out = export_forward_board()
    assert isinstance(out["generated_at"], str) and out["generated_at"]
    assert out["status"] == "valid"
    assert set(out["domains"].keys()) == {"au", "hkjc", "nba", "tennis"}
    assert out["domains"]["au"]["missing"] is False
    assert out["domains"]["au"]["stale"] is False
    assert out["domains"]["au"]["tests"][0]["roi"] == -0.085
    assert out["domains"]["hkjc"]["missing"] is False
    assert out["domains"]["hkjc"]["stale"] is True
    assert out["domains"]["nba"]["missing"] is False
    assert out["domains"]["nba"]["stale"] is False
    assert out["domains"]["tennis"]["missing"] is True
    assert out["domains"]["tennis"]["stale"] is True
    assert out["domains"]["tennis"]["tests"] == []
    assert out["summary"]["collecting"] == 2
    assert out["summary"]["decided"] == 1
    assert out["summary"]["ready"] == 1
    assert set(out["summary"]["stale_domains"]) == {"hkjc", "tennis"}
