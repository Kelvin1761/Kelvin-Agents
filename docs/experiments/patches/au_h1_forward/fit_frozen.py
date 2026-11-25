#!/usr/bin/env python3
"""EXP-20261125-11 H1：一次過 fit 試閘＋備戰分嘅凍結係數（**只跑一次**，2026-11-25）。

候選 ability = live ability + w_trial·z(trial_score) + w_prep·z(preparation_score)
  z = 場內標準化（(x − 場均) / 場內母體 SD；SD < 1e-9 → 0），同 EXP-20261125-06 `disagree.enrich` 一樣。
  fit：入頭三 logistic，同 `au_logloss_ruler` v2 校準同一個形狀，再加兩欄：
      logit P = a + α·(ability − 場均) + γ·logit(3/N) + β_trial·z_trial + β_prep·z_prep
  用 `au_logloss_ruler._xy(version="v2")` 同 `_fit`（bit-identical 嘅 Newton），(a, α, γ, β_t, β_p) 一齊 fit。
  凍結權重換算返 ability 分：w = β / α（因為判決尺會自己重 fit α，所以候選要喺 ability 尺度）。

數據：BASE dump（`au-debut-trainer-20261124/BASE.json`），`au_logloss_ruler.eligible`（2026-08-05 起），
      日期 ≤ 2026-11-25。之後**永遠唔再 fit**（forward 腳本會核對 frozen.json 嘅 sha256）。

    PYTHONDONTWRITEBYTECODE=1 python3 fit_frozen.py BASE.json frozen.json
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / ".agents/skills/au_racing/au_wong_choi_auto/scripts"))
import au_logloss_ruler as L  # noqa: E402

FIT_UNTIL = "2026-11-25"
FEATURES = ("trial_score", "preparation_score")


def race_z(values) -> np.ndarray:
    v = np.asarray(values, float)
    sd = v.std()
    return (v - v.mean()) / sd if sd > 1e-9 else np.zeros_like(v)


def design(race):
    x, y = L._xy(race, version="v2")
    zs = [race_z([row["features"][f] for row in race["rows"]]) for f in FEATURES]
    return np.column_stack([x] + zs), y


def main():
    base, out = Path(sys.argv[1]), Path(sys.argv[2])
    races = [r for r in L.eligible(json.loads(base.read_text())["races"]) if r["date"] <= FIT_UNTIL]
    races = [r for r in races if all(f in row["features"] for row in r["rows"] for f in FEATURES)]
    X, Y = zip(*(design(r) for r in races))
    X, Y = np.concatenate(X), np.concatenate(Y)
    a, alpha, gamma, bt, bp = L._fit(X, Y)
    a0, alpha0, gamma0 = L._fit(X[:, :2], Y)

    def ll(beta, cols):
        A = np.column_stack([np.ones(len(X)), X[:, cols]])
        p = np.clip(1 / (1 + np.exp(-A @ np.array(beta))), 1e-12, 1 - 1e-12)
        return float(-(Y * np.log(p) + (1 - Y) * np.log(1 - p)).mean())
    frozen = {
        "experiment": "EXP-20261125-11",
        "hypothesis": "H1（EXP-20261125-06）：試閘＋備戰分喺 ability 入面份量太細",
        "candidate": "ability + w_trial*z(trial_score) + w_prep*z(preparation_score)；z = 場內母體標準化，SD<1e-9 → 0",
        "fit": {"source": str(base), "source_sha256": hashlib.sha256(base.read_bytes()).hexdigest(),
                "since": L.CLEAN_SINCE, "until": FIT_UNTIL, "races": len(races), "runners": int(len(Y)),
                "days": len({r["date"] for r in races}),
                "shape": "logit P(top3) = a + α·(ability−場均) + γ·log(3/max(N−3,1e-9)) + β_t·z_t + β_p·z_p",
                "a": a, "alpha": alpha, "gamma": gamma, "beta_trial": bt, "beta_prep": bp,
                "reference_without_z": {"a": a0, "alpha": alpha0, "gamma": gamma0},
                "in_sample_logloss": {"without_z": ll([a0, alpha0, gamma0], [0, 1]),
                                      "with_z": ll([a, alpha, gamma, bt, bp], [0, 1, 2, 3]),
                                      "note": "in-sample，只供參考；唔係證據"}},
        "weights": {"trial_score": bt / alpha, "preparation_score": bp / alpha},
        "unit": "ability 分 / 場內 SD",
    }
    out.write_text(json.dumps(frozen, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(frozen, ensure_ascii=False, indent=1))
    print("sha256", hashlib.sha256(out.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
