"""``Tennis_Daily_Report.txt``: the day's 精選 and every value prop, read from the ledger.

Written to ``<project>/<date> Tennis Analysis/`` and copied to the Google
Drive output root when one is configured (TENNIS_ANALYSIS_OUTPUT_ROOT).
"""
from __future__ import annotations

import os
from collections import defaultdict
from pathlib import Path

from tennis_wc.store.db import get_connection

PROJECT_ROOT = Path(__file__).resolve().parents[3]
REPORT_NAME = "Tennis_Daily_Report.txt"


def local_dir(match_date: str) -> Path:
    return PROJECT_ROOT / f"{match_date} Tennis Analysis"


def drive_dir(match_date: str) -> Path:
    """The Drive copy if its root exists, else the local folder."""
    root = os.environ.get("TENNIS_ANALYSIS_OUTPUT_ROOT")
    if root:
        try:
            if Path(root).is_dir():
                return Path(root) / f"{match_date} Tennis Analysis"
        except OSError:
            pass
    return local_dir(match_date)


def render(match_date: str) -> str:
    from tennis_wc.pricing.families import family_for_market
    from tennis_wc.select.featured import FAMILY_LABELS

    with get_connection() as conn:
        featured = conn.execute("""
            SELECT rank, match_label, feed_market_name, feed_selection_name, selection, odds, edge
            FROM featured_picks WHERE match_date = ? ORDER BY rank""", (match_date,)).fetchall() \
            if conn.execute("SELECT 1 FROM sqlite_master WHERE name='featured_picks'").fetchone() else []
        props = conn.execute("""
            SELECT match_label, market_key, selection, decimal_odds, model_prob_raw,
                   market_prob_fair, edge, ev, is_value, feed_market_name, feed_selection_name
            FROM prop_tracker WHERE match_date = ? ORDER BY match_label, market_key, selection""",
            (match_date,)).fetchall()
    lines = [f"Tennis Wong Choi｜{match_date}", ""]
    lines.append(f"精選 {len(featured)}／10（一場一注，每注 1 單位；紙上前向測試，未證實賺錢）")
    for f in featured:
        lines.append(f"  #{f['rank']} {f['match_label']}｜{f['feed_market_name'] or ''} → "
                     f"{f['feed_selection_name'] or f['selection']}｜賠率 {f['odds']:.2f}｜edge {f['edge']:+.3f}")
    if not featured:
        lines.append("  （暫時無精選）")
    value = [p for p in props if p["is_value"]]
    lines += ["", f"其他 value props（紙上記錄，唔係建議）：{len(value)} 注；已定價 {len(props)} 行", ""]
    by_match: dict[str, list] = defaultdict(list)
    for p in value:
        by_match[p["match_label"]].append(p)
    for label, rows in by_match.items():
        lines.append(label)
        for p in rows:
            market = p["feed_market_name"] or FAMILY_LABELS.get(family_for_market(p["market_key"]), p["market_key"])
            lines.append(f"  {market} → {p['feed_selection_name'] or p['selection']}｜賠率 {p['decimal_odds']:.2f}｜模型 "
                         f"{p['model_prob_raw']:.1%} vs 市場 {p['market_prob_fair']:.1%}｜EV {p['ev']:+.3f}")
    return "\n".join(lines) + "\n"


def write_report(match_date: str) -> Path:
    path = local_dir(match_date) / REPORT_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(match_date), encoding="utf-8")
    mirror = drive_dir(match_date)
    try:
        if mirror.resolve() != path.parent.resolve():
            mirror.mkdir(parents=True, exist_ok=True)
            (mirror / REPORT_NAME).write_bytes(path.read_bytes())
    except OSError:
        pass  # Drive is a convenience copy; the local file is the record
    return path
