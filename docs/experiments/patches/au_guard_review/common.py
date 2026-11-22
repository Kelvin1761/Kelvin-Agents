"""EXP-20261123-01 AU log-loss 尺護欄檢討 —— 共用：讀 baseline、逐場 Gold／Good／場內 AUC、按賽日 bootstrap。

照 HKJC EXP-20261122-33（`patches/hkjc_guard_v51/`）嘅做法，但用 AU 尺本身（`au_logloss_ruler.py`）嘅
eligible／warm-up／walk-forward 校準，計分場次同判決器一樣。
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

W = Path(__file__).resolve().parents[4]
SCRIPTS = W / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
for p in (SCRIPTS, SCRIPTS.parents[2] / "shared_racing"):
    sys.path.insert(0, str(p))
import au_logloss_ruler as R  # noqa: E402

SCR = Path("/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch")
BASE = Path(os.environ.get("AU_GUARD_BASE", SCR / "au-going-sim/BASE.json"))


def load(path):
    return R.eligible(json.loads(Path(path).read_text())["races"])


def key(r):
    return (r["meeting"], r["race"])


def auc(race, raws):
    y = np.array([x["pos"] <= 3 for x in race["rows"]])
    p, n = raws[y], raws[~y]
    if not len(p) or not len(n):
        return 0.5
    d = p[:, None] - n[None, :]
    return float(((d > 0) + 0.5 * (d == 0)).mean())


class Bench:
    """固定 baseline；`run(delta)` 計候選（baseline raw + Δ）嘅逐場 Gold／Good／AUC Δ 同 bootstrap CI。"""

    def __init__(self, base_path=BASE, nb=1000, seed=1):
        self.races = load(base_path)
        self.cal = R.calibrations(self.races)
        self.scored = [i for i, r in enumerate(self.races) if r["date"] in self.cal]
        self.base_raw = [np.array([x["ability"] for x in r["rows"]], float) for r in self.races]
        self.base_m = {i: self._m(i, self.base_raw[i]) for i in self.scored}
        days = sorted({self.races[i]["date"] for i in self.scored})
        self.day_ix = np.array([days.index(self.races[i]["date"]) for i in self.scored])
        self.ndays, self.nb = len(days), nb
        self.rng = np.random.default_rng(seed)

    def _m(self, i, raws):
        r = self.races[i]
        rr = {**r, "rows": [{**x, "ability": float(v)} for x, v in zip(r["rows"], raws)]}
        g, gd, _, _ = R._metrics(rr)
        return np.array([g, gd, auc(r, raws)])

    def ci(self, D):
        S = np.zeros((self.ndays, D.shape[1]))
        np.add.at(S, self.day_ix, D)
        c = np.bincount(self.day_ix, minlength=self.ndays).astype(float)
        w = self.rng.multinomial(self.ndays, np.full(self.ndays, 1 / self.ndays), size=self.nb).astype(float)
        bs = (w @ S) / (w @ c)[:, None]
        return D.mean(0), np.percentile(bs, 2.5, axis=0), np.percentile(bs, 97.5, axis=0)

    def run(self, delta_fn):
        """delta_fn(i, race) → Δ raw；回傳 (mean, lo, hi)，單位：Gold／Good pp、AUC ×100。"""
        D = np.array([self._m(i, self.base_raw[i] + delta_fn(i, self.races[i])) - self.base_m[i] for i in self.scored])
        m, lo, hi = self.ci(D * 100)
        return m, lo, hi

    def logloss(self, delta_fn):
        cand = [{**r, "rows": [{**x, "ability": float(v)} for x, v in
                               zip(r["rows"], self.base_raw[i] + delta_fn(i, r))]} for i, r in enumerate(self.races)]
        return R.evaluate(self.races, cand, nnull=0)["dlogloss"]


def pair_delta(base_path, cand_path):
    """真候選嘅 raw Δ（cand − base，按 (場次, 馬號) 對齊）→ {(meeting, race): {n: Δ}}。"""
    raw = lambda p: {key(r): {x["n"]: x["ability"] for x in r["rows"]} for r in json.loads(Path(p).read_text())["races"]}  # noqa: E731
    B, C = raw(base_path), raw(cand_path)
    return {k: {n: C[k][n] - v for n, v in b.items() if n in C[k]} for k, b in B.items() if k in C}


def fmt(m, lo, hi, j):
    return f"{m[j]:+.2f} [{lo[j]:+.2f},{hi[j]:+.2f}]"
