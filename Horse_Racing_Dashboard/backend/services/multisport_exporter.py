"""Versioned NBA / Tennis dashboard snapshot exporters.

The dashboard must not calculate betting recommendations in the browser.  This
module only normalises artifacts already produced by the domain pipelines:

* NBA: validated Sportsbet JSON + deterministic Full Analysis markdown.
* Tennis: evidence-gated ``prop_tracker`` / ``combo_tracker`` rows in
  tennis_wc.db.

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
        **_tennis_input_completeness(connection, analysis_date),
    }


def _tennis_input_completeness(connection: sqlite3.Connection,
                               analysis_date: str) -> Dict[str, Any]:
    """How many of today's priced fixtures have both players' real inputs.

    "Modelled" says a probability was produced, not that it was produced from
    anything. The model has 168 feature leaves and 164 of them are one signal
    -- past results -- re-sliced; only Elo, surface Elo, rest days and rank
    carry independent information, and 27% of predictions land within 0.05 of
    0.5 because they were priced without them.

    This is the number Phase 1 moves, so it belongs on the page rather than in
    a notebook: on the 49.5% of fixtures where all three are present the model
    draws level with the market (Delta log-loss +0.0161, CI [-0.0063, +0.0379]);
    on the rest it loses by +0.0639.
    """
    # The exporter reads a database it does not own, so it must not assume the
    # schema: a fixture or an older copy can carry `players` without these
    # columns, and an OperationalError here is swallowed by the caller's
    # `except sqlite3.Error` and turns the whole tennis panel into
    # "unavailable" -- a diagnostic taking down the thing it describes.
    if not _table_exists(connection, "players"):
        return {}
    player_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(players)").fetchall()
    }
    if not {"current_rank", "overall_elo"} <= player_columns:
        return {}
    row = connection.execute(
        """
        SELECT COUNT(*) AS n,
               SUM(CASE WHEN pa.current_rank IS NOT NULL
                         AND pb.current_rank IS NOT NULL THEN 1 ELSE 0 END) AS ranked,
               SUM(CASE WHEN pa.overall_elo IS NOT NULL
                         AND pb.overall_elo IS NOT NULL THEN 1 ELSE 0 END) AS elo
        FROM matches m
        JOIN players pa ON pa.id = m.player_a_id
        JOIN players pb ON pb.id = m.player_b_id
        WHERE m.match_date = ?
        """,
        (analysis_date,),
    ).fetchone()
    total = int(row["n"] or 0)
    if not total:
        return {}
    return {
        "both_players_ranked": int(row["ranked"] or 0),
        "both_players_ranked_ratio": round((row["ranked"] or 0) / total, 4),
        "both_players_elo": int(row["elo"] or 0),
        "both_players_elo_ratio": round((row["elo"] or 0) / total, 4),
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
    if key.startswith("player_double_faults_"):
        return "player_double_faults"
    if key.startswith("player_total_games_"):
        return "player_total_games"
    if key.startswith("player_win_a_set_"):
        return "player_win_a_set"
    if key.startswith("first_set_winner_"):
        return "first_set_winner"
    if key.startswith("player_game_handicap_"):
        return "player_game_handicap"
    if key.startswith("player_set_handicap_"):
        return "player_set_handicap"
    if key.startswith("player_exact_set_score_"):
        return "player_exact_set_score"
    if key.startswith("total_match_games"):
        return "match_total_games"
    if key.startswith("total_aces") or key == "total_aces_in_the_match":
        return "match_total_aces"
    if "_aces" in key:
        return "player_aces"
    return key


def _normalise_tennis_quality(value: Any) -> float:
    quality = _safe_float(value) or 0.0
    if quality > 1.0:
        quality /= 100.0
    return max(0.0, min(1.0, quality))


def _tennis_confidence_score(data_quality: Any, family_stats: Dict[str, Any]) -> int:
    quality = _normalise_tennis_quality(data_quality)
    evidence = min(
        1.0, float(family_stats.get("scorecard_settled") or 0) / 120.0
    )
    try:
        advantage = float(family_stats["market_brier"]) - float(
            family_stats["model_brier"]
        )
        skill = max(0.0, min(1.0, 0.5 + advantage / 0.04))
    except (KeyError, TypeError, ValueError):
        skill = 0.25
    return round(100 * (0.45 * quality + 0.35 * evidence + 0.20 * skill))


def _tennis_stake_units(
    probability: Any,
    odds: Any,
    confidence_score: Any,
    *,
    combo: bool = False,
    early: bool = False,
) -> float:
    """Mirror Tennis' confidence-haircut tenth-Kelly display stake."""
    p = _safe_float(probability) or 0.0
    price = _safe_float(odds) or 0.0
    reliability = max(
        0.0, min(1.0, (_safe_float(confidence_score) or 0.0) / 100.0)
    )
    if not 0 < p < 1 or price <= 1 or reliability < 0.70:
        return 0.0
    full_kelly = (p * price - 1.0) / (price - 1.0)
    if full_kelly <= 0:
        return 0.0
    cap = 0.5 if early else 1.0 if combo else 2.0
    units = min(cap, full_kelly * 0.10 * 100.0 * reliability)
    units = max(0.5, units)
    return min(cap, round(units / 0.5) * 0.5)


def _tennis_source_quality(
    connection: sqlite3.Connection, row: Dict[str, Any]
) -> float:
    """Return the evidence quality of the model that priced this prop.

    Aces and double-fault models are built from serve-count history, so a
    general match feature score is neither necessary nor sufficient for those
    families.  Older dashboard fixtures/databases do not carry the newer
    subject-player fields; they retain the general-quality fallback instead of
    failing the export.
    """
    general = _normalise_tennis_quality(row.get("data_quality_score"))
    family = _tennis_prop_family(row.get("market_key"))
    if family not in {
        "player_aces", "match_total_aces", "player_double_faults"
    } or not _table_exists(connection, "player_match_history"):
        return general
    match_id = row.get("match_id")
    match_date = row.get("match_date")
    if match_id is None or not match_date:
        return general
    match = connection.execute(
        "SELECT player_a_id, player_b_id FROM matches WHERE id = ?",
        (match_id,),
    ).fetchone()
    if not match:
        return general
    subject = row.get("subject_player_id")
    if family == "match_total_aces":
        player_ids = (match["player_a_id"], match["player_b_id"])
        column = "ace_count"
    elif family == "player_aces" and subject is not None:
        opponent = (
            match["player_b_id"]
            if subject == match["player_a_id"] else match["player_a_id"]
        )
        player_ids = (subject, opponent)
        column = "ace_count"
    elif family == "player_double_faults" and subject is not None:
        player_ids = (subject,)
        column = "double_fault_count"
    else:
        return general
    history_columns = {
        item["name"]
        for item in connection.execute(
            "PRAGMA table_info(player_match_history)"
        ).fetchall()
    }
    if column not in history_columns:
        return general
    counts = [
        connection.execute(
            f"SELECT COUNT(*) FROM (SELECT 1 FROM player_match_history "
            f"WHERE player_id = ? AND match_date < ? AND {column} IS NOT NULL "
            "ORDER BY match_date DESC LIMIT 15)",
            (player_id, match_date),
        ).fetchone()[0]
        for player_id in player_ids if player_id is not None
    ]
    return min(counts, default=0) / 15.0


def _tennis_strategy_state(
    connection: sqlite3.Connection, as_of_date: Optional[str] = None
) -> Dict[str, Any]:
    """Mirror the pipeline's pre-registered prop evidence gate for display."""
    if not _table_exists(connection, "prop_tracker"):
        return {
            "status": "RESEARCH_ONLY",
            "enabled_families": [],
            "raw_scorecard_settled": 0,
            "reason": "prop_tracker unavailable",
        }
    prop_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(prop_tracker)").fetchall()
    }
    canonical_clause = "AND p.side='over'" if "side" in prop_columns else ""
    if {"prop_scope", "subject_player_id"} <= prop_columns:
        canonical_clause += (
            " AND (p.prop_scope!='player_first_set' "
            "OR p.subject_player_id=m.player_a_id)"
        )
    score_date_clause = "AND p.match_date < ?" if as_of_date else ""
    score_params = (as_of_date,) if as_of_date else ()
    score_rows = connection.execute(
        f"""
        SELECT p.match_id, p.market_key, p.model_prob_raw, p.market_prob_fair, p.result_status
        FROM prop_tracker p JOIN matches m ON m.id=p.match_id
        WHERE p.result_status IN ('WON','LOST')
          AND p.model_prob_raw IS NOT NULL
          AND p.market_prob_fair IS NOT NULL
          {canonical_clause}
          {score_date_clause}
        """,
        score_params,
    ).fetchall()
    raw_n = len(score_rows)
    subject_sql = (
        "subject_player_id"
        if "subject_player_id" in prop_columns else "NULL AS subject_player_id"
    )
    family_date_clause = (
        "AND prop_tracker.match_date < ?" if as_of_date else ""
    )
    family_params = (as_of_date,) if as_of_date else ()
    family_rows = connection.execute(
        f"""
        SELECT prop_tracker.match_id, prop_tracker.match_date, market_key,
               result_status, stake_units, profit_loss_units,
               {subject_sql},
               (SELECT MIN(fs.data_quality_score)
                FROM feature_snapshots fs
                WHERE fs.match_id = prop_tracker.match_id) AS data_quality_score
        FROM prop_tracker
        WHERE result_status IN ('WON','LOST')
          AND stake_units > 0
          AND is_value = 1
          AND blended_prob >= 0.58
          AND decimal_odds BETWEEN 1.30 AND 2.25
          AND edge > 0
          AND ev > 0
          {family_date_clause}
        """,
        family_params,
    ).fetchall()
    families: Dict[str, Dict[str, float]] = {}
    for row in family_rows:
        item = dict(row)
        if _tennis_source_quality(connection, item) < 0.65:
            continue
        bucket = families.setdefault(
            _tennis_prop_family(row["market_key"]),
            {"settled": 0, "staked": 0.0, "pnl": 0.0},
        )
        bucket["settled"] += 1
        bucket["staked"] += float(row["stake_units"] or 0)
        bucket["pnl"] += float(row["profit_loss_units"] or 0)
    enabled = []
    validated = []
    early_main = []
    supported = (
        "match_total_aces", "player_aces", "player_double_faults",
        "player_total_games", "player_win_a_set", "first_set_winner",
        "player_game_handicap", "player_set_handicap",
        "player_exact_set_score",
    )
    recommendable_player_families = set(supported) - {"match_total_aces"}
    family_scores: Dict[str, list] = {}
    for row in score_rows:
        family_scores.setdefault(_tennis_prop_family(row["market_key"]), []).append(row)
    for family in supported:
        stats = families.setdefault(
            family, {"settled": 0, "staked": 0.0, "pnl": 0.0}
        )
        staked = float(stats.get("staked") or 0)
        stats["roi"] = float(stats.get("pnl") or 0) / staked if staked else None
        score_sample = family_scores.get(family) or []
        if score_sample:
            model_brier = sum(
                (float(row["model_prob_raw"]) - (1 if row["result_status"] == "WON" else 0)) ** 2
                for row in score_sample
            ) / len(score_sample)
            market_brier = sum(
                (float(row["market_prob_fair"]) - (1 if row["result_status"] == "WON" else 0)) ** 2
                for row in score_sample
            ) / len(score_sample)
        else:
            model_brier = market_brier = None
        score_count = (
            len({int(row["match_id"]) for row in score_sample})
            if family == "player_exact_set_score"
            else len(score_sample)
        )
        stats["scorecard_settled"] = score_count
        stats["model_brier"] = model_brier
        stats["market_brier"] = market_brier
        stats["recommendable_player_prop"] = family in recommendable_player_families
        qualified = (
            family in recommendable_player_families
            and score_count >= 120
            and model_brier is not None
            and market_brier is not None
            and model_brier <= market_brier - 0.005
            and int(stats.get("settled") or 0) >= 50
            and stats["roi"] is not None
            and stats["roi"] > 0
        )
        early_qualified = (
            not qualified
            and family in recommendable_player_families
            and score_count >= 50
            and model_brier is not None
            and market_brier is not None
            and model_brier <= market_brier - 0.005
            and int(stats.get("settled") or 0) >= 3
            and stats["roi"] is not None
            and stats["roi"] > 0
        )
        stats["tier"] = (
            "VALIDATED" if qualified
            else "EARLY_MAIN" if early_qualified
            else "RESEARCH_ONLY"
        )
        stats["enabled"] = qualified or early_qualified
        stats["validated"] = qualified
        stats["early_main"] = early_qualified
        if qualified or early_qualified:
            enabled.append(family)
        if qualified:
            validated.append(family)
        elif early_qualified:
            early_main.append(family)
    return {
        "status": (
            "VALIDATED_SINGLE" if validated
            else "EARLY_MAIN" if early_main
            else "RESEARCH_ONLY"
        ),
        "enabled_families": enabled,
        "validated_families": validated,
        "early_main_families": early_main,
        "raw_scorecard_settled": raw_n,
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
    prop_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(prop_tracker)").fetchall()
    }
    subject_sql = (
        "p.subject_player_id"
        if "subject_player_id" in prop_columns else "NULL AS subject_player_id"
    )
    rows = connection.execute(
        f"""
        SELECT
            p.id, p.match_id, p.market_key, p.selection, p.side, p.line,
            p.decimal_odds, p.blended_prob, p.market_prob_fair, p.edge, p.ev,
            p.result_status, p.profit_loss_units, p.match_label,
            {subject_sql},
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
        ORDER BY p.ev DESC, p.id
        """,
        (analysis_date,),
    ).fetchall()
    recommendations = []
    selected_matches: set[int] = set()
    for row in rows:
        item = dict(row)
        family = _tennis_prop_family(item.get("market_key"))
        if family not in enabled:
            continue
        source_quality = _tennis_source_quality(connection, item)
        if source_quality < 0.65:
            continue
        match_id = int(item["match_id"])
        if match_id in selected_matches:
            continue
        event_name = f"{item.get('player_a') or '?'} vs {item.get('player_b') or '?'}"
        line = item.get("line")
        selection = str(item.get("selection") or "").strip()
        if line is not None and str(line) not in selection:
            selection = f"{selection} {line:g}" if isinstance(line, (int, float)) else f"{selection} {line}"
        outcome = _tennis_outcome(item.get("result_status"))
        model_probability = _safe_float(item.get("blended_prob"))
        odds = _safe_float(item.get("decimal_odds"))
        family_stats = (strategy.get("families") or {}).get(family) or {}
        early = family_stats.get("tier") == "EARLY_MAIN"
        confidence_score = _tennis_confidence_score(
            source_quality, family_stats
        )
        recommendations.append(
            {
                "id": f"tennis:prop:{item['id']}",
                "sport": "tennis",
                "category": "early_main_prop" if early else "validated_prop",
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
                    "hit_probability": model_probability,
                    "market_fair_probability": _safe_float(item.get("market_prob_fair")),
                    "edge": _safe_float(item.get("edge")),
                    "expected_value": _safe_float(item.get("ev")),
                    "data_quality": source_quality,
                    "confidence": confidence_score,
                    "confidence_score": confidence_score,
                    "stake_units": _tennis_stake_units(
                        model_probability, odds, confidence_score, early=early
                    ),
                    "profit_loss_units": _safe_float(item.get("profit_loss_units")),
                },
                "insight": (
                    f"{family} · EARLY_MAIN early profitable trend"
                    if early else f"{family} · evidence gate validated"
                ),
                "risk": (
                    "早期樣本有限；每注上限 0.5u，ROI 或模型優勢轉負即降級。"
                    if early else "模型即使已驗證仍有短期波動。"
                ),
                "decision": "BET",
                "confidence": confidence_score,
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
        selected_matches.add(match_id)
        if len(recommendations) == 2:
            break
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
        "confidence_score": leg.get("confidence_score"),
        "hit_probability": leg.get("hit_probability"),
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
        ORDER BY ((adjusted_confidence / 100.0) * combo_odds - 1.0) DESC,
                 recorded_at, combo_key
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
        if len(legs) != 2 or len(raw_legs) != 2:
            continue
        if len({leg.get("match_id") for leg in raw_legs}) != 2:
            continue
        if any(
            _tennis_prop_family(leg.get("market_key")) not in enabled
            or float(leg.get("odds") or 0) < 1.30
            or float(leg.get("odds") or 0) > 2.25
            or float(leg.get("confidence") or 0) < 58
            or float(leg.get("confidence_score") or 0) < 70
            or _normalise_tennis_quality(leg.get("data_quality")) < 0.65
            for leg in raw_legs
        ):
            continue
        joint_probability = _product(
            float(leg.get("confidence") or 0) / 100 for leg in raw_legs
        )
        joint_ev = (
            float(joint_probability or 0) * float(item.get("combo_odds") or 0) - 1
        )
        if joint_ev < 0.03:
            continue
        combo_confidence = min(
            float(leg.get("confidence_score") or 0) for leg in raw_legs
        )
        combo_early = any(
            ((strategy.get("families") or {}).get(
                _tennis_prop_family(leg.get("market_key"))
            ) or {}).get("tier") == "EARLY_MAIN"
            for leg in raw_legs
        )
        outcome = _tennis_outcome(item.get("result_status"))
        selection = " + ".join(leg["selection"] for leg in legs if leg["selection"])
        recommendations.append(
            {
                "id": f"tennis:combo:{item['combo_key']}",
                "sport": "tennis",
                "category": (
                    "early_main_prop_combo" if combo_early
                    else "validated_prop_combo"
                ),
                "event_date": item["match_date"],
                "event_name": (
                    "2-match Combo · EARLY_MAIN_2_LEG" if combo_early
                    else "2-match Combo · VALIDATED_2_LEG"
                ),
                "market": "Tennis Multi",
                "selection": selection,
                "odds": _safe_float(item.get("combo_odds")),
                "odds_status": "sportsbet_extracted",
                "bet_type": "combo",
                "legs": legs,
                "metrics": {
                    "model_probability": _safe_float(joint_probability),
                    "hit_probability": _safe_float(joint_probability),
                    "confidence_score": combo_confidence,
                    "edge": _safe_float(item.get("adjusted_edge")),
                    "expected_value": _safe_float(joint_ev),
                    "stake_units": _tennis_stake_units(
                        joint_probability, item.get("combo_odds"),
                        combo_confidence, combo=True, early=combo_early,
                    ),
                    "profit_loss_units": _safe_float(item.get("profit_loss_units")),
                },
                "insight": (
                    "兩腳跨場 player prop · EARLY_MAIN early trend"
                    if combo_early else
                    "兩腳跨場 player prop · evidence gate validated"
                ),
                "risk": (
                    "早期兩腳組合上限 0.5u；任何一腳落空會令整注落空，"
                    "ROI 或模型優勢轉負即降級。"
                    if combo_early else
                    "組合注要逐腳結算；任何一腳落空會令整注落空。"
                ),
                "decision": "BET",
                "confidence": item.get("adjusted_confidence"),
                "outcome": outcome,
                "actual": "待賽果" if outcome == "pending" else str(item.get("result_status")),
                "provenance": f"tennis_wc.db · combo_tracker#{item['combo_key']}",
                "source_files": ["tennis-wong-choi/tennis_wc.db"],
                "validation_status": "valid",
            }
        )
        break
    return recommendations


def _tennis_verified_record(connection: sqlite3.Connection) -> Dict[str, Any]:
    """The record on rows that were provably written before the match started.

    The panel showed a family scorecard and four archived July props and no
    overall figure at all, which reads as "quietly ticking along". It is not.
    2026-08-26: 9,594 of 13,658 prop rows were written by one run on 08-10 for
    match dates going back to 05-10, and the whole tracker then read +2.86% ROI
    while the rows that can be shown to predate their match read -23.38%
    (95% CI [-33.92, -12.65]). The profitable-looking half is the half that
    cannot be timed.

    So the page states the admissible sample and its result, and how much is
    excluded. `is_point_in_time = 1` -- never `!= 0`, which would let the
    untimeable rows back in through NULL. Returns {} on an older database
    without the column rather than guessing.
    """
    if not _table_exists(connection, "prop_tracker"):
        return {}
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(prop_tracker)").fetchall()
    }
    if "is_point_in_time" not in columns:
        return {}
    row = connection.execute(
        """
        SELECT
          SUM(CASE WHEN is_point_in_time = 1 THEN 1 ELSE 0 END) AS graded,
          SUM(CASE WHEN is_point_in_time = 1 THEN stake_units ELSE 0 END) AS staked,
          SUM(CASE WHEN is_point_in_time = 1 THEN profit_loss_units ELSE 0 END) AS pnl,
          SUM(CASE WHEN is_point_in_time = 1 AND result_status = 'WON'
                   THEN 1 ELSE 0 END) AS won,
          SUM(CASE WHEN is_point_in_time IS NOT 1 THEN 1 ELSE 0 END) AS excluded
        FROM prop_tracker
        WHERE result_status IN ('WON','LOST') AND is_value = 1 AND stake_units > 0
        """
    ).fetchone()
    graded = int(row["graded"] or 0)
    staked = float(row["staked"] or 0.0)
    if not graded or staked <= 0:
        return {}
    return {
        "point_in_time_settled": graded,
        "point_in_time_won": int(row["won"] or 0),
        "point_in_time_roi": round(float(row["pnl"] or 0.0) / staked, 4),
        "excluded_from_judgement": int(row["excluded"] or 0),
        "live_stakes_placed": 0 if not _table_exists(connection, "prop_live_bets")
        else connection.execute("SELECT COUNT(*) FROM prop_live_bets").fetchone()[0],
    }


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
        strategy = _tennis_strategy_state(connection, as_of_date=analysis_date)
        recommendations = _export_tennis_singles(connection, analysis_date, strategy)
        recommendations.extend(_export_tennis_combos(connection, analysis_date, strategy))
        coverage = _tennis_coverage(connection, analysis_date)
        verified_record = _tennis_verified_record(connection)
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
        "verified_record": verified_record,
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
