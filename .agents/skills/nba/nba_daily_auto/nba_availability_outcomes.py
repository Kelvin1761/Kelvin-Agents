#!/usr/bin/env python3
"""Did listed players actually play? Read-only calibration of injury statuses.

Joins each game's latest published pre-tip `availability_obs` (ESPN status and league
injury-report status) to the box score in Results_Brief. Answers questions like
"how often does a league 'Questionable' player play?" with counts, so day-to-day
handling can later be set from data instead of guessed. Never changes a pick.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import nba_market_ledger as ledger

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[3]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(HERE.parent))
import nba_official_injuries as official  # noqa: E402

FINAL = re.compile(r"final(?:/\d*ot|\s+\([^()]+\))?")


def _minutes(value) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if ":" in text:
            mins, secs = text.split(":", 1)
            return int(mins) + int(secs) / 60
        return float(text)
    except ValueError:
        return None


def brief_paths(target_date: str, roots: list[Path]) -> list[Path]:
    folders = []
    for root in roots:
        folders += [root / f"{target_date} NBA Analysis", *sorted(root.glob(f"{target_date} NBA Analysis*"))]
    return [p for p in (ledger.results_brief_for(f, target_date) for f in folders) if p.is_file()]


def outcomes(root: Path, analysis_roots: list[Path], since: str | None, until: str | None) -> list[dict]:
    out = []
    for day in ledger._iter_dates(since, until, root):
        rows = [r for r in ledger.read_rows(root, day) if r.get("row_type") == "availability_obs"]
        if not rows:
            continue
        by_player = defaultdict(list)
        for r in rows:
            by_player[(r.get("game_tag"), r.get("team"), r.get("name_key"))].append(r)
        briefs = brief_paths(day, analysis_roots)
        games = json.loads(briefs[0].read_text()).get("games", []) if briefs else []
        for (tag, team, key), group in by_player.items():
            snap = ledger._choose_snapshot(group)
            if snap is None:
                continue
            obs = max((r for r in group if r.get("snapshot_id") == snap),
                      key=lambda r: str(r.get("snapshot_created_at") or ""))
            game = ledger._match_game(tag, games) if games else None
            if game is None or not FINAL.fullmatch(str(game.get("status") or "").strip().lower()):
                continue
            players = [p for p in game.get("players") or []
                       if official.name_key(p.get("name")) == key and p.get("team") == team]
            minutes = _minutes(players[0].get("minutes")) if len(players) == 1 else None
            out.append({"date": day, "game_tag": tag, "team": team, "player": obs.get("player"),
                        "espn_status": obs.get("espn_status"), "official_status": obs.get("official_status"),
                        "snapshot_role": obs.get("snapshot_role"),
                        "in_box_score": len(players) == 1,
                        "played": bool(minutes and minutes > 0)})
    return out


def summarise(rows: list[dict]) -> dict:
    def table(field):
        groups = defaultdict(lambda: [0, 0])
        for r in rows:
            g = groups[r.get(field) or "not_listed"]
            g[0] += 1
            g[1] += r["played"]
        return {k: {"n": n, "played": p, "play_rate": round(p / n, 3)} for k, (n, p) in sorted(groups.items())}
    cross = defaultdict(lambda: [0, 0])
    for r in rows:
        c = cross[f'{r.get("espn_status") or "-"} | {r.get("official_status") or "-"}']
        c[0] += 1
        c[1] += r["played"]
    return {"players": len(rows), "by_official_status": table("official_status"),
            "by_espn_status": table("espn_status"),
            "espn_x_official": {k: {"n": n, "played": p} for k, (n, p) in sorted(cross.items())},
            "note": "latest published pre-tip snapshot per player-game; descriptive counts, no thresholds"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--analysis-root", type=Path, action="append", default=None)
    parser.add_argument("--since")
    parser.add_argument("--until")
    args = parser.parse_args(argv)
    roots = args.analysis_root
    if not roots:
        from wongchoi_paths import NBA_ANALYSIS
        roots = [PROJECT_ROOT, NBA_ANALYSIS]
    rows = outcomes(args.root or ledger.ledger_root(), roots, args.since, args.until)
    print(json.dumps(summarise(rows), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
