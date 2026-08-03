#!/usr/bin/env python3
"""由 archive 嘅 Formguide 抽逐場獎金（班次代理）落本地 cache。

為咩用獎金做班次：
  * `_form_score` 個 `class_mult` 註釋自己認咗係「全場統一」常數 ——
    `entry["class"]` 呢個 key 由來冇存在過，所以 entry_tier 永遠係空字串嘅 tier，
    即係 form_score **完全冇**逐場班次調整。一匹馬喺弱班入前列同喺強班入前列同分。
  * 賽績表個「班次」欄 85% 係 fallback "Maiden/SW"（`hc` 缺失），只有 15% 有真 BM 值。
  * 但 Formguide 每一行都有獎金，**跨所有年代 100% 密度**（實測 39/39、100/100、
    23/23、90/90），而且已經喺本地檔，唔需要 scrape。
  * AU 獎金排班次排得好準：鄉下 BM ~$27k、省級 ~$40k、都會 ~$130k、Group 1 ~$5M。

唯讀。輸出 scratch/au_prize_cache.json。
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from au_archive_calibrator import ARCHIVE_ROOT, normalize_track_name  # noqa: E402

HORSE = re.compile(r"^\[(\d+)\]\s+(.+?)\s*\((\d+|None)\)\s*$")
RUN = re.compile(
    r"^(?P<venue>.+?)(?P<trial>\s+\*\*\(TRIAL\)\*\*)?\s+R(?P<race>\d+)\s+"
    r"(?P<date>\d{4}-\d{2}-\d{2})\s+(?P<dist>\d+)m\s+cond:(?P<cond>\S+)\s+"
    r"\$(?P<prize>[\d,]+)"
)
MARGIN = re.compile(r"\bmargin:([\d.]+)")
STARTERS = re.compile(r"\bstarters:(\d+)")
HC = re.compile(r"\bHC:(\d+)")
RACE_NO = re.compile(r"Race[_ ](\d+)")


def parse_formguide(text):
    """{horse_number: [run, ...]} for one race's formguide."""
    out = {}
    current = None
    for line in text.splitlines():
        stripped = line.strip()
        h = HORSE.match(stripped)
        if h:
            current = int(h.group(1))
            out[current] = {"name": h.group(2).strip(), "runs": []}
            continue
        if current is None:
            continue
        m = RUN.match(stripped)
        if not m:
            continue
        mg = MARGIN.search(stripped)
        st = STARTERS.search(stripped)
        hc = HC.search(stripped)
        out[current]["runs"].append({
            "venue": m.group("venue").strip(),
            "venue_slug": normalize_track_name(m.group("venue")),
            "race_no": int(m.group("race")),
            "date": m.group("date"),
            "distance": int(m.group("dist")),
            "prize": int(m.group("prize").replace(",", "")),
            "is_trial": bool(m.group("trial")),
            "margin": float(mg.group(1)) if mg else None,
            "starters": int(st.group(1)) if st else None,
            "hc": int(hc.group(1)) if hc else None,
        })
    return out


def main():
    out = {}
    meetings = races = 0
    prize_hist = Counter()
    totals = Counter()
    for folder in sorted(p for p in ARCHIVE_ROOT.iterdir() if p.is_dir()):
        guides = sorted(folder.glob("*Formguide.md"))
        if not guides:
            continue
        meetings += 1
        for guide in guides:
            m = re.search(r"Race\s+(\d+)\s+Formguide", guide.name)
            if not m:
                continue
            race_no = int(m.group(1))
            try:
                text = guide.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            parsed = parse_formguide(text)
            if not parsed:
                continue
            races += 1
            for horse_no, rec in parsed.items():
                key = f"{folder.name}|{race_no}|{horse_no}"
                out[key] = rec
                for run in rec["runs"]:
                    if run["is_trial"]:
                        continue
                    totals["official"] += 1
                    totals["prize"] += 1
                    if run["margin"] is not None:
                        totals["margin"] += 1
                    if run["starters"]:
                        totals["starters"] += 1
                    if run["hc"]:
                        totals["hc"] += 1
                    prize_hist[min(run["prize"] // 25000, 20)] += 1

    dest = Path(__file__).resolve().parent / "au_prize_cache.json"
    dest.write_text(json.dumps(out), encoding="utf-8")
    off = max(1, totals["official"])
    print(f"meetings {meetings}  races {races}  horse-blocks {len(out)}")
    print(f"正式 runs {totals['official']}")
    for field in ("prize", "margin", "starters", "hc"):
        print(f"  {field:9} {totals[field]:>7} ({100*totals[field]/off:.1f}%)")
    print("\n獎金分佈（每 25k 一格，20 = $500k+）:")
    for bucket in sorted(prize_hist):
        label = f"${bucket*25}k-{(bucket+1)*25}k" if bucket < 20 else "$500k+"
        print(f"   {label:14} {prize_hist[bucket]:>6}"
              f" ({100*prize_hist[bucket]/off:>5.1f}%)")
    print(f"→ {dest}")


if __name__ == "__main__":
    main()
