"""Daily point-in-time snapshots of ESPN data that has no history.

ESPN's league injury list (body part, type, expected return date) and team
depth charts exist only as "today". A future feature built on them needs a
record of what was known on each day, and that record can only be taken on the
day itself -- a missed day is lost for good. See
docs/plans/2026-11-01-nba-espn-as-primary-source.md.

Research input only: nothing in the live pipeline reads these files. One
snapshot per Sydney day; partial captures are kept and say which teams failed.
Requests go through nba_espn_http (spacing + circuit): 32 calls a day.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import nba_espn_http

SITE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
SYDNEY = ZoneInfo("Australia/Sydney")
CONTRACT = "nba-espn-daily-snapshot/v1"


def snapshot_root() -> Path:
    override = os.environ.get("WC_NBA_ESPN_SNAPSHOT_DIR")
    if override:
        return Path(override)
    return Path.home() / "WongChoiData" / "NBA_ESPN_Snapshots"


def _save(folder: Path, name: str, payload) -> dict:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    (folder / name).write_bytes(data)
    return {"name": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def take_daily(*, now: datetime | None = None, get=None) -> dict:
    """Capture today's injuries and depth charts once; never raises."""
    now = now or datetime.now(timezone.utc)
    day = now.astimezone(SYDNEY).date().isoformat()
    final = snapshot_root() / day
    if (final / "manifest.json").exists():
        return {"status": "already_taken", "day": day}
    temp = final.with_name(f".{day}.tmp{os.getpid()}")
    try:
        temp.mkdir(parents=True, exist_ok=True)
        files, failures = [], []
        try:
            files.append(_save(temp, "injuries.json",
                               nba_espn_http.get_json(f"{SITE}/injuries", get=get)))
        except Exception as exc:
            failures.append({"source": "injuries", "error": f"{type(exc).__name__}: {exc}"[:200]})
        try:
            teams = [entry["team"] for entry in
                     nba_espn_http.get_json(f"{SITE}/teams", get=get)["sports"][0]["leagues"][0]["teams"]]
        except Exception as exc:
            teams = []
            failures.append({"source": "teams", "error": f"{type(exc).__name__}: {exc}"[:200]})
        for team in teams:
            abbr = str(team.get("abbreviation") or team.get("id"))
            try:
                payload = nba_espn_http.get_json(f"{SITE}/teams/{team['id']}/depthcharts", get=get)
                files.append(_save(temp, f"depthchart_{abbr}.json", payload))
            except nba_espn_http.EspnBlocked as exc:
                failures.append({"source": f"depthchart_{abbr}", "error": str(exc)[:200]})
                break   # the circuit is open: stop asking
            except Exception as exc:
                failures.append({"source": f"depthchart_{abbr}", "error": f"{type(exc).__name__}: {exc}"[:200]})
        status = "complete" if not failures and len(teams) == 30 else ("partial" if files else "failed")
        manifest = {"contract": CONTRACT, "day": day, "captured_at": now.isoformat(),
                    "status": status, "teams": len(teams), "files": files, "failures": failures}
        if status == "failed":
            return {"status": "failed", "day": day, "failures": failures}
        (temp / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, final)
        return {"status": status, "day": day, "files": len(files), "failures": len(failures)}
    except Exception as exc:
        return {"status": "failed", "day": day, "error": f"{type(exc).__name__}: {exc}"[:200]}
    finally:
        if temp.exists():
            for leftover in temp.iterdir():
                leftover.unlink()
            temp.rmdir()
