#!/usr/bin/env python3
"""逐個手調項：佢個符號同佢實際嘅方向一致嗎？

點解需要呢個工具。`au_runtime_micro_ablation.py` 答「剷走成個家族會唔會蝕」，
但答唔到 Kelvin 真正問嘅嗰句 ——「呢啲手調項本身有冇道理、訊號有冇改善空間」。
一個家族可以整體有用，但入面某一項符號係反嘅，而 ablation 會被其餘項蓋過。

而呢個 repo 已經有**四次**同一種 bug，全部都係人手讀參數表捉到嘅：

    career5_unplaced_pen   曾經係 +0.82（變數叫「懲罰」卻加分）
    heavy_place_bonus      曾經係 −2.88（重地曾上名反被扣分）
    best_formal_mult       被 ML search 推成 −0.06（沿用最佳配搭反而扣分）
    going_poor_pen2_dry    曾經 −7.08 罰得重過「2 戰零上名」（非單調）

四次都係**語義同數字唔一致**，而 A/B 捉唔到 —— A/B 只會話你「郁佢會蝕」，
唔會話你「你把尺方向反咗」。呢個工具把嗰個人手檢查系統化：跑一次引擎，
記錄每匹馬觸發咗邊幾項，然後量每一項嘅 cohort 實際表現。

⚠️ **一定要修正馬群大細。** 8 匹馬嘅場次前三率天然 37.5%、18 匹係 16.7%。
某一項如果集中喺大場（新馬多嘅維持賽），未修正嘅數字會話你佢差。
呢個 repo 已經因為漏咗呢步而得出過「差檔位跑得好」嘅假結論。

⚠️ **「方向唔一致」唔等於「改咗會贏」。** 呢個工具搵嫌疑犯，唔判罪。
每一個嫌疑犯都要照跑 dev / 5-fold / holdout / walk-forward 四道閘。
一個項可能同結果反向但同**其他項相關**，改佢會連帶郁到其他嘢。

用法：
    python3 au_adjustment_audit.py --archive-root <scored> --results-csv <sb_results.csv>
"""
from __future__ import annotations

import argparse
import copy
import sys
from collections import defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR.parents[2] / "shared_racing"))

from au_archive_calibrator import detect_meeting_date, load_historical_results  # noqa: E402
from au_auto_orchestrator import _build_field_summary  # noqa: E402
from au_runtime_micro_ablation import (aligned_race, discover_logic_files,  # noqa: E402
                                      iter_aligned_races)
from au_racing_engine.engine_core import RacingEngine, backfill_pf_metrics  # noqa: E402

# 邊幾個 leaf 有逐項明細。其餘（class / track / sectional / pace）冇
# `adjustments` 結構，所以呢個工具照唔到 —— 講明好過靜靜漏。
DETAILS = (("trial", "trial_detail"), ("trainer", "trainer_detail"),
           ("jt_fit", "jt_fit_detail"), ("consistency", "consistency_detail"))


def main():
    ap = argparse.ArgumentParser(description="逐個手調項嘅方向審計")
    ap.add_argument("--archive-root", type=Path, required=True)
    ap.add_argument("--results-csv", type=Path, required=True)
    ap.add_argument("--limit-races", type=int)
    ap.add_argument("--min-n", type=int, default=80)
    args = ap.parse_args()

    files, placeholders = discover_logic_files(args.archive_root)
    files = sorted(files + placeholders,
                   key=lambda p: (p.parent.name, p.stem))
    if args.limit_races:
        files = files[:args.limit_races]
    results = load_historical_results(args.results_csv)

    # cohort[(leaf, factor, sign)] → [命中數, 匹數, 期望和]
    cohort = defaultdict(lambda: [0, 0, 0.0])
    by_size = defaultdict(lambda: [0, 0])
    seen = []          # (field_size, placed, [(leaf, factor, delta)…])
    races = 0

    for path, aligned in iter_aligned_races(files, results, prefetch_workers=4):
        if aligned[0] is None:
            continue
        logic, rows = aligned
        ctx = copy.deepcopy(logic["race_analysis"])
        backfill_pf_metrics(logic, path)
        ctx["field_summary"] = _build_field_summary(logic["horses"])
        ctx["field_horse_names"] = [h.get("horse_name") for h in logic["horses"].values()
                                    if isinstance(h, dict) and h.get("horse_name")]
        n = len(rows)
        races += 1
        for src in rows:
            horse = dict(src["horse"])
            horse.setdefault("horse_number", src["horse_number"])
            data = horse.get("_data") if isinstance(horse.get("_data"), dict) else {}
            eng = RacingEngine(horse, ctx, facts_section=data.get("facts_section", ""),
                               facts_path=path)
            eng.analyze_horse()
            placed = src["actual_pos"] <= 3
            by_size[n][0] += placed
            by_size[n][1] += 1
            fired = []
            for leaf, attr in DETAILS:
                d = getattr(eng, attr, None) or {}
                for a in (d.get("adjustments") or []):
                    delta = float(a.get("delta") or 0.0)
                    if delta:
                        fired.append((leaf, str(a.get("factor") or "?"), delta))
            seen.append((n, placed, fired))
        if races % 50 == 0:
            print(f"  已評 {races} 場", flush=True)

    expected = {n: (a / b if b else 0.0) for n, (a, b) in by_size.items()}
    for n, placed, fired in seen:
        for leaf, factor, delta in fired:
            key = (leaf, factor, "+" if delta > 0 else "−")
            c = cohort[key]
            c[0] += placed
            c[1] += 1
            c[2] += expected[n]

    print(f"\n{races} 場 / {len(seen)} 匹\n")
    print(f"{'leaf':12}{'符號':>4}  {'手調項':<34}{'匹數':>6}"
          f"{'實際':>8}{'期望':>8}{'超額':>8}  判斷")
    print("─" * 104)
    suspects = []
    for (leaf, factor, sign), (hits, cnt, exp) in sorted(
            cohort.items(), key=lambda kv: -kv[1][1]):
        if cnt < args.min_n:
            continue
        act = hits / cnt
        e = exp / cnt
        d = (act - e) * 100
        # 加分項應該對應正超額，扣分項應該對應負超額。
        agree = (d > 0) if sign == "+" else (d < 0)
        verdict = "一致" if agree else ("⚠️ 方向相反" if abs(d) > 1.5 else "方向相反但幅度細")
        if not agree and abs(d) > 1.5:
            suspects.append((leaf, factor, sign, cnt, d))
        print(f"{leaf:12}{sign:>4}  {factor[:34]:<34}{cnt:>6}"
              f"{act:>8.1%}{e:>8.1%}{d:>+8.1f}  {verdict}")

    print(f"\n嫌疑犯（符號同實際方向相反、幅度 >1.5pp、樣本 ≥{args.min_n}）：{len(suspects)} 個")
    for leaf, factor, sign, cnt, d in sorted(suspects, key=lambda x: -abs(x[4])):
        print(f"  {leaf:12}{sign}  {factor[:40]:<40}n={cnt:<6}超額 {d:+.1f}pp")
    if suspects:
        print("\n⚠️ 呢啲只係嫌疑犯。每個都要照跑 dev / 5-fold / holdout / walk-forward")
        print("   四道閘 —— 同結果反向可能係同其他項相關，唔一定係符號錯。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
