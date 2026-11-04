"""HKJC jockey / trainer / partnership standings and track-bias tables for the dashboard.

Display only: nothing here feeds scoring or selection. Every number is a count
of finishing places taken from the official results database
(`HKJC_Race_Results_Database/hkjc results YYYY YY/<date>/full_day_results.json`);
no odds, no returns. Tables are pre-aggregated per (period, venue) so the page
carries a few hundred KB instead of every runner row.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

VENUES = {"沙田": "ST", "ShaTin": "ST", "跑馬地": "HV", "HappyValley": "HV"}
NOT_STARTED = re.compile(r"^(WV|WX|WXNR)", re.I)
DRAW_BUCKETS = (("inner", 1, 4), ("middle", 5, 8), ("outer", 9, 99))
STYLES = ("front", "middle", "back")
PERIODS = ("meeting", "d30", "season", "all")
COMBO_MIN_STARTS = 3
TABLE_LIMIT = 80
HK = timezone(timedelta(hours=8))


def season_start(day: date) -> date:
    """HK seasons open in September; August belongs to the season about to start."""
    year = day.year if day.month >= 8 else day.year - 1
    return date(year, 8, 1)


def _int(value):
    match = re.match(r"\s*(\d+)", str(value or ""))
    return int(match.group(1)) if match else None


def _race_conditions(race: dict) -> dict:
    """Distance, class, going and rail live in the sectional-times header rows."""
    text = " ".join(str(cell) for row in race.get("sectional_times") or [] for cell in row)
    distance = _int(race.get("distance")) or _int((re.search(r"(\d{3,4})米", text) or [None, None])[1])
    going = race.get("going") or (re.search(r"場地狀況\s*:\s*(\S+)", text) or [None, None])[1]
    course = race.get("course") or race.get("track") or (re.search(r"賽道\s*:\s*([^：]+?賽道|全天候跑道)", text) or [None, None])[1] or ""
    rail = "AWT" if "全天候" in course else (re.search(r'"([A-C](?:\+\d)?)"', course) or [None, None])[1]
    klass = race.get("class_info") or (re.search(r"(第[一二三四五]班|一級賽|二級賽|三級賽|新馬賽|國際一級賽)", text) or [None, None])[1]
    return {"distance": distance, "going": going, "rail": rail, "class": klass}


def load_runners(results_root: Path) -> list[dict]:
    """One row per starter across every saved meeting."""
    runners = []
    for path in sorted(Path(results_root).glob("hkjc results */*/full_day_results.json")):
        try:
            meeting = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        day = path.parent.name[:10]
        for race in meeting.values() if isinstance(meeting, dict) else []:
            if not isinstance(race, dict):
                continue
            venue = VENUES.get(str(race.get("venue") or ""))
            starters = [r for r in race.get("results") or [] if not NOT_STARTED.match(str(r.get("pos") or ""))]
            if not venue or not starters:
                continue
            conditions = _race_conditions(race)
            field = len(starters)
            for row in starters:
                early = _int(str(row.get("running_positions") or "").split()[0] if row.get("running_positions") else None)
                runners.append({
                    "day": str(race.get("racedate") or day)[:10], "venue": venue, "race": _int(race.get("race_no")),
                    **conditions, "jockey": str(row.get("jockey") or "").strip(),
                    "trainer": str(row.get("trainer") or "").strip(), "draw": _int(row.get("draw")),
                    "pos": _int(row.get("pos")), "early": early, "field": field,
                    "horse": str(row.get("horse_name") or "").strip(),
                })
    return runners


def draw_bucket(draw):
    return next((name for name, low, high in DRAW_BUCKETS if draw and low <= draw <= high), None)


def run_style(early, field):
    """放頭 = in the first three at the first call, 後上 = back third, else 守中."""
    if not early or not field:
        return None
    if early <= 3:
        return "front"
    return "back" if early > field * 2 / 3 else "middle"


def _tally(rows):
    places = [r["pos"] for r in rows]
    starts = len(rows)
    counts = [sum(1 for p in places if p == n) for n in (1, 2, 3, 4)]
    return {"starts": starts, "w": counts, "top3": sum(counts[:3]), "top4": sum(counts)}


def _standings(rows, key, minimum=1):
    groups = defaultdict(list)
    for row in rows:
        name = key(row)
        if name and all(name):
            groups[name].append(row)
    table = []
    for name, group in groups.items():
        if len(group) < minimum:
            continue
        table.append({"name": list(name) if isinstance(name, tuple) else name, **_tally(group)})
    # 馬會排法：冠、亞、季、殿次數，再按出賽少者先。
    table.sort(key=lambda t: (*(-n for n in t["w"]), t["starts"]))
    return table[:TABLE_LIMIT]


def _bias(rows):
    """Draw buckets and running styles per venue × rail × distance, plus a venue total."""
    cells = defaultdict(lambda: {"draw": defaultdict(list), "style": defaultdict(list)})
    for row in rows:
        for cell_key in ((row["venue"], "all", 0), (row["venue"], row["rail"] or "?", row["distance"] or 0)):
            bucket, style = draw_bucket(row["draw"]), run_style(row["early"], row["field"])
            if bucket:
                cells[cell_key]["draw"][bucket].append(row)
            if style:
                cells[cell_key]["style"][style].append(row)
    out = []
    for (venue, rail, distance), cell in cells.items():
        races = len({(r["day"], r["race"]) for group in cell["draw"].values() for r in group})
        out.append({
            "venue": venue, "rail": rail, "distance": distance, "races": races,
            "draw": {b: _tally(cell["draw"][b]) for b, _, _ in DRAW_BUCKETS},
            "style": {s: _tally(cell["style"][s]) for s in STYLES},
        })
    out.sort(key=lambda c: (c["venue"], c["rail"] != "all", c["rail"], c["distance"]))
    return out


def _meeting_races(rows):
    """Race-by-race winners of one meeting: what the live panel shows as results land."""
    races = defaultdict(list)
    for row in rows:
        races[row["race"]].append(row)
    out = []
    for number in sorted(races):
        field = races[number]
        placed = sorted((r for r in field if r["pos"] and r["pos"] <= 4), key=lambda r: r["pos"])
        first = field[0]
        out.append({
            "race": number, "distance": first["distance"], "rail": first["rail"], "going": first["going"],
            "class": first["class"], "field": first["field"],
            "placed": [{"pos": r["pos"], "horse": r["horse"], "jockey": r["jockey"], "trainer": r["trainer"],
                        "draw": r["draw"], "bucket": draw_bucket(r["draw"]), "style": run_style(r["early"], r["field"])}
                       for r in placed],
        })
    return out


def build_insights(results_root: Path, *, today: date | None = None) -> dict:
    runners = load_runners(results_root)
    if not runners:
        return {"status": "unavailable", "generated_at": datetime.now(timezone.utc).isoformat()}
    latest = max(r["day"] for r in runners)
    latest_day = date.fromisoformat(latest)
    today = today or datetime.now(HK).date()
    since = {
        "meeting": latest,
        "d30": (latest_day - timedelta(days=30)).isoformat(),
        "season": season_start(latest_day).isoformat(),
        "all": "0000-00-00",
    }
    tables = {}
    for period in PERIODS:
        scoped = [r for r in runners if r["day"] >= since[period]]
        for venue in ("all", "ST", "HV"):
            rows = [r for r in scoped if venue == "all" or r["venue"] == venue]
            if not rows:
                continue
            tables[f"{period}:{venue}"] = {
                "races": len({(r["day"], r["race"]) for r in rows}),
                "meetings": len({r["day"] for r in rows}),
                "jockeys": _standings(rows, lambda r: r["jockey"]),
                "trainers": _standings(rows, lambda r: r["trainer"]),
                "combos": _standings(rows, lambda r: (r["jockey"], r["trainer"]),
                                     minimum=1 if period == "meeting" else COMBO_MIN_STARTS),
                "bias": _bias(rows),
            }
    meeting_rows = [r for r in runners if r["day"] == latest]
    return {
        "status": "valid",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "first_day": min(r["day"] for r in runners),
        "latest_day": latest,
        "latest_venue": meeting_rows[0]["venue"],
        "latest_is_today": latest == today.isoformat(),
        "since": since,
        "runner_count": len(runners),
        "tables": tables,
        "latest_meeting": _meeting_races(meeting_rows),
    }


def export_insights(repo_root: Path) -> dict:
    """Locate the canonical results database the reflector writes."""
    import sys
    sys.path.insert(0, str(Path(repo_root)))
    try:
        from wongchoi_paths import HK_RACING
    finally:
        sys.path.remove(str(Path(repo_root)))
    return build_insights(Path(HK_RACING) / "HKJC_Race_Results_Database")
