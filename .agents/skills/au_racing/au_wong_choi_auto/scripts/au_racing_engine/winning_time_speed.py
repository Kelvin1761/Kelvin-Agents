"""WinningTime 速度分 —— 唯一計算位置（EXP-20260927-02 定義；EXP-20261124-40 新尺 PASS，Kelvin 2026-11-24 實驗性上線）。

每仗往績（今仗日期之前、唔計試閘）：
    本駒時間 = 頭馬時間 + 輸距 × (2.4 ÷ 頭馬每秒米數)
    每 km 速度 = −(本駒時間 − 場地×路程中位標準 − 地況修正) ÷ (路程 ÷ 1000)
    標準：嚴格早過今日嘅參考賽事；場地×路程 ≥10 場先有標準，地況修正 ≥40 場
速度分 = 最好 3 仗平均（最少 3 仗有標準，唔夠 = 冇）
overlay = 0.5 × 場內 z（冇速度 = 0；場內有值少過 2 匹或者冇差異 = 全部 0）

`WC_AU_SPEED_LIVE=0` 回退。參考頭馬時間表（`AU_Speed_Reference.json`）由 `au_speed_reference_table.py` 每晚重建；
引擎只用賽日之前嘅行，所以表遲建／重評分舊場次都唔會前視。冇表 = 全部 0。
研究工具（`au_speed_venue_audit.py`、盲測 monitor）import 呢度，唔准另抄一份。
"""
from __future__ import annotations

import json
import os
import re
import statistics
import unicodedata
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

RUN_RE = re.compile(
    r"^(?P<track>.+?)\sR(?P<race>\d+)\s+(?P<date>\d{4}-\d{2}-\d{2})\s+"
    r"(?P<distance>\d+)m\s+cond:(?P<condition>\S+)"
)
WT_RE = re.compile(r"WinningTime:(?:(\d+):)?([\d.]+)")
MARGIN_RE = re.compile(r"margin:(-?[\d.]+)L?")
RE_RUNNER = re.compile(r"^\[(\d+)\]\s+(.+?)\s+\(\d+\)\s*$", re.M)
RE_HDR_DIST = re.compile(r"^RACE\s+(\d+)\s*[—–-]\s*(\d{3,5})m", re.M)

GLOBAL_SPEED_K = 0.5
SPEED_MIN_CELL_RACES = 10
SPEED_MIN_GOING_RACES = 40
SPEED_MIN_RUNNER_RUNS = 3
REFERENCE_NAME = "AU_Speed_Reference.json"


def speed_live() -> bool:
    return os.environ.get("WC_AU_SPEED_LIVE", "1") != "0"


def norm(name) -> str:
    s = unicodedata.normalize("NFKD", name or "").lower()
    s = re.sub(r"\([^)]*\)", "", s)
    return re.sub(r"[^a-z0-9]", "", s)


def parse_run(line: str) -> dict | None:
    match = RUN_RE.match(line)
    winning_time = WT_RE.search(line)
    if not match or not winning_time or "**(TRIAL)**" in line:
        return None
    seconds = float(winning_time.group(2))
    if winning_time.group(1):
        seconds += int(winning_time.group(1)) * 60
    if not 25.0 < seconds < 260.0:
        return None
    margin = MARGIN_RE.search(line)
    return {
        "track": match.group("track").strip(),
        "race": int(match.group("race")),
        "date": match.group("date"),
        "distance": int(match.group("distance")),
        "condition": match.group("condition"),
        "winning_time": seconds,
        "margin": float(margin.group(1)) if margin else 0.0,
    }


def collect_reference(root: Path) -> tuple[list[dict], int]:
    """所有 Formguide 往績行 → 去重嘅場級頭馬時間（同一場喺唔同馬嘅往績重複出現）。"""
    unique: dict[tuple, dict] = {}
    conflicts = 0
    for formguide in Path(root).rglob("*Formguide.md"):
        text = formguide.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            run = parse_run(line)
            if run is None:
                continue
            key = (run["track"], run["date"], run["race"], run["distance"])
            previous = unique.get(key)
            if previous and previous["winning_time"] != run["winning_time"]:
                conflicts += 1
                continue
            unique.setdefault(key, run)
    return sorted(unique.values(), key=lambda row: row["date"]), conflicts


def build_asof_standards(observations: list[dict], target_dates: list[str]) -> dict:
    """For date D, fit every median using race observations strictly before D."""
    history: list[dict] = []
    cursor = 0
    output = {}
    for target_date in sorted(set(target_dates)):
        while cursor < len(observations) and observations[cursor]["date"] < target_date:
            history.append(observations[cursor])
            cursor += 1
        per_cell: dict[tuple, list[float]] = defaultdict(list)
        for row in history:
            per_cell[(row["track"], row["distance"])].append(row["winning_time"])
        base = {key: statistics.median(values) for key, values in per_cell.items()
                if len(values) >= SPEED_MIN_CELL_RACES}
        deviations: dict[str, list[float]] = defaultdict(list)
        for row in history:
            standard = base.get((row["track"], row["distance"]))
            if standard is not None:
                deviations[row["condition"]].append(row["winning_time"] - standard)
        going = {condition: statistics.median(values) for condition, values in deviations.items()
                 if len(values) >= SPEED_MIN_GOING_RACES}
        output[target_date] = (base, going, len(history))
    return output


def runner_speed_best3(block: str, standards: tuple[dict, dict, int], target_date: str) -> float | None:
    base, going, _ = standards
    figures = []
    for line in block.splitlines():
        run = parse_run(line)
        if run is None or run["date"] >= target_date:
            continue
        standard = base.get((run["track"], run["distance"]))
        if standard is None:
            continue
        seconds_per_length = 2.4 / (run["distance"] / run["winning_time"])
        own_time = run["winning_time"] + run["margin"] * seconds_per_length
        adjusted = own_time - standard - going.get(run["condition"], 0.0)
        figures.append(-adjusted / (run["distance"] / 1000.0))
    if len(figures) < SPEED_MIN_RUNNER_RUNS:
        return None
    return sum(sorted(figures)[-3:]) / 3.0


def zscores(values: list[float | None]) -> list[float]:
    available = [value for value in values if value is not None]
    if len(available) < 2:
        return [0.0] * len(values)
    average = statistics.mean(available)
    spread = statistics.pstdev(available)
    if spread <= 0:
        return [0.0] * len(values)
    return [0.0 if value is None else (value - average) / spread for value in values]


# ── live：參考表 → 賽日標準 → 全場速度 ────────────────────────────────────────

def _data_root() -> Path:
    repo = Path(__file__).resolve().parents[6]
    marker = repo / ".wongchoi_au_data_root"
    return Path(marker.read_text().strip()) if marker.exists() else repo / "data"


def default_reference_path() -> Path:
    override = os.environ.get("WC_AU_SPEED_REFERENCE")
    return Path(override) if override else _data_root() / REFERENCE_NAME


@lru_cache(maxsize=4)
def _read_reference(path: str, mtime: float) -> tuple:
    try:
        rows = json.loads(Path(path).read_text(encoding="utf-8")).get("rows") or []
    except (OSError, ValueError):
        return ()
    return tuple(sorted(rows, key=lambda r: r["date"]))


@lru_cache(maxsize=64)
def _standards(path: str, mtime: float, date: str):
    rows = list(_read_reference(path, mtime))
    return build_asof_standards(rows, [date])[date] if rows else None


def standards_for(date: str, path: Path | None = None):
    p = Path(path) if path else default_reference_path()
    try:
        return _standards(str(p), p.stat().st_mtime, date)
    except OSError:
        return None


def formguide_blocks(meeting_dir: Path, race_no: int) -> dict[str, str]:
    """→ {norm(馬名): 往績段落}；搵唔到 Formguide = {}。"""
    for path in sorted(Path(meeting_dir).glob(f"* Race {race_no} Formguide.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        header = RE_HDR_DIST.search(text)
        if header and int(header.group(1)) != int(race_no):
            continue
        matches = list(RE_RUNNER.finditer(text))
        out = {}
        for i, m in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            out[norm(m.group(2))] = text[m.start():end]
        return out
    return {}


def prepare_field(logic_data: dict, meeting_dir: Path, race_no: int, date: str,
                  reference: Path | None = None) -> list[float | None]:
    """逐匹計速度分寫入 `horse["winning_time_speed"]`，回傳全場速度（畀 race_context["field_speeds"]）。"""
    horses = [h for h in (logic_data.get("horses") or {}).values() if isinstance(h, dict)]
    std = standards_for(date, reference) if date else None
    blocks = formguide_blocks(meeting_dir, race_no) if std else {}
    speeds = []
    for h in horses:
        block = blocks.get(norm(h.get("horse_name")))
        value = runner_speed_best3(block, std, date) if (block and std) else None
        value = None if value is None else round(value, 6)   # 全場名單同每匹自己用同一個捨入值（Sol 2026-11-24）
        h["winning_time_speed"] = {"speed": value,
                                   "standards_races": std[2] if std else 0,
                                   "status": "ok" if value is not None else ("no_reference" if not std else "insufficient_runs")}
        speeds.append(value)
    return speeds


def feature(own: float | None, field_speeds: list | None) -> float:
    """0.5 × 場內 z；回退開關關 / 冇值 = 0。"""
    if not speed_live() or own is None:
        return 0.0
    # 全場名單已經包自己（prepare_field 逐匹寫）；唔好再加多次 —— 以前捨入唔一致會令自己計兩次。
    available = [v for v in (field_speeds or []) if v is not None]
    if len(available) < 2:
        return 0.0
    spread = statistics.pstdev(available)
    if spread <= 0:
        return 0.0
    return round(GLOBAL_SPEED_K * (own - statistics.mean(available)) / spread, 4)
