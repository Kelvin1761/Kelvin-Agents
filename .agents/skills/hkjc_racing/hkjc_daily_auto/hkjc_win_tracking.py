"""HKJC win tracking — model top pick vs the market favourite, forward only.

Kelvin 2026-11-09 asked whether to switch the primary KPI to winners.  Answer:
not now (Good stays primary); track it instead.  On the 434-race replay the
model's top pick won 25.1% vs the closing favourite 28.1% (−3.0pp, CI
[−7.6, +1.2]) and placed 52.3% vs 60.1% (−7.8pp, CI below zero).

This module only *reports* — it never touches a score.  The prediction is the
latest immutable pre-race snapshot; the favourite is the lowest final win
dividend in the official results file (HK is pari-mutuel, so that is the price
actually paid).  No ROI here: ROI goes through the unified board only
(AGENTS.md), and HKJC has no betting definition yet.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
AUTO_SCRIPTS = ROOT / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts"
for path in (ROOT, AUTO_SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

FORWARD_START = date(2026, 11, 11)   # first meeting after the decision
REPLAY_REFERENCE = "回放基準（434 場）：首選頭馬 25.1% vs 熱門 28.1%，首選上名 52.3% vs 60.1%"


def _meeting_date(path: Path) -> date | None:
    try:
        return date.fromisoformat(path.name[:10])
    except ValueError:
        return None


def race_rows(meeting_dir: Path) -> list[dict]:
    """One row per race with a frozen top pick and a usable results/odds table."""
    import hkjc_shadow_monitor as monitor

    if monitor.is_excluded("hkjc", meeting_dir):  # live record invalid
        return []

    snapshot, _manifest = monitor._prerace_snapshot(meeting_dir)
    results = json.loads(monitor._results_file(meeting_dir).read_text(encoding="utf-8"))
    rows = []
    for logic_path in sorted(snapshot.glob("Race_*_Logic.json")):
        race_no = logic_path.stem.split("_")[1]
        logic = json.loads(logic_path.read_text(encoding="utf-8"))
        ranked = sorted(
            ((int((h.get("python_auto") or {}).get("rank") or 999), int(num))
             for num, h in (logic.get("horses") or {}).items() if isinstance(h, dict)),
        )
        race = results.get(race_no) or {}
        board = {}
        for item in race.get("results") or []:
            try:
                board[int(item["horse_no"])] = (int(item["pos"]), float(item["win_odds"]))
            except (KeyError, TypeError, ValueError):
                continue
        if not ranked or ranked[0][0] == 999 or len(board) < 4:
            continue
        top = ranked[0][1]
        favourite = min(board, key=lambda horse: (board[horse][1], horse))
        if top not in board:
            continue
        rows.append({
            "meeting": meeting_dir.name, "race": int(race_no),
            "top_won": board[top][0] == 1, "top_placed": board[top][0] <= 3,
            "fav_won": board[favourite][0] == 1, "fav_placed": board[favourite][0] <= 3,
            "same_pick": top == favourite,
        })
    return rows


def collect(root: Path, start: date = FORWARD_START) -> list[dict]:
    rows = []
    for meeting_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        day = _meeting_date(meeting_dir)
        if day is None or day < start:
            continue
        try:
            rows.extend(race_rows(meeting_dir))
        except (RuntimeError, OSError, ValueError):
            continue   # no snapshot / results yet
    return rows


def section(root: Path, start: date = FORWARD_START) -> str:
    rows = collect(root, start)
    if not rows:
        return f"\n\n🏁 頭馬追蹤（由 {start.isoformat()} 起，唔影響模型）：未有完成場次\n{REPLAY_REFERENCE}"
    n = len(rows)
    pct = lambda key: 100.0 * sum(r[key] for r in rows) / n  # noqa: E731
    return (
        f"\n\n🏁 頭馬追蹤（由 {start.isoformat()} 起，{n} 場，唔影響模型）\n"
        f"首選頭馬 {pct('top_won'):.1f}% vs 熱門 {pct('fav_won'):.1f}%｜"
        f"首選上名 {pct('top_placed'):.1f}% vs 熱門 {pct('fav_placed'):.1f}%｜"
        f"同熱門一樣 {pct('same_pick'):.0f}%\n{REPLAY_REFERENCE}"
    )


if __name__ == "__main__":
    import wongchoi_paths

    print(section(Path(wongchoi_paths.HK_RACING)).strip())
