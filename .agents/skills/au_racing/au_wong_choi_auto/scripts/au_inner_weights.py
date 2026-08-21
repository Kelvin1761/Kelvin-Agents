#!/usr/bin/env python3
"""每個維度**內部**嘅 leaf 權重值唔值嗰個份額？

`au_matrix_refit.py` 調嘅係維度之間嘅 `MATRIX_WEIGHTS`。呢個工具調嘅係
`MATRIX_FORMULAS` 入面每個維度**內部**嗰組 leaf 權重 —— 兩件從來冇一齊查過嘅事。

只有三個維度真正有得調：

    stability       form 0.60 / consistency 0.40
    pace_perf       pace_figure 0.759 / sectional 0.194 / trial 0.047
    jockey_trainer  jockey 0.28 / trainer 0.20 / jockey_horse_fit 0.52

`race_shape` / `track` 係單 leaf ×1.0，`form_line` 所屬維度權重 0.000（惰性）。
`class_weight` 係單 leaf 但係 ×0.70 —— 即係一個**收縮**，所以佢個 0.70 本身
就係一個內部權重問題，一齊測。

最可疑嗰個：`jockey_horse_fit_score` 攞 jockey_trainer 過半權重（0.52），
但場內 AUC 只有 0.532，而同維度嘅 jockey 0.600 / trainer 0.605。

⚠️ **內部權重同維度尺度係鎖住嘅。** 維度分 = clip(60 + Σ inner_w·(leaf−60))，
所以由一個散佈細嘅 leaf 移權重去一個散佈大嘅 leaf，就算 inner_w 加埋仍然係 1.0，
個維度嘅 SD 都會變 —— 而 ranking 食 weight × spread。SD 一變，等於偷偷改埋
`MATRIX_WEIGHTS`，個 A/B 就唔乾淨。所以每個候選都報 SD 變化，SD 動得多嘅
唔可以當「純內部權重效果」讀。

紀律（同 `au_matrix_refit.py` 一致）：
  * dev 85% / holdout 15% **依時間**切，holdout 唔准睇住調
  * dev 內 5 fold 非退步閘
  * **consensus 而唔係 argmax** —— 過閘候選逐個維度取中位數。
    argmax 喺呢個語料已經三次重現同一個 overfit（見 REFIT_PLAN.md）。
  * 主指標 = Gold + Good（Kelvin 2026-08-03 定嘅優先），t3prec / winT3 做守門
"""
from __future__ import annotations

import argparse
import itertools
import json
import statistics
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR.parents[2] / "shared_racing"))

from au_racing_engine import matrix_mapper  # noqa: E402
from eval_metrics import race_metrics, summarize_races  # noqa: E402
from au_racing_engine.scoring import MATRIX_WEIGHTS  # noqa: E402

KEYS = ("gold", "good_positional", "pass", "champion", "winner_in_top3")
# Kelvin 2026-08-03：Gold + Good 係要追嘅。t3prec / winT3 做守門 ——
# 唔准為咗 Gold 而蝕咗整體命中。
PRIORITY = ("gold", "good_positional")
GUARD = ("t3prec", "winner_in_top3")


def evaluate(races, formulas=None, weights=None):
    """→ 指標 dict。`formulas` patch `MATRIX_FORMULAS`，其餘一律用現行值。"""
    saved = matrix_mapper.MATRIX_FORMULAS
    if formulas is not None:
        matrix_mapper.MATRIX_FORMULAS = formulas
    w = weights or MATRIX_WEIGHTS
    try:
        rows = []
        for r in races:
            scored = []
            for row in r["rows"]:
                m = matrix_mapper.map_features_to_matrix_scores(row["features"])
                ability = sum(m.get(k, 60.0) * ww for k, ww in w.items()) + row["wet"]
                scored.append((ability, row["name"], row["pos"]))
            scored.sort(key=lambda x: -x[0])
            picks = [s[1] for s in scored]
            pos = {s[1]: s[2] for s in scored}
            top3 = {h for h, p in pos.items() if p <= 3}
            win = next((h for h, p in pos.items() if p == 1), None)
            if not top3 or win is None:
                continue
            rows.append(race_metrics(picks, top3, winner=win, actual_pos=pos,
                                     field_size=max(pos.values())))
    finally:
        matrix_mapper.MATRIX_FORMULAS = saved
    if not rows:
        return None
    c = summarize_races(rows)["counts"]
    n = len(rows)
    out = {k: 100.0 * c[k] / n for k in KEYS}
    out["gold_strict"] = 100.0 * c["gold_strict"] / n
    out["t3prec"] = 100.0 * sum(x["hits"] for x in rows) / \
        sum(min(3, len(x["picks"])) for x in rows)
    return out


def dimension_sd(races, dim, formulas):
    """一個維度喺全語料嘅標準差 —— 用嚟捉「SD 偷偷變咗」嗰個 confound。"""
    saved = matrix_mapper.MATRIX_FORMULAS
    matrix_mapper.MATRIX_FORMULAS = formulas
    try:
        vals = [matrix_mapper.map_features_to_matrix_scores(row["features"]).get(dim, 60.0)
                for r in races for row in r["rows"]]
    finally:
        matrix_mapper.MATRIX_FORMULAS = saved
    return statistics.pstdev(vals) if len(vals) > 1 else 0.0


def patch(dim, weights_tuple):
    """→ 一份 MATRIX_FORMULAS，只換咗 `dim` 嗰組內部權重。"""
    out = dict(matrix_mapper.MATRIX_FORMULAS)
    out[dim] = tuple(weights_tuple)
    return out


def normalise_races(payload):
    """Accept compact leaves and the richer current-runtime audit snapshot."""
    races = []
    for race in payload["races"]:
        metadata = race.get("metadata") or {}
        rows = []
        for row in race["rows"]:
            rows.append({
                **row,
                "name": row.get("name", row.get("horse_name", "")),
                "n": row.get("n", row.get("horse_number", 999)),
                "pos": row.get("pos", row.get("actual_pos")),
                "features": row.get("features", row.get("feature_scores", {})),
                "wet": row.get("wet", row.get("wet_form_feature", 0.0)),
            })
        races.append({
            **race,
            "date": race.get("date", metadata.get("date")),
            "field": int(race.get("field") or metadata.get("field_size") or len(rows)),
            "rows": rows,
        })
    return races


def simplex(leaves, step, total=1.0):
    """所有加埋等於 `total` 嘅權重組合（`step` 粒度）。"""
    n = len(leaves)
    steps = int(round(total / step))
    for combo in itertools.product(range(steps + 1), repeat=n - 1):
        rest = steps - sum(combo)
        if rest < 0:
            continue
        yield tuple(zip(leaves, [c * step for c in combo] + [rest * step]))


def candidates(dim, step):
    cur = matrix_mapper.MATRIX_FORMULAS[dim]
    leaves = [k for k, _ in cur]
    total = sum(w for _, w in cur)
    return list(simplex(leaves, step, total))


def main():
    ap = argparse.ArgumentParser(description="維度內部 leaf 權重審查")
    ap.add_argument("--data", required=True, help="au_dump_sb_leaves.py 出嘅 JSON")
    ap.add_argument("--dim", action="append",
                    help="限定維度（可重複）；預設全部多-leaf 維度")
    ap.add_argument("--step", type=float, default=0.05)
    ap.add_argument("--holdout", type=float, default=0.15)
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--sd-tol", type=float, default=0.15,
                    help="維度 SD 相對變化上限；超過就標記 confound")
    ap.add_argument("--json", help="把 consensus 寫落呢個檔")
    args = ap.parse_args()

    races = normalise_races(json.loads(Path(args.data).read_text()))
    cut = int(len(races) * (1 - args.holdout))
    dev, hold = races[:cut], races[cut:]
    fold = len(dev) // args.folds
    folds = [dev[i * fold:(i + 1) * fold] if i < args.folds - 1 else dev[i * fold:]
             for i in range(args.folds)]

    dims = args.dim or [d for d, f in matrix_mapper.MATRIX_FORMULAS.items()
                        if len(f) > 1 and MATRIX_WEIGHTS.get(d, 0) > 0]
    print(f"{len(races)} 場（dev {len(dev)} / holdout {len(hold)}）")
    print(f"維度：{', '.join(dims)}\n")

    base_dev = evaluate(dev)
    base_hold = evaluate(hold)
    base_folds = [evaluate(f) for f in folds]
    consensus = {}

    for dim in dims:
        cur = matrix_mapper.MATRIX_FORMULAS[dim]
        base_sd = dimension_sd(races, dim, matrix_mapper.MATRIX_FORMULAS)
        cands = candidates(dim, args.step)
        print(f"── {dim} ──  現行 " +
              " / ".join(f"{k.replace('_score','')} {w:.3f}" for k, w in cur) +
              f"   SD {base_sd:.2f}   候選 {len(cands)}")

        gated = []
        for cand in cands:
            if all(abs(w - cw) < 1e-9 for (_, w), (_, cw) in zip(cand, cur)):
                continue
            F = patch(dim, cand)
            # 閘 1：dev 主指標唔准跌，守門指標唔准跌
            d = evaluate(dev, F)
            if any(d[k] - base_dev[k] < -0.001 for k in PRIORITY + GUARD):
                continue
            # 閘 2：5 fold 非退步（守門指標）
            ok = sum(1 for f, b in zip(folds, base_folds)
                     if (c := evaluate(f, F)) and
                     all(c[k] - b[k] >= -0.01 for k in GUARD))
            if ok < args.folds:
                continue
            sd = dimension_sd(races, dim, F)
            gated.append({"w": cand, "dev": d, "sd": sd,
                          "sd_rel": (sd - base_sd) / base_sd if base_sd else 0.0,
                          "folds": ok})

        if not gated:
            print("   冇候選過 dev + 5-fold 閘 —— 現行內部權重守得住\n")
            continue

        print(f"   {len(gated)} 個過閘。取逐 leaf 中位數（consensus，唔係 argmax）：")
        med = {}
        for i, (leaf, _) in enumerate(cur):
            med[leaf] = statistics.median(g["w"][i][1] for g in gated)
        s = sum(med.values()) or 1.0
        tot = sum(w for _, w in cur)
        cons = tuple((k, v / s * tot) for k, v in med.items())
        F = patch(dim, cons)
        cd, ch = evaluate(dev, F), evaluate(hold, F)
        sd = dimension_sd(races, dim, F)
        rel = (sd - base_sd) / base_sd if base_sd else 0.0
        print("   " + " / ".join(f"{k.replace('_score','')} {w:.3f}" for k, w in cons))
        print(f"   維度 SD {base_sd:.2f} → {sd:.2f}（{rel:+.1%}）" +
              ("  ⚠️ 超出容差，唔可以當純內部權重效果讀" if abs(rel) > args.sd_tol else ""))
        print(f"   {'':10}{'Gold':>9}{'Good位':>9}{'Pass':>8}{'champ':>8}{'winT3':>8}{'t3prec':>9}")
        for nm, c, b in (("dev", cd, base_dev), ("holdout", ch, base_hold)):
            print(f"   {nm:10}" + "".join(
                f"{c[k] - b[k]:>+9.2f}" if k != "pass" else f"{c[k] - b[k]:>+8.2f}"
                for k in ("gold", "good_positional", "pass", "champion",
                          "winner_in_top3", "t3prec")))
        hold_ok = all(ch[k] - base_hold[k] >= -0.001 for k in GUARD)
        print(f"   holdout 守門：{'✅ 冇跌' if hold_ok else '❌ 有跌 —— 唔 ship'}")

        # ── SD 對照組：呢個收益係「分配改對咗」定係「維度食多咗影響力」？──────
        #
        # 維度 SD 升 rel% 之後，喺同一組 MATRIX_WEIGHTS 之下佢嘅實際影響力
        # 就升咗 rel% —— ranking 食 weight × spread。所以「新內部權重贏」
        # 有兩個可能解釋，而上面嗰個表分唔開佢哋。
        #
        # 對照組 = **保留現行內部權重**，但把呢個維度嘅 MATRIX_WEIGHTS 放大
        # 同等幅度（其餘按比例縮返，令總和不變）。咁樣對照組同候選有一樣嘅
        # 影響力、唔一樣嘅分配。
        #
        #   對照組 ≈ 候選  → 收益係影響力，唔係分配。呢個要行 au_matrix_refit，
        #                    而佢已經搵過維度權重，即係呢度冇新嘢。
        #   候選 > 對照組  → 分配真係改對咗，值得 ship。
        if abs(rel) > 0.02:
            scaled = {k: (v * (1.0 + rel) if k == dim else v)
                      for k, v in MATRIX_WEIGHTS.items()}
            s2 = sum(scaled.values())
            scaled = {k: v / s2 for k, v in scaled.items()}
            kd = evaluate(dev, None, scaled)
            kh = evaluate(hold, None, scaled)
            print(f"   ── SD 對照組（現行分配，維度權重 ×{1 + rel:.3f}）──")
            for nm, c, b in (("dev", kd, base_dev), ("holdout", kh, base_hold)):
                print(f"   {nm:10}" + "".join(
                    f"{c[k] - b[k]:>+9.2f}" if k != "pass" else f"{c[k] - b[k]:>+8.2f}"
                    for k in ("gold", "good_positional", "pass", "champion",
                              "winner_in_top3", "t3prec")))
            beats = sum(1 for k in PRIORITY + GUARD if cd[k] - kd[k] > 0.001)
            loses = sum(1 for k in PRIORITY + GUARD if cd[k] - kd[k] < -0.001)
            verdict = ("分配真係改對咗" if beats > loses else
                       "收益主要係影響力，唔係分配" if loses > beats else "分唔開")
            print(f"   dev 候選 vs 對照組：{beats}↑/{loses}↓ → **{verdict}**")
            if loses >= beats:
                hold_ok = False
        print()
        if hold_ok:
            consensus[dim] = [[k, round(w, 6)] for k, w in cons]

    if consensus and args.json:
        Path(args.json).write_text(json.dumps(consensus, indent=1))
        print(f"consensus → {args.json}")
    if not consensus:
        print("結論：三個維度嘅內部權重全部守得住，冇一個候選過埋 holdout。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
