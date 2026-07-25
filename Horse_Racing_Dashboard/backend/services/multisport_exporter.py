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
    return {
        "selection": cells[1],
        "market": "NBA player/team milestone",
        "odds": odds,
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
                "odds_status": "archived",
                "bet_type": "combo",
                "legs": legs,
                "metrics": {"leg_count": len(legs)},
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
        recommendations.extend(_parse_nba_combos(content, analysis_date, game_tag, source_files))
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
    row = connection.execute(
        """
        SELECT MAX(candidate_date)
        FROM (
          SELECT MAX(m.match_date) AS candidate_date
          FROM market_predictions mp
          JOIN matches m ON m.id = mp.match_id
          WHERE mp.decision = 'BET' AND m.match_date <= ?
          UNION ALL
          SELECT MAX(ct.match_date) AS candidate_date
          FROM combo_tracker ct
          WHERE ct.match_date <= ?
        )
        """,
        (today, today),
    ).fetchone()
    return row[0] if row and row[0] else None


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


def _export_tennis_singles(connection: sqlite3.Connection, analysis_date: str) -> List[Dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT
            mp.id, mp.match_id, mp.market_key, mp.market_name,
            mp.selection_name, mp.selection_side, mp.line, mp.odds,
            mp.model_probability, mp.no_vig_market_probability, mp.edge,
            mp.minimum_acceptable_odds, mp.decision, mp.banker_eligible,
            mp.confidence, mp.risk, mp.reason, mp.pricing_json,
            m.match_date, m.tour, m.round,
            pa.name AS player_a, pb.name AS player_b,
            t.name AS tournament_name
        FROM market_predictions mp
        JOIN matches m ON m.id = mp.match_id
        LEFT JOIN players pa ON pa.id = m.player_a_id
        LEFT JOIN players pb ON pb.id = m.player_b_id
        LEFT JOIN tournaments t ON t.id = m.tournament_id
        WHERE m.match_date = ? AND mp.decision = 'BET'
        ORDER BY mp.banker_eligible DESC, mp.confidence DESC, mp.edge DESC, mp.id
        """,
        (analysis_date,),
    ).fetchall()
    recommendations = []
    for row in rows:
        item = dict(row)
        pricing = _load_pricing_json(item.get("pricing_json"))
        tier = pricing.get("tier") or ("BANKER" if item.get("banker_eligible") else "VALUE")
        event_name = f"{item.get('player_a') or '?'} vs {item.get('player_b') or '?'}"
        line = item.get("line")
        selection = str(item.get("selection_name") or "").strip()
        if line is not None and str(line) not in selection:
            selection = f"{selection} {line:g}" if isinstance(line, (int, float)) else f"{selection} {line}"
        recommendations.append(
            {
                "id": f"tennis:market:{item['id']}",
                "sport": "tennis",
                "category": str(tier).lower(),
                "event_date": item["match_date"],
                "event_name": event_name,
                "market": item.get("market_name") or item.get("market_key"),
                "selection": selection,
                "odds": _safe_float(item.get("odds")),
                "odds_status": "archived",
                "bet_type": "single",
                "legs": [],
                "metrics": {
                    "model_probability": _safe_float(item.get("model_probability")),
                    "market_fair_probability": _safe_float(item.get("no_vig_market_probability")),
                    "edge": _safe_float(item.get("edge")),
                    "minimum_acceptable_odds": _safe_float(item.get("minimum_acceptable_odds")),
                    "confidence": item.get("confidence"),
                },
                "insight": item.get("reason") or f"{tier} · Tennis pricing engine",
                "risk": item.get("risk") or "",
                "decision": "BET",
                "confidence": item.get("confidence"),
                "outcome": "pending",
                "actual": "待賽果",
                "provenance": f"tennis_wc.db · market_predictions#{item['id']}",
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
    }


def _export_tennis_combos(connection: sqlite3.Connection, analysis_date: str) -> List[Dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT combo_key, match_date, match_label, tier, legs_json, combo_odds,
               adjusted_confidence, adjusted_edge, stake_units, result_status,
               profit_loss_units, recorded_at
        FROM combo_tracker
        WHERE match_date = ?
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
        outcome = _tennis_outcome(item.get("result_status"))
        selection = " + ".join(leg["selection"] for leg in legs if leg["selection"])
        recommendations.append(
            {
                "id": f"tennis:combo:{item['combo_key']}",
                "sport": "tennis",
                "category": "combo",
                "event_date": item["match_date"],
                "event_name": f"{len(legs)}-match Combo · {item.get('tier') or ''}".strip(),
                "market": "Tennis Multi",
                "selection": selection,
                "odds": _safe_float(item.get("combo_odds")),
                "odds_status": "archived",
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
                "insight": f"{item.get('tier') or 'Combo'} · Tennis combo tracker",
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
    """Export eligible Tennis BET rows and combo tracker entries."""
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
        recommendations = _export_tennis_singles(connection, analysis_date)
        recommendations.extend(_export_tennis_combos(connection, analysis_date))
        connection.close()
    except sqlite3.Error as exc:
        return _empty_snapshot("tennis", run_id, "blocked", [f"tennis_database_error:{exc}"])

    return {
        "sport": "tennis",
        "analysis_run_id": f"tennis:{analysis_date}",
        "generated_at": _utc_now(),
        "validation_status": "valid" if recommendations else "unavailable",
        "recommendations": recommendations,
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
