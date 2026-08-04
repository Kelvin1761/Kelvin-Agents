#!/usr/bin/env python3
"""**一把尺。** 所有 AU Wong Choi 嘅候選改動都行呢度，唔好再各自砌。

點解要有呢個檔。到 2026-08-04 為止，同一個問題（「呢個改動好唔好？」）散落喺
七八個 harness、每個各有一套指標同閘門：dev / holdout / 5-fold / walk-forward /
全樣本 / Gold / gold_strict / Good位 / any2 / any1 / champion / winT3 / t3prec /
場內 AUC（全場）/ 場內 AUC（頭 5 位）。**冇一份文件講過邊把先算數**，
結果係同一個候選喺唔同 harness 之下可以得出相反結論，而我自己就試過幾次
攞住唔同 harness 嘅數字互相比較（跨語料、跨基準），得出錯嘅結論。

呢度定死一次：

┌─ 判決規則（PRIMARY）────────────────────────────────────────────────────┐
│ **頭 K 位配對嘅場內 AUC，holdout 上 95% 配對 bootstrap 區間唔過 0。**    │
│ dev 唔准係負（點估計）。就係咁多。                                       │
└────────────────────────────────────────────────────────────────────────┘

點解係呢個，唔係場數指標：

  * **場數指標冇功效。** 2026-08-04 校準過：對 leaf 加 ±0.3 隨機擾動
    （**確定中性**）跑 40 次，dev 5-fold 5/5 + walk-forward 5/5 + holdout
    三道閘**全過嘅係 0/40**。假陽性率 0 好，但佢同時拒絕細幅度嘅真改動 ——
    一個真 +1pp 嘅改動大機會過唔到。用佢做裁判會系統性拒絕所有細改善。
  * **AUC 有功效。** ~600 個二元場次標籤 vs ~13,000 對比較，高一個數量級。
  * **要限喺頭 K 位。** 深位馬之間排錯次序拉高全場 AUC，但對 Gold（前三全部
    喺頭四揀）同 Good位（頭兩揀都上名）**完全冇影響**。只喺全場贏、
    頭 K 位唔贏 = 對揀馬冇價值。K=5 留一格緩衝。
  * **bootstrap 要按場重抽。** 同一場入面嘅配對唔獨立，按對重抽會低估區間。
  * **配對 bootstrap。** 同一批重抽場次餵兩個模型，令場次難易度抵消。

場數指標（Gold / Good位 / t3prec…）**照報，做幅度參考**，但**唔做閘**。
佢哋答「贏幾多」，AUC 答「係咪真係贏」。兩個問題唔同。

⚠️ 有兩件事 AUC 一樣捉唔到，要另外做：
  1. **洩漏** —— 統計閘捉唔到。要逐個欄位做賽前檢查，最可靠係
     「由另一個已驗證嘅來源獨立計同一個特徵，兩者唔夾就係洩漏」。
     見 REFIT_PLAN.md 嘅 `last6` 個案。
  2. **wet overlay lockstep** —— 改動一旦令 ability 散佈變，濕地 overlay
     要按同一比例郁。`test_neutral_display_scale.py` 會捉。

用法：
    from au_eval import compare, load_races
    races = load_races("leaves.json")
    print(compare(races, base_scorer, cand_scorer, label="我個候選"))

    python3 au_eval.py --data leaves.json --swap-leaf trial_score=60   # 快速檢查
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR / "racing_engine"))
sys.path.insert(0, str(SCRIPT_DIR.parents[2] / "shared_racing"))

import matrix_mapper  # noqa: E402
from eval_metrics import race_metrics, summarize_races  # noqa: E402
from scoring import MATRIX_WEIGHTS  # noqa: E402

TOP_K = 5           # 決定 Gold（頭四揀）／Good位 嘅區域，留一格緩衝
HOLDOUT = 0.15      # 依時間切，holdout 唔准睇住調
BOOT = 2000
CONTEXT_KEYS = ("gold", "good_positional", "good_any2", "champion",
                "winner_in_top3")


def load_races(path):
    """讀 leaves dump（`{"races":[{"rows":[{features,wet,pos}]}]}`）。"""
    return json.loads(Path(path).read_text())["races"]


def default_scorer(row):
    """現行引擎：ability = Σ 維度分 × 權重 + 濕地 overlay。"""
    m = matrix_mapper.map_features_to_matrix_scores(row["features"])
    return sum(m.get(k, 60.0) * w for k, w in MATRIX_WEIGHTS.items()) + row["wet"]


def _pairs(races, scorer, top_only):
    """→ 逐場 (concordant, comparable)。留返逐場係為咗配對 bootstrap。"""
    out = []
    for r in races:
        sc = [(scorer(x), x["pos"]) for x in r["rows"]]
        order = sorted(range(len(sc)), key=lambda i: -sc[i][0])
        rank = {i: p + 1 for p, i in enumerate(order)}
        c = n = 0
        for i in range(len(sc)):
            for j in range(len(sc)):
                if not (sc[i][1] <= 3 and sc[j][1] > 3):
                    continue
                if top_only and rank[i] > TOP_K and rank[j] > TOP_K:
                    continue
                n += 1
                c += 1.0 if sc[i][0] > sc[j][0] else (0.5 if sc[i][0] == sc[j][0] else 0.0)
        out.append((c, n))
    return out


def _auc(pairs, lo=0, hi=None):
    seg = pairs[lo:hi]
    n = sum(x[1] for x in seg)
    return (sum(x[0] for x in seg) / n) if n else float("nan")


def _boot_ci(base, cand, lo, hi, seed=7):
    """配對 bootstrap，**按場**重抽。"""
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


def _counts(races, scorer):
    rows = []
    for r in races:
        sc = sorted(((scorer(x), i, x["pos"]) for i, x in enumerate(r["rows"])),
                    key=lambda t: -t[0])
        pos = {t[1]: t[2] for t in sc}
        t3 = {h for h, p in pos.items() if p <= 3}
        win = next((h for h, p in pos.items() if p == 1), None)
        if len(t3) < 3 or win is None:
            continue
        rows.append(race_metrics([t[1] for t in sc], t3, winner=win,
                                 actual_pos=pos, field_size=max(pos.values())))
    if not rows:
        return {}
    c = summarize_races(rows)["counts"]
    n = len(rows)
    o = {k: 100.0 * c[k] / n for k in CONTEXT_KEYS}
    o["t3prec"] = 100.0 * sum(x["hits"] for x in rows) / \
        sum(min(3, len(x["picks"])) for x in rows)
    return o


@dataclass
class Verdict:
    label: str
    races: int
    ship: bool
    reason: str
    top_dev: float = 0.0
    top_hold: float = 0.0
    top_hold_ci: tuple = (0.0, 0.0)
    all_dev: float = 0.0
    all_hold: float = 0.0
    all_hold_ci: tuple = (0.0, 0.0)
    counts: dict = field(default_factory=dict)

    def __str__(self):
        def band(d, ci):
            mark = "✅" if ci[0] > 0 else ("❌" if ci[1] < 0 else "·")
            return f"{d:+.4f} [{ci[0]:+.4f}, {ci[1]:+.4f}] {mark}"
        lines = [
            f"── {self.label} ──  {self.races} 場",
            f"  【判決依據】頭 {TOP_K} 位配對 AUC",
            f"     dev      {self.top_dev:+.4f}",
            f"     holdout  {band(self.top_hold, self.top_hold_ci)}",
            f"  【參考】全場配對 AUC",
            f"     dev      {self.all_dev:+.4f}",
            f"     holdout  {band(self.all_hold, self.all_hold_ci)}",
        ]
        if self.counts:
            lines.append("  【參考】場數指標（唔做閘，只睇幅度）")
            lines.append("     " + " · ".join(
                f"{k.replace('good_positional','Good位').replace('winner_in_top3','winT3')}"
                f" {v:+.2f}" for k, v in self.counts.items()))
        lines.append(f"  ➜ {'✅ 可以 ship' if self.ship else '❌ 唔 ship'}：{self.reason}")
        return "\n".join(lines)


def compare(races, base_scorer=None, cand_scorer=None, *, label="候選",
            holdout=HOLDOUT, with_counts=True):
    """一個候選 vs 基準。→ `Verdict`。

    判決：頭 K 位 holdout 區間唔過 0，而且 dev 點估計唔係負。
    """
    base_scorer = base_scorer or default_scorer
    n = len(races)
    cut = int(n * (1 - holdout))
    bt, ct = _pairs(races, base_scorer, True), _pairs(races, cand_scorer, True)
    ba, ca = _pairs(races, base_scorer, False), _pairs(races, cand_scorer, False)

    td = _auc(ct, 0, cut) - _auc(bt, 0, cut)
    th = _auc(ct, cut, n) - _auc(bt, cut, n)
    tci = _boot_ci(bt, ct, cut, n)
    ad = _auc(ca, 0, cut) - _auc(ba, 0, cut)
    ah = _auc(ca, cut, n) - _auc(ba, cut, n)
    aci = _boot_ci(ba, ca, cut, n)

    if tci[0] > 0 and td >= 0:
        ship, why = True, f"holdout 頭 {TOP_K} 位區間唔過 0，dev 唔係負"
    elif tci[1] < 0:
        ship, why = False, "holdout 區間全負 —— 呢個改動令排序變差"
    elif td < 0:
        ship, why = False, "dev 點估計係負"
    else:
        ship, why = False, "holdout 區間跨 0 —— 呢把尺分唔開，證明唔到有改善"

    counts = {}
    if with_counts:
        b, c = _counts(races, base_scorer), _counts(races, cand_scorer)
        counts = {k: c[k] - b[k] for k in c if k in b}
    return Verdict(label, n, ship, why, td, th, tci, ad, ah, aci, counts)


def main():
    ap = argparse.ArgumentParser(description="AU Wong Choi 統一評估")
    ap.add_argument("--data", required=True, help="leaves dump JSON")
    ap.add_argument("--swap-leaf", action="append", default=[],
                    help="LEAF=VALUE，把某個 leaf 設成常數（用嚟量佢貢獻）")
    ap.add_argument("--holdout", type=float, default=HOLDOUT)
    args = ap.parse_args()

    races = load_races(args.data)
    print(f"{len(races)} 場 · 判決 = 頭 {TOP_K} 位配對 AUC 嘅 holdout 區間\n")
    if not args.swap_leaf:
        b = _pairs(races, default_scorer, True)
        n = len(races)
        cut = int(n * (1 - args.holdout))
        print(f"現行基準：頭 {TOP_K} 位 AUC  dev {_auc(b,0,cut):.4f} · "
              f"holdout {_auc(b,cut,n):.4f}")
        return 0
    for spec in args.swap_leaf:
        leaf, _, val = spec.partition("=")
        v = float(val)

        def cand(row, _leaf=leaf, _v=v):
            f = dict(row["features"])
            f[_leaf] = _v
            m = matrix_mapper.map_features_to_matrix_scores(f)
            return sum(m.get(k, 60.0) * w for k, w in MATRIX_WEIGHTS.items()) + row["wet"]

        print(compare(races, default_scorer, cand,
                      label=f"{leaf} 設成常數 {v:g}", holdout=args.holdout))
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
