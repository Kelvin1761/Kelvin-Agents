"""HKJC 即場形勢: race-day jockey / trainer / partnership standings and track bias.

Display only: nothing here feeds scoring or selection. Every number is a count
of finishing places on ONE race day, taken from the official results database
(`HKJC_Race_Results_Database/hkjc results YYYY YY/<date>/full_day_results.json`);
no odds, no returns, no season aggregates (Kelvin 2026-11-04: "everything is
just for that day's race only"). Only the newest meeting is shown: once its
pre-race analysis is done it replaces the last one, every name on the card at
zero until its results land.
"""
from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

VENUES = {"沙田": "ST", "ShaTin": "ST", "跑馬地": "HV", "HappyValley": "HV"}
NOT_STARTED = re.compile(r"^(WV|WX|WXNR)", re.I)
DRAW_BUCKETS = (("inner", 1, 4), ("middle", 5, 8), ("outer", 9, 99))
STYLES = ("front", "middle", "back")
MEETINGS_KEPT = 1  # only the newest meeting (Kelvin 2026-11-04: no need to show previous race days)
TABLE_LIMIT = 80
HK = timezone(timedelta(hours=8))


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


def _result_files(results_root: Path):
    """Canonical full-day files, then tonight's per-race live captures (`_live/<date>.json`).

    The live file is written race by race by hkjc_live_results.py; a race already in
    the canonical file is always taken from there.
    """
    root = Path(results_root)
    for path in sorted(root.glob("hkjc results */*/full_day_results.json")):
        yield path.parent.name[:10], path
    for path in sorted((root / "_live").glob("????-??-??.json")):
        yield path.stem, path


def load_runners(results_root: Path) -> list[dict]:
    """One row per starter across every saved meeting."""
    runners, seen = [], set()
    for day, path in _result_files(results_root):
        try:
            meeting = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for race in meeting.values() if isinstance(meeting, dict) else []:
            if not isinstance(race, dict):
                continue
            key = (str(race.get("racedate") or day)[:10], _int(race.get("race_no")))
            if key in seen:
                continue
            seen.add(key)
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


def load_card(racing_root: Path, *, keep: int = MEETINGS_KEPT) -> list[dict]:
    """Jockey / trainer per declared runner of each meeting the pre-race analysis has finished.

    `HKJC_Auto_Scoring.csv` is written once the auto engine has scored the card, so its
    presence is the "analysis is made" marker: from then on the meeting shows in
    即場形勢 with every name at zero until results land (Kelvin 2026-11-04).
    """
    card, analysed = [], 0
    for folder in sorted((p for p in Path(racing_root).glob("????-??-??_*") if p.is_dir()), reverse=True):
        day, _, venue_name = folder.name.partition("_")
        venue = VENUES.get(venue_name)
        path = folder / "HKJC_Auto_Scoring.csv"
        if not venue or not path.is_file():
            continue  # facts extracted but not analysed yet: the previous meeting stays
        if analysed == keep:
            break
        analysed += 1
        try:
            with path.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
        except (OSError, csv.Error):
            continue
        for row in rows:
            race = _int(row.get("race_number"))
            if race:
                card.append({"day": day, "venue": venue, "race": race,
                             "jockey": str(row.get("jockey") or "").strip(),
                             "trainer": str(row.get("trainer") or "").strip()})
    return card


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


def _standings(rows, key, card=()):
    """Placings from results; names still to ride tonight (from the card) are listed at zero."""
    groups, rides = defaultdict(list), defaultdict(int)
    for row in rows:
        name = key(row)
        if name and all(name):
            groups[name].append(row)
    for row in card:
        name = key(row)
        if name and all(name):
            rides[name] += 1
    table = []
    for name in {**groups, **rides}:
        table.append({"name": list(name) if isinstance(name, tuple) else name, **_tally(groups.get(name, [])),
                      "rides": len(groups.get(name, [])) + rides.get(name, 0)})
    # 馬會排法：冠、亞、季、殿次數，再按出賽少者先；未有賽果嘅按今晚坐騎多者先。
    table.sort(key=lambda t: (*(-n for n in t["w"]), t["starts"], -t["rides"]))
    return table[:TABLE_LIMIT]


def _bias(rows):
    """Where tonight's placings came from: draw bucket and run style, counted not rated."""
    return {
        "draw": {b: _tally([r for r in rows if draw_bucket(r["draw"]) == b]) for b, _, _ in DRAW_BUCKETS},
        "style": {s: _tally([r for r in rows if run_style(r["early"], r["field"]) == s]) for s in STYLES},
    }


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


def build_insights(results_root: Path, *, card_root: Path | None = None, today: date | None = None,
                   keep: int = MEETINGS_KEPT) -> dict:
    runners = load_runners(results_root)
    card = load_card(card_root, keep=keep) if card_root else []
    if not runners and not card:
        return {"status": "unavailable", "generated_at": datetime.now(timezone.utc).isoformat()}
    today = today or datetime.now(HK).date()
    days = sorted({r["day"] for r in runners + card}, reverse=True)[:keep]
    meetings = []
    for day in days:
        rows = [r for r in runners if r["day"] == day]
        declared = [r for r in card if r["day"] == day]
        # Only races still to run come from the card; a finished race's names are its starters.
        done = {r["race"] for r in rows}
        upcoming = [r for r in declared if r["race"] not in done]
        meetings.append({
            "day": day, "venue": (rows or declared)[0]["venue"],
            "scheduled": len({r["race"] for r in rows + declared}),
            "races": _meeting_races(rows),
            "jockeys": _standings(rows, lambda r: r["jockey"], upcoming),
            "trainers": _standings(rows, lambda r: r["trainer"], upcoming),
            "combos": _standings(rows, lambda r: (r["jockey"], r["trainer"]), upcoming),
            "bias": _bias(rows),
        })
    return {
        "status": "valid",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "latest_is_today": days[0] == today.isoformat(),
        "meetings": meetings,
    }


def export_insights(repo_root: Path) -> dict:
    """Locate the canonical results database the reflector writes."""
    import sys
    sys.path.insert(0, str(Path(repo_root)))
    try:
        from wongchoi_paths import HK_RACING
    finally:
        sys.path.remove(str(Path(repo_root)))
    return build_insights(Path(HK_RACING) / "HKJC_Race_Results_Database", card_root=Path(HK_RACING))
