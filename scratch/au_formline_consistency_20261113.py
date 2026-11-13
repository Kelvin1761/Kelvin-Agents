#!/usr/bin/env python3
"""賽績線：上游 Facts 標題級別 vs 引擎讀到嘅級別，逐匹對照（AU 標籤審計跟進 2026-11-13）。

    au_formline_consistency_20261113.py SINCE

用現行 code 嘅 RacingEngine（只讀 Logic／Facts，唔寫檔）。上游有對手線（valid ≥1）嘅馬，
引擎 `_formline_support_summary` 應該同上游「強組比例 a/b」一樣。
"""
import collections
import glob
import json
import os
import re
import sys
from pathlib import Path

W = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(W / ".agents/skills/au_racing/au_wong_choi_auto/scripts"))
from au_racing_engine.engine_core import RacingEngine  # noqa: E402

ROOT = open(W / ".wongchoi_au_data_root").read().strip()
STATS = re.compile(r"強組比例:\s*([\d.]+)/(\d+)")


def main():
    since = sys.argv[1]
    dirs = sorted(d for d in glob.glob(ROOT + "/20*") + glob.glob(ROOT + "/Archive/20*")
                  if os.path.basename(d)[:10] >= since)
    agree = collections.Counter()
    bad = []
    for d in dirs:
        for lp in glob.glob(d + "/Race_*_Logic.json"):
            logic = json.load(open(lp))
            ctx = dict(logic.get("race_analysis") or {})
            for hnum, horse in (logic.get("horses") or {}).items():
                data = horse.get("_data") or {}
                m = STATS.search(str(data.get("formline_line") or ""))
                if not m:
                    continue
                up = (float(m.group(1)), int(m.group(2)))
                eng = RacingEngine(dict(horse), ctx, facts_section=data.get("facts_section", ""))
                got = eng._formline_support_summary()
                ok = abs(got[0] - up[0]) < 1e-9 and got[1] == up[1]
                agree[ok] += 1
                if not ok and len(bad) < 8:
                    bad.append((os.path.basename(d), lp[-15:], horse.get("horse_name"), up, got))
    print(f"上游 vs 引擎 一致 {agree[True]}，唔一致 {agree[False]}")
    for b in bad:
        print("  ", b)


if __name__ == "__main__":
    main()
