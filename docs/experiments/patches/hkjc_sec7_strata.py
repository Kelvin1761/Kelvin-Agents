"""§7 預先聲明 cohort（HKJC）：馬群 ×4、首選（baseline 第一選）SP ×5，Gold／Good 配對 Δ，賽日 bootstrap 95% CI.

    python3 hkjc_sec7_strata.py base.jsonl cand.jsonl
"""
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path("/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/HK_Racing")
FIELD = [("≤9 匹", 0, 9), ("10–11 匹", 10, 11), ("12 匹", 12, 12), ("13–14 匹", 13, 14)]
SP = [("SP <2.6", 0, 2.6), ("SP 2.6–4", 2.6, 4), ("SP 4–7", 4, 7), ("SP 7–12", 7, 12), ("SP ≥12", 12, 9999)]


def rows(path):
    out = {}
    for line in open(path):
        r = json.loads(line)
        if "error" not in r and "speed_score" not in (r.get("meeting_dead_fields") or []):
            out[(r["meeting"], r["race"])] = r
    return out


_odds = {}


def sp_of(meeting, race, horse):
    if meeting not in _odds:
        f = next((ROOT / meeting).glob("*全日賽果.json"), None)
        _odds[meeting] = json.loads(f.read_text(encoding="utf-8")) if f else {}
    for h in (_odds[meeting].get(str(race)) or {}).get("results") or []:
        if str(h.get("horse_no")) == str(horse):
            try:
                return float(h.get("win_odds"))
            except (TypeError, ValueError):
                return None
    return None


def main():
    b, c = rows(sys.argv[1]), rows(sys.argv[2])
    keys = sorted(b.keys() & c.keys())
    groups = defaultdict(list)
    for k in keys:
        rb, rc = b[k], c[k]
        diff = {m: (rc[m] or 0) - (rb[m] or 0) for m in ("gold", "good_positional")}
        for name, lo, hi in FIELD:
            if lo <= rb["field"] <= hi:
                groups[name].append((rb["date"], diff))
        sp = sp_of(k[0], k[1], rb["picks"][0]) if rb.get("picks") else None
        for name, lo, hi in SP:
            if sp is not None and lo <= sp < hi:
                groups[name].append((rb["date"], diff))
    rng = random.Random(7)
    worst = []
    for name in [n for n, *_ in FIELD + SP]:
        items = groups[name]
        by_day = defaultdict(list)
        for d, diff in items:
            by_day[d].append(diff)
        days = list(by_day)
        line = f"{name:10s} n {len(items):3d}"
        for m in ("gold", "good_positional"):
            pt = sum(x[m] for _, x in items) / len(items)
            boots = []
            for _ in range(2000):
                pick = [x for _ in days for x in by_day[days[rng.randrange(len(days))]]]
                boots.append(sum(x[m] for x in pick) / len(pick))
            boots.sort()
            lo, hi = boots[49], boots[1949]
            line += f"  {m} {pt * 100:+.2f}pp [{lo * 100:+.2f}, {hi * 100:+.2f}]"
            if hi < 0:
                worst.append((name, m))
        print(line)
    print("CI 全負嘅 cohort：", worst or "冇")


if __name__ == "__main__":
    main()
