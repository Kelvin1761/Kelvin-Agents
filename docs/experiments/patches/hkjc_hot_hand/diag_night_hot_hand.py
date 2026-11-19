"""Kelvin 2026-11-19「騎師手風需唔需要調整」：當晚之前場次騎師／練馬師戰績（同一賽日、場次細過今場），live 之上殘差。
只用舊季（dev 2020–23、holdout 2024–25）；唔掂 EXP-20261104-11 forward（2026-11-04 起）。用法：python3 diag_night_hot_hand.py <live dump>
"""
import json, re, sys
from collections import defaultdict
import numpy as np
sys.path.insert(0, "/Users/imac/Antigravity-repo/docs/experiments/patches/hkjc_incidents")
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
from diag import season  # noqa: E402
from diag_full import calibrate  # noqa: E402
import hkjc_history_replay_build as b  # noqa: E402

idx = b.load_index(); ppl = {}; night = defaultdict(list)   # date -> [(race, jockey, trainer, pos)]
for (d, n), race in idx["results"].items():
    for row in race.get("results", []):
        try: p = int(str(row.get("pos")).strip())
        except ValueError: p = None
        j, t = str(row.get("jockey") or "").strip(), str(row.get("trainer") or "").strip()
        ppl[(d, n, str(row.get("horse_no")))] = (j, t)
        night[d].append((n, j, t, p))
def feats(d, n, j, t):
    prev = [x for x in night[d] if x[0] < n]
    jr = [x for x in prev if x[1] == j]; tr = [x for x in prev if x[2] == t]
    jw = sum(x[3] == 1 for x in jr); jp = sum((x[3] or 99) <= 3 for x in jr)
    tw = sum(x[3] == 1 for x in tr)
    return {
        "騎師當晚已贏 ≥1": jw >= 1, "騎師當晚已贏 ≥2": jw >= 2,
        "騎師當晚已入位 ≥2": jp >= 2,
        "騎師當晚 ≥4 騎 0 入位（冷手）": len(jr) >= 4 and jp == 0,
        "練馬師當晚已贏 ≥1": tw >= 1,
        "騎師當晚未騎過（對照）": len(jr) == 0,
    }
rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
calib = calibrate(rows); recs = []
for x in rows:
    s = season(x["date"])
    if not 2020 <= s <= 2025: continue
    hs = [h for h in x["horses"] if h["pos"]]
    r = np.array([h["raw"] for h in hs]); rc = r - r.mean(); a, bb = calib[s]
    for h, z in zip(hs, rc):
        jt = ppl.get((x["date"], x["race"], str(h["n"])))
        if not jt: continue
        recs.append((s, int(h["pos"] <= 3) - 1 / (1 + np.exp(-(a + bb * z))), feats(x["date"], x["race"], *jt), x["race"]))
print("馬次", len(recs))
rng = np.random.default_rng(0)
for k in recs[0][2]:
    out = []
    for lo, hi in ((2020, 2023), (2024, 2025)):
        y = np.array([r[1] for r in recs if lo <= r[0] <= hi and r[2][k]])
        if len(y) < 30: out.append(f"n={len(y)}"); continue
        bt = [y[rng.integers(0, len(y), len(y))].mean() for _ in range(1000)]
        out.append(f"{100*y.mean():+.1f}[{100*np.percentile(bt,2.5):+.1f},{100*np.percentile(bt,97.5):+.1f}] n={len(y)}")
    print(f"{k}｜dev {out[0]}｜holdout {out[1]}")
