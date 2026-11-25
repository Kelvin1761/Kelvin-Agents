#!/usr/bin/env python3
"""通用假設 forward：一次過 fit 一個 arm 嘅凍結係數（每個 arm **只跑一次**）。

同 `au_h1_forward/fit_frozen.py` 同一個形狀：
    logit P(top3) = a + α·(ability − 場均) + γ·logit(3/N) + Σ β_k·term_k
term 定義直接用（fit 時再減場均：forward 嘅 shift 加入 ability 之後，判決尺會減場均，所以等價） `au_hypothesis_forward.term_values`（forward 同 fit 一份 code）。凍結權重 w_k = β_k / α（ability 尺度）。
數據：BASE dump（`au_dump_engine_leaves.py`），`au_logloss_ruler.eligible`（2026-08-05 起）、日期 ≤ FIT_UNTIL。
注意：BASE 嘅 rows 只有有名次嘅馬，所以 fit 時 z 喺完賽馬入面計；forward 喺成個賽前快照場計（同 H1 一樣嘅已知細微差別，
對候選唔有利，即係保守）。

    PYTHONDONTWRITEBYTECODE=1 python3 fit_frozen.py --arm EXP-… BASE.json OUT.frozen.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / ".agents/skills/au_racing/au_wong_choi_auto/scripts"))
import au_logloss_ruler as L  # noqa: E402
import au_hypothesis_forward as F  # noqa: E402

FIT_UNTIL = "2026-11-25"


def field_rows(race):
    out = []
    for row in race["rows"]:
        x = dict(row["features"])
        v = row.get("days_since_last")
        try:   # 同 forward `_logic_value` 一樣：空字串／讀唔到 = None（= 唔喺組別）
            x["days_since_last"] = float(v) if v not in (None, "") else None
        except (TypeError, ValueError):
            x["days_since_last"] = None
        out.append(x)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True, choices=sorted(F.ARMS))
    ap.add_argument("base")
    ap.add_argument("out")
    a = ap.parse_args()
    arm = F.ARMS[a.arm]
    base, out = Path(a.base), Path(a.out)
    races = [r for r in L.eligible(json.loads(base.read_text())["races"]) if r["date"] <= FIT_UNTIL]
    races = [r for r in races if all(f in row["features"] for row in r["rows"] for f in arm.z_leaves)]
    keys = [t.key for t in arm.terms]
    Xs, Ys, cover = [], [], {k: 0.0 for k in keys}
    for r in races:
        x, y = L._xy(r, version="v2")
        vals = F.term_values(arm, field_rows(r))
        for k in keys:
            cover[k] += float(np.abs(vals[k]).sum()) if arm.terms[keys.index(k)].kind == "ind" else 0.0
        # forward 將 shift 加落 ability，判決尺再減場均 → 等於 term 場內置中；fit 要用同一個定義
        Xs.append(np.column_stack([x] + [vals[k] - vals[k].mean() for k in keys]))
        Ys.append(y)
    X, Y = np.concatenate(Xs), np.concatenate(Ys)
    beta = L._fit(X, Y)
    a0, alpha, gamma = beta[:3]
    b = beta[3:]
    ref = L._fit(X[:, :2], Y)

    def ll(bb, cols):
        A = np.column_stack([np.ones(len(X)), X[:, cols]])
        p = np.clip(1 / (1 + np.exp(-A @ np.array(bb))), 1e-12, 1 - 1e-12)
        return float(-(Y * np.log(p) + (1 - Y) * np.log(1 - p)).mean())
    frozen = {
        "experiment": arm.id, "hypothesis": f"{arm.title}（{arm.source}）",
        "terms": [t.__dict__ for t in arm.terms],
        "fit": {"source": str(base), "source_sha256": hashlib.sha256(base.read_bytes()).hexdigest(),
                "since": L.CLEAN_SINCE, "until": FIT_UNTIL, "races": len(races), "runners": int(len(Y)),
                "days": len({r["date"] for r in races}),
                "shape": "logit P(top3) = a + α·(ability−場均) + γ·log(3/max(N−3,1e-9)) + Σ β_k·term_k",
                "a": float(a0), "alpha": float(alpha), "gamma": float(gamma),
                "beta": {k: float(v) for k, v in zip(keys, b)},
                "indicator_coverage": {k: cover[k] / len(Y) for k in keys if cover[k]},
                "reference_without_terms": {"a": float(ref[0]), "alpha": float(ref[1]), "gamma": float(ref[2])},
                "in_sample_logloss": {"without": ll(list(ref), [0, 1]),
                                      "with": ll(list(beta), list(range(X.shape[1]))),
                                      "note": "in-sample，只供參考；唔係證據"}},
        "weights": {k: float(v / alpha) for k, v in zip(keys, b)},
        "unit": "ability 分 / term 單位（z = 場內 SD；ind = 0／1）",
    }
    out.write_text(json.dumps(frozen, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(frozen, ensure_ascii=False, indent=1))
    print("sha256", hashlib.sha256(out.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
