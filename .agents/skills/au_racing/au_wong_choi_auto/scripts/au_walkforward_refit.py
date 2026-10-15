#!/usr/bin/env python3
"""AU walk-forward refit 預測產生器 —— 合約 §8「兩邊都 refit」嘅 B arm。

由一份 `au_dump_engine_leaves.py` dump 出發，逐場輸出兩個分數：

    ability_live   現行 MATRIX_WEIGHTS（A arm）
    ability_refit  每個日期窗用「之前日期」fit 出嚟嘅共識權重（B arm）

兩個分數都用 production 嘅 `map_features_to_matrix_scores` +
`compose_matrix_score` + overlay 次序同 4dp 捨入重算（`exact_score`）。
numpy 只用嚟**提案**（篩 Dirichlet draws）；共識權重會再用 production
算術重檢一次，輸出亦全部係 production 算術，唔係 numpy 捷徑。

程序沿用 EXP-20261015-02（`scratch/au_trial_cutoff_refit_20261015.py`）：
乾淨語料 2026-08-05 起、warmup 30 個賽日、每 7 個賽日一個窗（尾窗保留）、
256 個 Dirichlet draws（seed 7，一半 broad 一半近現行權重）、place 目標、
五個日期塊至少四塊不負、逐維度中位數共識、中位數再過閘、唔過就 fallback
現行權重。**唔取 argmax。**

`procedure_hash` 係程序設定（連本檔 source）嘅 content hash。§8 判決器
`evaluate_with_refit_arms` 要求 B0 同 B1 嘅 hash 一樣 —— baseline 同
candidate 兩份 dump 用同一個 commit 嘅本工具跑，hash 就一樣。

用法：
    python3 au_dump_engine_leaves.py --out leaves.json
    python3 au_walkforward_refit.py predict --data leaves.json --out wf.json
    python3 au_walkforward_refit.py stale   --pred wf.json          # B0 vs A0
    python3 au_walkforward_refit.py hash                             # 只印 hash

研究工具：輸出唔係 source-certified `au_oos_predictions` intake，
fit 出嚟嘅權重**唔准**直接上線（要當獨立純權重候選過閘）。唯讀。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR.parents[2] / "shared_racing"))

from au_eval import _counts, _stage4_metric_rows  # noqa: E402
from au_matrix_refit import dirichlet  # noqa: E402
from au_racing_engine.matrix_mapper import map_features_to_matrix_scores  # noqa: E402
from au_racing_engine.scoring import MATRIX_WEIGHTS, compose_matrix_score  # noqa: E402
from model_evaluation_decision import (  # noqa: E402
    _full_record_metric, evaluate_full_record)

DIMS = tuple(MATRIX_WEIGHTS)
RANKING_METRICS = ("top3_capture_at5", "ndcg_at5", "top5_pairwise_auc")

# 預先登記嘅程序。改任何一項 = 另一個程序（hash 會變），唔可以同舊 arm 比。
PROCEDURE = {
    "algorithm": "au-walkforward-refit/v1 (EXP-20261015-02 procedure)",
    "clean_since": "2026-08-05",
    "warmup_days": 30,
    "window_days": 7,
    "draws": 256,
    "seed": 7,
    "proposal_mix": "even i: Dirichlet(1); odd i: Dirichlet(max(25*anchor, 0.35))",
    "objective": ["gold", "good_positional", "pass", "t3prec"],
    "eligibility": "train gold>=anchor AND good>=anchor AND objective>anchor",
    "time_blocks": 5,
    "min_nonnegative_blocks": 4,
    "consensus": "per-dimension median of eligible draws, renormalised to anchor total",
    "median_recheck": "production arithmetic; same primary/objective/block gate",
    "fallback": "anchor weights",
    "label_filter": ">=3 placed and a winner",
    "tie_rule": "saddlecloth order (stable)",
    "dims": list(DIMS),
    "anchor_weights": {k: float(v) for k, v in MATRIX_WEIGHTS.items()},
}


def procedure_hash(procedure=None) -> str:
    """程序設定 + 本檔 source 嘅 sha256。B0／B1 一定要一樣。"""
    body = json.dumps(procedure or PROCEDURE, sort_keys=True, ensure_ascii=False)
    source = Path(__file__).read_bytes()
    return hashlib.sha256(body.encode("utf-8") + b"\0" + source).hexdigest()


# ── production arithmetic ─────────────────────────────────────────────────
def exact_score(row, weights) -> float:
    """同 engine_core 一樣嘅次序同捨入（engine_core.py ~L800-819）。"""
    pure = round(compose_matrix_score(map_features_to_matrix_scores(row["features"]),
                                      weights), 4)
    base = round(pure + float(row.get("wet") or 0.0)
                 + float(row.get("proven_class") or 0.0), 4)
    return round(base + float(row.get("full_time") or 0.0), 4)


# ── numpy proposal accelerator（只用嚟篩 draws）────────────────────────────
class Matrix:
    def __init__(self, races):
        rows = [row for race in races for row in race["rows"]]
        mapped = [map_features_to_matrix_scores(row["features"]) for row in rows]
        self.mx = np.array([[m[k] for k in DIMS] for m in mapped], dtype=float)
        self.wet_class = np.array([float(r.get("wet") or 0) + float(r.get("proven_class") or 0)
                                   for r in rows])
        self.full_time = np.array([float(r.get("full_time") or 0) for r in rows])
        self.slices = []
        start = 0
        for race in races:
            self.slices.append((start, start + len(race["rows"])))
            start += len(race["rows"])

    def batch(self, weights, n_races):
        end = self.slices[n_races - 1][1] if n_races else 0
        delta = np.zeros((len(weights), end))
        for j in range(len(DIMS)):
            delta += weights[:, j:j + 1] * (self.mx[None, :end, j] - 60.0)
        base = np.round(np.round(60.0 + delta, 4) + self.wet_class[None, :end], 4)
        return np.round(base + self.full_time[None, :end], 4)


def metric_table(races, scores):
    """(draw, race, [gold, good_positional, pass, t3prec])，數值係 0/1 或比例。"""
    out = np.empty((len(scores), len(races), 4))
    start = 0
    for i, race in enumerate(races):
        rows = race["rows"]
        width = len(rows)
        ranked = np.argsort(-scores[:, start:start + width], axis=1, kind="stable")
        placed = np.array([r["pos"] <= 3 for r in rows])
        hits = placed[ranked]
        h3 = hits[:, :3].sum(axis=1)
        out[:, i, 0] = hits[:, :4].sum(axis=1) == placed.sum()
        out[:, i, 1] = hits[:, :2].all(axis=1)
        out[:, i, 2] = h3 >= 2
        out[:, i, 3] = h3 / 3.0
        start += width
    return out


def date_blocks(races, n_blocks):
    """按完整日期切塊，一日唔會被拆開。"""
    dates = sorted({r["date"] for r in races})
    chunks = [set(c) for c in np.array_split(dates, n_blocks)]
    return [[i for i, r in enumerate(races) if r["date"] in chunk] for chunk in chunks]


def _gate(table, anchor, blocks, min_blocks):
    """table/anchor：(race, 4)。primary 不跌、目標要升、夠塊數不負。"""
    means, base = table.mean(axis=0), anchor.mean(axis=0)
    if not (means[0] >= base[0] and means[1] >= base[1] and means.mean() > base.mean()):
        return False
    return sum(table[g].mean() >= anchor[g].mean() for g in blocks) >= min_blocks


def fit_window(train, matrix, procedure=PROCEDURE):
    """只收 train（窗口之前嘅日期）。回傳 (weights, metadata)。"""
    anchor_w = procedure["anchor_weights"]
    if len({r["date"] for r in train}) < procedure["time_blocks"]:
        # 空日期塊會令閘門靜靜變 NaN；呢個唔係「冇共識」而係唔夠日子 fit。
        raise ValueError("training window has fewer dates than time blocks")
    total = sum(anchor_w.values())
    rng = random.Random(procedure["seed"])
    shipped = [max(anchor_w[k], 1e-4) for k in DIMS]
    draws = []
    for i in range(procedure["draws"]):
        alpha = [1.0] * len(DIMS) if i % 2 == 0 else [max(s * 25.0, 0.35) for s in shipped]
        draws.append(dirichlet(rng, alpha))
    weights = np.array([[anchor_w[k] for k in DIMS], *draws])
    proposed = metric_table(train, matrix.batch(weights, len(train)))
    blocks = date_blocks(train, procedure["time_blocks"])
    need = procedure["min_nonnegative_blocks"]
    eligible = [i for i in range(1, len(weights))
                if _gate(proposed[i], proposed[0], blocks, need)]
    meta = {"training_races": len(train), "accepted_draws": len(eligible)}
    if not eligible:
        return dict(anchor_w), {**meta, "fallback": "no_consensus"}
    consensus = np.median(weights[eligible], axis=0)
    consensus = consensus * total / consensus.sum()
    mapping = {k: float(v) for k, v in zip(DIMS, consensus)}
    exact_c = np.array([[exact_score(r, mapping) for race in train for r in race["rows"]]])
    exact_a = np.array([[exact_score(r, anchor_w) for race in train for r in race["rows"]]])
    if not _gate(metric_table(train, exact_c)[0], metric_table(train, exact_a)[0], blocks, need):
        return dict(anchor_w), {**meta, "fallback": "consensus_failed_gate"}
    return mapping, {**meta, "fallback": None}


# ── corpus ────────────────────────────────────────────────────────────────
def load_clean(path, procedure=PROCEDURE):
    races = json.loads(Path(path).read_text(encoding="utf-8"))["races"]
    out = []
    for race in races:
        if race["date"] < procedure["clean_since"]:
            continue
        rows = sorted(race["rows"], key=lambda r: r["n"])
        if sum(r["pos"] <= 3 for r in rows) < 3 or not any(r["pos"] == 1 for r in rows):
            continue
        out.append({**race, "rows": rows})
    out.sort(key=lambda r: (r["date"], r["meeting"], r["race"]))
    return out


def walk_forward(races, procedure=PROCEDURE, log=print):
    """逐窗 fit → 預測。每窗只見窗口之前嘅日期。"""
    dates = sorted({r["date"] for r in races})
    warmup, step = procedure["warmup_days"], procedure["window_days"]
    if len(dates) <= warmup:
        raise ValueError(f"only {len(dates)} clean dates; warmup needs > {warmup}")
    matrix = Matrix(races)
    anchor_w = procedure["anchor_weights"]
    windows, predictions = [], []
    for start in range(warmup, len(dates), step):
        test_dates = dates[start:start + step]
        n_train = sum(r["date"] < dates[start] for r in races)
        assert all(r["date"] < test_dates[0] for r in races[:n_train])
        weights, meta = fit_window(races[:n_train], matrix, procedure)
        windows.append({"train_until": dates[start - 1], "test_dates": test_dates,
                        **meta, "weights": weights})
        for race in races:
            if race["date"] not in test_dates:
                continue
            predictions.append({
                "date": race["date"], "meeting": race["meeting"], "race": race["race"],
                "field": race.get("field"), "window": len(windows) - 1,
                "rows": [{"n": r["n"], "name": r["name"], "pos": r["pos"],
                          "ability_engine": r.get("ability"),
                          "ability_live": exact_score(r, anchor_w),
                          "ability_refit": exact_score(r, weights)} for r in race["rows"]],
            })
        log(f"window {len(windows) - 1}: train ≤{dates[start - 1]} ({n_train} races) "
            f"test {test_dates[0]}→{test_dates[-1]}  accepted {meta['accepted_draws']}  "
            f"fallback={meta['fallback']}")
    return windows, predictions


def verify(races, procedure=PROCEDURE):
    """live 權重下：production 重算 == dump 存檔 ability；numpy 提案 == 正典計數。"""
    exact = np.array([exact_score(r, procedure["anchor_weights"])
                      for race in races for r in race["rows"]])
    engine = np.array([float(r["ability"]) for race in races for r in race["rows"]])
    max_engine = float(np.max(np.abs(exact - engine)))
    matrix = Matrix(races)
    anchor = np.array([[procedure["anchor_weights"][k] for k in DIMS]])
    fast = matrix.batch(anchor, len(races))[0]
    max_fast = float(np.max(np.abs(fast - exact)))
    table = metric_table(races, exact[None, :])[0].mean(axis=0) * 100
    canon = _counts(races, lambda r: exact_score(r, procedure["anchor_weights"]))
    canon_v = np.array([canon[k] for k in ("gold", "good_positional", "pass", "t3prec")])
    max_metric = float(np.max(np.abs(table - canon_v)))
    return {"max_abs_exact_vs_engine": max_engine, "max_abs_numpy_vs_exact": max_fast,
            "max_abs_metric_table_vs_canonical": max_metric,
            "ok": max_engine < 5.1e-5 and max_fast < 5.1e-5 and max_metric < 1e-8}


# ── judging helpers ───────────────────────────────────────────────────────
def arm_races(predictions, arm):
    """arm = 'live' | 'refit' → au_eval 用嘅 races（row['ability']）。"""
    key = f"ability_{arm}"
    return [{**race, "rows": [{**r, "ability": r[key]} for r in race["rows"]]}
            for race in predictions]


def arm_metric_rows(predictions, arm):
    """§8 判決器要嘅逐場 Stage-4 rows，次序同 predictions 一樣。"""
    return _stage4_metric_rows(arm_races(predictions, arm), lambda r: r["ability"])


def _pass_rows(races):
    out = []
    for race in races:
        ranked = sorted(range(len(race["rows"])), key=lambda i: -race["rows"][i]["ability"])
        out.append(float(sum(race["rows"][i]["pos"] <= 3 for i in ranked[:3]) >= 2))
    return out


def stale_check(predictions, leakage_audit_passed=True):
    """合約 §8 stale arm：B0（refit）vs A0（live），walk_forward_oos。"""
    dates = [r["date"] for r in predictions]
    live, refit = arm_races(predictions, "live"), arm_races(predictions, "refit")
    verdict = evaluate_full_record(
        domain="au", mode="walk_forward_oos", dates=dates,
        baseline_rows=arm_metric_rows(predictions, "live"),
        candidate_rows=arm_metric_rows(predictions, "refit"),
        leakage_audit_passed=leakage_audit_passed, ranking_metrics=RANKING_METRICS)
    pass_ev = _full_record_metric(_pass_rows(live), _pass_rows(refit), dates,
                                  higher_is_better=True, blocks=6, bootstrap=2000, seed=7)
    score = lambda r: r["ability"]  # noqa: E731
    return {"verdict": verdict, "pass_diagnostic": vars(pass_ev),
            "counts_live": _counts(live, score), "counts_refit": _counts(refit, score),
            "races": len(predictions), "meeting_days": len(set(dates))}


# ── CLI ───────────────────────────────────────────────────────────────────
def cmd_predict(args):
    races = load_clean(args.data)
    check = verify(races)
    print(f"clean races {len(races)}  dates {len({r['date'] for r in races})}  verify {check}")
    if not check["ok"]:
        raise SystemExit("replica/production mismatch — refuse to fit")
    windows, predictions = walk_forward(races)
    out = {"procedure": PROCEDURE, "procedure_hash": procedure_hash(),
           "input": str(args.data),
           "input_sha256": hashlib.sha256(Path(args.data).read_bytes()).hexdigest(),
           "verify": check, "windows": windows, "predictions": predictions,
           "source_audit": "FLAG: input/label availability not source-certified",
           "promotion_authorized": False}
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"procedure_hash {out['procedure_hash']}\n→ {args.out}")


def cmd_stale(args):
    pred = json.loads(Path(args.pred).read_text(encoding="utf-8"))
    if pred["procedure_hash"] != procedure_hash():
        print("⚠️ prediction file was produced by a different procedure/source")
    result = stale_check(pred["predictions"])
    result["procedure_hash"] = pred["procedure_hash"]
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False))
    v = result["verdict"]
    print(f"races {result['races']}  days {result['meeting_days']}")
    print(f"verdict {v['verdict']}  reason {v['reason']}")
    for sec in ("primary", "ranking"):
        for name, ev in v["detail"][sec].items():
            print(f"  {name:22} Δ {ev['delta']:+.5f}  CI [{ev['ci_low']:+.5f}, "
                  f"{ev['ci_high']:+.5f}]  p {ev['p_value']:.3f}  blocks "
                  + " ".join(f"{b:+.4f}" for b in ev["block_deltas"]))
    pe = result["pass_diagnostic"]
    print(f"  {'pass (diagnostic)':22} Δ {pe['delta']:+.5f}  CI [{pe['ci_low']:+.5f}, "
          f"{pe['ci_high']:+.5f}]  p {pe['p_value']:.3f}")
    for k in ("gold", "good_positional", "pass", "t3prec"):
        print(f"  {k:16} live {result['counts_live'][k]:6.2f}%  "
              f"refit {result['counts_refit'][k]:6.2f}%")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("predict")
    p.add_argument("--data", required=True)
    p.add_argument("--out", required=True)
    s = sub.add_parser("stale")
    s.add_argument("--pred", required=True)
    s.add_argument("--out")
    sub.add_parser("hash")
    args = ap.parse_args(argv)
    if args.cmd == "hash":
        print(procedure_hash())
    else:
        {"predict": cmd_predict, "stale": cmd_stale}[args.cmd](args)


if __name__ == "__main__":
    main()
