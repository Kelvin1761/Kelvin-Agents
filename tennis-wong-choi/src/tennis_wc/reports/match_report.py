from __future__ import annotations

import json

from tennis_wc.database.db import get_connection


def get_latest_match_prediction(match_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT p.*, m.match_date, m.round, t.name AS tournament_name, tl.level, tl.surface
            FROM predictions p
            JOIN matches m ON m.id = p.match_id
            JOIN tournaments t ON t.id = m.tournament_id
            JOIN tournament_levels tl ON tl.tournament_id = m.tournament_id AND tl.tour = m.tour
            WHERE p.match_id = ?
            ORDER BY p.id DESC
            LIMIT 1
            """,
            (match_id,),
        ).fetchone()
    return dict(row) if row else None


def render_match_report(match_id: int) -> str:
    row = get_latest_match_prediction(match_id)
    if not row:
        return f"搵唔到賽事 {match_id} 嘅 prediction。\n"
    payload = json.loads(row["pricing_json"])
    pricing = payload["pricing"]
    filter_result = payload["filter"]
    lines = [
        f"# 單場分析報告：{match_id}",
        "",
        f"賽事：{row['tournament_name']}",
        f"日期：{row['match_date']}",
        f"級別：{row['level']}",
        f"圈數：{row['round']}",
        f"場地：{row['surface']}",
        "",
        f"選擇：{row['selection_name']}",
        f"決策：{row['decision']}",
        f"注碼：{row['stake_units']}u",
        f"Edge：{row['edge']}",
        "",
        "## 定價",
        "",
        json.dumps(pricing, indent=2, sort_keys=True),
        "",
        "## 過濾器",
        "",
        json.dumps(filter_result, indent=2, sort_keys=True),
    ]
    return "\n".join(lines) + "\n"
