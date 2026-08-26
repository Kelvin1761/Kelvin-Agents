#!/usr/bin/env python3
"""AU 維度矩陣離線重新配權（2026-08-01，第二次）。

點解可以離線做：
    ability = Σ_k  round(clip(60 + (clip(60 + Σ_i inner_i·(leaf_i−60)) − 60)·gain_k), 2) · w_k
              + wet_form
係**對 leaf 分線性**嘅，所以一份評好分嘅 dataset 就可以評估任何 (gain, weight)
組合，唔使重跑引擎。`verify` 會先證明呢個 replica 同真引擎逐匹一致，
未 verify 過就唔好信任何搜索結果。

⚠️ 一定要行 `map_features_to_matrix_scores` 嗰條路（gain 同 weight 一齊食落
排名）。之前有一次量度漏咗 `MATRIX_DISPLAY_GAINS`，直接得出相反結論。

紀律：dev 85% / 未碰過 holdout 15%（依時間排序），dev 內部再切 5 個時間 fold
做閘。**唔喺 holdout 揀參數。**取閘後候選嘅逐維度中位數（共識），唔取 argmax
—— argmax 係教科書級 overfit。

呢個工具取代咗 `au_matrix_weight_search.py` / `au_clean_7d_weight_search.py` /
`au_weight_improvement_search.py` —— 嗰幾個係 coordinate descent／argmax，實測
會 overfit（dev good_pos +3.80 但 holdout 舊 any-one 指標 −5.61）。要改權重就用呢個。

用法：
    python3 au_dump_engine_leaves.py --out /tmp/leaves.json      # 建 dataset
    python3 au_matrix_refit.py verify      --data /tmp/leaves.json   # 先驗 replica
    python3 au_matrix_refit.py gains       --data /tmp/leaves.json   # 重推 display gain
    python3 au_matrix_refit.py refit       --data /tmp/leaves.json   # 搜索 + 共識
    python3 au_matrix_refit.py walkforward --data /tmp/leaves.json   # 滾動窗口驗證
    python3 au_matrix_refit.py compare     --data /tmp/leaves.json --weights w.json

唯讀，唔會寫任何 Logic.json。
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR.parents[2] / "shared_racing"))

from eval_metrics import race_metrics, summarize_races  # noqa: E402
from au_racing_engine.matrix_mapper import (  # noqa: E402
    MATRIX_DISPLAY_GAINS, MATRIX_DISPLAY_TARGET_SD, MATRIX_FORMULAS,
    map_features_to_matrix_scores)
from au_racing_engine.scoring import MATRIX_ABILITY_SCALE, MATRIX_WEIGHTS  # noqa: E402

HERE = Path.cwd()
HOLDOUT = 0.15
FOLDS = 5
# form_line 出廠權重 0（退役維度），搜索空間同另一條線一致，維持 6 個維度。
DIMS = ("stability", "pace_perf", "race_shape", "jockey_trainer", "class_weight", "track")
KEYS = ("gold", "good_pos", "pass", "champ", "winT3", "t3prec", "mrr",
        "blowout", "compet", "ndcg5")
# 目標函數：九項 pp 指標嘅平均（blowout 反號）。刻意同時涵蓋
# 上名（good_pos / pass / t3prec）、贏馬（champ / winT3 / mrr）同排序質素
# （gold / ndcg5 / blowout），唔畀搜索用上名覆蓋率去買贏馬命中率。
OBJ_PRESETS = {
    # 均衡（預設）：上名、贏馬、排序質素各佔一份，唔畀搜索用一邊買另一邊
    "balanced": ("gold", "good_pos", "pass", "champ", "winT3", "t3prec", "mrr",
                 "ndcg5", "blowout"),
    # 只計上名（本 project 嘅 KPI）
    "place": ("gold", "good_pos", "pass", "t3prec"),
    # 只計贏馬
    "win": ("champ", "winT3", "mrr"),
}
# 2026-08-23：預設由 `balanced` 改為 `place`。
# 理由（用戶決定，已記入 docs/model-evaluation-contract.md）：本 project 嘅 KPI
# 係**上名捕捉**，唔係贏馬。`balanced` 會令搜索用 `champ` / `winT3` / `mrr`
# 買 `pass` / `t3prec`，即係用一個我哋唔追嘅目標換走一個我哋追嘅目標。
# `place` = (gold, good_pos, pass, t3prec) —— 四個全部係上名指標。
# 要對回歷史紀錄（2026-08-01 / 08-03 / 08-08 三次重 fit 都係 balanced）就
# 明確傳 `--obj balanced`。
OBJ_KEYS = OBJ_PRESETS["place"]
OBJ_SIGN = {}


def set_objective(name):
    global OBJ_KEYS, OBJ_SIGN
    OBJ_KEYS = OBJ_PRESETS[name]
    OBJ_SIGN = {k: (-1.0 if k == "blowout" else 1.0) for k in OBJ_KEYS}


set_objective("balanced")


# ── dataset ────────────────────────────────────────────────────────────────
class Dataset:
    """把 dump 拍成 numpy，並預先計好『未食 gain』嘅維度分。"""

    def __init__(self, path: Path):
        races = json.loads(path.read_text(encoding="utf-8"))["races"]
        # Accept both the compact leaves dump and the richer current-runtime
        # audit snapshot.  Keeping one evaluator removes a recurring source of
        # stale-schema crashes and cross-corpus metric comparisons.
        self.races = [self._normalise_race(race) for race in races]
        self.slices, self.rows = [], []
        start = 0
        for race in self.races:
            n = len(race["rows"])
            self.slices.append((start, start + n))
            start += n
            self.rows.extend(race["rows"])
        self.n = start
        self.wet = np.array([float(r["wet"] or 0.0) for r in self.rows])
        self.proven_class = np.array(
            [float(r.get("proven_class") or 0.0) for r in self.rows]
        )
        self.engine_ability = np.array([float(r["ability"]) for r in self.rows])
        # raw[k] = clip(60 + Σ inner·(leaf−60))，即係食 gain 之前嘅維度分。
        # 佢淨係睇 leaf，同 gain / weight 完全無關，所以可以預先算死。
        self.raw = {}
        for key, comps in MATRIX_FORMULAS.items():
            acc = np.full(self.n, 60.0)
            for leaf, w in comps:
                acc += w * np.clip(
                    np.array([float(r["features"].get(leaf, 60.0)) for r in self.rows]),
                    0.0, 100.0) - w * 60.0
            self.raw[key] = np.clip(acc, 0.0, 100.0)

    @staticmethod
    def _normalise_race(race):
        metadata = race.get("metadata") or {}
        field_size = race.get("field") or metadata.get("field_size")
        rows = []
        for row in race["rows"]:
            rows.append({
                **row,
                "n": row.get("n", row.get("horse_number")),
                "name": row.get("name", row.get("horse_name", "")),
                "pos": row.get("pos", row.get("actual_pos")),
                "sp": row.get("sp", row.get("result_sp_label")),
                "features": row.get("features", row.get("feature_scores", {})),
                "wet": row.get("wet", row.get("wet_form_feature", 0.0)),
                "proven_class": row.get(
                    "proven_class", row.get("proven_class_feature", 0.0)
                ),
                "ability": row.get("ability", row.get("score")),
            })
        return {
            **race,
            "date": race.get("date", metadata.get("date")),
            "race": race.get("race", metadata.get("race_number")),
            "field": int(field_size or len(rows)),
            "rows": rows,
        }

    def dim_matrix(self, gains):
        """食完 gain、clip、2dp 之後嘅維度分 —— 只要 gain 唔變就可以重用。"""
        cols = []
        for key in DIMS:
            g = float(gains.get(key, 1.0))
            cols.append(np.round(np.clip(60.0 + (self.raw[key] - 60.0) * g, 0.0, 100.0), 2))
        return np.column_stack(cols)

    def ability(self, mx, weights, wet_scale=1.0):
        w = np.array([float(weights.get(k, 0.0)) for k in DIMS])
        # 跟 `engine_core` 條 ability 公式（2026-08-26 加咗 MATRIX_ABILITY_SCALE）。
        # 候選權重會自己歸一，所以同一個尺對 baseline 同候選都啱。
        core = np.round(mx @ w, 4)
        return (60.0 + (core - 60.0) / MATRIX_ABILITY_SCALE
                + self.wet * wet_scale + self.proven_class)

    def evaluate(self, ability, lo=0, hi=None):
        hi = len(self.slices) if hi is None else hi
        out = []
        for idx in range(lo, hi):
            a, b = self.slices[idx]
            race = self.races[idx]
            nums = [r["n"] for r in race["rows"]]
            pos = {r["n"]: r["pos"] for r in race["rows"]}
            order = sorted(range(a, b), key=lambda i: (-ability[i], nums[i - a]))
            picks = [nums[i - a] for i in order]
            top3 = [n for n, p in pos.items() if p <= 3]
            win = [n for n, p in pos.items() if p == 1]
            out.append(race_metrics(picks, top3, winner=win[0] if win else None,
                                    actual_pos=pos, field_size=race["field"]))
        return digest(summarize_races(out))


def digest(s):
    r, c = s["rates"], s["competitiveness"]
    return {"gold": 100 * r["gold"], "good_pos": 100 * r["good_positional"],
            "pass": 100 * r["pass"],
            "champ": 100 * r["champion"], "winT3": 100 * r["winner_in_top3"],
            "t3prec": 100 * s["top3_precision"], "mrr": 100 * s["mrr"],
            "blowout": 100 * c["top_pick_blowout"]["rate"],
            "compet": 100 * c["top_pick_competitive"]["rate"],
            "ndcg5": 100 * c["mean_ndcg_at5"]}


def objective(d):
    return sum(OBJ_SIGN[k] * d[k] for k in OBJ_KEYS) / len(OBJ_KEYS)


def fold_bounds(n_dev):
    edges = [round(n_dev * i / FOLDS) for i in range(FOLDS + 1)]
    return list(zip(edges[:-1], edges[1:]))


def table(title, base, cand):
    print(f"\n{title}")
    print(f"{'':10}" + "".join(f"{k:>12}" for k in KEYS))
    print(f"{'baseline':10}" + "".join(f"{base[k]:>12.2f}" for k in KEYS))
    print(f"{'candidate':10}" + "".join(f"{cand[k]:>12.2f}" for k in KEYS))
    print(f"{'delta':10}" + "".join(f"{cand[k] - base[k]:>+12.2f}" for k in KEYS))


# ── subcommands ────────────────────────────────────────────────────────────
def cmd_verify(ds, _args):
    """證明 replica == 真引擎，先至可以信之後嘅搜索。"""
    mine = ds.ability(ds.dim_matrix(MATRIX_DISPLAY_GAINS), MATRIX_WEIGHTS)
    # 對照組：真正行一次 map_features_to_matrix_scores（唔用 numpy 捷徑）
    slow = np.array([
        60.0
        + (round(sum(map_features_to_matrix_scores(r["features"])[k] * MATRIX_WEIGHTS[k]
                     for k in MATRIX_WEIGHTS), 4) - 60.0) / MATRIX_ABILITY_SCALE
        + float(r["wet"] or 0.0)
        + float(r.get("proven_class") or 0.0)
        for r in ds.rows])
    for label, ref in (("真引擎存檔 ability", ds.engine_ability),
                       ("map_features_to_matrix_scores", slow)):
        diff = np.abs(mine - ref)
        print(f"{label:34} n={len(ref)}  max|Δ|={diff.max():.6f}  "
              f"mean|Δ|={diff.mean():.8f}  >0.01: {(diff > 0.01).sum()}")


def cmd_gains(ds, _args):
    """按現行 leaf 分佈重新推導 display gain。

    gain = min(TARGET_SD / 實測SD, 令實測極值仍然落喺 1..99 之內嘅最大 gain)
    headroom 嗰半好緊要：唔封住就會一堆馬撞 0/100 造成假平手。
    """
    print(f"TARGET_SD = {MATRIX_DISPLAY_TARGET_SD}")
    print(f"{'維度':16}{'SD':>8}{'min':>8}{'max':>8}{'SD gain':>10}"
          f"{'headroom':>10}{'新 gain':>10}{'現行':>10}{'Δ%':>9}")
    new = {}
    for key in MATRIX_FORMULAS:
        raw = ds.raw[key]
        sd = float(raw.std(ddof=1))
        lo, hi = float(raw.min()), float(raw.max())
        g_sd = MATRIX_DISPLAY_TARGET_SD / sd if sd > 1e-9 else 1.0
        caps = [g_sd]
        if lo < 60.0:
            caps.append(59.0 / (60.0 - lo))
        if hi > 60.0:
            caps.append(39.0 / (hi - 60.0))
        g = min(caps)
        new[key] = round(g, 4)
        cur = MATRIX_DISPLAY_GAINS.get(key, 1.0)
        head = min([c for c in caps[1:]] or [float("inf")])
        print(f"{key:16}{sd:>8.2f}{lo:>8.1f}{hi:>8.1f}{g_sd:>10.4f}"
              f"{head:>10.4f}{g:>10.4f}{cur:>10.4f}{100 * (g / cur - 1):>+8.1f}%")
    print("\nMATRIX_DISPLAY_GAINS = " + json.dumps(new, indent=4))
    (HERE / "au_refit_gains.json").write_text(json.dumps(new), encoding="utf-8")
    print(f"→ {HERE / 'au_refit_gains.json'}")

    # gain 一改，權重要同步除返個 gain，否則等於偷偷 re-weight。
    equiv = {k: MATRIX_WEIGHTS[k] * MATRIX_DISPLAY_GAINS.get(k, 1.0) / new.get(k, 1.0)
             for k in MATRIX_WEIGHTS}
    total = sum(equiv.values())
    equiv = {k: round(v / total, 5) for k, v in equiv.items()}
    print("\n等價權重（新 gain 之下複製現行排名）：")
    print("MATRIX_WEIGHTS = " + json.dumps(equiv))
    (HERE / "au_refit_equiv_weights.json").write_text(json.dumps(equiv), encoding="utf-8")


def dirichlet(rng, alpha):
    draw = [rng.gammavariate(a, 1.0) for a in alpha]
    total = sum(draw) or 1.0
    return [d / total for d in draw]


def fit_consensus(ds, mx, base_w, train_end, seed, n, min_folds, quiet=True):
    """喺 races[0:train_end] 上面 fit 一組共識權重。完全唔會掂 train_end 之後嘅嘢。"""
    folds = fold_bounds(train_end)

    def obj_of(weights, lo, hi):
        return objective(ds.evaluate(ds.ability(mx, weights), lo, hi))

    base_dev = obj_of(base_w, 0, train_end)
    base_folds = [obj_of(base_w, lo, hi) for lo, hi in folds]
    rng = random.Random(seed)
    shipped = [max(base_w.get(k, 0.0), 1e-4) for k in DIMS]
    gated = []
    for i in range(n):
        alpha = [1.0] * len(DIMS) if i % 2 == 0 else [max(s * 25.0, 0.35) for s in shipped]
        vec = dirichlet(rng, alpha)
        weights = dict(zip(DIMS, vec))
        if obj_of(weights, 0, train_end) <= base_dev:
            continue
        if sum(1 for (lo, hi), b in zip(folds, base_folds)
               if obj_of(weights, lo, hi) >= b) >= min_folds:
            gated.append(vec)
    if not gated:
        return None, 0
    cons = {k: statistics.median(v[i] for v in gated) for i, k in enumerate(DIMS)}
    total = sum(cons.values())
    return {k: v / total for k, v in cons.items()}, len(gated)


def cmd_walkforward(ds, args):
    """滾動窗口：每個窗口只用**之前**嘅場次 fit，再喺之後嗰段從未見過嘅場次評估。

    單一個 15% holdout 得 107 場，一場就係 0.93pp —— 分唔清真訊號同噪音。
    呢度改為每次都用一段全新嘅未來場次去驗，總驗證量係 holdout 嘅四倍幾。
    """
    gains = json.loads(Path(args.gains).read_text()) if args.gains else MATRIX_DISPLAY_GAINS
    base_w = json.loads(Path(args.baseline_weights).read_text()) if args.baseline_weights \
        else MATRIX_WEIGHTS
    mx = ds.dim_matrix(gains)
    n_races = len(ds.races)
    starts = [args.wf_start + i * args.wf_window
              for i in range((n_races - args.wf_start) // args.wf_window)]
    print(f"races {n_races}  首個訓練段 {args.wf_start} 場  窗口 {args.wf_window} 場  "
          f"共 {len(starts)} 個窗口  總驗證 {len(starts) * args.wf_window} 場")

    agg_base, agg_cand, rows = [], [], []
    for t in starts:
        hi = min(t + args.wf_window, n_races)
        cons, n_gated = fit_consensus(ds, mx, base_w, t, args.seed, args.n, args.min_folds)
        if cons is None:
            print(f"  訓練 0..{t}  →  冇候選過閘，跳過")
            continue
        b = ds.evaluate(ds.ability(mx, base_w), t, hi)
        c = ds.evaluate(ds.ability(mx, cons), t, hi)
        agg_base.append(b)
        agg_cand.append(c)
        rows.append((t, hi, n_gated, cons, b, c))
        print(f"\n── 訓練 0..{t}（{t} 場，{n_gated} 條過閘）→ 驗證 {t}..{hi}（{hi - t} 場）")
        print("   共識 " + json.dumps({k: round(v, 4) for k, v in cons.items()}))
        print(f"   {'':8}" + "".join(f"{k:>11}" for k in KEYS))
        print(f"   {'delta':8}" + "".join(f"{c[k] - b[k]:>+11.2f}" for k in KEYS))

    if not rows:
        return
    print(f"\n===== {len(rows)} 個窗口嘅平均（每個窗口都係未見過嘅未來場次）=====")
    print(f"{'':10}" + "".join(f"{k:>12}" for k in KEYS))
    mean_b = {k: sum(d[k] for d in agg_base) / len(agg_base) for k in KEYS}
    mean_c = {k: sum(d[k] for d in agg_cand) / len(agg_cand) for k in KEYS}
    print(f"{'baseline':10}" + "".join(f"{mean_b[k]:>12.2f}" for k in KEYS))
    print(f"{'candidate':10}" + "".join(f"{mean_c[k]:>12.2f}" for k in KEYS))
    print(f"{'delta':10}" + "".join(f"{mean_c[k] - mean_b[k]:>+12.2f}" for k in KEYS))
    wins = sum(1 for b, c in zip(agg_base, agg_cand) if objective(c) > objective(b))
    print(f"\nOBJ 贏嘅窗口：{wins}/{len(rows)}")
    pooled = {k: statistics.median(r[3][k] for r in rows) for k in DIMS}
    total = sum(pooled.values())
    pooled = {k: round(v / total, 5) for k, v in pooled.items()}
    print("跨窗口共識（逐維度中位數）：" + json.dumps(pooled))
    (HERE / "au_refit_walkforward.json").write_text(json.dumps(pooled), encoding="utf-8")


def cmd_refit(ds, args):
    gains = json.loads(Path(args.gains).read_text()) if args.gains else MATRIX_DISPLAY_GAINS
    base_w = json.loads(Path(args.baseline_weights).read_text()) if args.baseline_weights \
        else MATRIX_WEIGHTS
    mx = ds.dim_matrix(gains)
    n_races = len(ds.races)
    split = int(n_races * (1 - HOLDOUT))
    folds = [(lo, hi) for lo, hi in fold_bounds(split)]
    print(f"races {n_races}  dev {split}  holdout {n_races - split}  "
          f"folds {[hi - lo for lo, hi in folds]}")
    print(f"gains  = {json.dumps({k: gains.get(k, 1.0) for k in DIMS})}")
    print(f"基準權重 = {json.dumps({k: round(base_w.get(k, 0.0), 5) for k in DIMS})}")

    def obj_of(weights, lo, hi):
        return objective(ds.evaluate(ds.ability(mx, weights), lo, hi))

    base_dev = obj_of(base_w, 0, split)
    base_folds = [obj_of(base_w, lo, hi) for lo, hi in folds]
    print(f"\n基準 dev OBJ = {base_dev:.4f}   逐 fold = "
          f"{['%.3f' % v for v in base_folds]}")

    rng = random.Random(args.seed)
    shipped = [max(base_w.get(k, 0.0), 1e-4) for k in DIMS]
    cands = []
    for i in range(args.n):
        # 一半均勻鋪滿單純形（廣度），一半圍住現行權重（深度）。
        alpha = [1.0] * len(DIMS) if i % 2 == 0 else [max(s * 25.0, 0.35) for s in shipped]
        cands.append(dirichlet(rng, alpha))

    beat_dev, gated = 0, []
    for vec in cands:
        weights = dict(zip(DIMS, vec))
        if obj_of(weights, 0, split) <= base_dev:
            continue
        beat_dev += 1
        wins = sum(1 for (lo, hi), b in zip(folds, base_folds)
                   if obj_of(weights, lo, hi) >= b)
        if wins >= args.min_folds:
            gated.append((vec, wins))
    print(f"\n{args.n} 條隨機權重：{beat_dev} 條贏 dev，其中 {len(gated)} 條"
          f"再過 {args.min_folds}/{FOLDS} fold 閘")
    if not gated:
        print("冇候選過閘 —— 現行權重喺呢個目標函數下已經係局部最優。")
        return

    consensus = {k: statistics.median(v[i] for v, _ in gated) for i, k in enumerate(DIMS)}
    total = sum(consensus.values())
    consensus = {k: round(v / total, 5) for k, v in consensus.items()}
    print(f"\n共識權重（{len(gated)} 條過閘候選嘅逐維度中位數，睇 holdout 之前已經定死）：")
    print(json.dumps(consensus))
    (HERE / "au_refit_consensus.json").write_text(json.dumps(consensus), encoding="utf-8")

    # 對照 argmax，示範點解要取中位數
    best = max(gated, key=lambda vc: obj_of(dict(zip(DIMS, vc[0])), 0, split))[0]
    argmax = {k: round(v, 5) for k, v in zip(DIMS, best)}
    (HERE / "au_refit_argmax.json").write_text(json.dumps(argmax), encoding="utf-8")
    print(f"argmax 權重（只作對照，唔會 ship）：{json.dumps(argmax)}")

    for label, cfg in (("共識", consensus), ("argmax", argmax)):
        b_dev = ds.evaluate(ds.ability(mx, base_w), 0, split)
        c_dev = ds.evaluate(ds.ability(mx, cfg), 0, split)
        b_ho = ds.evaluate(ds.ability(mx, base_w), split, n_races)
        c_ho = ds.evaluate(ds.ability(mx, cfg), split, n_races)
        table(f"===== {label}：dev ({split} 場) =====", b_dev, c_dev)
        table(f"===== {label}：holdout ({n_races - split} 場，未碰過) =====", b_ho, c_ho)


def cmd_compare(ds, args):
    """候選 (gains, weights) vs **真正出廠設定**（PF off + 現行權重／gain）。

    搜索過程嘅內部基準未必等於出廠設定 —— 一定要同真 production 比一次。
    """
    prod = ds.evaluate(ds.ability(ds.dim_matrix(MATRIX_DISPLAY_GAINS), MATRIX_WEIGHTS))
    gains = json.loads(Path(args.gains).read_text()) if args.gains else MATRIX_DISPLAY_GAINS
    weights = json.loads(Path(args.weights).read_text())
    n = len(ds.races)
    split = int(n * (1 - HOLDOUT))
    mx = ds.dim_matrix(gains)
    ws = args.wet_scale
    if ws != 1.0:
        print(f"濕地 overlay ×{ws:.4f}（保持佢相對 ability spread 嘅影響力不變）")
    pmx = ds.dim_matrix(MATRIX_DISPLAY_GAINS)
    cand = ds.evaluate(ds.ability(mx, weights, ws))
    table(f"===== 全樣本 {n} 場：候選 vs 出廠 =====", prod, cand)
    table("===== dev =====",
          ds.evaluate(ds.ability(pmx, MATRIX_WEIGHTS), 0, split),
          ds.evaluate(ds.ability(mx, weights, ws), 0, split))
    table("===== holdout（未碰過）=====",
          ds.evaluate(ds.ability(pmx, MATRIX_WEIGHTS), split, n),
          ds.evaluate(ds.ability(mx, weights, ws), split, n))


def main():
    global DIMS
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("verify", "gains", "refit", "compare", "walkforward"))
    ap.add_argument("--data", required=True,
                    help="au_dump_engine_leaves.py 出嘅 dataset")
    ap.add_argument("--gains")
    ap.add_argument("--weights")
    ap.add_argument("--baseline-weights")
    ap.add_argument("--n", type=int, default=3000)
    ap.add_argument("--min-folds", type=int, default=4)
    ap.add_argument("--seed", type=int, default=20260801)
    ap.add_argument("--obj", choices=tuple(OBJ_PRESETS), default="place",
                    help="判決目標。預設 `place`（本 project KPI：上名捕捉）。"
                         "歷史紀錄係 `balanced` 出嘅，要對比就明確傳 balanced。")
    ap.add_argument("--wf-start", type=int, default=250)
    ap.add_argument("--wf-window", type=int, default=92)
    ap.add_argument("--wet-scale", type=float, default=1.0)
    ap.add_argument("--drop-dim", action="append", default=[],
                    help="由排名剔走一個維度，再喺剩低嗰啲重新 fit。"
                         "剷維度唔應該用按比例歸一 —— 嗰個係隨手分，"
                         "唔係量出嚟嘅最優分配。")
    ap.add_argument("--with-form-line", action="store_true",
                    help="把出廠權重 0 嘅 form_line（賽績線）維度加返入搜索空間")
    args = ap.parse_args()
    if args.with_form_line and "form_line" not in DIMS:
        DIMS = DIMS + ("form_line",)
    for _dim in args.drop_dim:
        if _dim in DIMS:
            DIMS = tuple(d for d in DIMS if d != _dim)
            print(f"⚠️  由排名剔走維度：{_dim}　→ 剩低 {len(DIMS)} 個：{', '.join(DIMS)}")
    set_objective(args.obj)
    ds = Dataset(Path(args.data))
    print(f"dataset {args.data}  races {len(ds.races)}  runners {ds.n}  obj={args.obj} {OBJ_KEYS}")
    {"verify": cmd_verify, "gains": cmd_gains, "refit": cmd_refit,
     "compare": cmd_compare, "walkforward": cmd_walkforward}[args.cmd](ds, args)


if __name__ == "__main__":
    main()
