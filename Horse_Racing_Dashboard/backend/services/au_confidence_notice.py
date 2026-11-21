"""AU 賽事可信度提示（純顯示，唔入評分、唔郁落注）—— Kelvin 2026-11-21：大爛地標「預測可信度較低」。

「乜嘢算大爛地」只有一個定義：引擎 `au_racing_engine.stability.is_heavy_going`（H2 forward 同一個）。
證據：EXP-20261121-38／-39（大爛地 overlay、分場地權重、場地相似度加權全部 REJECT —— 係場地本身難預測，
唔係用錯資訊）；頭二選位注上名率 大爛地 44.2%／48.4%（dev／holdout）vs 其他場地 50–54%。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / ".agents/skills/au_racing/au_wong_choi_auto/scripts"))
from au_racing_engine.stability import is_heavy_going  # noqa: E402

HEAVY_NOTICE = {
    "level": "low",
    "label": "大爛地 · 預測可信度較低",
    "detail": "大爛地頭二選上名率約 44–48%，其他場地約 50–54%；試過三種調整（逐項加權、分場地權重、按場地揀往績）都改善唔到，"
              "係場地本身難預測。純提示，唔入評分、唔郁排名。",
    "evidence": "EXP-20261121-38, EXP-20261121-39",
}


def confidence_notice(going) -> dict | None:
    return dict(HEAVY_NOTICE, going=str(going)) if going and is_heavy_going(going) else None
