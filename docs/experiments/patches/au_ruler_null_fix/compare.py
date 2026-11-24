#!/usr/bin/env python3
"""EXP-20261124-41：v2 vs v2.1（null 計返冇郁場次）判決比較。 compare.py OUT.json
對：真 dump 候選（R2、TRES、F1、SPG）＋細 cohort 純噪音（3% 馬 N(0, σ)，冇資訊，應該全部 REJECT）。"""
import json, sys
from pathlib import Path
import numpy as np
SC = Path(__file__).resolve().parents[4] / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SC)); sys.path.insert(0, str(SC.parents[2] / "shared_racing"))
import au_logloss_ruler as L  # noqa: E402
X = Path("/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch")
load = lambda p: L.eligible(json.loads(Path(p).read_text())["races"])
pairs = {
    "R2（live vs 冇 R2）": (X / "au-rejudge-20261124/NO_R2.json", X / "au-rejudge-20261124/BASE.json"),
    "TRES（live vs 冇練馬師剩餘表現）": (X / "au-rejudge-20261124/NO_TRES.json", X / "au-rejudge-20261124/BASE.json"),
    "F1（EXP-20261123-06）": (X / "au-v2-rescreen-20261123/BASE.json", X / "au-v2-rescreen-20261123/F1.json"),
    "SPG（EXP-20261123-06）": (X / "au-v2-rescreen-20261123/BASE.json", X / "au-v2-rescreen-20261123/SPG.json"),
}
out = {}
def run(name, b, c):
    res = {}
    for v in ("v2", "v2.1"):
        e = L.evaluate(b, c, nnull=200, version=v)
        res[v] = {k: e.get(k) for k in ("verdict", "reason", "dlogloss", "beats_null_share", "checks")}
    out[name] = res
    print(f"{name:38s} v2 {res['v2']['verdict']:6s} null {res['v2']['beats_null_share']:.3f} | v2.1 {res['v2.1']['verdict']:6s} null {res['v2.1']['beats_null_share']:.3f} | Δ {res['v2']['dlogloss'][0]:+.6f}", flush=True)
for name, (bp, cp) in pairs.items():
    run(name, load(bp), load(cp))
base = load(X / "au-rejudge-20261124/BASE.json")
rng = np.random.default_rng(11)
for sigma in (1.0, 3.0):
    for k in range(5):
        cand = []
        for r in base:
            rows = []
            for x in r["rows"]:
                bump = rng.normal(0, sigma) if rng.random() < 0.03 else 0.0
                rows.append(dict(x, ability=x["ability"] + bump))
            cand.append(dict(r, rows=rows))
        run(f"噪音 3% 馬 σ{sigma} #{k}", base, cand)
Path(sys.argv[1]).write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float))
