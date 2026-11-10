"""Unified Wong Choi ROI board -> dashboard snapshot (Portfolio page).

The board (`<WongChoiControl>/roi_board.json`, written by
`shared_racing/scripts/wongchoi_roi.py`) is the one ROI ruler Kelvin set on
2026-11-05: each 旺財 writes its own settled numbers per day after settling
(AU `au_betting` 位注策略, NBA dashboard tracking, tennis 精選 paper bets).
This module only copies those numbers into the snapshot; it never recomputes
them, so the Portfolio page cannot disagree with the Telegram board.

HKJC is not on the board (no betting definition yet). The Portfolio page takes
HKJC from the D1 ledger via `/api/portfolio` instead and labels it as such.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1
LEDGER_NAME = "roi_board.json"

# Display order + where each number comes from (shown under each card).
DOMAINS = (
    ("au", "AU 賽馬", "au_betting 位注策略（平注 1u）"),
    ("nba", "NBA SGM", "dashboard tracking（21:00 穩膽 $1）"),
    ("nba_featured", "NBA 大細盤精選", "大細盤精選紙上盤（平注 1u，2026-11-11 起）"),
    ("tennis", "網球", "精選紙上盤（平注 1u）"),
)
FIELDS = ("bets", "hits", "stake", "pnl")


def ledger_path() -> Path:
    root = os.environ.get("WONGCHOI_CONTROL_STATE_ROOT") or (
        Path.home() / "WongChoiData" / "WongChoiControl")
    return Path(root) / LEDGER_NAME


def _row(raw) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    bets = int(raw.get("bets") or 0)
    stake = raw.get("stake")
    return {
        "bets": bets,
        "hits": int(raw.get("hits") or 0),
        "stake": round(float(bets if stake is None else stake or 0.0), 4),
        "pnl": round(float(raw.get("pnl") or 0.0), 4),
    }


def export_roi_board(path: Path | None = None) -> dict:
    """Snapshot-ready copy of the board. Raises if the ledger cannot be read."""
    path = Path(path or ledger_path())
    data = json.loads(path.read_text(encoding="utf-8"))
    raw_domains = data.get("domains") if isinstance(data, dict) else None
    if not isinstance(raw_domains, dict):
        raise ValueError(f"{path} has no domains")
    domains = {}
    for key, label, source in DOMAINS:
        entry = raw_domains.get(key) or {}
        days = {str(day): _row(row) for day, row in sorted((entry.get("days") or {}).items())}
        domains[key] = {
            "label": label,
            "source": source,
            "since": entry.get("since"),
            "day": entry.get("day"),
            "updated_at": entry.get("updated_at"),
            "cumulative": _row(entry.get("cumulative")),
            "days": days,
            # A domain that only ever wrote its cumulative row cannot be split by
            # period; the page says so instead of inventing a daily series.
            "has_days": bool(days),
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "valid",
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "domains": domains,
    }
