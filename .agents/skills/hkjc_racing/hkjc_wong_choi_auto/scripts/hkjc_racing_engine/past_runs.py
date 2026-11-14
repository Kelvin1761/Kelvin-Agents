"""逐仗往績（賽績檔）：負磅、路程、分段時間 —— 畀段速維度做負磅換算同「對馬會標準」顯示。

Logic 只有近仗字串（L400、名次、輸頭馬），冇逐仗負磅同分段時間；賽績檔（`*Race N 賽績.md`）有。
呢個 module 喺評分前由 orchestrator 叫一次（`attach`），將以下寫入每匹馬 `_data`：

* ``formguide_today_weight``：今仗實際負磅（賽績檔頂部 `負磅:`，已扣見習減磅）
* ``l400_last_run``：上仗 {date, distance, weight, l400}
  —— 段速分「L400 絕對值」按負磅換算用（EXP-20261112-05／-13，入分）
* ``std_pace``：近 6 仗對馬會標準分段嘅偏差（EXP-20261112-09 定義，**只顯示，唔入分**；forward shadow 見 EXP-20261112-13）

全部只用賽日之前嘅仗。
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path

# .agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts/hkjc_racing_engine/past_runs.py → .agents/
_AGENTS = Path(__file__).resolve().parents[5]
STANDARD_TIMES_JSON = _AGENTS / "scripts" / "hkjc_standard_times.json"

# EXP-20261112-09：早段每慢 1 秒，末段平均追返 0.382 秒（馬匹 FE，只用 2026-05-03 之前 5,541 仗估）。
PACE_RECOVERY_RHO = 0.382
# EXP-20261112-06：每多 1 磅，完成時間慢 0.01123 秒／公里（只用 2026-05-03 之前賽果估）。
WEIGHT_SECONDS_PER_KM_PER_LB = 0.01123
STD_PACE_RUNS = 6

_RUN_HEAD = re.compile(r"^\s*\[(\d+)\]\s+(\d{2}/\d{2}/\d{4})\s*\|[^|\n]*\|\s*(\S+)\s+\"([^\"]*)\"\s+(\d{3,4})\b")
_RUN_WEIGHT = re.compile(r"負磅:\s*(\d+)")
_RUN_POS = re.compile(r"名次:\s*(\S+)\s*/\s*(\d+)")
_RUN_SPLITS = re.compile(r"分段時間:\s*([\d\., ]+)")
_CLASS_CODES = {"第一班": "C1", "第二班": "C2", "第三班": "C3", "第四班": "C4", "第五班": "C5",
                "一級賽": "G", "二級賽": "G", "三級賽": "G", "分級賽": "G", "新馬賽": "GR"}
_RECENT_CLASS = re.compile(r"第\d仗\((\d{2}/\d{2}/\d{4})\s+([^)]*?)\)")


def parse_formguide(text: str) -> dict[int, dict]:
    """{馬號: {"today_weight": int|None, "runs": [run, ...]}}，run 由新到舊（照檔案次序）。"""
    out: dict[int, dict] = {}
    for block in re.split(r"\n(?=馬號:\s*\d+)", str(text or "")):
        m = re.match(r"\s*馬號:\s*(\d+)", block)
        if not m:
            continue
        today = re.search(r"^負磅:\s*(\d+)", block, re.M)
        runs, cur = [], None
        for line in block.splitlines():
            head = _RUN_HEAD.match(line)
            if head:
                try:
                    run_date = datetime.strptime(head.group(2), "%d/%m/%Y").date()
                except ValueError:
                    cur = None
                    continue
                cur = {"date": run_date, "venue": head.group(3), "course": head.group(4),
                       "awt": "AWT" in head.group(4).upper(), "distance": int(head.group(5)),
                       "weight": None, "pos": None, "splits": []}
                runs.append(cur)
                continue
            if cur is None:
                continue
            if cur["weight"] is None and "負磅:" in line:
                w = _RUN_WEIGHT.search(line)
                cur["weight"] = int(w.group(1)) if w else None
                p = _RUN_POS.search(line)
                if p and p.group(1).isdigit():
                    cur["pos"] = int(p.group(1))
            if not cur["splits"] and "分段時間:" in line:
                s = _RUN_SPLITS.search(line)
                cur["splits"] = [float(x) for x in re.findall(r"\d+\.\d+", s.group(1))] if s else []
        out[int(m.group(1))] = {"today_weight": int(today.group(1)) if today else None, "runs": runs}
    return out


def class_code(text) -> str | None:
    compact = re.sub(r"\s+", "", str(text or ""))
    for label, code in _CLASS_CODES.items():
        if label in compact:
            return code
    m = re.search(r"(?:CLASS|C)\s*([1-5])", compact, re.I)
    return f"C{m.group(1)}" if m else None


@lru_cache(maxsize=1)
def _reference_sectionals() -> dict:
    try:
        return json.loads(STANDARD_TIMES_JSON.read_text(encoding="utf-8")).get("reference_sectionals", {}).get("venues", {})
    except (OSError, ValueError):
        return {}


def standard_sections(venue: str, awt: bool, distance: int, code: str | None) -> list[float] | None:
    """馬會標準分段（場地、路程、班次）；搵唔到返 None，唔借第二個班次。"""
    if not code:
        return None
    vkey = "sha_tin_awt" if awt else ("happy_valley_turf" if "跑馬地" in str(venue) else "sha_tin_turf")
    entry = ((_reference_sectionals().get(vkey) or {}).get(str(distance)) or {}).get(code) or {}
    sections = entry.get("sections")
    return [float(x) for x in sections] if sections else None


def std_pace(runs: list[dict], today_weight: int | None, today_class: str | None, run_classes: dict) -> dict | None:
    """EXP-20261112-09：近 6 仗對馬會標準嘅偏差（秒，越細越好）。

    標準一律用今仗班次（令唔同班次嘅往績可以比）；今仗班次喺嗰個場地路程冇標準先用嗰仗自己班次。
    p0 = Σ(分段 − 標準分段)；p1 = p0 − (1 − ρ) × 早段偏差；p2 = p1 ＋ 每仗換算到今仗負磅。近 6 仗 1/k 加權，最少 2 仗。
    """
    use = []
    for run in runs[:STD_PACE_RUNS]:      # 最近 6 仗入面有標準嘅先計（同 EXP-09 一樣，唔向更舊嘅仗補數）
        std = standard_sections(run["venue"], run["awt"], run["distance"], today_class) or \
            standard_sections(run["venue"], run["awt"], run["distance"], run_classes.get(run["date"]))
        if not std or len(std) != len(run["splits"]) or run["weight"] is None:
            continue
        diffs = [a - b for a, b in zip(run["splits"], std)]
        dev, early = sum(diffs), sum(diffs[:-1])
        adj = dev - (1 - PACE_RECOVERY_RHO) * early
        conv = (WEIGHT_SECONDS_PER_KM_PER_LB * run["distance"] / 1000.0 * (today_weight - run["weight"])
                if today_weight is not None else 0.0)
        use.append({"date": run["date"].isoformat(), "distance": run["distance"], "weight": run["weight"],
                    "p0": round(dev, 2), "p1": round(adj, 2), "p2": round(adj + conv, 2), "weight_conversion": round(conv, 2)})
    if len(use) < 2:
        return None
    wts = [1.0 / k for k in range(1, len(use) + 1)]
    avg = {key: round(sum(u[key] * w for u, w in zip(use, wts)) / sum(wts), 4) for key in ("p0", "p1", "p2")}
    return {**avg, "runs": use, "n": len(use)}


def attach(formguide_text: str, horses: dict, race_context: dict, race_date: date | None) -> int:
    """寫入 `_data`：formguide_today_weight、l400_last_run、std_pace。返回處理咗幾多匹。"""
    if race_date is None:
        return 0
    parsed = parse_formguide(formguide_text)
    today_class = class_code(race_context.get("race_class"))
    count = 0
    for num, horse in horses.items():
        if not isinstance(horse, dict) or not str(num).isdigit():
            continue
        entry = parsed.get(int(num))
        if not entry:
            continue
        data = horse.setdefault("_data", {})
        runs = [r for r in entry["runs"] if r["date"] < race_date]
        runs.sort(key=lambda r: r["date"], reverse=True)
        if entry["today_weight"] is not None:
            data["formguide_today_weight"] = entry["today_weight"]
        if runs and runs[0]["weight"] is not None and runs[0]["splits"]:
            last = runs[0]
            data["l400_last_run"] = {"date": last["date"].isoformat(), "distance": last["distance"],
                                     "weight": last["weight"], "l400": last["splits"][-1]}
        run_classes = {}
        for d, cls in _RECENT_CLASS.findall(str(data.get("recent_6_detail") or "")):
            try:
                run_classes[datetime.strptime(d, "%d/%m/%Y").date()] = class_code(cls)
            except ValueError:
                continue
        pace = std_pace(runs, entry["today_weight"], today_class, run_classes)
        if pace:
            data["std_pace"] = pace
        ft = _sectional_ft(runs, race_date, today_class, run_classes)
        if ft:
            data["sectional_ft"] = ft
        count += 1
    return count


def _sectional_ft(runs: list[dict], race_date: date, today_class: str | None, run_classes: dict) -> dict | None:
    """段速 FT 組件（EXP-20261114-04；Kelvin 2026-11-14 決定上線）：前段＋全程對 as-of 標準、扣當日快慢。
    計法喺 `pit_sections.ft_values`（同離線回放 arm 同一個 function）；冇表（本機資料根冇 pit_sections.json）= 唔計。"""
    from . import pit_sections
    table = pit_sections.load_table()
    if not table:
        return None
    rows = []
    for r in runs:
        if not r.get("splits"):
            continue
        track = "AWT" if r.get("awt") else ("HV" if "跑馬地" in str(r.get("venue")) else "ST")
        rows.append({"date": r["date"].isoformat(), "track": track, "dist": r["distance"],
                     "cls": run_classes.get(r["date"]) or "OT", "secs": r["splits"]})
    first_v, total_v = pit_sections.ft_values(rows, race_date.isoformat(), today_class, table)
    if first_v is None and total_v is None:
        return None
    return {"first_v": first_v, "total_v": total_v, "points": round(pit_sections.ft_points(first_v, total_v, table), 4)}
