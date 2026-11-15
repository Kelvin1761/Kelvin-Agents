"""Import-safe native HKJC completed-result parsing and selection.

No data-root resolution or discovery occurs on import. Production filesystem
contexts and held-byte contexts use these same parsers and selection rules.
"""
from __future__ import annotations
import io
import ast
import json
from pathlib import Path
import re
import pandas as pd

STATIC_SEASONS = {
    "24_25": {"csv": "race_results_24_25.csv", "results_dir": "hkjc results 2024 25"},
    "25_26": {"csv": "race_results_25_26.csv", "results_dir": "hkjc results 2025 26"},
}


RESULTS_SEASON_RE = re.compile(r"^hkjc results (\d{4}) (\d{2})$")


BASE_COLUMNS = (
    "Date", "Venue", "Track", "Distance", "Horse", "Jockey", "Trainer",
    "Rank", "Win", "Place", "Odds", "Profit",
)


def season_key_from_results_dir(name: str) -> str | None:
    """Convert ``hkjc results 2026 27`` to the stats key ``26_27``."""
    match = RESULTS_SEASON_RE.fullmatch(str(name or "").strip())
    if not match:
        return None
    return f"{match.group(1)[-2:]}_{match.group(2)}"


VENUE_NORM = {
    "ST": "沙田",
    "HV": "跑馬地",
    "Sha Tin": "沙田",
    "ShaTin": "沙田",
    "Happy Valley": "跑馬地",
    "HappyValley": "跑馬地",
}


DISTANCE_RE = re.compile(r"(\d{3,4})\s*米")


def race_metadata(race: dict) -> tuple[float | None, str]:
    """Recover distance/surface from the result header tables.

    HKJC's JSON does not expose dedicated fields here, but the official header
    remains present in ``sectional_times`` / ``cumulative_times``.
    """
    header = json.dumps(
        race.get("sectional_times") or race.get("cumulative_times") or "",
        ensure_ascii=False,
    )
    distance_match = DISTANCE_RE.search(header)
    distance = float(distance_match.group(1)) if distance_match else None
    if "全天候" in header or "泥地" in header:
        track = "AWT"
    elif "草地" in header:
        track = "Turf"
    else:
        track = "Unknown"
    return distance, track


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


CLASS_LABELS = (
    ("新馬", "Griffin"), ("第一班", "Class 1"), ("第二班", "Class 2"), ("第三班", "Class 3"),
    ("第四班", "Class 4"), ("第五班", "Class 5"), ("一級賽", "Group 1"), ("國際", "Group 1"),
    ("二級賽", "Group 2"), ("三級賽", "Group 3"),
)


def _header_rows(race: dict) -> list[list[str]]:
    raw = race.get("sectional_times") or race.get("cumulative_times") or []
    if isinstance(raw, str):
        # The results writer stores the header table as a Python repr string.
        try:
            raw = ast.literal_eval(raw)
        except (ValueError, SyntaxError):
            return []
    return [[str(c).strip() for c in row] for row in raw if isinstance(row, (list, tuple))]


def _cell_after(rows: list[list[str]], label: str) -> str:
    for row in rows:
        for i, cell in enumerate(row):
            if label in cell:
                rest = [c for c in row[i + 1:] if c and c != ":"]
                return rest[0] if rest else "Unknown"
    return "Unknown"


def race_header(race: dict) -> dict:
    """Class, going and course from the official result header.

    The snapshot builder put the race title in Going and the race name in
    Course (it took the first cell of the row instead of the cell after the
    label). Rows appended here carry the real values: ``好地`` and
    ``草地 - "C" 賽道``.
    """
    rows = _header_rows(race)
    text = " ".join(" ".join(r) for r in rows) or json.dumps(race.get("sectional_times") or "", ensure_ascii=False)
    title = next((r[0] for r in rows if r and "米" in r[0] and " - " in r[0]), text)
    # None (not "Unknown") so pit_sources can still fill it from Logic／排位表.
    race_class = next((label for token, label in CLASS_LABELS if token in title), None)
    return {"RaceClass": race_class, "Going": _cell_after(rows, "場地狀況"), "Course": _cell_after(rows, "賽道")}


def _finish_seconds(value) -> float | None:
    match = re.fullmatch(r"(?:(\d+):)?(\d+(?:\.\d+)?)", str(value or "").strip())
    if not match or not match.group(1):
        return None
    return int(match.group(1)) * 60 + float(match.group(2))


def _run_style(positions: str) -> str:
    first = str(positions or "").split()[:1]
    if not first or not first[0].isdigit():
        return "Unknown"
    early = int(first[0])
    return "Frontrunner" if early <= 3 else "Midpack" if early <= 7 else "Closer"


def _odds_bucket(odds: float | None) -> str:
    if not odds or odds <= 0:
        return "Unknown"
    for cap, label in ((3, "Hot Fav (<3)"), (6, "Fav (3-6)"), (10, "Contender (6-10)"),
                       (20, "Mid (10-20)"), (50, "Longshot (20-50)")):
        if odds < cap:
            return label
    return "Outsider (50+)"


def _weight_bucket(wt: float | None) -> str:
    if wt is None:
        return "Unknown"
    for cap, label in ((115, "Light (<=115)"), (120, "Med-Light (116-120)"),
                       (126, "Medium (121-126)"), (130, "Med-Heavy (127-130)")):
        if wt <= cap:
            return label
    return "Heavy (131+)"


def hkjc_season(day: str) -> str:
    year, month = int(day[:4]), int(day[5:7])
    start = year if month >= 9 else year - 1
    return f"{start % 100:02d}/{(start + 1) % 100:02d}"


def result_row(day: str, race_key, race: dict, row: dict, header: dict) -> dict | None:
    """One runner from ``full_day_results.json`` in the race_results CSV schema.

    Until 2026-10-25 appended rows only had the 12 BASE_COLUMNS, so every
    meeting after the 2026-05-09 snapshot had no finish time, draw, weights,
    running positions or horse ID — and nothing reported it.
    """
    pos = _num(re.sub(r"\D", "", str(row.get("pos", ""))) or None)
    if pos is None or pos <= 0:
        return None
    venue = VENUE_NORM.get(str(race.get("venue", "")).strip(), str(race.get("venue", "")).strip())
    distance, track = race_metadata(race)
    odds = _num(row.get("win_odds"))
    win = 1 if pos == 1 else 0
    actual_wt = _num(row.get("actual_wt"))
    positions = str(row.get("running_positions") or "").strip()
    horse = str(row.get("horse_name", ""))
    horse_id = re.search(r"\(([A-Z]\d{3})\)\s*$", horse)
    race_no = _num(race.get("race_no")) or _num(race_key)
    return {
        "Date": day,
        "Month": day[:7],
        "Season": hkjc_season(day),
        "RaceNo": race_no,
        "RaceClass": header["RaceClass"],
        "Venue": venue,
        "Track": track,
        "Course": header["Course"],
        "Going": header["Going"],
        "Distance": distance,
        "Horse": horse,
        "Jockey": str(row.get("jockey", "")).strip(),
        "Trainer": str(row.get("trainer", "")).strip(),
        "Draw": _num(row.get("draw")),
        "Rank": pos,
        "Win": win,
        "Place": 1 if pos <= 3 else 0,
        "Odds": odds,
        "OddsBucket": _odds_bucket(odds),
        "Profit": (odds - 1.0) if (win and odds) else (-1.0 if odds else 0.0),
        "ActualWt": actual_wt,
        "WtBucket": _weight_bucket(actual_wt),
        "HorseWt": _num(row.get("horse_wt")),
        "FinishTimeSec": _finish_seconds(row.get("finish_time")),
        "RunStyle": _run_style(positions),
        "RunningPos": positions or None,
        "HorseID": horse_id.group(1) if horse_id else None,
        "Sire": "Unknown",
        "DamSire": "Unknown",
        "Origin": "Unknown",
    }



def seasons_from_entries(entries):
    seasons = {key: {**value, 'base_required': True} for key, value in STATIC_SEASONS.items()}
    for name, is_dir in entries:
        key = season_key_from_results_dir(name) if is_dir else None
        if key:
            seasons.setdefault(key, {'csv': f'race_results_{key}.csv', 'results_dir': name, 'base_required': False})
    return dict(sorted(seasons.items()))


def discover_seasons(root):
    try:
        children = list(Path(root).iterdir())
    except OSError:
        children = []
    return seasons_from_entries((path.name, path.is_dir()) for path in children)


class FilesystemRows:
    strict = False
    def __init__(self, root, stats_root, seasons, materialized):
        self.root, self.stats_root, self.seasons, self.materialized = root, stats_root, seasons, materialized
    def base_path(self, season): return self.stats_root / season / str(self.seasons[season]['csv'])
    def base_input(self, season):
        path = self.base_path(season)
        return path if self.materialized(path) else None
    def results_exist(self, season): return (self.root / self.seasons[season]['results_dir']).exists()
    def entries(self, season):
        return [(path.name, path.is_dir()) for path in sorted((self.root / self.seasons[season]['results_dir']).iterdir())]
    def daily_text(self, season, day):
        path = self.root / self.seasons[season]['results_dir'] / day / 'full_day_results.json'
        return path.read_text(encoding='utf-8') if path.exists() else None


class HeldRows:
    strict = True
    def __init__(self, root, seasons, directories, files):
        self.root, self.seasons, self.directories, self.files = root, seasons, directories, files
    def base_path(self, season): return self.root / 'comprehensive_stats' / season / str(self.seasons[season]['csv'])
    def base_input(self, season):
        raw = self.files['comprehensive_stats/' + season + '/' + str(self.seasons[season]['csv'])]
        return io.BytesIO(raw) if raw is not None else None
    def results_exist(self, season): return self.directories[self.seasons[season]['results_dir']] is not None
    def entries(self, season): return self.directories[self.seasons[season]['results_dir']]
    def daily_text(self, season, day):
        raw = self.files[self.seasons[season]['results_dir'] + '/' + day + '/full_day_results.json']
        return raw.decode('utf-8') if raw is not None else None


def load_base_rows(season_key, context):
    config = context.seasons[season_key]
    value = context.base_input(season_key)
    if value is not None:
        df = pd.read_csv(value, encoding='utf-8-sig')
        df['Date'] = df['Date'].astype(str)
        return df
    if bool(config.get('base_required', False)):
        raise RuntimeError(f'HKJC source CSV is not materialized locally: {context.base_path(season_key)}. '
                           'Mark the statistics folder Available offline before rebuilding/PIT replay.')
    if not context.results_exist(season_key):
        raise RuntimeError(f'HKJC results-only season is unavailable: {context.root / config["results_dir"]}')
    return pd.DataFrame(columns=BASE_COLUMNS)


def selected_days(season_key, base, context):
    if not context.results_exist(season_key): return []
    maximum = str(base['Date'].max()) if not base.empty else ''
    return [name for name, is_dir in context.entries(season_key) if is_dir and name > maximum]


def append_new_meetings(season_key, base, context):
    new_rows, added_dates = [], []
    for day in selected_days(season_key, base, context):
        try:
            raw = context.daily_text(season_key, day)
            if raw is None: continue
            data = json.loads(raw)
        except Exception:
            if context.strict: raise
            continue
        for race_key, race in data.items():
            if not isinstance(race, dict): continue
            header = race_header(race)
            for row in race.get('results', []):
                record = result_row(day, race_key, race, row, header)
                if record is not None: new_rows.append(record)
        added_dates.append(day)
    if not new_rows: return base, []
    appended = pd.DataFrame(new_rows)
    return (appended if base.empty else pd.concat([base, appended], ignore_index=True)), added_dates


def load_all_completed_rows(context):
    frames = []
    for season in context.seasons:
        base = load_base_rows(season, context)
        base, _added = append_new_meetings(season, base, context)
        frames.append(base)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=BASE_COLUMNS)
