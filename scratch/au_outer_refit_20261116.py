#!/usr/bin/env python3
"""EXP-20261116-02：AU 外層權重 walk-forward refit（HKJC EXP-20261114-03 S 版嘅 AU 版）。

    python3 scratch/au_outer_refit_20261116.py BASE.json OUTDIR

六個維度分 m_k（map_features_to_matrix_scores），場內置中。每 REFIT_EVERY 個賽日用之前賽日（2026-08-05 起）嘅賽果擬合
logistic 入位 ~ a + Σ c_k·m_k + c_r·rest，rest = 冇 refit 嘅部分（overlay＋固定維度）。
新權重 w_k = max(c_k, 0) × S，S 令 refit 維度權重總和 = 現行總和（同 HKJC 一樣縮放到現行總和）。
arm：R（pace_perf 固定，Kelvin「段速係核心」，其餘五維 fit）、RF（六維全部 fit，診斷）。
頭 WARMUP 個賽日用現行權重。判決用 au_prior_odds_judge（walk_forward_oos）。
"""
import collections
import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

W = Path(__file__).resolve().parents[1]
SCRIPTS = W / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SCRIPTS))
from au_racing_engine.dimensions import MATRIX_WEIGHTS  # noqa: E402
from au_racing_engine.matrix_mapper import map_features_to_matrix_scores  # noqa: E402
from au_racing_engine.scoring import compose_matrix_score  # noqa: E402

START, WARMUP, REFIT_EVERY = "2026-08-05", 20, 7
DIMS = list(MATRIX_WEIGHTS)
ARMS = {"R": [k for k in DIMS if k != "pace_perf"], "RF": DIMS}


def overlay(row):
    return row["wet"] + row["proven_class"] + row["full_time"] + row["draw"]


def fit_logit(X, y):
    w = np.zeros(X.shape[1])
    for _ in range(60):
        z = np.clip(X @ w, -30, 30); p = 1 / (1 + np.exp(-z))
        g = X.T @ (y - p); H = (X * (p * (1 - p))[:, None]).T @ X
        step = np.linalg.solve(H + 1e-9 * np.eye(len(w)), g); w += step
        if np.max(np.abs(step)) < 1e-9:
            break
    return w


def race_matrix(race, fitted):
    """→ (M 場內置中 n×k, rest 場內置中, y, rows)。rest = overlay + 冇 fit 嘅維度（現行權重）。"""
    rows = [x for x in race["rows"] if isinstance(x.get("pos"), int) and x["pos"] > 0]
    if len(rows) < 3:
        return None
    M = np.array([[x["_m"][k] - 60.0 for k in fitted] for x in rows])
    rest = np.array([overlay(x) + sum((x["_m"][k] - 60.0) * MATRIX_WEIGHTS[k] for k in DIMS if k not in fitted)
                     for x in rows])
    y = np.array([1.0 if x["pos"] <= 3 else 0.0 for x in rows])
    return M - M.mean(0), rest - rest.mean(), y


def main():
    base_path, out = Path(sys.argv[1]), Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
    data = json.loads(base_path.read_text())
    worst = 0.0
    for race in data["races"]:
        for x in race["rows"]:
            x["_m"] = map_features_to_matrix_scores(x["features"])
            worst = max(worst, abs(compose_matrix_score(x["_m"]) + overlay(x) - x["ability"]))
    print(f"A/A replica max |Δability| = {worst:.6f}")
    if worst > 1e-3:
        sys.exit("replica does not match the engine — stop")
    races = [r for r in data["races"] if r["date"] >= START]
    by_day = collections.defaultdict(list)
    for r in races:
        by_day[r["date"]].append(r)
    days = sorted(by_day)
    for arm, fitted in ARMS.items():
        cur_sum = sum(MATRIX_WEIGHTS[k] for k in fitted)
        Xs, ys, weights_of, log = [], [], {}, []
        current = dict(MATRIX_WEIGHTS)
        for i, d in enumerate(days):
            if i >= WARMUP and (i - WARMUP) % REFIT_EVERY == 0:
                X = np.vstack(Xs); y = np.concatenate(ys)
                c = fit_logit(np.column_stack([np.ones(len(y)), X]), y)[1:]
                ck = np.maximum(c[:len(fitted)], 0.0)
                scale = cur_sum / ck.sum() if ck.sum() > 0 else 0.0
                current = dict(MATRIX_WEIGHTS)
                if scale > 0:
                    current.update({k: float(v * scale) for k, v in zip(fitted, ck)})
                log.append({"date": d, "n_train": int(len(y)), "c_rest": round(float(c[-1]), 5),
                            "weights": {k: round(v, 4) for k, v in current.items()}})
            weights_of[d] = dict(current)
            for r in by_day[d]:  # 當日賽果收市之後先入訓練
                m = race_matrix(r, fitted)
                if m is not None:
                    Xs.append(np.column_stack([m[0], m[1]])); ys.append(m[2])
        cand = copy.deepcopy(data); moved = 0
        for r in cand["races"]:
            if r["date"] < START:
                continue
            wts = weights_of[r["date"]]
            for x in r["rows"]:
                new = compose_matrix_score(x["_m"], wts) + overlay(x)
                moved += abs(new - x["ability"]) > 1e-9; x["ability"] = new
        for r in cand["races"]:
            for x in r["rows"]:
                x.pop("_m", None)
        print(f"{arm}: refits {len(log)}; last weights {log[-1]['weights'] if log else None}; horses moved {moved}")
        (out / f"{arm}.weights.json").write_text(json.dumps(log, indent=1))
        p = out / f"{arm}.json"; p.write_text(json.dumps(cand))
        subprocess.run([sys.executable, str(W / "scratch/au_prior_odds_judge_20261116.py"),
                        str(base_path), str(p), str(out / f"{arm}.verdict.json")], check=True,
                       env=dict(os.environ, JUDGE_MODE="walk_forward_oos", PYTHONDONTWRITEBYTECODE="1"))
        p.unlink()


if __name__ == "__main__":
    main()
