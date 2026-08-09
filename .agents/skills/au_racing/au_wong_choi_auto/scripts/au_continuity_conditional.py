#!/usr/bin/env python3
"""騎師連續性三項：條件化量度。

`au_adjustment_audit.py` 量到三項嘅**無條件** cohort 超額同符號相反：

    今場離開上仗已證明配搭  −2.98  n=1,670  +4.8pp
    沿用上仗騎師，部署連貫  +2.00  n=  961  −3.7pp
    今場騎師未及上仗騎師   −4.11  n=  235  +5.5pp

但四個修法（歸零／反符號／半反）全部改善唔到排名。假設：**cohort 超額
唔等於因果貢獻**。「離開已證明配搭」嘅馬按定義 `current_formal_rides == 0`，
所以佢哋一定攞唔到「曾策騎此駒」嗰批 +5 至 +10 嘅加分。拿佢哋同**全體**比，
量到嘅其實係「冇配搭紀錄嘅馬 vs 有配搭紀錄嘅馬」，唔係嗰個 −2.98 嘅效果。

正確做法：對照組唔係全體，而係**行到同一個分岔點但冇觸發**嘅馬。

    leave_proven_jockey_pen 觸發條件：
        換咗騎師 且 上仗騎師策過此駒 且 今場騎師冇策過 且 上仗騎師上名率 ≥ 0.50
    正確對照組：
        換咗騎師 且 上仗騎師策過此駒 且 今場騎師冇策過 且 上名率 **< 0.50**

    signal_same_jockey_bonus 觸發：`jockey_change_signal` 含「沿用上仗騎師」
    正確對照組：有 jockey_change_signal 但係其他類別（即係一樣有換騎師資訊）

    latest_downgrade_pen 觸發：今場有策過 且 上仗騎師上名率 > 今場 + 0.20
    正確對照組：今場有策過 且 上仗騎師上名率 ≤ 今場 + 0.20

⚠️ 一樣要修正馬群大細 —— 8 匹嘅場前三率 37.5%、18 匹係 16.7%。

用法：
    python3 au_continuity_conditional.py --archive-root <scored> --results-csv <csv>
"""
from __future__ import annotations

import argparse
import copy
import sys
from collections import defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR / "racing_engine"))
sys.path.insert(0, str(SCRIPT_DIR.parents[2] / "shared_racing"))

from au_archive_calibrator import load_historical_results  # noqa: E402
from au_auto_orchestrator import _build_field_summary  # noqa: E402
from au_runtime_micro_ablation import (discover_logic_files,  # noqa: E402
                                      iter_aligned_races)
from engine_core import RacingEngine, backfill_pf_metrics  # noqa: E402


def safe_ratio(a, b):
    return (a / b) if b else 0.0


def main():
    ap = argparse.ArgumentParser(description="騎師連續性三項條件化量度")
    ap.add_argument("--archive-root", type=Path, required=True)
    ap.add_argument("--results-csv", type=Path, required=True)
    ap.add_argument("--limit-races", type=int)
    args = ap.parse_args()

    files, ph = discover_logic_files(args.archive_root)
    files = sorted(files + ph, key=lambda p: (p.parent.name, p.stem))
    if args.limit_races:
        files = files[:args.limit_races]
    results = load_historical_results(args.results_csv)

    rows = []          # (field_size, placed, feature dict)
    by_size = defaultdict(lambda: [0, 0])
    races = 0
    for path, aligned in iter_aligned_races(files, results, prefetch_workers=4):
        if aligned[0] is None:
            continue
        logic, aligned_rows = aligned
        ctx = copy.deepcopy(logic["race_analysis"])
        backfill_pf_metrics(logic, path)
        ctx["field_summary"] = _build_field_summary(logic["horses"])
        ctx["field_horse_names"] = [h.get("horse_name") for h in logic["horses"].values()
                                    if isinstance(h, dict) and h.get("horse_name")]
        n = len(aligned_rows)
        races += 1
        for src in aligned_rows:
            horse = dict(src["horse"])
            horse.setdefault("horse_number", src["horse_number"])
            data = horse.get("_data") if isinstance(horse.get("_data"), dict) else {}
            eng = RacingEngine(horse, ctx, facts_section=data.get("facts_section", ""),
                               facts_path=path)
            eng.analyze_horse()
            jockey = eng._clean_identity(horse.get("jockey"))
            cf_rides = eng._current_jockey_formal_rides()
            cf_places = eng._current_jockey_formal_places()
            lo_jockey = eng._latest_official_jockey()
            lo_rides = eng._latest_official_jockey_formal_rides()
            lo_places = eng._latest_official_jockey_formal_places()
            placed = src["actual_pos"] <= 3
            by_size[n][0] += placed
            by_size[n][1] += 1
            rows.append((n, placed, {
                "changed": bool(lo_jockey and lo_jockey != jockey),
                "lo_rides": lo_rides,
                "lo_rate": safe_ratio(lo_places, lo_rides),
                "cf_rides": cf_rides,
                "cf_rate": safe_ratio(cf_places, cf_rides),
                "signal": str(eng._jockey_change_signal() or ""),
            }))
        if races % 100 == 0:
            print(f"  已評 {races} 場", flush=True)

    expected = {n: (a / b if b else 0.0) for n, (a, b) in by_size.items()}

    def cohort(pred):
        sel = [(n, p) for n, p, f in rows if pred(f)]
        if not sel:
            return None
        act = sum(p for _, p in sel) / len(sel)
        exp = sum(expected[n] for n, _ in sel) / len(sel)
        return len(sel), act, exp, (act - exp) * 100

    def show(title, fired, control, note):
        print(f"\n── {title} ──")
        print(f"   {note}")
        a, b = cohort(fired), cohort(control)
        print(f"   {'':22}{'匹數':>7}{'實際':>9}{'期望':>9}{'超額':>9}")
        for lbl, r in (("觸發", a), ("對照（同分岔點）", b)):
            if r is None:
                print(f"   {lbl:22}    冇樣本")
                continue
            print(f"   {lbl:22}{r[0]:>7}{r[1]:>9.1%}{r[2]:>9.1%}{r[3]:>+9.1f}")
        if a and b:
            gap = a[3] - b[3]
            print(f"   {'觸發 − 對照':22}{'':>7}{'':>9}{'':>9}{gap:>+9.1f}"
                  f"   ← 呢個先係嗰項嘅實際效果")
            print(f"   判斷：{'扣分係啱嘅' if gap < -1.5 else ('扣分方向反咗' if gap > 1.5 else '分唔開，幅度細過 1.5pp')}")

    print(f"\n{races} 場 / {len(rows)} 匹")

    show("leave_proven_jockey_pen（−2.98）",
         lambda f: (f["changed"] and f["lo_rides"] > 0 and f["cf_rides"] == 0
                    and f["lo_rate"] >= 0.50),
         lambda f: (f["changed"] and f["lo_rides"] > 0 and f["cf_rides"] == 0
                    and f["lo_rate"] < 0.50),
         "換騎師 + 上仗騎師策過 + 今場騎師未策過。分：上仗騎師上名率 ≥50% vs <50%")

    show("latest_downgrade_pen（−4.11）",
         lambda f: (f["changed"] and f["cf_rides"] > 0 and f["lo_rides"] > 0
                    and f["lo_rate"] > f["cf_rate"] + 0.20),
         lambda f: (f["changed"] and f["cf_rides"] > 0 and f["lo_rides"] > 0
                    and f["lo_rate"] <= f["cf_rate"] + 0.20),
         "換騎師 + 兩個騎師都策過此駒。分：上仗騎師明顯好 vs 唔明顯好")

    show("signal_same_jockey_bonus（+2.00）",
         lambda f: "沿用上仗騎師" in f["signal"],
         lambda f: bool(f["signal"]) and "沿用上仗騎師" not in f["signal"],
         "有 jockey_change_signal。分：沿用上仗騎師 vs 其他訊號類別")

    print("\n⚠️ 「觸發 − 對照」先係嗰項嘅效果。無條件 cohort 超額包含咗"
          "「有／冇配搭紀錄」呢個更大嘅差異，會蓋過嗰項本身。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
