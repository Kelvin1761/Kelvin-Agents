"""Versioned NBA / Tennis dashboard snapshot exporters.

The dashboard must not calculate betting recommendations in the browser.  This
module only normalises artifacts already produced by the domain pipelines:

* NBA: validated Sportsbet JSON + deterministic Full Analysis markdown.
* Tennis: ``market_predictions`` / ``combo_tracker`` rows in tennis_wc.db.

If the evidence pair is incomplete, the exporter returns a blocked snapshot
instead of inventing a line, odds, probability, or recommendation.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


SCHEMA_VERSION = 2
NBA_DIR_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}) NBA Analysis$")
NBA_REPORT_RE = re.compile(r"^Game_(.+?)_Full_Analysis\.md$")
NBA_COMBO_HEADING_RE = re.compile(
    r"^###\s+.*?組合\s+(\d+|X).*?組合賠率\s*@\s*(\d+(?:\.\d+)?)",
    re.MULTILINE,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_float(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number, 6)


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _empty_snapshot(sport: str, analysis_run_id: str, status: str, warnings: Iterable[str]) -> Dict[str, Any]:
    return {
        "sport": sport,
        "analysis_run_id": analysis_run_id,
        "generated_at": _utc_now(),
        "validation_status": status,
        "recommendations": [],
        "source_files": [],
        "warnings": list(dict.fromkeys(warnings)),
    }


def _find_nba_analysis_dir(root: Path, target_date: Optional[str]) -> Tuple[Optional[Path], Optional[str]]:
    root = Path(root)
    if target_date:
        candidate = root / f"{target_date} NBA Analysis"
        return (candidate, target_date) if candidate.is_dir() else (None, target_date)
    candidates = []
    if root.is_dir():
        for item in root.iterdir():
            match = NBA_DIR_RE.match(item.name)
            if item.is_dir() and match:
                candidates.append((match.group(1), item))
    if not candidates:
        return None, None
    analysis_date, directory = sorted(candidates, reverse=True)[0]
    return directory, analysis_date


def _sportsbet_tag(path: Path, payload: Dict[str, Any]) -> str:
    if payload.get("game_tag"):
        return str(payload["game_tag"]).strip()
    return path.stem.replace("Sportsbet_Odds_", "")


def _valid_sportsbet_payload(payload: Dict[str, Any], target_date: str) -> bool:
    props = payload.get("player_props")
    if not isinstance(props, dict) or not props:
        return False
    explicit_date = payload.get("target_analysis_date") or payload.get("event_local_date")
    if explicit_date and str(explicit_date) != target_date:
        return False
    source = str(payload.get("source") or "").lower()
    return not source or "sportsbet" in source


def _parse_nba_leg_row(line: str) -> Optional[Dict[str, Any]]:
    if not line.lstrip().startswith("|") or "🧩" not in line:
        return None
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    if len(cells) < 3:
        return None
    odds_match = re.search(r"@?\s*(\d+(?:\.\d+)?)", cells[2])
    if not odds_match:
        return None
    odds = _safe_float(odds_match.group(1))
    if odds is None or odds <= 1:
        return None
    selection = cells[1]

    def percent_at(index: int) -> Optional[float]:
        if index >= len(cells):
            return None
        match = re.search(r"([+-]?\d+(?:\.\d+)?)\s*%", cells[index])
        return _safe_float(float(match.group(1)) / 100) if match else None

    l10_hit_rate = percent_at(3)
    model_probability = percent_at(4)
    if len(cells) >= 8:
        edge = percent_at(5)
        expected_value = percent_at(6)
        cov_match = re.search(r"(\d+(?:\.\d+)?)", cells[7])
    else:
        edge = None
        expected_value = percent_at(5)
        cov_match = None

    player = ""
    stat = ""
    line_value = None
    patterns = [
        re.compile(
            r"^(?P<player>.+?)(?:\s+\([A-Z]{2,4}\))?\s+"
            r"(?P<stat>PTS|REB|AST|3PM|PRA|PR|PA|RA|STL|BLK|TOV)\s+"
            r"(?P<line>\d+(?:\.\d+)?)\+",
            re.IGNORECASE,
        ),
        re.compile(
            r"^(?P<player>.+?)(?:\s+\([A-Z]{2,4}\))?\s+"
            r"(?P<line>\d+(?:\.\d+)?)\+\s+"
            r"(?P<stat>PTS|REB|AST|3PM|PRA|PR|PA|RA|STL|BLK|TOV)",
            re.IGNORECASE,
        ),
    ]
    for pattern in patterns:
        parsed = pattern.search(selection)
        if parsed:
            player = parsed.group("player").strip()
            stat = parsed.group("stat").upper()
            line_value = _safe_float(parsed.group("line"))
            break
    return {
        "selection": selection,
        "market": f"Player {stat}" if stat else "NBA player/team milestone",
        "odds": odds,
        "player": player,
        "stat": stat,
        "line": line_value,
        "metrics": {
            "l10_hit_rate": l10_hit_rate,
            "model_probability": model_probability,
            "edge": edge,
            "expected_value": expected_value,
            "coefficient_of_variation": _safe_float(cov_match.group(1)) if cov_match else None,
        },
        "source_row": line.strip(),
    }


def _parse_nba_combos(
    content: str,
    analysis_date: str,
    game_tag: str,
    source_files: List[str],
) -> List[Dict[str, Any]]:
    matches = list(NBA_COMBO_HEADING_RE.finditer(content))
    recommendations = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        section = content[match.start():end]
        # Stop before the next level-two section when this is the final combo.
        level_two = re.search(r"^##\s+", section[len(match.group(0)):], re.MULTILINE)
        if level_two:
            section = section[: len(match.group(0)) + level_two.start()]
        legs = []
        for line in section.splitlines():
            leg = _parse_nba_leg_row(line)
            if leg:
                legs.append(leg)
        if not legs:
            continue
        combo_key = match.group(1)
        combined_odds = _safe_float(match.group(2))
        heading = match.group(0).lstrip("# ").strip()
        risk_match = re.search(r"\((Low|Mid|High)[^)]*\)", heading, re.IGNORECASE)
        risk = risk_match.group(1).title() if risk_match else ""
        recommendations.append(
            {
                "id": f"nba:{analysis_date}:{game_tag}:combo:{combo_key}",
                "sport": "nba",
                "category": "sgm",
                "event_date": analysis_date,
                "event_name": game_tag.replace("_", " @ "),
                "market": "Same Game Multi",
                "selection": heading,
                "odds": combined_odds,
                "odds_status": "sportsbet_extracted",
                "bet_type": "combo",
                "legs": legs,
                "metrics": {
                    "leg_count": len(legs),
                    "model_probability": _safe_float(
                        _product(
                            leg.get("metrics", {}).get("model_probability")
                            for leg in legs
                        )
                    ),
                    "average_edge": _safe_float(
                        _mean(
                            leg.get("metrics", {}).get("edge")
                            for leg in legs
                        )
                    ),
                },
                "insight": "由 NBA Wong Choi Python Auto-Selection 正式報告直接匯出。",
                "risk": risk,
                "decision": "BET",
                "confidence": None,
                "outcome": "pending",
                "actual": "待賽果",
                "provenance": f"NBA Wong Choi · Game_{game_tag}_Full_Analysis.md",
                "source_files": source_files,
                "validation_status": "valid",
            }
        )
    return recommendations


def _product(values: Iterable[Optional[float]]) -> Optional[float]:
    usable = [float(value) for value in values if value is not None]
    if not usable:
        return None
    result = 1.0
    for value in usable:
        result *= value
    return result


def _mean(values: Iterable[Optional[float]]) -> Optional[float]:
    usable = [float(value) for value in values if value is not None]
    return sum(usable) / len(usable) if usable else None


def _build_nba_bankers(combos: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    bankers = []
    for combo in combos:
        if not str(combo.get("id") or "").endswith(":combo:1"):
            continue
        legs = combo.get("legs") or []
        if not legs:
            continue
        leg = max(
            legs,
            key=lambda item: (
                item.get("metrics", {}).get("expected_value") is not None,
                item.get("metrics", {}).get("expected_value") or float("-inf"),
                item.get("metrics", {}).get("edge") or float("-inf"),
                item.get("metrics", {}).get("l10_hit_rate") or float("-inf"),
            ),
        )
        bankers.append(
            {
                "id": str(combo["id"]).replace(":combo:1", ":banker"),
                "sport": "nba",
                "category": "banker",
                "event_date": combo["event_date"],
                "event_name": combo["event_name"],
                "market": leg.get("market") or "NBA player prop",
                "selection": leg.get("selection") or "",
                "odds": leg.get("odds"),
                "odds_status": combo.get("odds_status"),
                "bet_type": "single",
                "legs": [],
                "metrics": leg.get("metrics") or {},
                "insight": "組合 1 入面最高 EV 嘅正式 Banker leg；直接由 Python Auto-Selection 表格匯出。",
                "risk": combo.get("risk") or "",
                "decision": "BET",
                "confidence": (
                    (leg.get("metrics") or {}).get("model_probability")
                ),
                "outcome": "pending",
                "actual": "待賽果",
                "provenance": combo.get("provenance"),
                "source_files": combo.get("source_files") or [],
                "validation_status": "valid",
                "settlement_contract": {
                    "player": leg.get("player") or "",
                    "stat": leg.get("stat") or "",
                    "line": leg.get("line"),
                    "direction": "over_or_milestone",
                },
            }
        )
    return bankers


def export_nba_snapshot(root: Path, target_date: Optional[str] = None) -> Dict[str, Any]:
    """Export validated NBA combos from one orchestrator analysis directory."""
    analysis_dir, analysis_date = _find_nba_analysis_dir(Path(root), target_date)
    run_id = f"nba:{analysis_date or target_date or 'unavailable'}"
    if not analysis_dir:
        return _empty_snapshot("nba", run_id, "unavailable", ["nba_analysis_directory_not_found"])

    sportsbet_by_tag = {}
    all_source_files = []
    for path in sorted(analysis_dir.glob("Sportsbet_Odds_*.json")):
        payload = _read_json(path)
        if _valid_sportsbet_payload(payload, analysis_date):
            sportsbet_by_tag[_sportsbet_tag(path, payload)] = path
            all_source_files.append(path.name)

    reports = sorted(analysis_dir.glob("Game_*_Full_Analysis.md"))
    if not reports:
        return _empty_snapshot("nba", run_id, "blocked", ["nba_full_analysis_not_found"])

    warnings = []
    recommendations = []
    for report in reports:
        match = NBA_REPORT_RE.match(report.name)
        if not match:
            continue
        game_tag = match.group(1)
        sportsbet_path = sportsbet_by_tag.get(game_tag)
        if not sportsbet_path:
            warnings.append("missing_matching_sportsbet_json")
            continue
        content = report.read_text(encoding="utf-8", errors="replace")
        required_markers = ["SPORTSBET_LIVE", "Python Auto-Selection", "未填寫項目 殘留: 0"]
        if any(marker not in content for marker in required_markers) or "[FILL]" in content:
            warnings.append(f"nba_report_validation_failed:{game_tag}")
            continue
        source_files = [sportsbet_path.name, report.name]
        combos = _parse_nba_combos(content, analysis_date, game_tag, source_files)
        recommendations.extend(combos)
        recommendations.extend(_build_nba_bankers(combos))
        all_source_files.extend(source_files)

    if not recommendations:
        if not warnings:
            warnings.append("no_validated_nba_combos")
        status = "blocked"
    else:
        status = "valid" if not warnings else "partial"
    return {
        "sport": "nba",
        "analysis_run_id": run_id,
        "generated_at": _utc_now(),
        "validation_status": status,
        "recommendations": recommendations,
        "source_files": sorted(set(all_source_files)),
        "warnings": list(dict.fromkeys(warnings)),
    }


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return bool(row)


def _resolve_tennis_date(connection: sqlite3.Connection, target_date: Optional[str]) -> Optional[str]:
    if target_date:
        return target_date
    today = date.today().isoformat()
    candidate_queries = [
        """
        SELECT MAX(m.match_date)
        FROM market_predictions mp
        JOIN matches m ON m.id = mp.match_id
        WHERE m.match_date <= ?
        """,
        """
        SELECT MAX(ct.match_date)
        FROM combo_tracker ct
        WHERE ct.match_date <= ?
        """,
    ]
    if _table_exists(connection, "odds_snapshots"):
        candidate_queries.append(
            """
            SELECT MAX(m.match_date)
            FROM odds_snapshots o
            JOIN matches m ON m.id = o.match_id
            WHERE o.source_provider = 'sportsbet' AND m.match_date <= ?
            """
        )
    row = connection.execute(
        "SELECT MAX(candidate_date) FROM ("
        + " UNION ALL ".join(
            f"SELECT ({query.strip()}) AS candidate_date" for query in candidate_queries
        )
        + ")",
        tuple(today for _ in candidate_queries),
    ).fetchone()
    return row[0] if row and row[0] else None


def _tennis_coverage(connection: sqlite3.Connection, analysis_date: str) -> Dict[str, Any]:
    """Expose the live-card completeness counters used by the dashboard."""
    fixtures = connection.execute(
        "SELECT COUNT(*) FROM matches WHERE match_date = ?",
        (analysis_date,),
    ).fetchone()[0]

    priced_match_ids: set[int] = set()
    singles_candidate_ids: set[int] = set()
    latest_scrape = None
    if _table_exists(connection, "odds_snapshots"):
        latest_scrape = connection.execute(
            """
            SELECT MAX(o.fetched_at)
            FROM odds_snapshots o
            JOIN matches m ON m.id = o.match_id
            WHERE m.match_date = ? AND o.source_provider = 'sportsbet'
            """,
            (analysis_date,),
        ).fetchone()[0]
        priced_rows = connection.execute(
            """
            SELECT DISTINCT m.id, t.name AS tournament_name
            FROM odds_snapshots o
            JOIN matches m ON m.id = o.match_id
            LEFT JOIN tournaments t ON t.id = m.tournament_id
            WHERE m.match_date = ? AND o.source_provider = 'sportsbet'
            """,
            (analysis_date,),
        ).fetchall()
        priced_match_ids = {int(row["id"]) for row in priced_rows}
        singles_candidate_ids = {
            int(row["id"])
            for row in priced_rows
            if not re.search(r"\bdoubles\b", str(row["tournament_name"] or ""), re.IGNORECASE)
        }

    latest_run_started = None
    if _table_exists(connection, "raw_api_responses"):
        row = connection.execute(
            """
            SELECT fetched_at
            FROM raw_api_responses
            WHERE provider_name = 'tennis_wc_pipeline'
              AND entity_type = 'run_daily_source_errors'
              AND entity_external_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (analysis_date,),
        ).fetchone()
        latest_run_started = row[0] if row else None

    modelled_match_ids: set[int] = set()
    latest_analysis = None
    if _table_exists(connection, "predictions"):
        time_clause = " AND p.created_at >= ?" if latest_run_started else ""
        params: tuple[Any, ...] = (
            (analysis_date, latest_run_started)
            if latest_run_started
            else (analysis_date,)
        )
        modelled_rows = connection.execute(
            f"""
            SELECT DISTINCT p.match_id, p.created_at
            FROM predictions p
            JOIN matches m ON m.id = p.match_id
            WHERE m.match_date = ?{time_clause}
            """,
            params,
        ).fetchall()
        modelled_match_ids = {int(row["match_id"]) for row in modelled_rows}
        latest_analysis = max(
            (row["created_at"] for row in modelled_rows if row["created_at"]),
            default=None,
        )
    elif _table_exists(connection, "feature_snapshots"):
        time_clause = " AND f.created_at >= ?" if latest_run_started else ""
        params = (
            (analysis_date, latest_run_started)
            if latest_run_started
            else (analysis_date,)
        )
        modelled_rows = connection.execute(
            f"""
            SELECT DISTINCT f.match_id, f.created_at
            FROM feature_snapshots f
            JOIN matches m ON m.id = f.match_id
            WHERE m.match_date = ?{time_clause}
            """,
            params,
        ).fetchall()
        modelled_match_ids = {int(row["match_id"]) for row in modelled_rows}
        latest_analysis = max(
            (row["created_at"] for row in modelled_rows if row["created_at"]),
            default=None,
        )
    else:
        modelled_rows = connection.execute(
            """
            SELECT DISTINCT mp.match_id, mp.created_at
            FROM market_predictions mp
            JOIN matches m ON m.id = mp.match_id
            WHERE m.match_date = ?
            """,
            (analysis_date,),
        ).fetchall()
        modelled_match_ids = {int(row["match_id"]) for row in modelled_rows}
        latest_analysis = max(
            (row["created_at"] for row in modelled_rows if row["created_at"]),
            default=None,
        )

    fixtures = int(fixtures or 0)
    priced = len(priced_match_ids)
    modelled = len(modelled_match_ids & singles_candidate_ids)
    return {
        "fixtures_found": fixtures,
        "sportsbet_priced_matches": priced,
        "singles_candidates": len(singles_candidate_ids),
        "modelled_matches": modelled,
        "unmodelled_priced_matches": len(singles_candidate_ids - modelled_match_ids),
        "priced_ratio": round(priced / fixtures, 4) if fixtures else None,
        "latest_sportsbet_scrape": latest_scrape,
        "latest_run_started": latest_run_started,
        "latest_analysis": latest_analysis,
    }


def _load_pricing_json(value: Any) -> Dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _tennis_outcome(status: Any) -> str:
    value = str(status or "PENDING").strip().lower()
    return {
        "win": "won",
        "won": "won",
        "loss": "lost",
        "lost": "lost",
        "void": "void",
        "push": "void",
    }.get(value, "pending")


def _tennis_prop_family(market_key: Any) -> str:
    key = str(market_key or "")
    if key.startswith("total_match_games"):
        return "match_total_games"
    if key.startswith("total_aces") or key == "total_aces_in_the_match":
        return "match_total_aces"
    if "_aces" in key:
        return "player_aces"
    return key


def _tennis_strategy_state(connection: sqlite3.Connection) -> Dict[str, Any]:
    """Mirror the pipeline's pre-registered prop evidence gate for display."""
    if not _table_exists(connection, "prop_tracker"):
        return {
            "status": "RESEARCH_ONLY",
            "enabled_families": [],
            "raw_scorecard_settled": 0,
            "reason": "prop_tracker unavailable",
        }
    score = connection.execute(
        """
        SELECT COUNT(*) AS settled,
               AVG((model_prob_raw - CASE WHEN result_status = 'WON' THEN 1.0 ELSE 0.0 END)
                   * (model_prob_raw - CASE WHEN result_status = 'WON' THEN 1.0 ELSE 0.0 END)) AS model_brier,
               AVG((market_prob_fair - CASE WHEN result_status = 'WON' THEN 1.0 ELSE 0.0 END)
                   * (market_prob_fair - CASE WHEN result_status = 'WON' THEN 1.0 ELSE 0.0 END)) AS market_brier
        FROM prop_tracker
        WHERE result_status IN ('WON','LOST')
          AND model_prob_raw IS NOT NULL
          AND market_prob_fair IS NOT NULL
        """
    ).fetchone()
    raw_n = int(score["settled"] or 0)
    model_brier = _safe_float(score["model_brier"])
    market_brier = _safe_float(score["market_brier"])
    model_beats_market = (
        model_brier is not None
        and market_brier is not None
        and model_brier <= market_brier - 0.005
    )
    family_rows = connection.execute(
        """
        SELECT market_key, result_status, stake_units, profit_loss_units
        FROM prop_tracker
        WHERE result_status IN ('WON','LOST')
          AND stake_units > 0
          AND is_value = 1
        """
    ).fetchall()
    families: Dict[str, Dict[str, float]] = {}
    for row in family_rows:
        bucket = families.setdefault(
            _tennis_prop_family(row["market_key"]),
            {"settled": 0, "staked": 0.0, "pnl": 0.0},
        )
        bucket["settled"] += 1
        bucket["staked"] += float(row["stake_units"] or 0)
        bucket["pnl"] += float(row["profit_loss_units"] or 0)
    enabled = []
    for family in ("match_total_aces", "player_aces"):
        stats = families.get(family) or {}
        staked = float(stats.get("staked") or 0)
        stats["roi"] = float(stats.get("pnl") or 0) / staked if staked else None
        if (
            raw_n >= 120
            and model_beats_market
            and int(stats.get("settled") or 0) >= 50
            and stats["roi"] is not None
            and stats["roi"] > 0
        ):
            enabled.append(family)
    return {
        "status": "VALIDATED" if enabled else "RESEARCH_ONLY",
        "enabled_families": enabled,
        "raw_scorecard_settled": raw_n,
        "model_brier": model_brier,
        "market_brier": market_brier,
        "families": families,
        "reason": None if enabled else "minimum evidence gate not met",
    }


def _export_tennis_singles(
    connection: sqlite3.Connection,
    analysis_date: str,
    strategy: Dict[str, Any],
) -> List[Dict[str, Any]]:
    enabled = set(strategy.get("enabled_families") or [])
    if (
        not enabled
        or not _table_exists(connection, "prop_tracker")
        or not _table_exists(connection, "feature_snapshots")
    ):
        return []
    rows = connection.execute(
        """
        SELECT
            p.id, p.match_id, p.market_key, p.selection, p.side, p.line,
            p.decimal_odds, p.blended_prob, p.market_prob_fair, p.edge, p.ev,
            p.result_status, p.profit_loss_units, p.match_label,
            (SELECT MIN(fs.data_quality_score)
             FROM feature_snapshots fs
             WHERE fs.match_id = p.match_id) AS data_quality_score,
            m.match_date, m.tour, m.round,
            pa.name AS player_a, pb.name AS player_b,
            t.name AS tournament_name
        FROM prop_tracker p
        JOIN matches m ON m.id = p.match_id
        LEFT JOIN players pa ON pa.id = m.player_a_id
        LEFT JOIN players pb ON pb.id = m.player_b_id
        LEFT JOIN tournaments t ON t.id = m.tournament_id
        WHERE m.match_date = ?
          AND p.is_value = 1
          AND p.result_status = 'PENDING'
          AND p.blended_prob >= 0.58
          AND p.decimal_odds BETWEEN 1.30 AND 2.25
          AND (SELECT MIN(fs.data_quality_score)
               FROM feature_snapshots fs
               WHERE fs.match_id = p.match_id) >= 0.80
        ORDER BY p.ev DESC, p.id
        """,
        (analysis_date,),
    ).fetchall()
    recommendations = []
    for row in rows:
        item = dict(row)
        family = _tennis_prop_family(item.get("market_key"))
        if family not in enabled:
            continue
        event_name = f"{item.get('player_a') or '?'} vs {item.get('player_b') or '?'}"
        line = item.get("line")
        selection = str(item.get("selection") or "").strip()
        if line is not None and str(line) not in selection:
            selection = f"{selection} {line:g}" if isinstance(line, (int, float)) else f"{selection} {line}"
        outcome = _tennis_outcome(item.get("result_status"))
        model_probability = _safe_float(item.get("blended_prob"))
        odds = _safe_float(item.get("decimal_odds"))
        recommendations.append(
            {
                "id": f"tennis:prop:{item['id']}",
                "sport": "tennis",
                "category": "validated_prop",
                "event_date": item["match_date"],
                "event_name": event_name,
                "market": item.get("market_key"),
                "selection": selection,
                "odds": odds,
                "odds_status": "sportsbet_extracted",
                "bet_type": "single",
                "legs": [],
                "metrics": {
                    "model_probability": model_probability,
                    "market_fair_probability": _safe_float(item.get("market_prob_fair")),
                    "edge": _safe_float(item.get("edge")),
                    "expected_value": _safe_float(item.get("ev")),
                    "data_quality": _safe_float(item.get("data_quality_score")),
                    "confidence": round(float(model_probability or 0) * 100),
                    "profit_loss_units": _safe_float(item.get("profit_loss_units")),
                },
                "insight": f"{family} · evidence gate validated",
                "risk": "固定 1u；模型即使已驗證仍有短期波動。",
                "decision": "BET",
                "confidence": round(float(model_probability or 0) * 100),
                "outcome": outcome,
                "actual": (
                    "待賽果"
                    if outcome == "pending"
                    else f"{item.get('result_status')} · {item.get('profit_loss_units') or 0:+g}u"
                ),
                "provenance": f"tennis_wc.db · prop_tracker#{item['id']}",
                "source_files": ["tennis-wong-choi/tennis_wc.db"],
                "validation_status": "valid",
                "context": {
                    "tour": item.get("tour"),
                    "round": item.get("round"),
                    "tournament": item.get("tournament_name"),
                    "match_id": item.get("match_id"),
                },
            }
        )
    return recommendations


def _normalise_tennis_leg(leg: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(leg.get("id") or ""),
        "event_name": str(leg.get("match_label") or ""),
        "market": str(leg.get("market_name") or leg.get("market_key") or ""),
        "selection": str(leg.get("selection_name") or ""),
        "line": leg.get("line"),
        "odds": _safe_float(leg.get("odds")),
        "confidence": leg.get("confidence"),
        "edge": _safe_float(leg.get("edge")),
        "data_quality": _safe_float(leg.get("data_quality")),
    }


def _export_tennis_combos(
    connection: sqlite3.Connection,
    analysis_date: str,
    strategy: Dict[str, Any],
) -> List[Dict[str, Any]]:
    enabled = set(strategy.get("enabled_families") or [])
    if not enabled:
        return []
    rows = connection.execute(
        """
        SELECT combo_key, match_date, match_label, tier, legs_json, combo_odds,
               adjusted_confidence, adjusted_edge, stake_units, result_status,
               profit_loss_units, recorded_at
        FROM combo_tracker
        WHERE match_date = ?
          AND tier = 'PROP_2_LEG_TRIAL'
          AND result_status = 'PENDING'
          AND combo_odds >= 2.0
        ORDER BY recorded_at, combo_key
        """,
        (analysis_date,),
    ).fetchall()
    recommendations = []
    for row in rows:
        item = dict(row)
        try:
            raw_legs = json.loads(item.get("legs_json") or "[]")
        except (TypeError, ValueError):
            raw_legs = []
        legs = [_normalise_tennis_leg(leg) for leg in raw_legs if isinstance(leg, dict)]
        if not legs:
            continue
        if any(
            _tennis_prop_family(leg.get("market_key")) not in enabled
            or float(leg.get("odds") or 0) < 1.30
            or float(leg.get("odds") or 0) > 2.25
            or float(leg.get("confidence") or 0) < 58
            or float(leg.get("data_quality") or 0) < 0.80
            for leg in raw_legs
        ):
            continue
        outcome = _tennis_outcome(item.get("result_status"))
        selection = " + ".join(leg["selection"] for leg in legs if leg["selection"])
        recommendations.append(
            {
                "id": f"tennis:combo:{item['combo_key']}",
                "sport": "tennis",
                "category": "validated_prop_combo",
                "event_date": item["match_date"],
                "event_name": f"{len(legs)}-match Combo · {item.get('tier') or ''}".strip(),
                "market": "Tennis Multi",
                "selection": selection,
                "odds": _safe_float(item.get("combo_odds")),
                "odds_status": "sportsbet_extracted",
                "bet_type": "combo",
                "legs": legs,
                "metrics": {
                    "model_probability": (
                        _safe_float(item.get("adjusted_confidence") / 100)
                        if item.get("adjusted_confidence") is not None
                        else None
                    ),
                    "edge": _safe_float(item.get("adjusted_edge")),
                    "stake_units": _safe_float(item.get("stake_units")),
                    "profit_loss_units": _safe_float(item.get("profit_loss_units")),
                },
                "insight": "兩腳跨場 prop · evidence gate validated",
                "risk": "組合注要逐腳結算；任何一腳落空會令整注落空。",
                "decision": "BET",
                "confidence": item.get("adjusted_confidence"),
                "outcome": outcome,
                "actual": "待賽果" if outcome == "pending" else str(item.get("result_status")),
                "provenance": f"tennis_wc.db · combo_tracker#{item['combo_key']}",
                "source_files": ["tennis-wong-choi/tennis_wc.db"],
                "validation_status": "valid",
            }
        )
    return recommendations


def export_tennis_snapshot(db_path: Path, target_date: Optional[str] = None) -> Dict[str, Any]:
    """Export only evidence-gated Tennis prop recommendations."""
    db_path = Path(db_path)
    run_id = f"tennis:{target_date or 'unavailable'}"
    if not db_path.is_file():
        return _empty_snapshot("tennis", run_id, "unavailable", ["tennis_database_not_found"])
    try:
        connection = sqlite3.connect(str(db_path))
        connection.row_factory = sqlite3.Row
        required = ["matches", "players", "tournaments", "market_predictions", "combo_tracker"]
        missing = [table for table in required if not _table_exists(connection, table)]
        if missing:
            connection.close()
            return _empty_snapshot(
                "tennis",
                run_id,
                "blocked",
                [f"missing_tennis_table:{table}" for table in missing],
            )
        analysis_date = _resolve_tennis_date(connection, target_date)
        if not analysis_date:
            connection.close()
            return _empty_snapshot(
                "tennis",
                "tennis:unavailable",
                "unavailable",
                ["no_eligible_tennis_date"],
            )
        strategy = _tennis_strategy_state(connection)
        recommendations = _export_tennis_singles(connection, analysis_date, strategy)
        recommendations.extend(_export_tennis_combos(connection, analysis_date, strategy))
        coverage = _tennis_coverage(connection, analysis_date)
        connection.close()
    except sqlite3.Error as exc:
        return _empty_snapshot("tennis", run_id, "blocked", [f"tennis_database_error:{exc}"])

    return {
        "sport": "tennis",
        "analysis_run_id": f"tennis:{analysis_date}",
        "generated_at": _utc_now(),
        "validation_status": (
            "valid"
            if recommendations or coverage["modelled_matches"] > 0
            else "unavailable"
        ),
        "recommendations": recommendations,
        "strategy": strategy,
        "coverage": coverage,
        "source_files": [str(db_path)],
        "warnings": [] if recommendations else ["no_eligible_tennis_recommendations"],
    }


def validate_multisport_feed(feed: Dict[str, Any]) -> List[str]:
    """Return contract errors without mutating the supplied feed."""
    errors = []
    if feed.get("schema_version") != SCHEMA_VERSION:
        errors.append("unsupported_schema_version")
    sports = feed.get("sports")
    if not isinstance(sports, dict):
        return errors + ["sports_must_be_object"]
    seen = set()
    for sport in ("nba", "tennis"):
        snapshot = sports.get(sport) or {}
        recommendations = snapshot.get("recommendations") or []
        if not isinstance(recommendations, list):
            errors.append(f"recommendations_must_be_array:{sport}")
            continue
        for recommendation in recommendations:
            recommendation_id = str(recommendation.get("id") or "")
            if not recommendation_id:
                errors.append(f"missing_recommendation_id:{sport}")
                continue
            if recommendation_id in seen:
                errors.append(f"duplicate_recommendation_id:{recommendation_id}")
            seen.add(recommendation_id)
            if (
                recommendation.get("decision") == "BET"
                and recommendation.get("validation_status") == "valid"
                and recommendation.get("odds") is None
            ):
                errors.append(f"missing_live_odds:{recommendation_id}")
    return errors


def build_multisport_feed(
    repo_root: Path,
    target_date: Optional[str] = None,
    tennis_db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    repo_root = Path(repo_root)
    tennis_db = tennis_db_path or repo_root / "tennis-wong-choi" / "tennis_wc.db"
    feed = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "sports": {
            "nba": export_nba_snapshot(repo_root, target_date=target_date),
            "tennis": export_tennis_snapshot(tennis_db, target_date=target_date),
        },
    }
    errors = validate_multisport_feed(feed)
    feed["validation_status"] = "valid" if not errors else "blocked"
    feed["validation_errors"] = errors
    return feed
