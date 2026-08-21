#!/usr/bin/env python3
"""騎師連續性三項係唔係反咗？—— 四道閘 A/B。

`au_adjustment_audit.py` 喺 718 場上量到 `jockey_horse_fit_score` 入面三個
關於**騎師連續性**嘅手調項，符號同實際方向全部相反：

    今場離開上仗已證明配搭      −2.98   n=1,670   超額 **+4.8pp**
    沿用上仗騎師，部署連貫      +2.00   n=  961   超額 **−3.7pp**
    今場騎師對此駒往績未及上仗   −4.11   n=  235   超額 **+5.5pp**

三個獨立項指向同一件事，覆蓋 39% 嘅跑手。而同一個 leaf 入面「騎師策過呢匹馬
而且交代好」嗰批項係強正嘅（+5 至 +10pp）—— 即係 AUC 0.532 唔係冇訊號，
係正項被呢三個反向項抵消。

⚠️ **反向唔等於改咗會贏。** 呢三項同其他項相關（例如「離開已證明配搭」嘅馬
必然冇「現役騎師曾策騎此駒」嘅加分），所以改佢會連帶郁到成個 leaf 嘅分佈。
所以三個變體全部要過四道閘。

⚠️ **「歸零」比「反符號」更保守。** 把符號反過來去啱返實測超額，等於用結果
擬合參數 —— 呢個語料已經三次令 argmax 式搜索 overfit。歸零只係講「我哋
證明唔到呢個方向」，而反符號係講「反方向係對嘅」，後者要更強嘅證據。

用法：
    python3 au_fit_continuity_ab.py --archive-root <scored> --results-csv <sb_results.csv>
"""
from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR.parents[2] / "shared_racing"))

from au_auto_orchestrator import _build_field_summary  # noqa: E402
from au_runtime_micro_ablation import (discover_logic_files,  # noqa: E402
                                      iter_aligned_races, patched_weights)
from au_archive_calibrator import detect_meeting_date, load_historical_results  # noqa: E402
from au_racing_engine.engine_core import RacingEngine, backfill_pf_metrics  # noqa: E402
from eval_metrics import race_metrics, summarize_races  # noqa: E402
from au_racing_engine.scoring import (CONSISTENCY_MICRO_WEIGHTS, FIT_MICRO_WEIGHTS,  # noqa: E402
                     TRIAL_MICRO_WEIGHTS)

W, C, T = FIT_MICRO_WEIGHTS, CONSISTENCY_MICRO_WEIGHTS, TRIAL_MICRO_WEIGHTS

# 逐項審計（718 場）搵出嘅「大覆蓋、零訊號」項 —— 剷佢哋係為咗乾淨，
# 前提係唔蝕。每個都要過四道閘。
# `au_continuity_conditional.py`（718 場）嘅**條件化**效果 —— 對照組係
# 「行到同一個分岔點但冇觸發」嘅馬，唔係全體：
#
#   leave_proven_jockey_pen   觸發 +4.8 vs 對照 **−6.8**  →  效果 **+11.7pp**
#   latest_downgrade_pen      觸發 +5.5 vs 對照  +2.1  →  效果  **+3.4pp**
#   signal_same_jockey_bonus  觸發 −3.7 vs 對照  +0.9  →  效果  **−4.6pp**
#
# 對照組揭示咗真正機制：同一個分岔點之下，唯一分別係**上仗騎師同呢匹馬嘅
# 上名率**。≥50% 嘅今日跑 +4.8、<50% 嘅跑 −6.8。即係嗰個數字量緊**呢匹馬
# 嘅質素**，唔係「配搭連續性」。變數揀啱、符號錯、個名令人讀錯。
#
# ⚠️ 幅度**唔跟**實測超額。用結果擬合幅度就係之前三次 overfit 嘅做法。
# 呢度只採用實測嘅**符號**，幅度保留原本嘅絕對值（或者更保守），再用 AUC 驗。
LEAVE, DOWN, SAME = "leave_proven_jockey_pen", "latest_downgrade_pen", "signal_same_jockey_bonus"

MULT = "latest_jockey_record_mult"
# 連續分級項取代兩個單邊門檻 —— 所以啟用佢嗰陣要同時關掉舊嗰兩個，否則重複計。
def graded(m):
    return [(W, MULT, m), (W, LEAVE, 0.0), (W, DOWN, 0.0)]

VARIANTS = [
    ("現行", []),
    ("分級項 mult=4", graded(4.0)),
    ("分級項 mult=8", graded(8.0)),
    ("分級項 mult=12", graded(12.0)),
    ("分級項 mult=8 + 反 SAME", graded(8.0) + [(W, SAME, -2.0)]),
]

KEYS = ("gold", "good_positional", "pass", "champion", "winner_in_top3")
PRIORITY = ("gold", "good_positional")
GUARD = ("t3prec", "winner_in_top3")


def score_race(logic, rows, path, patches):
    ctx = copy.deepcopy(logic["race_analysis"])
    backfill_pf_metrics(logic, path)
    ctx["field_summary"] = _build_field_summary(logic["horses"])
    ctx["field_horse_names"] = [h.get("horse_name") for h in logic["horses"].values()
                                if isinstance(h, dict) and h.get("horse_name")]
    out = []
    with patched_weights(patches):
        for src in rows:
            horse = dict(src["horse"])
            horse.setdefault("horse_number", src["horse_number"])
            data = horse.get("_data") if isinstance(horse.get("_data"), dict) else {}
            r = RacingEngine(horse, ctx, facts_section=data.get("facts_section", ""),
                             facts_path=path).analyze_horse()
            out.append((float(r["ability_score"]), src["horse_number"], src["actual_pos"]))
    return out


def auc_pairs(scored_races, top_only=False, K=5):
    """→ 逐場 (concordant, comparable)。場數指標喺 718 場之下功效唔夠 ——
    校準過：40 個確定中性嘅改動，三道閘全過 0/40。場內 AUC 用晒每一對比較。"""
    out = []
    for race in scored_races:
        ranked = sorted(race, key=lambda x: (-x[0], x[1]))
        rank = {r[1]: i + 1 for i, r in enumerate(ranked)}
        c = n = 0
        for a in race:
            for b in race:
                if not (a[2] <= 3 and b[2] > 3):
                    continue
                if top_only and rank[a[1]] > K and rank[b[1]] > K:
                    continue
                n += 1
                c += 1.0 if a[0] > b[0] else (0.5 if a[0] == b[0] else 0.0)
        out.append((c, n))
    return out


def auc_of(pairs, lo=0, hi=None):
    seg = pairs[lo:hi]
    n = sum(x[1] for x in seg)
    return (sum(x[0] for x in seg) / n) if n else float("nan")


def boot_ci(base, cand, lo, hi, seed=7):
    """配對 bootstrap，**按場**重抽 —— 同場比較唔獨立，按對重抽會低估區間。"""
    import random
    rng = random.Random(seed)
    m = hi - lo
    ds = []
    for _ in range(2000):
        idx = [lo + rng.randrange(m) for _ in range(m)]
        nb = sum(base[i][1] for i in idx)
        nc = sum(cand[i][1] for i in idx)
        if nb and nc:
            ds.append(sum(cand[i][0] for i in idx) / nc
                      - sum(base[i][0] for i in idx) / nb)
    ds.sort()
    return ds[len(ds) // 40], ds[-len(ds) // 40]


def metrics(scored_races):
    rows = []
    for race in scored_races:
        ranked = sorted(race, key=lambda x: (-x[0], x[1]))
        picks = [x[1] for x in ranked]
        pos = {x[1]: x[2] for x in race}
        top3 = {h for h, p in pos.items() if p <= 3}
        win = next((h for h, p in pos.items() if p == 1), None)
        if not top3 or win is None:
            continue
        rows.append(race_metrics(picks, top3, winner=win, actual_pos=pos,
                                 field_size=len(pos)))
    if not rows:
        return None
    c = summarize_races(rows)["counts"]
    n = len(rows)
    o = {k: 100.0 * c[k] / n for k in KEYS}
    o["t3prec"] = 100.0 * sum(x["hits"] for x in rows) / \
        sum(min(3, len(x["picks"])) for x in rows)
    return o


def main():
    ap = argparse.ArgumentParser(description="騎師連續性三項 A/B")
    ap.add_argument("--archive-root", type=Path, required=True)
    ap.add_argument("--results-csv", type=Path, required=True)
    ap.add_argument("--holdout", type=float, default=0.15)
    ap.add_argument("--limit-races", type=int)
    args = ap.parse_args()

    files, ph = discover_logic_files(args.archive_root)
    files = sorted(files + ph, key=lambda p: (p.parent.name, p.stem))
    if args.limit_races:
        files = files[:args.limit_races]
    results = load_historical_results(args.results_csv)

    scored = {name: [] for name, _ in VARIANTS}
    for path, aligned in iter_aligned_races(files, results, prefetch_workers=4):
        if aligned[0] is None:
            continue
        logic, rows = aligned
        for name, patches in VARIANTS:
            scored[name].append(score_race(logic, rows, path, patches))
        if len(scored["現行"]) % 50 == 0:
            print(f"  已評 {len(scored['現行'])} 場", flush=True)

    n = len(scored["現行"])
    cut = int(n * (1 - args.holdout))
    fold = cut // 5
    wn = n // 5
    print(f"\n{n} 場（dev {cut} / holdout {n - cut}）\n")

    base = {k: metrics(v) for k, v in
            (("all", scored["現行"]), ("dev", scored["現行"][:cut]),
             ("hold", scored["現行"][cut:]))}
    hdr = (f"{'':18}{'Gold':>8}{'Good':>9}{'Pass':>8}{'champ':>8}"
           f"{'winT3':>8}{'t3prec':>9}")
    for seg, lo, hi in (("全樣本", 0, n), ("dev", 0, cut), ("holdout（未碰）", cut, n)):
        b = metrics(scored["現行"][lo:hi])
        print(f"===== {seg} =====")
        print(hdr)
        for name, _ in VARIANTS[1:]:
            c = metrics(scored[name][lo:hi])
            print(f"{name:18}" + "".join(
                f"{c[k] - b[k]:>+8.2f}" if k != "good_positional" else f"{c[k] - b[k]:>+9.2f}"
                for k in ("gold", "good_positional", "pass", "champion",
                          "winner_in_top3", "t3prec")))
        print()

    print("===== ability 場內 AUC（配對 bootstrap 95% 區間）=====")
    for label, top in (("全場配對", False), (f"頭 5 位配對", True)):
        b = auc_pairs(scored["現行"], top)
        print(f"\n── {label} ──  現行 dev {auc_of(b,0,cut):.4f} · "
              f"holdout {auc_of(b,cut,n):.4f}")
        print(f"{'':22}{'dev Δ':>10}{'dev 95% CI':>24}{'hold Δ':>10}{'hold 95% CI':>24}")
        for name, _ in VARIANTS[1:]:
            c = auc_pairs(scored[name], top)
            dd = auc_of(c, 0, cut) - auc_of(b, 0, cut)
            hd = auc_of(c, cut, n) - auc_of(b, cut, n)
            dl, dh = boot_ci(b, c, 0, cut)
            hl, hh = boot_ci(b, c, cut, n)
            f = lambda l, h: f"[{l:+.4f}, {h:+.4f}]" + ("✅" if l > 0 else ("❌" if h < 0 else "·"))
            print(f"{name:22}{dd:>+10.4f}{f(dl,dh):>26}{hd:>+10.4f}{f(hl,hh):>26}")
    print()

    print("===== 閘門（已知功效不足，只作參考）=====")
    print(f"{'':18}{'dev 5-fold':>12}{'walk-forward':>14}{'holdout 守門':>14}")
    for name, _ in VARIANTS[1:]:
        f_ok = 0
        for i in range(5):
            s = slice(i * fold, (i + 1) * fold if i < 4 else cut)
            b, c = metrics(scored["現行"][s]), metrics(scored[name][s])
            if b and c and all(c[k] - b[k] >= -0.01 for k in GUARD):
                f_ok += 1
        w_ok = 0
        for i in range(5):
            s = slice(i * wn, (i + 1) * wn if i < 4 else n)
            b, c = metrics(scored["現行"][s]), metrics(scored[name][s])
            if b and c and all(c[k] - b[k] >= -0.01 for k in GUARD):
                w_ok += 1
        bh, ch = metrics(scored["現行"][cut:]), metrics(scored[name][cut:])
        h_ok = all(ch[k] - bh[k] >= -0.001 for k in GUARD + PRIORITY)
        print(f"{name:18}{f'{f_ok}/5':>12}{f'{w_ok}/5':>14}"
              f"{('✅' if h_ok else '❌'):>14}")
    print("\n落實條件：dev 5-fold 5/5、walk-forward 5/5、holdout 主指標同守門都唔跌。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
