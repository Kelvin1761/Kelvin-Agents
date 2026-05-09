from __future__ import annotations

import json
from pathlib import Path

from tennis_wc.database.db import get_connection
from tennis_wc.ingestion.sportsbet_fixture_mapping import sportsbet_competition_meta


PROJECT_ROOT = Path(__file__).resolve().parents[4]


def latest_predictions_for_date(match_date: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT p.*, m.match_date, m.round, t.name AS tournament_name, tl.level, tl.surface
            FROM predictions p
            JOIN matches m ON m.id = p.match_id
            JOIN tournaments t ON t.id = m.tournament_id
            JOIN tournament_levels tl ON tl.tournament_id = m.tournament_id AND tl.tour = m.tour
            WHERE m.match_date = ?
              AND EXISTS (
                SELECT 1
                FROM odds_snapshots o
                WHERE o.match_id = m.id
                  AND o.source_provider = 'sportsbet'
              )
              AND p.id IN (
                SELECT MAX(id)
                FROM predictions
                GROUP BY match_id
              )
            ORDER BY p.decision, p.edge DESC
            """,
            (match_date,),
        ).fetchall()
    return [dict(row) for row in rows]


def analysis_output_dir(match_date: str) -> Path:
    return PROJECT_ROOT / f"{match_date} Tennis Analysis"


def generate_daily_report(match_date: str, output_dir: str | Path | None = None) -> Path:
    rows = latest_predictions_for_date(match_date)
    source_status = source_status_for_date(match_date)
    unanalysed = unanalysed_sportsbet_rows(match_date)
    output_dir = Path(output_dir) if output_dir is not None else analysis_output_dir(match_date)
    output_path = output_dir / "Tennis_Daily_Report.txt"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_daily_report(match_date, rows, source_status, unanalysed), encoding="utf-8")
    export_market_odds_report(match_date, output_dir)
    return output_path


def export_market_odds_report(match_date: str, output_dir: str | Path | None = None) -> Path:
    output_dir = Path(output_dir) if output_dir is not None else analysis_output_dir(match_date)
    output_path = output_dir / "Tennis_Market_Odds.txt"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_market_odds_report(match_date), encoding="utf-8")
    return output_path


def source_status_for_date(match_date: str) -> dict:
    with get_connection() as conn:
        latest_run_errors = conn.execute(
            """
            SELECT response_json
            FROM raw_api_responses
            WHERE provider_name = 'tennis_wc_pipeline'
              AND entity_type = 'run_daily_source_errors'
              AND entity_external_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (match_date,),
        ).fetchone()
        latest_raw = conn.execute(
            """
            SELECT id
            FROM raw_api_responses
            WHERE entity_type = 'odds'
              AND entity_external_id = ?
              AND provider_name = 'sportsbet'
            ORDER BY id DESC
            LIMIT 1
            """,
            (match_date,),
        ).fetchone()
        raw_id = int(latest_raw["id"]) if latest_raw else None
        sportsbet = conn.execute(
            """
            SELECT COUNT(*) AS odds_rows, COUNT(match_id) AS linked_rows, MAX(fetched_at) AS latest_fetch
            FROM odds_snapshots
            WHERE source_provider = 'sportsbet' AND raw_response_id = ?
            """,
            (raw_id,),
        ).fetchone()
        bsd_error = conn.execute(
            """
            SELECT response_json
            FROM raw_api_responses
            WHERE provider_name = 'bsd_tennis' AND status_code >= 400
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        market_count = conn.execute(
            """
            SELECT COUNT(*) AS rows, COUNT(DISTINCT market_key) AS markets
            FROM market_odds_snapshots mo
            JOIN matches m ON m.id = mo.match_id
            WHERE m.match_date = ?
              AND mo.id IN (
                SELECT MAX(mo2.id)
                FROM market_odds_snapshots mo2
                JOIN matches m2 ON m2.id = mo2.match_id
                WHERE m2.match_date = ?
                GROUP BY mo2.match_id, mo2.market_key, mo2.market_name, mo2.selection_name, COALESCE(mo2.line, -999999)
              )
            """,
            (match_date, match_date),
        ).fetchone()
    return {
        "sportsbet_odds_rows": int(sportsbet["odds_rows"] or 0),
        "sportsbet_linked_rows": int(sportsbet["linked_rows"] or 0),
        "sportsbet_latest_fetch": sportsbet["latest_fetch"],
        "bsd_fixture_status": _bsd_status(bsd_error["response_json"] if bsd_error else None),
        "fixture_note": "Sportsbet odds-backed provisional fixtures enabled; unconfirmed competitions remain NO_BET.",
        "history_source": "Jeff Sackmann ATP/WTA snapshots + local Elo cache",
        "market_odds_note": f"{int(market_count['rows'] or 0)} selections across {int(market_count['markets'] or 0)} market types. Non-match-winner markets are review-only.",
        "latest_run_errors": json.loads(latest_run_errors["response_json"]) if latest_run_errors else [],
    }


def clear_pipeline_source_errors(match_date: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            DELETE FROM raw_api_responses
            WHERE provider_name = 'tennis_wc_pipeline'
              AND entity_type = 'run_daily_source_errors'
              AND entity_external_id = ?
            """,
            (match_date,),
        )


def unanalysed_sportsbet_rows(match_date: str) -> list[dict]:
    with get_connection() as conn:
        raw_rows = conn.execute(
            """
            SELECT response_json
            FROM raw_api_responses
            WHERE entity_type = 'odds'
              AND entity_external_id = ?
              AND provider_name = 'sportsbet'
            ORDER BY id DESC
            LIMIT 1
            """,
            (match_date,),
        ).fetchone()
        linked = {
            row["event_id"]
            for row in conn.execute(
                "SELECT DISTINCT event_id FROM odds_snapshots WHERE match_id IS NOT NULL"
            ).fetchall()
        }
    if not raw_rows:
        return []
    rows = json.loads(raw_rows["response_json"])
    unanalysed = []
    for row in rows:
        if str(row.get("event_id")) in linked:
            continue
        meta = sportsbet_competition_meta(row.get("competition"))
        unanalysed.append(
            {
                "competition": row.get("competition") or "UNKNOWN",
                "match": f"{row.get('player_a_name')} v {row.get('player_b_name')}",
                "reason": meta.reason or "not_linked_to_feature_snapshot",
                "event_url": row.get("event_url"),
            }
        )
    return unanalysed


def render_daily_report(match_date: str, rows: list[dict], source_status: dict | None = None, unanalysed: list[dict] | None = None) -> str:
    bets = [row for row in rows if row["decision"] == "BET"]
    watchlist = [row for row in rows if row["decision"] == "WATCHLIST"]
    no_bets = [row for row in rows if row["decision"] == "NO_BET"]
    source_status = source_status or {}
    unanalysed = unanalysed or []
    lines = [
        "Tennis Wong Choi 每日分析報告",
        f"日期：{match_date}",
        "",
        f"已分析賽事：{len(rows)}",
        f"建議投注：{len(bets)}",
        f"觀察名單：{len(watchlist)}",
        f"不下注：{len(no_bets)}",
        f"未能進入分析賽事：{len(unanalysed)}",
        "",
        "## 數據源狀態",
        "",
        f"- Sportsbet odds rows：{source_status.get('sportsbet_odds_rows', 0)}",
        f"- 已配對 / 已建 provisional fixture：{source_status.get('sportsbet_linked_rows', 0)}",
        f"- Sportsbet 最新抓取時間：{source_status.get('sportsbet_latest_fetch') or 'N/A'}",
        "- Bankroll：$500 virtual bankroll；1 unit = $5",
        "- Mode：SNAPSHOT_MODE（使用最近已成功保存嘅 Sportsbet / local history snapshot；唔扮 live odds）",
        f"- BSD fixture source：{source_status.get('bsd_fixture_status') or 'N/A'}",
        f"- Fixture 補齊策略：{source_status.get('fixture_note') or 'N/A'}",
        f"- 歷史數據 / Elo：{source_status.get('history_source') or 'N/A'}",
        f"- 多市場 odds：{source_status.get('market_odds_note') or 'N/A'}",
        "",
    ]
    run_errors = source_status.get("latest_run_errors") or []
    if run_errors:
        lines.extend(
            [
                "## 今次 full run 警告",
                "",
                "今次 live API refresh 未完整成功；以下報告只可作 debug / pipeline 檢查，唔應作真實下注清單。",
            ]
        )
        for error in run_errors:
            lines.append(f"- {_source_label(str(error.get('source')))}：{_source_error_label(str(error.get('error')))}")
        lines.append("")
    lines.extend(
        [
            "## 下注候選一覽",
            "",
            *_bet_summary_lines(bets),
            "",
            "## 注單摘要",
            "",
        ]
    )
    if not bets:
        lines.extend(["暫時未有通過所有 hard rule 嘅 BET。", ""])
    for idx, row in enumerate(bets + watchlist + no_bets, start=1):
        payload = json.loads(row["pricing_json"])
        pricing = payload["pricing"]
        filter_result = payload["filter"]
        lines.extend(
            [
                f"## {row['decision']} {idx}",
                "",
                f"賽事 ID：{row['match_id']}",
                f"賽事：{_display_label(row['tournament_name'])}",
                f"級別：{_display_label(row['level'])}",
                f"圈數：{_display_label(row['round'])}",
                f"場地：{_display_label(row['surface'])}",
                "市場：Match Winner",
                f"選擇：{_display_label(row['selection_name'])}",
                "",
                f"現時賠率：{_fmt(row['current_market_odds'])}",
                f"模型勝率：{_pct(row['model_probability'])}",
                f"公平賠率：{_fmt(row['fair_odds'])}",
                f"去水市場勝率：{_pct(row['no_vig_market_probability'])}",
                f"Edge：{_pct(row['edge'], signed=True)}",
                f"最低可接受賠率：{_fmt(row['minimum_acceptable_odds'])}",
                "",
                f"信心分：{row['confidence']}",
                f"風險：{row['risk']}",
                f"建議注碼：{_stake_label(row['stake_units'], row['decision'])}",
                f"決策：{row['decision']}",
                "",
                "主要模型原因：",
            ]
        )
        components = pricing.get("model", {}).get("components", [])
        for component in components[:5]:
            lines.append(f"- {component['name']}：勝率 {_pct(component['probability'])}，權重 {component['weight']}")
        red_flags = _report_red_flags(filter_result)
        lines.extend(["", "紅旗／注意事項："])
        if red_flags:
            lines.extend(f"- {flag}" for flag in red_flags)
        else:
            lines.append("- 無")
        lines.extend(["", ""])
    if unanalysed:
        lines.extend(["## 未分析 / 資料不足", ""])
        for row in unanalysed:
            lines.append(f"- {_display_label(row['competition'])}｜{_display_label(row['match'])}｜{_hk_reason(row['reason'])}")
            if row.get("event_url"):
                lines.append(f"  URL：{row['event_url']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_market_odds_report(match_date: str) -> str:
    rows = market_odds_for_date(match_date)
    lines = [
        "Tennis Wong Choi Market Odds Inventory",
        f"Date: {match_date}",
        "",
        "Pricing status: Match Winner is priced. Other markets are extracted for review only until a dedicated model is added.",
        "",
    ]
    current_match = None
    for row in rows:
        match_label = f"{row['tournament_name']} | {row['player_a_name']} v {row['player_b_name']}"
        if match_label != current_match:
            current_match = match_label
            lines.extend(["", f"## {match_label}", ""])
        status = _market_pricing_status(row)
        line = _fmt(row["line"])
        lines.append(
            f"- {row['market_name']} [{row['market_key']}] | "
            f"{row['selection_name']} | line {line} | odds {_fmt(row['odds'])} | {status}"
        )
    if not rows:
        lines.append("No market odds snapshots found.")
    return "\n".join(lines).strip() + "\n"


def market_odds_for_date(match_date: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                mo.*,
                t.name AS tournament_name,
                tl.level AS tournament_level,
                tl.surface AS tournament_surface,
                p1.name AS player_a_name,
                p2.name AS player_b_name,
                lp.prediction_id,
                lp.decision AS prediction_decision
            FROM market_odds_snapshots mo
            JOIN matches m ON m.id = mo.match_id
            JOIN tournaments t ON t.id = m.tournament_id
            LEFT JOIN tournament_levels tl ON tl.tournament_id = m.tournament_id AND tl.tour = m.tour
            JOIN players p1 ON p1.id = m.player_a_id
            JOIN players p2 ON p2.id = m.player_b_id
            LEFT JOIN (
                SELECT p1.match_id, p1.id AS prediction_id, p1.decision
                FROM predictions p1
                JOIN (
                    SELECT match_id, MAX(id) AS max_prediction_id
                    FROM predictions
                    GROUP BY match_id
                ) latest ON latest.max_prediction_id = p1.id
            ) lp ON lp.match_id = m.id
            WHERE m.match_date = ?
              AND mo.id IN (
                SELECT MAX(mo2.id)
                FROM market_odds_snapshots mo2
                JOIN matches m2 ON m2.id = mo2.match_id
                WHERE m2.match_date = ?
                GROUP BY mo2.match_id, mo2.market_key, mo2.market_name, mo2.selection_name, COALESCE(mo2.line, -999999)
              )
            ORDER BY t.name, p1.name, p2.name, mo.market_key, mo.market_name, mo.line, mo.selection_name
            """,
            (match_date, match_date),
        ).fetchall()
    return [dict(row) for row in rows]


def _pct(value: float | None, signed: bool = False) -> str:
    if value is None:
        return "N/A"
    prefix = "+" if signed and value > 0 else ""
    return f"{prefix}{value * 100:.1f}%"


def _fmt(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.4g}"


def _market_pricing_status(row: dict) -> str:
    if row["market_key"] != "match_winner":
        return "ODDS_ONLY_MODEL_NOT_BUILT"
    if _outside_mvp_scope(row):
        return "ODDS_ONLY_OUTSIDE_MVP_SCOPE"
    if row.get("prediction_id") is None:
        return "ODDS_ONLY_OUTSIDE_MODEL_SCOPE"
    return f"PRICED_{row.get('prediction_decision') or 'REVIEW'}"


def _outside_mvp_scope(row: dict) -> bool:
    tournament = str(row.get("tournament_name") or "").lower()
    player_a = str(row.get("player_a_name") or "")
    player_b = str(row.get("player_b_name") or "")
    level = str(row.get("tournament_level") or "").upper()
    if any(token in tournament for token in ("challenger", "itf", "futures", "utr")):
        return True
    if "/" in player_a or "/" in player_b:
        return True
    return level == "UNKNOWN"


def _bet_summary_lines(bets: list[dict]) -> list[str]:
    if not bets:
        return ["暫時未有通過所有 hard rule 嘅 BET。"]
    lines = [
        "| 選擇 | 賽事 | 現時賠率 | 最低可接受 | 模型勝率 | Edge | 注碼 | 風險 |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in bets:
        lines.append(
            "| "
            f"{row['selection_name']} | "
            f"{row['tournament_name']} | "
            f"{_fmt(row['current_market_odds'])} | "
            f"{_fmt(row['minimum_acceptable_odds'])} | "
            f"{_pct(row['model_probability'])} | "
            f"{_pct(row['edge'], signed=True)} | "
            f"{_stake_label(row['stake_units'], row['decision'])} | "
            f"{row['risk']} |"
        )
    lines.append("")
    lines.append("只可喺現時賠率仍然高過「最低可接受」時先考慮；跌穿即 NO_BET。")
    return lines


def _bsd_status(raw_response: str | None) -> str:
    if not raw_response:
        return "未見近期錯誤"
    try:
        payload = json.loads(raw_response)
    except json.JSONDecodeError:
        return "fixture source error"
    message = str(payload.get("message") or payload)
    if "Sports Addon" in message or "402" in message:
        return "不可即時刷新：BSD Tennis API 需要 Sports Addon"
    return message[:160]


def _hk_reason(reason: str) -> str:
    labels = {
        "current_odds_below_minimum_acceptable_odds": "現時賠率低過最低可接受賠率",
        "data_quality_score_below_65": "資料質素低過 65 分",
        "data_provenance_validation_failed": "資料 provenance 驗證失敗",
        "doubles_outside_mvp_scope": "雙打，不在 MVP 範圍",
        "challenger_outside_mvp_scope": "Challenger，不在 MVP 範圍",
        "itf_outside_mvp_scope": "ITF/Futures，不在 MVP 範圍",
        "longshot_requires_higher_data_quality": "高賠率 longshot 需要更高資料質素",
        "missing_core_elo_inputs": "缺少核心 Elo 輸入",
        "missing_market_odds": "缺少市場賠率",
        "utr_outside_mvp_scope": "UTR，不在 MVP 範圍",
        "competition_metadata_not_confirmed": "賽事級別/場地未有確認 mapping",
        "missing_competition": "缺少賽事 competition metadata",
        "not_linked_to_feature_snapshot": "未能配對到 feature snapshot",
    }
    return labels.get(reason, reason)


def _source_label(source: str) -> str:
    labels = {
        "tournaments": "賽事 metadata",
        "rankings_atp": "ATP ranking",
        "rankings_wta": "WTA ranking",
        "history": "歷史賽果 / Elo",
        "upcoming_matches": "明日賽程",
        "odds": "Sportsbet odds",
        "event_markets": "Sportsbet 單場 markets",
    }
    return labels.get(source, source)


def _source_error_label(error: str) -> str:
    lowered = error.lower()
    if "nodename nor servname provided" in lowered or "could not resolve host" in lowered:
        return "本地 DNS 無法解析外部網站，live refresh 未能連線"
    if "http 402" in lowered or "sports addon" in lowered:
        return "API plan 權限不足，需要 Sports Addon / 對應 provider 權限"
    if "403" in lowered or "forbidden" in lowered:
        return "來源拒絕存取或被封鎖"
    if "timeout" in lowered or "timed out" in lowered:
        return "連線逾時"
    return "資料源連線失敗"


def _stake_label(stake_units: float | None, decision: str | None = None) -> str:
    if decision != "BET" or float(stake_units or 0) <= 0:
        return "不下注"
    return "1 unit ($5.00)"


def _display_label(value: str | None, fallback: str = "未確認（資料不足）") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    if not text or text.upper() == "UNKNOWN" or text.lower() == "none":
        return fallback
    return text


def _report_red_flags(filter_result: dict) -> list[str]:
    hard_reasons = filter_result.get("hard_no_bet_reasons") or []
    if hard_reasons:
        return [_hk_reason(reason) for reason in hard_reasons[:5]]

    warnings = filter_result.get("warnings") or []
    labels = []
    if any("low_sample" in warning for warning in warnings):
        labels.append("部分 split 樣本偏低，已降低注碼/信心")
    if any("missing_historical_rank" in warning for warning in warnings):
        labels.append("部分歷史對手排名缺失，沒有用現時排名代替")
    if any("missing_player_history" in warning for warning in warnings):
        labels.append("部分球員歷史資料不足，模型只使用有 provenance 嘅特徵")
    if any("unknown tournament level" in warning or "unknown_tournament_level" in warning for warning in warnings):
        labels.append("賽事級別未確認，不能作投注建議")
    if any("stale" in warning for warning in warnings):
        labels.append("部分資料接近 freshness 上限")
    return labels[:5]
