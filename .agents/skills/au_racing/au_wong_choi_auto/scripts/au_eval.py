#!/usr/bin/env python3
"""**一把尺。** 所有 AU Wong Choi 嘅候選改動都行呢度，唔好再各自砌。

點解要有呢個檔。到 2026-08-04 為止，同一個問題（「呢個改動好唔好？」）散落喺
七八個 harness、每個各有一套指標同閘門：dev / holdout / 5-fold / walk-forward /
全樣本 / Gold / gold_strict / Good位 / Pass / champion / winT3 / t3prec /
場內 AUC（全場）/ 場內 AUC（頭 5 位）。**冇一份文件講過邊把先算數**，
結果係同一個候選喺唔同 harness 之下可以得出相反結論，而我自己就試過幾次
攞住唔同 harness 嘅數字互相比較（跨語料、跨基準），得出錯嘅結論。

呢度定死一次：

┌─ Stage 4 v2 判決規則 ───────────────────────────────────────────────────┐
│ PRIMARY：Gold／Good位優先；dev + terminal 改善，terminal paired CI > 0。 │
│ RANKING：兩項預先登記排序指標改善，其中一項 terminal paired CI > 0，     │
│          同時 Gold／Good位不可回歸。                                      │
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

頭五位 AUC 仍然係排序 path 嘅其中一把有功效尺，但唔再凌駕 Gold／Good位。
舊 v1 AUC-only 規則只保留喺 `docs/model-evaluation-contract.md` 做歷史記錄。

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
from dataclasses import asdict
import json
import math
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR.parents[2] / "shared_racing"))

from au_racing_engine import matrix_mapper  # noqa: E402
from eval_metrics import race_metrics, summarize_races  # noqa: E402
from model_evaluation_decision import (  # noqa: E402
    build_evaluation_input,
    evaluate_candidate,
)
from au_racing_engine.scoring import (  # noqa: E402
    compose_matrix_score,
    MATRIX_WEIGHTS,
)

# 場數指標（Gold / Good位 / Pass）係「入唔入實際前三」嘅二元判斷，**冇按馬群大細
# 正規化**：8 匹馬入前三係 3/8，14 匹馬係 3/14。2026-08-21 實測（dev 901 場，
# 時間因素已隔離）Gold 由 ≤8 匹嘅 31.58% 一路跌到 13+ 匹嘅 8.91% —— 3.5 倍。
#
# 後果：任何令馬群組成改變嘅嘢（換語料、換窗、加新場次）都會偽裝成模型變化。
# 同日實測到嘅例子：pooled 數字係 dev Gold 16.13% vs holdout 20.70%（睇落
# 「holdout 好過 dev」），但 holdout 平均馬群 9.08、dev 10.51；控制到 9-10 匹之後
# 變成 dev 15.38% vs holdout 13.33% —— **方向相反**。
#
# 所以基準報告一定要同時出分層數字。呢個係**附加**輸出，唔改判決規則。
FIELD_BUCKETS = ((0, 8, "≤8"), (9, 10, "9-10"), (11, 12, "11-12"), (13, 99, "13+"))

TOP_K = 5           # 決定 Gold（頭四揀）／Good位 嘅區域，留一格緩衝
HOLDOUT = 0.15      # 依時間切，holdout 唔准睇住調
BOOT = 2000
CONTEXT_KEYS = (
    "gold",
    "gold_strict",
    "good_positional",
    "pass",
    "champion",
    "winner_in_top3",
    "winner_in_top5",
)


def load_races(path):
    """Read either compact leaves or the current-runtime audit snapshot."""
    source = json.loads(Path(path).read_text())["races"]
    races = []
    for race in source:
        metadata = race.get("metadata") or {}
        rows = []
        for row in race["rows"]:
            rows.append({
                **row,
                "features": row.get("features", row.get("feature_scores", {})),
                "wet": row.get("wet", row.get("wet_form_feature", 0.0)),
                "proven_class": row.get(
                    "proven_class", row.get("proven_class_feature", 0.0)
                ),
                "pos": row.get("pos", row.get("actual_pos")),
            })
        races.append({
            **race,
            "date": race.get("date", metadata.get("date")),
            "rows": rows,
        })
    return races


def default_scorer(row):
    """現行引擎：ability = Σ 維度分 × 權重 + 所有已聲明 overlay。"""
    m = matrix_mapper.map_features_to_matrix_scores(row["features"])
    return (
        compose_matrix_score(m)
        + float(row["wet"] or 0.0)
        + float(row.get("proven_class") or 0.0)
    )


def configured_scorer(*, weights=None, wet_scale=1.0, leaf_overrides=None):
    """Build one candidate scorer without inventing another evaluation path.

    Research tools may search on development data, but every final candidate
    comes through this function and :func:`compare`, so date partitioning,
    metrics and the paired bootstrap stay identical.
    """
    weights = dict(weights or MATRIX_WEIGHTS)
    leaf_overrides = dict(leaf_overrides or {})

    # ⚠️ 2026-08-22 修：呢兩行本來 iterate **live `MATRIX_WEIGHTS`**，所以任何唔喺
    # live 權重表嘅維度會被**靜靜丟掉** —— 候選返 +0.0000，個報告寫「呢把尺分唔開」，
    # 而真相係「你個維度我無視咗」。
    #
    # 實測：mapper 出 7 個維度（含 `form_line` 同 `race_shape`），而 live
    # `MATRIX_WEIGHTS` 得 5 個。後果係
    #   * `form_line` 權重一直係 0，所以**由來都冇得測**（`au_weight_improvement_search.py`
    #     個 docstring 明寫「notably the currently zero-weighted form_line dimension」——
    #     嗰個目標結構上做唔到）
    #   * `race_shape` 2026-08-22 退出排名之後，就**再也無法 A/B 佢返轉頭**
    #
    # 而家 iterate live 權重同候選 key 嘅**聯集**，而唔認識嘅 key 會大聲死。
    # 候選 key ⊆ live 權重表嘅情況（過去所有用法）行為完全不變。
    mappable = set(matrix_mapper.MATRIX_FORMULAS)
    unknown = sorted(key for key in weights if key not in mappable)
    if unknown:
        raise ValueError(
            f"矩陣權重有 mapper 出唔到嘅維度：{unknown}。"
            f" 可用嘅係 {sorted(mappable)}。"
        )
    keys = tuple(dict.fromkeys((*MATRIX_WEIGHTS, *weights)))
    total = sum(float(weights.get(key, 0.0)) for key in keys)
    if total <= 0:
        raise ValueError("Matrix weights must have a positive total.")
    # Search relative allocations at the live coefficient budget. Explicit
    # coefficients can be evaluated with compose_matrix_score directly.
    budget = sum(MATRIX_WEIGHTS.values())
    normalised = {key: float(weights.get(key, 0.0)) * budget / total for key in keys}

    def scorer(row):
        features = dict(row["features"])
        features.update(leaf_overrides)
        matrices = matrix_mapper.map_features_to_matrix_scores(features)
        # 一定要跟 `engine_core` 嗰條 ability 公式（2026-08-26 加咗
        # MATRIX_ABILITY_SCALE）。唔跟就會同真引擎差一個只影響 wet /
        # proven_class 相對份量嘅偏差 —— `au_matrix_refit verify` 就係捉呢類嘢。
        return (
            compose_matrix_score(matrices, normalised)
            + float(row["wet"] or 0.0) * float(wet_scale)
            + float(row.get("proven_class") or 0.0)
        )

    return scorer


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


def _auc_indices(pairs, indices):
    selected = [pairs[index] for index in indices]
    n = sum(row[1] for row in selected)
    return (sum(row[0] for row in selected) / n) if n else float("nan")


def _boot_ci(base, cand, indices, seed=7):
    """配對 bootstrap，**按場**重抽。"""
    rng = random.Random(seed)
    indices = list(indices)
    m = len(indices)
    ds = []
    for _ in range(BOOT):
        idx = [indices[rng.randrange(m)] for _ in range(m)]
        nb = sum(base[i][1] for i in idx)
        nc = sum(cand[i][1] for i in idx)
        if nb and nc:
            ds.append(sum(cand[i][0] for i in idx) / nc
                      - sum(base[i][0] for i in idx) / nb)
    ds.sort()
    return ds[len(ds) // 40], ds[-len(ds) // 40]


def date_partitions(races, holdout=HOLDOUT):
    """Whole-date dev/holdout split; never cut a meeting day in half."""
    dates = [race.get("date") for race in races]
    if dates and all(dates):
        unique = sorted(set(dates))
        holdout_date_count = max(1, math.ceil(len(unique) * holdout))
        holdout_dates = set(unique[-holdout_date_count:])
        dev = [index for index, date in enumerate(dates) if date not in holdout_dates]
        terminal = [index for index, date in enumerate(dates) if date in holdout_dates]
        if dev and terminal:
            return dev, terminal
    cut = int(len(races) * (1 - holdout))
    return list(range(cut)), list(range(cut, len(races)))


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
        metadata = r.get("metadata") or {}
        field_size = int(r.get("field") or metadata.get("field_size") or len(pos))
        rows.append(race_metrics([t[1] for t in sc], t3, winner=win,
                                 actual_pos=pos, field_size=field_size))
    if not rows:
        return {}
    c = summarize_races(rows)["counts"]
    n = len(rows)
    o = {k: 100.0 * c[k] / n for k in CONTEXT_KEYS}
    o["t3prec"] = 100.0 * sum(x["hits"] for x in rows) / \
        sum(min(3, len(x["picks"])) for x in rows)
    return o


def _field_size(race):
    metadata = race.get("metadata") or {}
    return int(race.get("field") or metadata.get("field_size") or len(race["rows"]))


def _counts_by_field(races, scorer):
    """場數指標按馬群大細分桶。冇分桶嘅比較會被組成變化冒充成模型變化。"""
    out = {}
    for lo, hi, label in FIELD_BUCKETS:
        subset = [r for r in races if lo <= _field_size(r) <= hi]
        if not subset:
            continue
        counts = _counts(subset, scorer)
        if counts:
            out[label] = {"races": len(subset), **counts}
    return out


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
    stage4_verdict: str = "REJECT"
    decision_detail: dict = field(default_factory=dict)

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
        lines.append(
            f"  ➜ {'✅ 可以 ship' if self.ship else '❌ 唔 ship'} "
            f"[{self.stage4_verdict}]：{self.reason}"
        )
        return "\n".join(lines)


def verdict_dict(verdict):
    """JSON-safe public representation used by all companion audits."""
    output = asdict(verdict)
    output["top_hold_ci"] = list(verdict.top_hold_ci)
    output["all_hold_ci"] = list(verdict.all_hold_ci)
    return output


def baseline_report(races, holdout=HOLDOUT, scorer=None):
    """Return the one canonical baseline report for all/dev/terminal data."""
    scorer = scorer or default_scorer
    top = _pairs(races, scorer, True)
    all_field = _pairs(races, scorer, False)
    dev_indices, terminal_indices = date_partitions(races, holdout)
    return {
        "design": {
            "races": len(races),
            "development_races": len(dev_indices),
            "terminal_holdout_races": len(terminal_indices),
            "holdout_fraction_by_whole_date": holdout,
            # ⚠️ 上面係**日期**佔比。實際**場次**佔比可以差好遠 —— 唔同日期嘅場次
            # 密度唔同（2026-08-21 實測：15% 日期 = 36.2% 場次）。所有講
            # 「holdout 15%」嘅文字都要對照呢個數。
            "holdout_share_of_races": (
                len(terminal_indices) / len(races) if races else 0.0
            ),
            "top_k": TOP_K,
            "promotion_rule": (
                "Stage4 v2: Gold/Good primary; ranking-only requires primary "
                "non-regression, two predeclared gains and one positive terminal CI"
            ),
        },
        "auc": {
            "top_k_all": _auc(top),
            "top_k_development": _auc_indices(top, dev_indices),
            "top_k_terminal": _auc_indices(top, terminal_indices),
            "all_field_all": _auc(all_field),
            "all_field_development": _auc_indices(all_field, dev_indices),
            "all_field_terminal": _auc_indices(all_field, terminal_indices),
        },
        "metrics": {
            "all": _counts(races, scorer),
            "development": _counts([races[index] for index in dev_indices], scorer),
            "terminal": _counts([races[index] for index in terminal_indices], scorer),
        },
        # 分層 —— 見 FIELD_BUCKETS 上面嘅註釋。pooled 數字唔可以單獨信。
        "metrics_by_field": {
            "all": _counts_by_field(races, scorer),
            "development": _counts_by_field([races[i] for i in dev_indices], scorer),
            "terminal": _counts_by_field([races[i] for i in terminal_indices], scorer),
        },
        "field_size": {
            "development_mean": (
                sum(_field_size(races[i]) for i in dev_indices) / len(dev_indices)
                if dev_indices else 0.0
            ),
            "terminal_mean": (
                sum(_field_size(races[i]) for i in terminal_indices) / len(terminal_indices)
                if terminal_indices else 0.0
            ),
        },
    }


def _stage4_metric_rows(races, scorer):
    pairs = _pairs(races, scorer, True)
    rows = []
    for race, pair in zip(races, pairs):
        scored = sorted(
            ((scorer(row), index, row["pos"]) for index, row in enumerate(race["rows"])),
            key=lambda item: -item[0],
        )
        actual_pos = {index: position for _score, index, position in scored}
        actual_top3 = {index for index, position in actual_pos.items() if position <= 3}
        winner = next((index for index, position in actual_pos.items() if position == 1), None)
        metrics = race_metrics(
            [index for _score, index, _position in scored],
            actual_top3,
            winner=winner,
            actual_pos=actual_pos,
            field_size=_field_size(race),
        )
        rows.append(
            {
                "gold": metrics["gold"],
                "good_positional": metrics["good_positional"],
                "top3_capture_at5": metrics["top3_capture_at5"],
                "mean_top3_model_rank": metrics["top3_mean_model_rank"],
                "competitive_recall_at5": metrics["competitive_recall_at5"],
                "ndcg_at5": metrics["ndcg_at5"],
                "top5_pairwise_auc": pair[0] / pair[1] if pair[1] else None,
            }
        )
    return rows


def compare(races, base_scorer=None, cand_scorer=None, *, label="候選",
            holdout=HOLDOUT, with_counts=True, leakage_audit_passed=False):
    """一個候選 vs 基準。→ `Verdict`。

    判決：頭 K 位 holdout 區間唔過 0，而且 dev 點估計唔係負。
    """
    base_scorer = base_scorer or default_scorer
    n = len(races)
    dev_indices, holdout_indices = date_partitions(races, holdout)
    bt, ct = _pairs(races, base_scorer, True), _pairs(races, cand_scorer, True)
    ba, ca = _pairs(races, base_scorer, False), _pairs(races, cand_scorer, False)

    td = _auc_indices(ct, dev_indices) - _auc_indices(bt, dev_indices)
    th = _auc_indices(ct, holdout_indices) - _auc_indices(bt, holdout_indices)
    tci = _boot_ci(bt, ct, holdout_indices)
    ad = _auc_indices(ca, dev_indices) - _auc_indices(ba, dev_indices)
    ah = _auc_indices(ca, holdout_indices) - _auc_indices(ba, holdout_indices)
    aci = _boot_ci(ba, ca, holdout_indices)

    stage4_input = build_evaluation_input(
        domain="au",
        dates=[str(race.get("date") or f"undated-{index:06d}")
               for index, race in enumerate(races)],
        baseline_rows=_stage4_metric_rows(races, base_scorer),
        candidate_rows=_stage4_metric_rows(races, cand_scorer),
        leakage_audit_passed=leakage_audit_passed,
        holdout_fraction=holdout,
        ranking_metrics=(
            "top3_capture_at5",
            "ndcg_at5",
            "top5_pairwise_auc",
        ),
    )
    decision = evaluate_candidate(stage4_input)
    ship = decision["verdict"] in {"PRIMARY_WIN", "RANKING_WIN"}
    why = str(decision["reason"])

    counts = {}
    if with_counts:
        b, c = _counts(races, base_scorer), _counts(races, cand_scorer)
        counts = {k: c[k] - b[k] for k in c if k in b}
    return Verdict(
        label, n, ship, why, td, th, tci, ad, ah, aci, counts,
        decision["verdict"], decision.get("detail") or {},
    )


def main():
    ap = argparse.ArgumentParser(description="AU Wong Choi 統一評估")
    ap.add_argument("--data", required=True, help="leaves dump JSON")
    ap.add_argument("--swap-leaf", action="append", default=[],
                    help="LEAF=VALUE，把某個 leaf 設成常數（用嚟量佢貢獻）")
    ap.add_argument("--holdout", type=float, default=HOLDOUT)
    ap.add_argument("--matrix-weights",
                    help="JSON weight candidate; generated elsewhere, judged only here")
    ap.add_argument("--wet-scale", type=float,
                    help="Candidate multiplier for the existing wet overlay")
    ap.add_argument("--output-json", help="Write the canonical report/verdicts")
    ap.add_argument(
        "--leakage-audit-passed",
        action="store_true",
        help="Confirm the candidate's separate point-in-time leakage audit passed",
    )
    args = ap.parse_args()

    races = load_races(args.data)
    print(f"{len(races)} 場 · Stage 4 v2 = Gold/Good primary + ranking evidence\n")
    report = {"baseline": baseline_report(races, args.holdout), "verdicts": []}
    has_candidate = bool(args.swap_leaf or args.matrix_weights or args.wet_scale is not None)
    if not has_candidate:
        base = report["baseline"]
        auc = base["auc"]
        print(
            f"現行基準：頭 {TOP_K} 位 AUC  all {auc['top_k_all']:.4f} · "
            f"dev {auc['top_k_development']:.4f} · "
            f"holdout {auc['top_k_terminal']:.4f}"
        )
        print(
            f"現行基準：全場 AUC       all {auc['all_field_all']:.4f} · "
            f"dev {auc['all_field_development']:.4f} · "
            f"holdout {auc['all_field_terminal']:.4f}"
        )
        design = base["design"]
        print(
            f"切分：dev {design['development_races']} 場 · "
            f"holdout {design['terminal_holdout_races']} 場 "
            f"（尾 {design['holdout_fraction_by_whole_date']:.0%} **日期**，"
            f"實際佔 {design['holdout_share_of_races']:.1%} 場次）"
        )
        fs = base["field_size"]
        print(
            f"平均馬群：dev {fs['development_mean']:.2f} · "
            f"holdout {fs['terminal_mean']:.2f}"
            + ("   ⚠️ 差距 >0.5，pooled 場數指標唔可比"
               if abs(fs["development_mean"] - fs["terminal_mean"]) > 0.5 else "")
        )
        for label, counts in base["metrics"].items():
            print(
                f"場數指標 {label:<7} "
                + " · ".join(f"{key} {value:.2f}%" for key, value in counts.items())
            )
        # 分層 —— pooled 數字會被馬群組成變化冒充成模型變化，所以一定要一齊出
        print("\n馬群分層（Gold / Good位 / Pass）")
        for label in ("development", "terminal"):
            buckets = base["metrics_by_field"].get(label) or {}
            if not buckets:
                continue
            print(f"  {label}")
            for bucket, counts in buckets.items():
                print(
                    f"    馬群 {bucket:<6} {counts['races']:>4} 場   "
                    f"gold {counts.get('gold', 0):5.2f}% · "
                    f"good_positional {counts.get('good_positional', 0):5.2f}% · "
                    f"pass {counts.get('pass', 0):5.2f}%"
                )
        if args.output_json:
            Path(args.output_json).write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        return 0
    for spec in args.swap_leaf:
        leaf, _, val = spec.partition("=")
        v = float(val)
        verdict = compare(
            races,
            default_scorer,
            configured_scorer(leaf_overrides={leaf: v}),
            label=f"{leaf} 設成常數 {v:g}",
            holdout=args.holdout,
            leakage_audit_passed=args.leakage_audit_passed,
        )
        report["verdicts"].append(verdict_dict(verdict))
        print(verdict)
        print()
    if args.matrix_weights:
        weights = json.loads(Path(args.matrix_weights).read_text(encoding="utf-8"))
        verdict = compare(
            races,
            default_scorer,
            configured_scorer(weights=weights),
            label=f"matrix weights: {Path(args.matrix_weights).name}",
            holdout=args.holdout,
            leakage_audit_passed=args.leakage_audit_passed,
        )
        report["verdicts"].append(verdict_dict(verdict))
        print(verdict)
        print()
    if args.wet_scale is not None:
        verdict = compare(
            races,
            default_scorer,
            configured_scorer(wet_scale=args.wet_scale),
            label=f"wet overlay ×{args.wet_scale:g}",
            holdout=args.holdout,
            leakage_audit_passed=args.leakage_audit_passed,
        )
        report["verdicts"].append(verdict_dict(verdict))
        print(verdict)
        print()
    if args.output_json:
        Path(args.output_json).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
