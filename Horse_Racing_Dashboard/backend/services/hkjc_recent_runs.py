"""HKJC 近績格逐仗表（Kelvin 2026-11-18）—— 純顯示，唔郁任何分數。

兩個來源都喺場次資料夾入面，都係 HKJC：
  * `*Race N 賽績.md`：排位表往績（速勢能量）—— 日數、檔位、馬重、負磅、騎師、名次／出馬、
    能量、分段時間、短評（步速／走位評述）。
  * `Race_N_Logic.json` 每匹馬 `_data.profile_runs`：HKJC 馬匹頁往績 —— 場次號（重播用）、
    班次、評分、練馬師、頭馬距離、獨贏賠率、沿途走位、完成時間、配備。
兩邊用賽事日期（DD/MM/YYYY）對。缺一邊就只出有嗰邊。
"""
import json
import re
from pathlib import Path

RACE_FILE_RE = re.compile(r"Race\s+(\d+)\s+賽績\.md$")
RUN_HEAD_RE = re.compile(r"^\s*\[(\d+)\]\s*(\d{2}/\d{2}/\d{4})\s*\|\s*日數:\s*([^|]*)\|\s*(.+?)\s*$")
FIELD_RE = re.compile(r"([^|:：]+?)\s*[:：]\s*([^|]*)")
REPLAY_URL = ("https://racing.hkjc.com/contentAsset/videoplayer_v4/video-player-iframe_v4.html"
              "?type=replay-full&date={date}&no={no:02d}&lang=chi&noPTbar=false&noLeading=false&videoParam=PAD")
RESULT_URL = ("https://racing.hkjc.com/zh-hk/local/information/localresults"
              "?racedate={date}&Racecourse={course}&RaceNo={no}")
MAX_RUNS = 6


def parse_formguide(path):
    """`{馬號: [run, ...]}`（新 → 舊）。"""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    out = {}
    for block in re.split(r"(?=^馬號:\s*)", text, flags=re.MULTILINE):
        m = re.search(r"^馬號:\s*(\d+)\s*$", block, re.MULTILINE)
        if not m:
            continue
        runs, cur = [], None
        for line in block.splitlines():
            head = RUN_HEAD_RE.match(line)
            if head:
                cur = {"date": head.group(2), "days": head.group(3).strip() or None,
                       "venue": head.group(4).strip()}
                runs.append(cur)
                continue
            if cur is None or not line.startswith("      "):
                continue
            body = line.strip()
            if body.startswith("短評"):
                cur["comment"] = body.split(":", 1)[-1].split("：", 1)[-1].strip()
                continue
            for k, v in FIELD_RE.findall(body):
                k, v = k.strip(), v.strip()
                if k == "檔位":
                    cur["draw"] = v
                elif k == "馬重":
                    cur["body_weight"] = v
                elif k == "負磅":
                    cur["weight"] = v
                elif k == "騎師":
                    cur["jockey"] = v
                elif k == "名次":
                    cur["placing"] = v
                elif k == "能量":
                    cur["energy"] = v
                elif k == "分段時間":
                    cur["sectionals"] = v
        out[int(m.group(1))] = runs[:MAX_RUNS]
    return out


def _profile_key(entry):
    full = str(entry.get("race_date_full") or "")
    m = re.match(r"(\d{4})/(\d{2})/(\d{2})$", full)
    if m:
        return f"{m.group(3)}/{m.group(2)}/{m.group(1)}"
    m = re.match(r"(\d{2})/(\d{2})/(\d{2})$", str(entry.get("date") or ""))
    return f"{m.group(1)}/{m.group(2)}/20{m.group(3)}" if m else None


def load_profile_runs(path):
    """`{馬號: [profile entry, ...]}` from one Race_N_Logic.json."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    horses = data.get("horses") or {}
    items = horses.items() if isinstance(horses, dict) else enumerate(horses, 1)
    out = {}
    for key, h in items:
        if not isinstance(h, dict):
            continue
        runs = ((h.get("_data") or {}).get("profile_runs")) or []
        try:
            number = int(h.get("horse_number") or key)
        except (TypeError, ValueError):
            continue
        if runs:
            out[number] = runs
    return out


def merge_runs(formguide_runs, profile_runs):
    profile = {_profile_key(e): e for e in profile_runs or [] if _profile_key(e)}
    rows = []
    dates = [r["date"] for r in formguide_runs or []]
    for e in profile_runs or []:
        k = _profile_key(e)
        if k and k not in dates:
            dates.append(k)
    dates.sort(key=lambda d: (d[6:], d[3:5], d[:2]), reverse=True)
    fg = {r["date"]: r for r in formguide_runs or []}
    for d in dates[:MAX_RUNS]:
        row = dict(fg.get(d) or {"date": d})
        p = profile.get(d)
        if p:
            row.update({k: v for k, v in {
                "class": p.get("class_grade"), "rating": p.get("rating"), "trainer": p.get("trainer"),
                "margin": p.get("margin_raw"), "odds": p.get("_win_odds"),
                "positions": p.get("running_positions_raw"), "finish_time": p.get("finish_time_raw"),
                "gear": p.get("gear"), "distance": p.get("distance"), "going": p.get("going"),
            }.items() if v not in (None, "", 0)})
            row.setdefault("jockey", p.get("jockey"))
            row.setdefault("draw", p.get("barrier"))
            if not row.get("placing") and p.get("placing_raw"):
                row["placing"] = str(p["placing_raw"]).lstrip("0")
            if not row.get("venue"):
                row["venue"] = " ".join(str(x) for x in (p.get("venue_track"), p.get("distance"), p.get("going")) if x)
            full = str(p.get("race_date_full") or "")
            no = p.get("race_no")
            if re.match(r"\d{4}/\d{2}/\d{2}$", full) and isinstance(no, int) and no > 0:
                row["replay_url"] = REPLAY_URL.format(date=full.replace("/", ""), no=no)
                if p.get("racecourse"):
                    row["result_url"] = RESULT_URL.format(date=full, course=p["racecourse"], no=no)
                row["race_no"] = no
        rows.append({k: v for k, v in row.items() if v not in (None, "")})
    return rows


def _profile_caches(folders):
    """HKJC 馬匹頁 cache（`scrape_hkjc_horse_profile` 寫喺 cwd/.hkjc_cache）。舊場次 Logic 冇
    `profile_runs` 時用嚟補，所以只取賽事日期早過今仗嘅往績。"""
    paths = [Path(f) / ".hkjc_cache" / "profile_cache.json" for f in folders]
    paths += [Path.cwd() / ".hkjc_cache" / "profile_cache.json",
              Path.home() / "wongchoi-scheduler" / ".hkjc_cache" / "profile_cache.json"]
    merged = {}
    for p in paths:
        try:
            cache = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for hid, item in cache.items():
            data = (item or {}).get("data") or {}
            if data.get("entries") and hid not in merged:
                merged[hid] = data["entries"]
    return merged


def _before(entry, meeting_date):
    k = _profile_key(entry)
    return bool(k) and f"{k[6:]}-{k[3:5]}-{k[:2]}" < meeting_date


def load_meeting_recent_runs(folder_paths, horse_ids=None, meeting_date=None):
    """`{場次: {馬號: [row, ...]}}` for one HKJC meeting.

    horse_ids: `{場次: {馬號: HK_2023_J463}}`（排位表），用嚟喺 Logic 冇 profile_runs 時查馬匹頁 cache。
    meeting_date: ISO 日期；cache 補嘅往績一定要早過佢。
    """
    folder_paths = list(folder_paths)
    caches = None
    out = {}
    for folder in folder_paths:
        folder = Path(folder)
        if not folder.is_dir():
            continue
        for fg_path in sorted(folder.glob("*Race * 賽績.md")):
            m = RACE_FILE_RE.search(fg_path.name)
            if not m:
                continue
            race = int(m.group(1))
            fg = parse_formguide(fg_path)
            prof = load_profile_runs(folder / f"Race_{race}_Logic.json")
            ids = (horse_ids or {}).get(race) or {}
            if meeting_date and ids and any(n not in prof for n in fg):
                if caches is None:
                    caches = _profile_caches(folder_paths)
                for n in fg:
                    if n not in prof and ids.get(n) in caches:
                        prof[n] = [e for e in caches[ids[n]] if _before(e, meeting_date)][:MAX_RUNS]
            for number in sorted(set(fg) | set(prof)):
                rows = merge_runs(fg.get(number), prof.get(number))
                if rows:
                    out.setdefault(race, {})[number] = rows
    return out
