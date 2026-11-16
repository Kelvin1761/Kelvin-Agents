"""Kelvin Q10：見習減磅值唔值佢個磅數？歷史排位表冇宣佈負磅（只有實際負磅），所以用騎師身份：
live Logic 有 jockey_allowance 嘅六位見習（2026-07 起）。殘差 = 入頭三 − p（live I1 dump，之前季校準）。
分：高減磅（袁幸堯、黃寶妮，live 減 7–10）／低減磅（周俊樂、黃智弘、鍾易禮、巫顯東，減 2–3）。
注意：歷史年份佢哋嘅減磅數唔一定同 live 一樣（減磅隨勝仗數減少）。
"""
import json
import sys

import numpy as np

sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
import hkjc_history_replay_build as b  # noqa: E402
from diag import calibrate, season  # noqa: E402

HIGH = {"袁幸堯", "黃寶妮"}
LOW = {"周俊樂", "黃智弘", "鍾易禮", "巫顯東"}
idx = b.load_index()
rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
cal = calibrate(rows)
recs = []
for x in rows:
    s = season(x["date"])
    if s < 2020:
        continue
    res = {str(r.get("horse_no")): r for r in (idx["results"].get((x["date"], x["race"])) or {}).get("results", [])}
    hs = [h for h in x["horses"] if h["pos"]]
    r = np.array([h["raw"] for h in hs]); z = r - r.mean(); a, bb = cal[s]
    for h, zz in zip(hs, z):
        j = (res.get(str(h["n"])) or {}).get("jockey", "")
        g = "high" if j in HIGH else "low" if j in LOW else "other"
        recs.append(dict(s=s, y=int(h["pos"] <= 3), p=1 / (1 + np.exp(-(a + bb * zz))), g=g, j=j))
rng = np.random.default_rng(0)
for lab, lo, hi in (("dev 2020-23", 2020, 2023), ("holdout 2024-25", 2024, 2025), ("2026/27", 2026, 2026)):
    for g in ("high", "low", "other"):
        y = np.array([r["y"] - r["p"] for r in recs if lo <= r["s"] <= hi and r["g"] == g])
        if len(y) < 30:
            print(lab, g, len(y)); continue
        bt = [y[rng.integers(0, len(y), len(y))].mean() for _ in range(400)]
        print(f"{lab} {g} n={len(y)} {100*y.mean():+.2f}[{100*np.percentile(bt,2.5):+.2f},{100*np.percentile(bt,97.5):+.2f}]")
for j in sorted(HIGH | LOW):
    for lab, lo, hi in (("dev", 2020, 2023), ("hold", 2024, 2026)):
        y = np.array([r["y"] - r["p"] for r in recs if lo <= r["s"] <= hi and r["j"] == j])
        print(j, lab, len(y), f"{100*y.mean():+.1f}" if len(y) else "")
