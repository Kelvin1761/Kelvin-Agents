"""一致性：舊候選喺 v1（11-21 尺）同 v2（加 logit(3/N)＋AUC 護欄）下嘅判決。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import SCR, R, load  # noqa: E402
from field_size import PAIRS  # noqa: E402

PAIRS = {**PAIRS, "P2": ("au-noise-20261113/BASE.json", "au-prior-odds-logloss/P2.json"),
         "G25s": ("au-going-sim/BASE.json", "au-going-sim/G25.json")}
nnull = int(sys.argv[1]) if len(sys.argv) > 1 else 100
out = {}
for name, (bp, cp) in PAIRS.items():
    base, cand = load(SCR / bp), load(SCR / cp)
    row = {}
    for ver in ("v1", "v2"):
        try:
            v = R.evaluate(base, cand, nnull=nnull, version=ver)
        except ValueError as e:
            row[ver] = {"verdict": "ERR", "reason": str(e)}
            continue
        row[ver] = {k: v[k] for k in ("verdict", "reason", "dlogloss", "beats_null_share", "gold_pp", "good_pp", "auc_delta", "top2_any_hit_pp")}
    out[name] = row
    f = lambda r: (f"{r['verdict']}/{r['reason']} Δ {r['dlogloss'][0]:+.5f} [{r['dlogloss'][1]:+.5f},{r['dlogloss'][2]:+.5f}] "  # noqa: E731
                   f"Gold {r['gold_pp'][0]:+.2f}({r['gold_pp'][1]:+.2f}) Good {r['good_pp'][0]:+.2f}({r['good_pp'][1]:+.2f}) "
                   f"AUC {r['auc_delta'][0]*100:+.3f}[{r['auc_delta'][1]*100:+.3f}] null {r['beats_null_share']}") if "dlogloss" in r else r["reason"]
    print(f"{name}｜v1 {f(row['v1'])}\n{' ' * len(name)}｜v2 {f(row['v2'])}", flush=True)
print(json.dumps(out, ensure_ascii=False))
