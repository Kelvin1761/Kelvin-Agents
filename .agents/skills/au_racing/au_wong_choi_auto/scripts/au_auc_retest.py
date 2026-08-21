#!/usr/bin/env python3
"""用**有功效嘅尺**重測所有舊嘅「REJECT」結論。

點解需要。2026-08-04 校準過原本嗰道閘（dev 5-fold 5/5 + walk-forward 5/5）：
40 個**確定中性**嘅擾動之下，三道閘全過嘅係 **0/40**。假陽性率 0 係好事，
但佢同時會拒絕細幅度嘅真改動 —— 而呢個 repo 過去大半年嘅 REJECT 全部係
用嗰道閘（或者更弱嘅場數指標對比）判嘅。所以嗰批結論要重讀。

新尺：**ability 場內 AUC**。13,237 對比較 vs ~600 個二元標籤，功效高一個
數量級。三個一定要做嘅細節：

  1. **配對 bootstrap，按場重抽** —— 同一場嘅比較唔獨立，按對重抽會低估區間。
  2. **兩個區域分開報**：全場配對 vs 只計至少一匹落喺模型頭 5 位嘅配對。
     深位馬之間排錯次序拉高全場 AUC 但對 Gold/Good 完全冇影響。
     只喺全場贏、頭 5 位唔贏 = 對揀馬冇價值。
  3. **dev / holdout 分開**，睇 holdout 有冇大過 dev（大過 = 唔係擬合 dev）。

⚠️ AUC 高唔等於要落實。佢答「排序有冇改善」，唔答「Gold/Good 有冇升」。
所以過咗呢度嘅候選仍然要用場數指標睇幅度，同埋睇 wet overlay lockstep。

⚠️ 呢個工具只可以測**leaf 同權重層面**嘅改動（ability 對 leaf 係線性，
所以離線重算係精確嘅）。改引擎內部公式嘅候選要重跑引擎。

用法：
    python3 au_auc_retest.py --data <sb_leaves_v2.json>
    python3 au_auc_retest.py --data ... --only form_line
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR.parents[2] / "shared_racing"))

from au_racing_engine import matrix_mapper  # noqa: E402
from eval_metrics import race_metrics, summarize_races  # noqa: E402
from au_racing_engine.scoring import MATRIX_WEIGHTS  # noqa: E402

TOP_K = 5          # 決定 Gold（頭四揀）／Good 嘅區域，留一格緩衝
BOOT = 2000


def renorm(d):
    s = sum(d.values())
    return {k: v / s for k, v in d.items()} if s else dict(d)


def pairs_per_race(races, formulas=None, weights=None, top_only=False):
    """→ 逐場 (concordant, comparable)。留返逐場係為咗做配對 bootstrap。"""
    saved = matrix_mapper.MATRIX_FORMULAS
    if formulas is not None:
        matrix_mapper.MATRIX_FORMULAS = formulas
    w = weights or MATRIX_WEIGHTS
    try:
        out = []
        for r in races:
            sc = []
            for row in r["rows"]:
                m = matrix_mapper.map_features_to_matrix_scores(row["features"])
                sc.append((sum(m.get(k, 60.0) * ww for k, ww in w.items()) + row["wet"],
                           row["pos"] <= 3))
            order = sorted(range(len(sc)), key=lambda i: -sc[i][0])
            rank = {i: p + 1 for p, i in enumerate(order)}
            c = n = 0
            for i in range(len(sc)):
                for j in range(len(sc)):
                    if not (sc[i][1] and not sc[j][1]):
                        continue
                    if top_only and rank[i] > TOP_K and rank[j] > TOP_K:
                        continue
                    n += 1
                    c += 1.0 if sc[i][0] > sc[j][0] else (0.5 if sc[i][0] == sc[j][0] else 0.0)
            out.append((c, n))
        return out
    finally:
        matrix_mapper.MATRIX_FORMULAS = saved


def auc(pairs, lo=0, hi=None):
    seg = pairs[lo:hi]
    n = sum(x[1] for x in seg)
    return (sum(x[0] for x in seg) / n) if n else float("nan")


def boot_ci(base, cand, lo, hi, seed=7):
    """配對 bootstrap：同一批重抽場次餵兩個模型，令場次難易度抵消。"""
    rng = random.Random(seed)
    m = hi - lo
    ds = []
    for _ in range(BOOT):
        idx = [lo + rng.randrange(m) for _ in range(m)]
        nb = sum(base[i][1] for i in idx)
        nc = sum(cand[i][1] for i in idx)
        if nb and nc:
            ds.append(sum(cand[i][0] for i in idx) / nc
                      - sum(base[i][0] for i in idx) / nb)
    ds.sort()
    return ds[len(ds) // 40], ds[-len(ds) // 40]


def race_counts(races, formulas=None, weights=None):
    saved = matrix_mapper.MATRIX_FORMULAS
    if formulas is not None:
        matrix_mapper.MATRIX_FORMULAS = formulas
    w = weights or MATRIX_WEIGHTS
    try:
        rows = []
        for r in races:
            sc = []
            for row in r["rows"]:
                m = matrix_mapper.map_features_to_matrix_scores(row["features"])
                sc.append((sum(m.get(k, 60.0) * ww for k, ww in w.items()) + row["wet"],
                           row["name"], row["pos"]))
            sc.sort(key=lambda x: -x[0])
            pos = {s[1]: s[2] for s in sc}
            t3 = {h for h, p in pos.items() if p <= 3}
            win = next((h for h, p in pos.items() if p == 1), None)
            if not t3 or win is None:
                continue
            rows.append(race_metrics([s[1] for s in sc], t3, winner=win,
                                     actual_pos=pos, field_size=max(pos.values())))
        c = summarize_races(rows)["counts"]
        n = len(rows)
        o = {k: 100.0 * c[k] / n for k in ("gold", "good_positional", "champion",
                                           "winner_in_top3")}
        o["t3prec"] = 100.0 * sum(x["hits"] for x in rows) / \
            sum(min(3, len(x["picks"])) for x in rows)
        return o
    finally:
        matrix_mapper.MATRIX_FORMULAS = saved


RACES_PROBE = []


def build_candidates():
    """每個候選 = (名, 舊結論, formulas 或 None, weights 或 None)。"""
    F = matrix_mapper.MATRIX_FORMULAS
    W = MATRIX_WEIGHTS
    out = []

    # ── 舊 REJECT #1：form_line 維度權重恢復 ───────────────────────────────
    # 舊結論：「holdout champion negative at every weight」→ 全部 REJECT。
    # 值得重測，因為賽績線 cohort 實測有 −6.9pp 嘅結構。
    for w in (0.02, 0.04, 0.06, 0.10):
        nw = renorm({**W, "form_line": w})
        out.append((f"form_line 權重 {w:.2f}", "REJECT（holdout champ 負）", None, nw))

    # ── 舊 REJECT #2：剷走 AUC <0.5 嘅 leaf ───────────────────────────────
    # 舊結論：「所有變體 holdout 都輸」。sectional_score AUC 0.469 反向，
    # 但佢 66% 嘅馬卡喺 60（冇 gradient），所以剷佢主要係剷噪音。
    pp = [(k, v) for k, v in F["pace_perf"] if k != "sectional_score"]
    tot = sum(v for _, v in pp)
    out.append(("pace_perf 剷 sectional", "REJECT（holdout 輸）",
                {**F, "pace_perf": tuple((k, v / tot * sum(v for _, v in F["pace_perf"]))
                                         for k, v in pp)}, None))

    # ── 舊 REJECT #3：track 維度剷走 ──────────────────────────────────────
    out.append(("剷 track 維度", "未正式測過",
                None, renorm({k: v for k, v in W.items() if k != "track"})))

    # ── 舊「未 ship」#4：stability form .60 → .65 ─────────────────────────
    out.append(("stability form .65", "過閘但冇 ship（鄰值跳）",
                {**F, "stability": (("form_score", 0.65), ("consistency_score", 0.35))},
                None))

    # ── `lo_record_score`：上仗騎師同此駒嘅往績，做獨立維度 ───────────────
    # 點解要做獨立維度而唔係塞返入 `jockey_horse_fit`：`jockey_trainer` 0.19149
    # × 內部 0.381 = **有效權重 0.073**，所以一個 ±4 分嘅 leaf 內調整落到
    # ability 只剩 ±0.29 分 —— 而 `form_score` 有效權重 0.229、範圍 50 分。
    # 個訊號係真嘅（喺 form_score 分層之內仲有 +11.8 / +4.9 / +8.8 / +4.1pp，
    # 即係佢**唔係**近績代理），但之前放咗喺一個太細嘅位，所以量唔到。
    if RACES_PROBE and any("lo_record_score" in row["features"]
                           for r in RACES_PROBE for row in r["rows"]):
        for w in (0.03, 0.05, 0.08, 0.12, 0.16):
            out.append((f"lo_record 做維度 w={w:.2f}", "新候選（今日量到）",
                        {**F, "_lo": (("lo_record_score", 1.0),)},
                        renorm({**W, "_lo": w})))

    # ── 從未入排名嘅 leaf：值唔值返嚟？ ──────────────────────────────────
    # class_score / distance_score / weight_score 都係以前被移除嘅。
    # 用一個新維度、細權重接返入去（同 au_candidate_dimension 一樣嘅做法）。
    for leaf, why in (("class_score", "2026-07-29 由 class_weight 移除"),
                      ("distance_score", "2026-06-29 移除"),
                      ("weight_score", "2026-08-01 移除（AUC 0.480）"),
                      ("confidence_score", "從未入排名"),
                      ("health_score", "從未入排名")):
        for w in (0.03, 0.06):
            nw = renorm({**W, f"_{leaf}": w})
            nf = {**F, f"_{leaf}": ((leaf, 1.0),)}
            out.append((f"{leaf} 做維度 w={w:.2f}", why, nf, nw))
    return out


def main():
    ap = argparse.ArgumentParser(description="用 AUC 重測舊 REJECT")
    ap.add_argument("--data", required=True)
    ap.add_argument("--only", help="淨係跑名入面含呢個字嘅候選")
    ap.add_argument("--holdout", type=float, default=0.15)
    args = ap.parse_args()

    races = json.loads(Path(args.data).read_text())["races"]
    RACES_PROBE[:] = races[:5]
    n = len(races)
    cut = int(n * (1 - args.holdout))
    cands = [c for c in build_candidates()
             if not args.only or args.only.lower() in c[0].lower()]

    base_all = pairs_per_race(races)
    base_top = pairs_per_race(races, top_only=True)
    bc = race_counts(races)
    print(f"{n} 場（dev {cut} / holdout {n - cut}）· "
          f"{sum(x[1] for x in base_all):,} 對全場 / "
          f"{sum(x[1] for x in base_top):,} 對頭 {TOP_K} 位")
    print(f"現行 AUC：全場 dev {auc(base_all,0,cut):.4f} / holdout {auc(base_all,cut,n):.4f}"
          f" · 頭 {TOP_K} 位 dev {auc(base_top,0,cut):.4f} / holdout {auc(base_top,cut,n):.4f}\n")

    print(f"{'候選':26}{'全場 dev':>12}{'全場 hold':>13}"
          f"{'頭5 dev':>12}{'頭5 hold':>13}   {'Gold':>6}{'Good位':>7}{'t3p':>7}  判斷")
    print("─" * 118)
    winners = []
    for name, old, F, W in cands:
        ca, ct = pairs_per_race(races, F, W), pairs_per_race(races, F, W, True)
        cells, flags = [], []
        for p_b, p_c in ((base_all, ca), (base_top, ct)):
            for lo, hi in ((0, cut), (cut, n)):
                d = auc(p_c, lo, hi) - auc(p_b, lo, hi)
                l, h = boot_ci(p_b, p_c, lo, hi)
                mark = "✅" if l > 0 else ("❌" if h < 0 else "·")
                flags.append(mark)
                cells.append(f"{d:+.4f}{mark}")
        rc = race_counts(races, F, W)
        good = flags.count("✅")
        bad = flags.count("❌")
        verdict = ("**過** " + "✅" * good) if good >= 2 and bad == 0 else \
                  ("方向反 ❌" if bad else "冇分別")
        if good >= 2 and bad == 0:
            winners.append((name, old, good))
        print(f"{name:26}{cells[0]:>12}{cells[1]:>13}{cells[2]:>12}{cells[3]:>13}   "
              f"{rc['gold']-bc['gold']:>+6.2f}{rc['good_positional']-bc['good_positional']:>+7.2f}"
              f"{rc['t3prec']-bc['t3prec']:>+7.2f}  {verdict}")

    print(f"\n✅ = 95% 區間唔過 0 · ❌ = 區間全負 · · = 跨 0（呢個尺分唔開）")
    if winners:
        print(f"\n值得跟進（≥2 個區域顯著、冇一個反向）：")
        for nm, old, g in sorted(winners, key=lambda x: -x[2]):
            print(f"  {nm:26} {g}/4 顯著   舊結論：{old}")
    else:
        print("\n冇候選喺新尺之下翻案 —— 舊嘅 REJECT 企得住。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
