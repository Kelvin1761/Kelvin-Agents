#!/usr/bin/env python3
"""Before/after measurement for the player-tour repair (EXP-20261030 tour repair).

Run once per database copy; each run is a separate process because the tennis
code reads DATABASE_URL at import time.

  PY=/Users/imac/Antigravity-repo/tennis-wong-choi/.venv/bin/python
  PYTHONDONTWRITEBYTECODE=1 $PY docs/audits/tennis-tour-repair-20261030-measure.py \
      --db before.db --out before.json [--start 2026-10-01 --end 2026-10-29]
  ... --db after.db --out after.json
  $PY docs/audits/tennis-tour-repair-20261030-measure.py --compare before.json after.json

Measures, with nothing else changed between the two copies:
  holds    -- `_ranking_identity_holds` replayed on the latest stored ATP and
              WTA ranking payloads (what the daily run would hold).
  wta_link -- share of WTA-ranked names `ingest_wta_stats._resolve_player`
              resolves (it only looks at players.tour = 'WTA').
  replay   -- match-winner probability from assemble_match_feature_snapshot +
              price_match_snapshot on settled Sportsbet fixtures, paired.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import random
import sqlite3
import sys

REPO = Path(__file__).resolve().parents[2]
# --src runs the same measurement against another checkout's code (the
# pre-change baseline); it must be on sys.path before anything is imported.
_SRC = sys.argv[sys.argv.index("--src") + 1] if "--src" in sys.argv else str(REPO / "tennis-wong-choi" / "src")
sys.path.insert(0, _SRC)


def _measure(db: Path, start: str, end: str) -> dict:
    os.environ["DATABASE_URL"] = f"sqlite:///{db}"
    from tennis_wc.features.feature_builder import assemble_match_feature_snapshot
    from tennis_wc.ingestion.ingest_rankings import _ranking_identity_holds
    from tennis_wc.ingestion.ingest_wta_stats import _resolve_player
    from tennis_wc.modelling.pricing import price_match_snapshot

    ro = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    ro.row_factory = sqlite3.Row
    out: dict = {"db": str(db)}

    holds = {}
    for tour in ("ATP", "WTA"):
        raw = ro.execute(
            "SELECT id, response_json FROM raw_api_responses WHERE entity_type='ranking' "
            "AND entity_external_id=? AND endpoint='/rankings' ORDER BY id DESC LIMIT 1", (tour,)
        ).fetchone()
        rows = json.loads(raw["response_json"])
        held = _ranking_identity_holds("composite", rows)
        holds[tour] = {"raw_response_id": raw["id"], "rows": len(rows), "held": len(held),
                       "errors": sorted({str(e).split(":")[0] for e in held.values()}),
                       "held_names": sorted(rows[i].get("player_name") for i in held)}
        if tour == "WTA":
            names = [r.get("player_name") for r in rows if r.get("player_name")]
            linked = sum(_resolve_player(ro, n) is not None for n in names)
            out["wta_link"] = {"names": len(names), "resolved": linked}
    out["holds"] = holds

    fixtures = ro.execute(
        """SELECT m.id, r.winner_player_id, m.player_a_id FROM matches m
           JOIN match_results r ON r.match_id = m.id
           WHERE m.source_provider = 'sportsbet' AND m.match_date BETWEEN ? AND ?
             AND COALESCE(m.fixture_status, '') != 'DISPUTED'
           GROUP BY m.id ORDER BY m.id""", (start, end)).fetchall()
    replay = {}
    for row in fixtures:
        try:
            snapshot, _ = assemble_match_feature_snapshot(int(row["id"]))
            priced = price_match_snapshot(snapshot)
        except Exception as exc:  # recorded, not hidden
            replay[row["id"]] = {"error": type(exc).__name__ + ": " + str(exc)[:120]}
            continue
        p_a = priced["model"].get("player_a_probability")
        replay[row["id"]] = {
            "p_a": p_a, "a_won": int(row["winner_player_id"] == row["player_a_id"]),
            "tours": [snapshot["player_a"].get("tour"), snapshot["player_b"].get("tour")],
            "fp": json.dumps({k: snapshot[k] for k in ("player_a", "player_b", "match_context")},
                             sort_keys=True, default=str),
        }
    out["replay"] = replay
    return out


def _ll(p, y):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))


# Provenance carries calculation timestamps, so every snapshot "differs" there.
_VOLATILE = {"provenance", "calculated_at", "source_timestamp", "raw_response_id"}


def _changed_paths(before, after, path=""):
    if isinstance(before, dict) and isinstance(after, dict):
        out = []
        for key in set(before) | set(after):
            if key in _VOLATILE:
                continue
            out += _changed_paths(before.get(key), after.get(key), f"{path}.{key}" if path else key)
        return out
    if before != after:
        # Collapse player_a/player_b so the count is per field, not per side.
        return [path.replace("player_a.", "player.").replace("player_b.", "player.")]
    return []


def _compare(before_path: Path, after_path: Path) -> dict:
    before, after = json.loads(before_path.read_text()), json.loads(after_path.read_text())
    paired, changed_fp, errors = [], 0, {"before": 0, "after": 0}
    changed_fields: dict[str, int] = {}
    for mid, b in before["replay"].items():
        a = after["replay"].get(mid)
        if "error" in b:
            errors["before"] += 1
        if a is None or "error" in a:
            errors["after"] += 1
        if a is None or "error" in a or "error" in b or b["p_a"] is None or a["p_a"] is None:
            continue
        diff = _changed_paths(json.loads(b["fp"]), json.loads(a["fp"]))
        changed_fp += bool(diff)
        for path in diff:
            changed_fields[path] = changed_fields.get(path, 0) + 1
        paired.append((b["p_a"], a["p_a"], b["a_won"]))
    n = len(paired)
    diffs = [_ll(pa, y) - _ll(pb, y) for pb, pa, y in paired]
    moved = sum(abs(pa - pb) > 1e-9 for pb, pa, _ in paired)
    rng = random.Random(20260826)
    boot = sorted(sum(diffs[rng.randrange(n)] for _ in range(n)) / n for _ in range(4000)) if n else []
    return {
        "holds": {t: {"before": before["holds"][t]["held"], "after": after["holds"][t]["held"],
                      "after_names": after["holds"][t]["held_names"]} for t in ("ATP", "WTA")},
        "wta_link": {"before": before["wta_link"], "after": after["wta_link"]},
        "replay": {
            "fixtures": len(before["replay"]), "paired": n, "errors": errors,
            "snapshot_changed": changed_fp, "changed_fields": changed_fields,
            "probability_moved": moved,
            "max_abs_move": max((abs(pa - pb) for pb, pa, _ in paired), default=0.0),
            "ll_before": sum(_ll(pb, y) for pb, _pa, y in paired) / n if n else None,
            "ll_after": sum(_ll(pa, y) for _pb, pa, y in paired) / n if n else None,
            "brier_before": sum((pb - y) ** 2 for pb, _pa, y in paired) / n if n else None,
            "brier_after": sum((pa - y) ** 2 for _pb, pa, y in paired) / n if n else None,
            "delta_ll_after_minus_before": sum(diffs) / n if n else None,
            "delta_ll_ci95": [boot[int(0.025 * len(boot))], boot[int(0.975 * len(boot)) - 1]] if boot else None,
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--start", default="2026-10-01")
    ap.add_argument("--end", default="2026-10-29")
    ap.add_argument("--compare", nargs=2, type=Path)
    ap.add_argument("--src", help="tennis_wc source tree to measure with (default: this checkout)")
    args = ap.parse_args()
    if args.compare:
        print(json.dumps(_compare(*args.compare), indent=2))
        return 0
    result = _measure(args.db, args.start, args.end)
    result["src"] = _SRC
    args.out.write_text(json.dumps(result))
    print(json.dumps({k: v for k, v in result.items() if k != "replay"}, indent=2)[:3000])
    print("replayed", len(result["replay"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
