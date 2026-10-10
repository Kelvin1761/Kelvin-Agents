"""Arm: partial forgiveness for bad runs with a trouble-in-running excuse.

Pre-registered 2026-10-10 (EXP-20261010-03). Fixed rule, nothing fitted:

  * Source: stewards' incident text for each past run, from the HKJC results
    database, keyed by (horse brand, race date). Only runs BEFORE the race
    being scored exist there for that horse, so this is point-in-time.
  * Trouble = blocked / no room / checked / squeezed / stumbled / lost balance
    at the start. Medical wording (bled, irregular heart, lame, vet) is NOT
    forgiven — screening showed excusing it makes form worse.
  * A run is "bad" when it finished in the bottom 40% of its field.
  * Bad + trouble → that run's placing is pulled 50% towards the median of the
    horse's other listed runs (rounded). Applied to `last_6_finishes` and
    `_data.recent_6_detail`, which feed form_score and consistency_score.

Screening (EXP-20261010-02): dropping excused runs entirely lowers form AUC;
"bad + trouble" adds a small positive on top of form (ΔLL CI clear of 0).
"""
from __future__ import annotations

import json
import re
import statistics
from pathlib import Path

ARM_NAME = "trouble_forgiveness_50"
TROUBLE = ("受困", "未能望空", "無法望空", "空位不足", "勒避", "被夾", "受嚴重阻礙",
           "被嚴重碰撞", "收慢至幾乎停下", "幾乎跌倒", "失蹄", "出閘時失去平衡")
MEDICAL = ("流鼻血", "心律不正常", "跛行", "不良於行", "呼吸", "獸醫", "拉傷", "受傷")
BRAND_RE = re.compile(r"\(([A-Z]\d{3})\)")
RUN_RE = re.compile(r"第(\d)仗\((\d{2})/(\d{2})/(\d{4})[^)]*\):\s*(\d+)名")

STATS = {"horses": 0, "runs_adjusted": 0, "unaligned": 0}


def _index() -> dict[tuple[str, str], tuple[int, str]]:
    import wongchoi_paths

    root = Path(wongchoi_paths.HK_RACING) / "HKJC_Race_Results_Database"
    out: dict[tuple[str, str], tuple[int, str]] = {}
    for path in root.glob("hkjc results */*/full_day_results.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for key, race in data.items():
            if not str(key).isdigit() or not isinstance(race, dict):
                continue
            day = str(race.get("racedate") or path.parent.name)[:10]
            field = sum(1 for row in race.get("results") or []
                        if re.fullmatch(r"\d+(?:\s+平頭馬)?", str(row.get("pos") or "").strip()))
            report = race.get("incident_report") or ""
            texts: dict[str, str] = {}
            if isinstance(report, list):
                for item in report:
                    brand = BRAND_RE.search(str((item or {}).get("horse_name") or ""))
                    if brand:
                        texts[brand.group(1)] = str(item.get("comment") or "")
            else:
                for match in re.finditer(r"\(([A-Z]\d{3})\)\s*(.*?)(?=\s\d+\s+\d+\s+\S+\s*\([A-Z]\d{3}\)|$)", report, flags=re.S):
                    texts[match.group(1)] = match.group(2)
            for row in race.get("results") or []:
                brand = BRAND_RE.search(str(row.get("horse_name") or ""))
                if brand:
                    out[(brand.group(1), day)] = (field, texts.get(brand.group(1), ""))
    return out


def _brand_map() -> dict[str, str]:
    """Horse name → brand from racecards (archived Logic lacks horse_code for ~73%)."""
    import wongchoi_paths

    out: dict[str, str] = {}
    for card in Path(wongchoi_paths.HK_RACING).glob("2026-*_*/*排位表.md"):
        try:
            text = card.read_text(encoding="utf-8")
        except OSError:
            continue
        for name, brand in re.findall(r"馬名:\s*(\S+)[\s\S]*?烙號:\s*([A-Z]\d{3})", text):
            out.setdefault(name, brand)
    return out


def _trouble(text: str) -> bool:
    return bool(text) and any(t in text for t in TROUBLE) and not any(m in text for m in MEDICAL)


def forgive(horse: dict, index, race_date: str = "", brands: dict | None = None) -> dict:
    data = horse.get("_data") if isinstance(horse.get("_data"), dict) else {}
    detail = str(data.get("recent_6_detail") or "")
    brand = str(horse.get("horse_code") or "") or (brands or {}).get(str(horse.get("horse_name") or "").strip(), "")
    if not brand:
        match = BRAND_RE.search(str(horse.get("horse_name") or ""))
        brand = match.group(1) if match else ""
    runs = [(m, int(m.group(5)), f"{m.group(4)}-{m.group(3)}-{m.group(2)}") for m in RUN_RE.finditer(detail)]
    if not brand or len(runs) < 2:
        return horse
    STATS["horses"] += 1
    ranks = [rank for _m, rank, _d in runs]
    new_ranks = list(ranks)
    for i, (_m, rank, day) in enumerate(runs):
        if race_date and day >= race_date:      # leakage guard: past runs only
            continue
        field, text = index.get((brand, day), (0, ""))
        if not field or rank < 0.6 * field + 1 or not _trouble(text):
            continue
        others = [r for j, r in enumerate(ranks) if j != i]
        new_ranks[i] = int(round(0.5 * rank + 0.5 * statistics.median(others)))
    if new_ranks == ranks:
        return horse
    # Rewrite recent_6_detail placings.
    pieces, last = [], 0
    for (m, _rank, _day), new in zip(runs, new_ranks):
        pieces.append(detail[last:m.start(5)] + str(new))
        last = m.end(5)
    pieces.append(detail[last:])
    horse = dict(horse)
    horse["_data"] = {**data, "recent_6_detail": "".join(pieces)}
    # Align last_6_finishes (it can carry extra leading non-placings).
    tokens = str(horse.get("last_6_finishes") or "").split("-")
    target = [str(r) for r in ranks]
    for offset in range(0, max(1, len(tokens) - len(target) + 1)):
        if tokens[offset:offset + len(target)] == target:
            tokens[offset:offset + len(target)] = [str(r) for r in new_ranks]
            horse["last_6_finishes"] = "-".join(tokens)
            break
    else:
        STATS["unaligned"] += 1
    STATS["runs_adjusted"] += sum(1 for a, b in zip(ranks, new_ranks) if a != b)
    return horse


def apply() -> None:
    from hkjc_racing_engine import engine_core

    index = _index()
    brands = _brand_map()
    original_init = engine_core.RacingEngine.__init__

    def init(self, horse_data, race_context=None, *args, **kwargs):
        if isinstance(horse_data, dict):
            race_date = str((race_context or {}).get("race_date") or "")[:10]
            horse_data = forgive(horse_data, index, race_date, brands)
        return original_init(self, horse_data, race_context, *args, **kwargs)

    engine_core.RacingEngine.__init__ = init
