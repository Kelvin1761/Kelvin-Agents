#!/usr/bin/env python3
"""AU 一段時間窗嘅表現檢討 —— 用**儲存咗嘅賽前排名**，唔重新評分。

點解要有呢個 harness：
- `au_eval` / `au_runtime_failure_audit` 全部用**現行引擎重新評分**，量到嘅係
  「今日個模型喺舊場次會點揀」，唔係「當日真係出咗咩」。
- 月報（Monthly_Reports）嘅失誤 cohort 只有數量冇分母，答唔到「邊度做得差」。
- 冇一個現成工具識得按日期窗切。

做法：
1. 每個場次揀**賽前快照**（`_prediction_snapshots/`）。賽事開跑時間冇存落場次
   資料夾，所以用「悉尼時間 11:00 前最後一個快照」；冇就退返「當日 17:00 前最早
   一個快照」並標記 `late`；再冇就剔走。兩個規則各用咗幾多場會印出嚟。
2. 賽果：場次資料夾 `Race_Results_Reflector.md`（有馬號 + SP）為主，canonical
   results CSV 用 (日期, 馬名) 補位同攞實際場地狀況。快照入面但賽果冇嘅馬當退出，
   由排名剔走（照 eval 慣例），並記低佢原本係咪模型頭四。
3. 指標一律經 `eval_metrics.race_metrics`（Gold = capture-at-4）。
4. 市場基準：同一批場次用 SP 排序當「模型」，計同一套指標。cohort 表報
   模型、市場、模型 − 市場（按場配對 bootstrap），同按馬匹數標準化嘅預期 Gold。

用法：
    PYTHONDONTWRITEBYTECODE=1 python3 au_window_review.py \
        --since 2026-09-09 --until 2026-10-08 \
        --out-json /tmp/x/dataset.json --out-md /tmp/x/report.md
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

SCRIPT_DIR = Path(__file__).resolve().parent
SKILLS = SCRIPT_DIR.parents[2]
REPO = SKILLS.parents[1]
sys.path.insert(0, str(SKILLS / "shared_racing"))
sys.path.insert(0, str(SKILLS / "shared_racing" / "scripts"))
sys.path.insert(0, str(REPO))

from corpus_paths import meeting_dirs  # noqa: E402
from eval_metrics import race_metrics  # noqa: E402
from wongchoi_paths import AU_RACING, au_historical_results_csv  # noqa: E402

sys.path.insert(0, str(SCRIPT_DIR))
from au_racing_engine.engine_core import _track_classification  # noqa: E402

SYD = ZoneInfo("Australia/Sydney")
CUTOFF_HOUR = 11      # 悉尼時間；AU 頭場極少早過 11:00
LATE_LIMIT_HOUR = 17  # 退路快照最遲幾點（之後當賽後）
BOOT = 2000
MIN_CELL = 20

# 窗口內出現嘅場地 → 州。engine_core.VENUE_STATE_MAP 只有 18 個大場，唔夠用。
STATE = {
    "NSW": "randwick rosehill warwick farm hawkesbury gosford canterbury wyong newcastle kembla "
           "grange illawarra kensington bathurst coffs harbour dubbo goulburn grafton gundagai "
           "kempsey lismore moree moruya muswellbrook queanbeyan scone tamworth tuncurry wagga "
           "wellington corowa port macquarie orange ballina cootamundra gunnedah narromine taree "
           "nowra armidale canberra mudgee walcha bowraville quirindi coonamble young cessnock "
           "inverell gilgandra parkes forbes",
    "VIC": "flemington caulfield cranbourne pakenham sale sandown moonee valley bendigo ballarat "
           "geelong kilmore mornington moe seymour tatura warrnambool wodonga hamilton kyneton "
           "donald mildura swan hill echuca bairnsdale coleraine stawell wangaratta yarra glen "
           "ararat benalla traralgon gunbower murtoa horsham colac terang st arnaud avoca",
    "QLD": "eagle farm doomben gold coast sunshine coast ipswich toowoomba mackay townsville "
           "rockhampton warwick dalby beaudesert gatton kilcoy bowen thangool longreach "
           "birdsville cloncurry cairns roma emerald",
    "SA": "morphettville murray bridge gawler balaklava bordertown port lincoln strathalbyn "
          "mount gambier naracoorte port augusta oakbank",
    "WA": "belmont ascot bunbury northam kalgoorlie york toodyay pinjarra geraldton esperance",
    "TAS": "launceston devonport hobart",
    "NT": "darwin alice springs",
}
STATE_ORDER = ["NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT"]


def venue_state(venue: str) -> str:
    v = venue.lower()
    best = ("?", 0)
    for state, names in STATE.items():
        for token in _phrases(names):
            if token in v and len(token) > best[1]:
                best = (state, len(token))
    return best[0]


def _phrases(blob: str) -> list[str]:
    # 多字場名（"eagle farm"）要當一個 token；用已知雙字名拼返。
    words = blob.split()
    doubles = {"warwick farm", "coffs harbour", "port macquarie", "moonee valley", "swan hill",
               "eagle farm", "gold coast", "sunshine coast", "murray bridge", "port lincoln",
               "mount gambier", "alice springs", "yarra glen", "st arnaud", "port augusta",
               "kembla grange"}
    out, i = [], 0
    while i < len(words):
        pair = " ".join(words[i:i + 2])
        if pair in doubles:
            out.append(pair)
            i += 2
        else:
            out.append(words[i])
            i += 1
    return out


def norm_name(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


# ---------------------------------------------------------------- snapshots

SNAP_STAMP = re.compile(r"^(\d{8}T\d{6})(?:\.\d+)?([+-]\d{4})")


def snapshot_time(name: str) -> datetime | None:
    """快照資料夾名有兩代格式：`...+0000`（UTC）同 `...+1000/+1100`（悉尼本地）。

    ⚠️ 唔可以當晒 UTC：2026-09 中之後嘅快照係本地時間，當 UTC 會將 10:39 早更
    快照當成 20:39 賽後，靜靜揀咗前一晚嗰份（未更新場地、未剔退出馬）。
    """
    m = SNAP_STAMP.match(name)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1) + m.group(2), "%Y%m%dT%H%M%S%z")
    except ValueError:
        return None


def pick_snapshot(meeting: Path, day: str) -> tuple[Path | None, str, str]:
    """→ (snapshot_dir, rule, local_time)。rule ∈ pre_cutoff / late / none。"""
    base = meeting / "_prediction_snapshots"
    if not base.is_dir():
        return None, "none", ""
    stamped = []
    for child in base.iterdir():
        t = snapshot_time(child.name)
        if t and child.is_dir():
            stamped.append((t.astimezone(SYD), child))
    stamped.sort()
    pre = [(t, p) for t, p in stamped
           if t.date().isoformat() < day or (t.date().isoformat() == day and t.hour < CUTOFF_HOUR)]
    if pre:
        t, p = pre[-1]
        return p, "pre_cutoff", t.strftime("%Y-%m-%d %H:%M")
    late = [(t, p) for t, p in stamped
            if t.date().isoformat() == day and t.hour < LATE_LIMIT_HOUR]
    if late:
        t, p = late[0]
        return p, "late", t.strftime("%Y-%m-%d %H:%M")
    return None, "none", ""


# ------------------------------------------------------------------ results

ORD = re.compile(r"^(\d+)(?:st|nd|rd|th)=?\s*:\s*#(\d+)\s+(.+?)(?:\s+\([^)]*\))?\s*(?:SP\$([\d.]+))?\s*$")


def parse_reflector_results(path: Path) -> dict[int, dict[int, dict]]:
    """→ {race: {horse_number: {pos, name, sp}}}"""
    out: dict[int, dict[int, dict]] = {}
    race = None
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"^##\s*Race\s+(\d+)", line)
        if m:
            race = int(m.group(1))
            out.setdefault(race, {})
            continue
        m = ORD.match(line.strip())
        if m and race is not None:
            out[race][int(m.group(2))] = {
                "pos": int(m.group(1)), "name": m.group(3).strip(),
                "sp": float(m.group(4)) if m.group(4) else None,
            }
    return out


def load_results_csv(path: Path, since: str, until: str) -> dict[tuple[str, str], list[dict]]:
    """(date, norm horse) → rows（同一匹馬同日理論上只跑一場）。"""
    idx: dict[tuple[str, str], list[dict]] = defaultdict(list)
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            d = row.get("Date", "")
            if not (since <= d <= until):
                continue
            idx[(d, norm_name(row.get("Horse")))].append(row)
    return idx


def _num(text) -> float | None:
    m = re.search(r"[\d.]+", str(text or ""))
    try:
        return float(m.group(0)) if m else None
    except ValueError:
        return None


# ------------------------------------------------------------- race buckets

def distance_m(text) -> int | None:
    v = _num(text)
    return int(v) if v else None


def distance_bucket(d: int | None) -> str:
    if not d:
        return "?"
    if d <= 1100:
        return "≤1100m 短途"
    if d <= 1300:
        return "1101-1300m"
    if d <= 1500:
        return "1301-1500m"
    if d <= 1800:
        return "1501-1800m"
    return "≥1801m 長途"


def class_bucket(name: str) -> str:
    v = str(name or "").lower()
    if re.search(r"\bgroup\s*1\b|\bg1\b", v):
        return "Group 1"
    if re.search(r"\bgroup\s*[23]\b|\bg[23]\b", v):
        return "Group 2/3"
    if "listed" in v:
        return "Listed"
    if "maiden" in v or "mdn" in v:
        return "Maiden"
    m = re.search(r"\b(?:bm|benchmark)\s*(\d+)", v)
    if m:
        r = int(m.group(1))
        return "BM≥78" if r >= 78 else ("BM64-76" if r >= 64 else "BM≤62")
    m = re.search(r"\b(?:class|cl)\s*(\d)", v)
    if m:
        return "Class 1-2" if int(m.group(1)) <= 2 else "Class 3-6"
    if re.search(r"rating|rst|restricted", v):
        return "Rating/Restricted"
    if re.search(r"\bhcp\b|handicap", v):
        return "Open Hcp"
    if re.search(r"quality|stakes|plate|cup|open", v):
        return "Stakes/Plate/Open"
    return "Other"


def field_bucket(n: int) -> str:
    if n <= 8:
        return "≤8"
    if n <= 10:
        return "9-10"
    if n <= 12:
        return "11-12"
    return "13+"


def going_family(text: str) -> str:
    v = str(text or "").strip().lower()
    if not v:
        return "?"
    if "synthetic" in v or v.startswith("syn"):
        return "Synthetic"
    if v.startswith(("good", "firm")):
        return "Good/Firm"
    if v.startswith("soft"):
        return "Soft"
    if v.startswith("heavy"):
        return "Heavy"
    return "Other"


def going_level(text: str) -> int | None:
    v = str(text or "").lower()
    m = re.search(r"(good|firm|soft|heavy)\s*(\d+)", v)
    return int(m.group(2)) if m else None


def gap_bucket(gap) -> str:
    try:
        g = float(gap)
    except (TypeError, ValueError):
        return "?"
    if g < 1:
        return "<1 (爭持)"
    if g < 3:
        return "1-3"
    if g < 6:
        return "3-6"
    return "≥6 (首選突出)"


def tier_name(classification: str) -> str:
    v = str(classification or "").lower()
    if "metro" in v:
        return "Metro"
    if "provincial" in v:
        return "Provincial"
    if "country" in v:
        return "Country"
    return classification or "?"


# ---------------------------------------------------------------- dataset

def build_race(meeting: Path, snap: Path, race_no: int, day: str, results: dict,
               csv_idx: dict) -> dict | None:
    logic_path = snap / f"Race_{race_no}_Logic.json"
    try:
        logic = json.loads(logic_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    ra = logic.get("race_analysis") or {}
    verdict = logic.get("python_auto_verdict") or {}
    horses_by_no = {str(k): v for k, v in (logic.get("horses") or {}).items()}
    ranking = verdict.get("ranking") or []
    res = results.get(race_no) or {}

    rows, scratched_top4, unmatched = [], 0, 0
    csv_condition = Counter()
    for r in sorted(ranking, key=lambda x: int(x.get("rank") or 999)):
        hn = int(r["horse_number"])
        name = r.get("horse_name") or ""
        h = horses_by_no.get(str(hn)) or {}
        pa = h.get("python_auto") or {}
        pos = sp = None
        if hn in res and norm_name(res[hn]["name"]) == norm_name(name):
            pos, sp = res[hn]["pos"], res[hn]["sp"]
        cands = csv_idx.get((day, norm_name(name))) or []
        for c in cands:
            csv_condition[c.get("Condition", "")] += 1
            if pos is None and str(c.get("Pos", "")).isdigit():
                pos, sp = int(c["Pos"]), _num(c.get("SP"))
            elif sp is None:
                sp = _num(c.get("SP"))
        if pos is None:
            unmatched += 1
            if int(r.get("rank") or 99) <= 4:
                scratched_top4 += 1
            continue
        data = h.get("_data") or {}
        rows.append({
            "n": hn, "name": name, "orig_rank": int(r.get("rank") or 0),
            "score": float(r.get("ability_score") or pa.get("rank_score") or 0.0),
            "pos": pos, "sp": sp,
            "barrier": h.get("barrier"), "career_starts": h.get("career_race_starts"),
            "career_tag": h.get("career_tag"),
            "features": pa.get("feature_scores") or {},
            "matrix": pa.get("matrix_scores") or {},
            "coverage_pct": (pa.get("data_coverage") or {}).get("coverage_pct"),
            "coverage_conf": (pa.get("data_coverage") or {}).get("confidence"),
            "missing": (pa.get("data_coverage") or {}).get("missing_features") or [],
            "risk_flags": pa.get("risk_flags") or [],
            "win_odds": data.get("win_odds"),
            "prep_stage": (pa.get("preparation_cycle") or {}).get("stage"),
            "days_since_last": (pa.get("preparation_cycle") or {}).get("days_since_last_run"),
            "prior_spell_days": (pa.get("preparation_cycle") or {}).get("prior_spell_days"),
        })
    if len(rows) < 4 or sum(1 for x in rows if x["pos"] <= 3) < 3:
        return {"skip": "incomplete_results", "meeting": meeting.name, "race": race_no,
                "ranked": len(ranking), "matched": len(rows)}

    # 退出馬剔走後重新排名（照 eval 慣例）
    rows.sort(key=lambda x: x["orig_rank"])
    for i, x in enumerate(rows, 1):
        x["rank"] = i
    actual_pos = {x["n"]: x["pos"] for x in rows}
    top3 = [n for n, p in actual_pos.items() if p <= 3]
    winner = next((n for n, p in actual_pos.items() if p == 1), None)
    model = race_metrics([x["n"] for x in rows], top3, winner, actual_pos, len(rows))

    sp_ok = all(x["sp"] for x in rows)
    market = None
    if sp_ok:
        mk = sorted(rows, key=lambda x: (x["sp"], x["n"]))
        for i, x in enumerate(mk, 1):
            x["mkt_rank"] = i
        market = race_metrics([x["n"] for x in mk], top3, winner, actual_pos, len(rows))

    going_pred = ra.get("going") or (ra.get("meeting_intelligence") or {}).get("going") or ""
    going_actual = csv_condition.most_common(1)[0][0] if csv_condition else ""
    speed_map = ra.get("speed_map") or {}
    dist = distance_m(ra.get("distance"))
    venue = (ra.get("meeting_intelligence") or {}).get("venue") or meeting.name[11:].split(" Race")[0]
    return {
        "meeting": meeting.name, "date": day, "venue": venue, "race": race_no,
        "state": venue_state(venue),
        # 舊快照嘅 classification 可能係空（幾何檔當時未補），退返引擎現行查表。
        "tier": tier_name((ra.get("track_profile") or {}).get("classification")
                          or _track_classification(venue)),
        "race_name": ra.get("race_class") or "", "class": class_bucket(ra.get("race_class")),
        "distance": dist, "dist_bucket": distance_bucket(dist),
        "going_pred": going_pred, "going_actual": going_actual,
        "going_family": going_family(going_actual or going_pred),
        "going_changed": bool(going_actual and going_family(going_actual) != going_family(going_pred)),
        "going_level_delta": (
            (going_level(going_actual) or 0) - (going_level(going_pred) or 0)
            if going_level(going_actual) and going_level(going_pred) else None),
        "going_refresh": ra.get("going_refresh") or {},
        "field": len(rows), "field_bucket": field_bucket(len(rows)),
        "ranked": len(ranking), "scratched_after_snapshot": unmatched,
        "scratched_in_top4": scratched_top4,
        "pace": speed_map.get("predicted_pace") or "?",
        "pace_conf": speed_map.get("pace_confidence") or "?",
        "confidence_tier": verdict.get("confidence_tier") or "?",
        "gap12": verdict.get("top1_top2_gap"), "gap_bucket": gap_bucket(verdict.get("top1_top2_gap")),
        "pf_coverage": verdict.get("pace_figure_coverage"),
        "rows": rows, "model": _slim(model), "market": _slim(market) if market else None,
    }


def _slim(m: dict) -> dict:
    keys = ("gold", "gold_strict", "good_positional", "pass", "hits", "champion",
            "winner_in_top3", "winner_in_top5", "top3_capture_at4", "top3_capture_at5",
            "winner_rank", "actual_top3_model_ranks", "exclusive_label", "top2_any_blowout")
    return {k: m.get(k) for k in keys}


def load_start_times(mapping_path: Path | None, cache_dir: Path | None):
    """→ fn(meeting_name) → {race_no: 開跑 datetime}。

    排程嘅 `sb_archive_meeting_ids.json` 有每場 Sportsbet raceId；cache 咗嘅賽事頁
    導覽列（`Race N<abbr data-utime=…>`）有**成個場次每場**嘅開跑時間。
    攞唔到就回 {}，由 caller 退返固定截止時間。
    """
    import hashlib as _h
    try:
        mapping = json.loads(Path(mapping_path).read_text(encoding="utf-8")) if mapping_path else {}
    except (OSError, ValueError):
        mapping = {}
    nav = re.compile(r'href="/\d+/\d+/">Race (\d+)<abbr data-utime="(\d+)"')

    def lookup(meeting_name: str) -> dict[int, datetime]:
        meta = mapping.get(meeting_name)
        if not meta or not cache_dir:
            return {}
        for rid in meta.get("races") or []:
            url = f"https://www.sportsbetform.com.au/{meta['meetingId']}/{rid}/"
            page = Path(cache_dir) / (_h.sha1(url.encode()).hexdigest() + ".html")
            try:
                text = page.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            found = {int(n): datetime.fromtimestamp(int(t), tz=timezone.utc)
                     for n, t in nav.findall(text)}
            if found:
                return found
        return {}
    return lookup


def stamped_snapshots(meeting: Path) -> list[tuple[datetime, Path]]:
    base = meeting / "_prediction_snapshots"
    if not base.is_dir():
        return []
    out = [(t, child) for child in base.iterdir()
           if child.is_dir() and (t := snapshot_time(child.name))]
    return sorted(out)


def pick_for_race(stamped, start: datetime | None, meeting: Path, day: str):
    """有開跑時間：該場開跑前最後一個快照（rule=pre_start）。冇：退返固定截止。"""
    if start is not None:
        pre = [(t, p) for t, p in stamped if t < start]
        if pre:
            t, p = pre[-1]
            return p, "pre_start", t.astimezone(SYD).strftime("%Y-%m-%d %H:%M")
        return None, "none", ""
    return pick_snapshot(meeting, day)


def build_dataset(root: Path, since: str, until: str, start_lookup=None) -> dict:
    csv_idx = load_results_csv(au_historical_results_csv(root), since, until)
    start_lookup = start_lookup or (lambda _name: {})
    races, skipped, meetings = [], [], []
    for meeting in meeting_dirs(root):
        day = meeting.name[:10]
        if not (since <= day <= until):
            continue
        stamped = stamped_snapshots(meeting)
        starts = start_lookup(meeting.name)
        numbers = sorted({int(m.group(1)) for _, snap in stamped for q in snap.glob("Race_*_Logic.json")
                          if (m := re.match(r"Race_(\d+)_Logic", q.name))})
        results = parse_reflector_results(meeting / "Race_Results_Reflector.md")
        rules = Counter()
        for race_no in numbers:
            snap, rule, local = pick_for_race(stamped, starts.get(race_no), meeting, day)
            rules[rule] += 1
            if snap is None:
                skipped.append({"meeting": meeting.name, "race": race_no, "skip": "no_pre_race_snapshot"})
                continue
            row = build_race(meeting, snap, race_no, day, results, csv_idx)
            if row is None:
                skipped.append({"meeting": meeting.name, "race": race_no, "skip": "bad_logic"})
            elif "skip" in row:
                skipped.append(row)
            else:
                row["snapshot_rule"], row["snapshot_local"], row["snapshot"] = rule, local, snap.name
                if starts.get(race_no):
                    row["start_local"] = starts[race_no].astimezone(SYD).strftime("%Y-%m-%d %H:%M")
                races.append(row)
        meetings.append({"meeting": meeting.name, "rules": dict(rules),
                         "has_start_times": bool(starts)})
    races.sort(key=lambda r: (r["date"], r["venue"], r["race"]))
    blob = json.dumps([(r["meeting"], r["race"], [(x["n"], x["rank"], x["pos"]) for x in r["rows"]])
                       for r in races], ensure_ascii=False).encode()
    return {"since": since, "until": until, "races": races, "skipped": skipped,
            "meetings": meetings, "fingerprint": hashlib.sha256(blob).hexdigest()}


# ---------------------------------------------------------------- summaries

def rate(races, side, key):
    vals = [r[side][key] for r in races if r.get(side) and r[side].get(key) is not None]
    return (sum(1 for v in vals if v) / len(vals)) if vals else float("nan")


def auc_top5(races, side):
    """au_eval._pairs 嘅 top_only 定義：上名 vs 非上名，至少一方喺頭五。"""
    c = n = 0.0
    key = "rank" if side == "model" else "mkt_rank"
    for r in races:
        rows = r["rows"]
        if side == "market" and not r.get("market"):
            continue
        for a in rows:
            if a["pos"] > 3:
                continue
            for b in rows:
                if b["pos"] <= 3:
                    continue
                if a[key] > 5 and b[key] > 5:
                    continue
                n += 1
                c += 1.0 if a[key] < b[key] else 0.0
    return c / n if n else float("nan")


def paired_ci(races, key, seed=7):
    """模型 − 市場（同一批場次），按場重抽。"""
    pairs = [(1.0 if r["model"][key] else 0.0, 1.0 if r["market"][key] else 0.0)
             for r in races if r.get("market")]
    if len(pairs) < 2:
        return float("nan"), float("nan"), float("nan")
    rng = random.Random(seed)
    m = len(pairs)
    point = sum(a - b for a, b in pairs) / m
    ds = []
    for _ in range(BOOT):
        s = 0.0
        for _ in range(m):
            a, b = pairs[rng.randrange(m)]
            s += a - b
        ds.append(s / m)
    ds.sort()
    return point, ds[int(0.025 * BOOT)], ds[int(0.975 * BOOT) - 1]


def mean_ci(vals, seed=11):
    """→ (mean, lo, hi)，按場重抽。"""
    if len(vals) < 2:
        return float("nan"), float("nan"), float("nan")
    rng = random.Random(seed)
    m = len(vals)
    ds = sorted(sum(vals[rng.randrange(m)] for _ in range(m)) / m for _ in range(BOOT))
    return sum(vals) / m, ds[int(0.025 * BOOT)], ds[int(0.975 * BOOT) - 1]


def baselines(all_races):
    """全窗口嘅基準：按馬匹數嘅 Gold/Good，同整體 模型−市場 差距。"""
    by_field = defaultdict(lambda: defaultdict(list))
    for r in all_races:
        for key in ("gold", "good_positional"):
            by_field[key][r["field_bucket"]].append(1.0 if r["model"][key] else 0.0)
    field = {key: {fb: sum(v) / len(v) for fb, v in d.items()} for key, d in by_field.items()}
    mk = [r for r in all_races if r.get("market")]
    gap = {key: sum((1.0 if r["model"][key] else 0.0) - (1.0 if r["market"][key] else 0.0)
                    for r in mk) / len(mk) for key in ("gold", "good_positional")}
    return field, gap


def cohort_rows(races, all_races, key_fn):
    field, gap = baselines(all_races)
    groups = defaultdict(list)
    for r in races:
        groups[key_fn(r)].append(r)
    nan3 = (float("nan"),) * 3
    out = []
    for name, rs in groups.items():
        with_mkt = [r for r in rs if r.get("market")]
        big = len(rs) >= MIN_CELL
        tests = {}
        for key, short in (("gold", "Gold"), ("good_positional", "Good")):
            resid = [(1.0 if r["model"][key] else 0.0) - field[key][r["field_bucket"]] for r in rs]
            rel = [((1.0 if r["model"][key] else 0.0) - (1.0 if r["market"][key] else 0.0)) - gap[key]
                   for r in with_mkt]
            tests[f"{short}_vs_field"] = mean_ci(resid) if big else nan3
            tests[f"{short}_vs_mkt_gap"] = mean_ci(rel) if len(with_mkt) >= MIN_CELL else nan3
        out.append({
            "cohort": name, "n": len(rs), "n_mkt": len(with_mkt),
            "avg_field": sum(r["field"] for r in rs) / len(rs),
            "gold": rate(rs, "model", "gold"),
            "gold_expected_by_field": sum(field["gold"][r["field_bucket"]] for r in rs) / len(rs),
            "good": rate(rs, "model", "good_positional"),
            "good_expected_by_field": sum(field["good_positional"][r["field_bucket"]] for r in rs) / len(rs),
            "champion": rate(rs, "model", "champion"),
            "win_in_top3": rate(rs, "model", "winner_in_top3"),
            "auc5": auc_top5(rs, "model"),
            "mkt_gold": rate(with_mkt, "market", "gold"),
            "mkt_good": rate(with_mkt, "market", "good_positional"),
            "mkt_auc5": auc_top5(with_mkt, "market"),
            "tests": tests,
            "miss_rate": sum(1 for r in rs if r["model"]["hits"] == 0) / len(rs),
        })
    out.sort(key=lambda x: -x["n"])
    return out


COHORTS = {
    "州": lambda r: r["state"],
    "場地級別": lambda r: r["tier"],
    "馬場": lambda r: r["venue"],
    "路程": lambda r: r["dist_bucket"],
    "班次": lambda r: r["class"],
    "馬匹數（退出後）": lambda r: r["field_bucket"],
    "場地狀況（實際）": lambda r: r["going_family"],
    "場地預測 vs 實際": lambda r: "預測同實際一致" if not r["going_changed"] else "預測錯咗場地類別",
    "預測步速": lambda r: r["pace"],
    "信心級別": lambda r: r["confidence_tier"],
    "頭兩名分差": lambda r: r["gap_bucket"],
    "快照後有退出馬": lambda r: ("模型頭四有馬退出" if r["scratched_in_top4"]
                              else ("有退出（唔喺頭四）" if r["scratched_after_snapshot"] else "冇")),
    "快照規則": lambda r: r["snapshot_rule"],
}


def pct(x, d=1):
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{100 * x:.{d}f}%"


def pp(x):
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{100 * x:+.1f}"


def ci_txt(t):
    return f"{pp(t[0])} [{pp(t[1])},{pp(t[2])}]"


def verdict(row):
    """四個檢定（Gold/Good × 對馬匹數預期／對整體市場差距）至少兩個同方向
    CI 唔跨零先下判斷。格多，單一個 CI 唔跨零好容易係偶然。"""
    if row["n"] < MIN_CELL:
        return "樣本細"
    ups = sum(1 for t in row["tests"].values() if t[1] > 0)
    downs = sum(1 for t in row["tests"].values() if t[2] < 0)
    if ups >= 2 and not downs:
        return "✅ 特別好"
    if downs >= 2 and not ups:
        return "❌ 特別差"
    if ups or downs:
        return "↑ 邊緣" if ups > downs else ("↓ 邊緣" if downs > ups else "混合")
    return "≈ 正常"


def render_md(ds: dict) -> str:
    races = ds["races"]
    rules = Counter(r["snapshot_rule"] for r in ds["races"])
    skip = Counter(s.get("skip") for s in ds["skipped"])
    with_mkt = [r for r in races if r.get("market")]
    lines = [
        f"# AU 表現檢討 {ds['since']} → {ds['until']}",
        "",
        f"- 場次：{len(ds['meetings'])}（有開跑時間 {sum(m['has_start_times'] for m in ds['meetings'])}）；"
        f"逐場快照規則：{dict(rules)}",
        f"- 計入場數：{len(races)}（有完整 SP：{len(with_mkt)}）；剔走：{dict(skip)}",
        f"- dataset fingerprint：`{ds['fingerprint'][:16]}`",
        "",
        "## 總覽（模型 vs 市場 SP 排序，同一批場次）",
        "",
        "| 指標 | 模型 | 市場 | 模型−市場 (95% CI) |",
        "|---|---:|---:|---:|",
    ]
    for key, label in (("gold", "Gold（前三全喺頭四）"), ("good_positional", "Good（頭兩揀都上名）"),
                       ("pass", "Pass（頭三揀≥2 上名）"), ("champion", "首選勝出"),
                       ("winner_in_top3", "頭馬喺頭三揀")):
        d = paired_ci(with_mkt, key)
        lines.append(f"| {label} | {pct(rate(with_mkt, 'model', key))} | "
                     f"{pct(rate(with_mkt, 'market', key))} | {pp(d[0])} [{pp(d[1])}, {pp(d[2])}] |")
    lines.append(f"| Top5 AUC | {auc_top5(with_mkt, 'model'):.4f} | {auc_top5(with_mkt, 'market'):.4f} | |")
    lines.append(f"| 完全 Miss（頭三揀 0 上名） | "
                 f"{pct(sum(1 for r in races if r['model']['hits'] == 0) / len(races))} | | |")
    lines += ["",
              "cohort 表：「Gold−預期」= 實際 Gold 減按馬匹數預期；「Gold 相對市場」= 呢格嘅"
              "（模型−市場）減整體（模型−市場），正數 = 呢格輸市場輸得少過平均。",
              "判斷要四個 CI 有兩個同方向唔跨零；格多，單一 CI 唔跨零好容易係偶然。", ""]
    for title, fn in COHORTS.items():
        rows = cohort_rows(races, races, fn)
        if title == "馬場":
            rows = [r for r in rows if r["n"] >= 15]
        lines += [f"## {title}", "",
                  "| cohort | 場數 | 平均馬數 | Gold | Gold−預期 [CI] | Gold 相對市場 [CI] | Good | "
                  "Good−預期 [CI] | Good 相對市場 [CI] | 首選勝 | AUC5 | 市場 Gold | 判斷 |",
                  "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
        for r in rows:
            t = r["tests"]
            lines.append(
                f"| {r['cohort']} | {r['n']} | {r['avg_field']:.1f} | {pct(r['gold'])} | "
                f"{ci_txt(t['Gold_vs_field'])} | {ci_txt(t['Gold_vs_mkt_gap'])} | {pct(r['good'])} | "
                f"{ci_txt(t['Good_vs_field'])} | {ci_txt(t['Good_vs_mkt_gap'])} | {pct(r['champion'])} | "
                f"{r['auc5']:.3f} | {pct(r['mkt_gold'])} | {verdict(r)} |")
        lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--since", required=True)
    ap.add_argument("--until", required=True)
    ap.add_argument("--root", default=str(AU_RACING))
    ap.add_argument("--mapping", default=str(SKILLS / "au_racing" / "data" / "sb_archive_meeting_ids.json"),
                    help="排程嘅 meeting→raceId 對應表（攞開跑時間用）")
    ap.add_argument("--sb-cache", default=str(SKILLS / "au_racing" / ".sportsbet_cache"))
    ap.add_argument("--out-json")
    ap.add_argument("--out-md")
    args = ap.parse_args(argv)
    ds = build_dataset(Path(args.root), args.since, args.until,
                       load_start_times(Path(args.mapping), Path(args.sb_cache)))
    if args.out_json:
        Path(args.out_json).write_text(json.dumps(ds, ensure_ascii=False), encoding="utf-8")
    md = render_md(ds)
    if args.out_md:
        Path(args.out_md).write_text(md, encoding="utf-8")
    else:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
