#!/usr/bin/env python3
"""用 Racing Australia Acceptances 頁嘅 `Meeting Type` 補 `au_track_geometry.json` 冇嘅場地級別。

點解：`fetch_au_track_geometry.py` 嘅級別只嚟自 racinglife，2026-10-09 實測：
  * 28 個場地 racinglife 冇級別、39 個窗口內場地根本唔喺清單
  * racinglife 而家回 503 —— **唔可以重跑生成器**，重跑會洗走現有 68 個級別
2026-09-09→10-08 月度檢討入面 36% 場次因此冇 Metro/Provincial/Country。

RA 每個 Acceptances 頁都有 `Meeting Type: Provincial (TAB MEETING)`，係官方來源，而且
排程每個場次都會抓（`ra_fields.apply_to_meeting`），cache 喺 `.ra_cache/`。

⚠️ 兩個來源用語唔同，所以**只補空格，唔覆蓋 racinglife**：
  * RA 係**逐個賽日**：同一個場地週六都會賽日會寫 Metro（Ipswich 3 Metro / 3 Provincial）
  * 維省 RA 將所有非都會叫 Country；racinglife 將 Ballarat／Bendigo 叫 Provincial
取多數；打和就唔填（留空 = 唔知，亂填 = 講大話）。寫入 `classification_source`。

    python3 backfill_track_classification_from_ra.py --dry-run
    python3 backfill_track_classification_from_ra.py --ra-cache <…/.ra_cache>
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from au_racing_engine.engine_core import (  # noqa: E402
    CLASSIFICATION_PARENT,
    TRACK_GEOMETRY_PATH,
    _track_geometry_key,
)

DEFAULT_RA_CACHE = SCRIPT_DIR.parents[1] / ".ra_cache"
TYPE_NAMES = {"metro": "Metropolitan", "provincial": "Provincial", "country": "Country"}
# RA 場地名前面嘅贊助商／營運商字頭。只剷明列嘅，唔估。
SPONSOR_PREFIXES = (
    "Sportsbet-", "Sportsbet ", "Ladbrokes ", "Picklebet Park ", "Aquis Park ", "Aquis ",
    "Southside ", "Thomas Farms RC ", "Royal ", "bet365 Park ", "bet365 ",
)
RA_ALIASES = {
    "devonport tapeta synthetic": "Devonport",
    "pinjarra park": "Pinjarra",
    "canberra acton": "Canberra",
}
MEETING = re.compile(
    r"\|\s*([A-Za-z][A-Za-z0-9 '\-]+?):\s*[^|]*?\|[^|]*\|[\s|]*Meeting Type:\s*([A-Za-z]+)")


def ra_venue_name(raw: str) -> str:
    name = raw.strip()
    for prefix in SPONSOR_PREFIXES:
        if name.startswith(prefix):
            name = name[len(prefix):]
    return RA_ALIASES.get(name.lower(), name)


def meeting_types(cache_dir: Path) -> dict[str, Counter]:
    out: dict[str, Counter] = defaultdict(Counter)
    for page in cache_dir.glob("*.html"):
        text = page.read_text(encoding="utf-8", errors="replace")
        flat = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " | ", text)))
        m = MEETING.search(flat)
        if m and m.group(2).lower() in TYPE_NAMES:
            out[_track_geometry_key(ra_venue_name(m.group(1)))][TYPE_NAMES[m.group(2).lower()]] += 1
    return out


def majority(counts: Counter) -> str:
    ranked = counts.most_common()
    if not ranked or (len(ranked) > 1 and ranked[0][1] == ranked[1][1]):
        return ""
    return ranked[0][0]


def backfill(payload: dict, types: dict[str, Counter]) -> list[tuple[str, str, dict]]:
    venues = payload.setdefault("venues", {})
    changed = []
    for key, counts in sorted(types.items()):
        label = majority(counts)
        if not label:
            continue
        parent = venues.get(CLASSIFICATION_PARENT.get(key, ""), {})
        if parent.get("classification"):
            continue  # 副跑道承繼主場（引擎 `_track_classification`），唔好撈兩套用語
        row = venues.get(key)
        if row is None:
            row = venues[key] = {
                "venue": key.replace("-", " ").title(), "circumference_m": 0, "straight_m": 0,
                "direction": "", "classification": "", "surface": "", "state": "", "note": "",
                "sources": [], "conflict": None,
            }
        if row.get("classification"):
            continue
        row["classification"] = label
        row["classification_source"] = (
            "racingaustralia Acceptances `Meeting Type`（多數）："
            + ", ".join(f"{k} {v}" for k, v in counts.most_common()))
        changed.append((key, label, dict(counts)))
    payload["venues"] = dict(sorted(venues.items()))
    payload["venues_total"] = len(payload["venues"])
    return changed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ra-cache", type=Path, default=DEFAULT_RA_CACHE)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    payload = json.loads(TRACK_GEOMETRY_PATH.read_text(encoding="utf-8"))
    changed = backfill(payload, meeting_types(args.ra_cache))
    for key, label, counts in changed:
        print(f"  {key:28s} → {label:13s} {counts}")
    print(f"補咗 {len(changed)} 個場地級別", file=sys.stderr)
    if not args.dry_run:
        TRACK_GEOMETRY_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                                       encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
