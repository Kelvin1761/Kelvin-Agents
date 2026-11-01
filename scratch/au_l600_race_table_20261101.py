#!/usr/bin/env python3
"""EXP-20261101-31：由全部 AU Formguide 砌「歷史賽事 race-level L600 原秒」表。

Formguide 只寫 `L600 Delta`（= Sportsbet L600 原秒 − 抽取當時嘅 `_lookup_standard_l600`）。
用而家嘅標準表反推原秒；同一場賽事出現喺多份 Formguide 時逐份比對，量度一致性。
輸出 JSON：{key: {track, date, race, distance, going, cls, raw, deltas, sources}}。
"""
from __future__ import annotations
import argparse, glob, json, re, statistics, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / ".agents/skills/au_racing/au_wong_choi_auto/scripts"))
from au_racing_engine.engine_core import _lookup_standard_l600, _normalize_track_name  # noqa: E402

RX = re.compile(r"^(.+?)\s+R(\d+)\s+(\d{4}-\d{2}-\d{2})\s+(\d+)m\s+cond:(\S+)(.*)$")
DELTA = re.compile(r"L600 Delta:\s*(-?\d+(?:\.\d+)?)")
RELIABLE_FROM = "2026-08-24"
CLS = re.compile(r"RaceClass:\[([^\]]*)\]")


def going(cond):
    c = cond.lower()
    for key in ("heavy", "soft", "good", "firm", "synthetic"):
        if c.startswith(key) or key in c:
            return key
    m = re.match(r"(\d+)", c)
    if m:
        n = int(m.group(1))
        return "firm" if n <= 2 else "good" if n <= 4 else "soft" if n <= 7 else "heavy"
    return "unknown"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    table = defaultdict(lambda: {"deltas": [], "sources": []})
    for f in glob.glob(args.root + "/**/*Formguide.md", recursive=True):
        name = Path(f).parent.name
        m8 = re.match(r"(\d{4})(\d{2})(\d{2})T", name)   # prediction snapshot 資料夾：YYYYMMDDT…
        meeting = f"{m8[1]}-{m8[2]}-{m8[3]}" if m8 else name[:10]
        for line in open(f, encoding="utf-8"):
            line = line.strip()
            if "L600 Delta" not in line or "TRIAL" in line.upper() or "JUMP" in line.upper():
                continue
            m = RX.match(line)
            d = DELTA.search(line)
            if not m or not d:
                continue
            venue = m[1].strip()
            key = f"{_normalize_track_name(venue)}|{m[3]}|{int(m[2])}"
            row = table[key]
            row.update({"track": _normalize_track_name(venue), "venue_raw": venue, "date": m[3],
                        "race": int(m[2]), "distance": int(m[4]), "going": going(m[5]),
                        "cls": (CLS.search(line) or [None, ""])[1]})
            row["deltas"].append(float(d[1]))
            row["sources"].append(meeting)
    out, spread = {}, []
    for key, row in table.items():
        std = _lookup_standard_l600(row["venue_raw"], row["distance"])
        if not std:
            continue
        uniq = sorted(set(row["deltas"]))
        spread.append(uniq[-1] - uniq[0])
        # 以最新一份 Formguide 嘅 delta 為準（最近期抽取 = 用而家嘅標準表）
        latest = max(range(len(row["sources"])), key=lambda i: row["sources"][i])
        out[key] = {k: row[k] for k in ("track", "date", "race", "distance", "going", "cls")}
        out[key]["raw"] = round(row["deltas"][latest] + std, 3)
        out[key]["n_sources"] = len(row["sources"])
        out[key]["delta_spread"] = round(uniq[-1] - uniq[0], 3)
        out[key]["latest_source"] = row["sources"][latest]
        out[key]["all_deltas"] = uniq
        # 08-23 標準表改咗（內插 + 單調）：只有 08-24 之後抽取嘅 Formguide 先可以用而家張表反推原秒。
        out[key]["reliable"] = row["sources"][latest] >= RELIABLE_FROM
    Path(args.out).write_text(json.dumps(out))
    multi = [s for s in spread]
    print("races", len(out), "with >1 distinct delta:", sum(s > 0.011 for s in multi),
          "spread>0.1:", sum(s > 0.1 for s in multi))
    raws = [v["raw"] for v in out.values()]
    print("raw L600 range", min(raws), statistics.median(raws), max(raws))


if __name__ == "__main__":
    main()
