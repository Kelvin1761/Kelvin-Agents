"""v2 尺重做 EXP-20261121-35 嗰批驗證：A/A、純噪音（σ 0.5／2.0）、人工真改善（上名馬 0.5% 加 0.3；排 3–5 嘅上名馬 0.5% 加 1.0）。"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import BASE, R, load  # noqa: E402

SEEDS = int(sys.argv[1]) if len(sys.argv) > 1 else 10
base = load(BASE)
print("A/A", R.evaluate(base, base, nnull=0)["verdict"], flush=True)
for sigma in (0.5, 2.0):
    res = []
    for s in range(SEEDS):
        rng = random.Random(100 + s)
        cand = [dict(r, rows=[dict(x, ability=x["ability"] + rng.gauss(0, sigma)) for x in r["rows"]]) for r in base]
        res.append(R.evaluate(base, cand, nnull=50)["verdict"])
    print(f"噪音 σ{sigma}：誤判 {res.count('PASS')}/{SEEDS}", flush=True)


def bump(share, amount, rank3to5, seed):
    rng = random.Random(1000 + seed)
    out = []
    for r in base:
        order = sorted(range(len(r["rows"])), key=lambda i: -r["rows"][i]["ability"])
        rk = {i: k + 1 for k, i in enumerate(order)}
        out.append(dict(r, rows=[dict(x, ability=x["ability"] + (amount if x["pos"] <= 3 and (not rank3to5 or 3 <= rk[i] <= 5)
                                                                     and rng.random() < share else 0.0))
                                 for i, x in enumerate(r["rows"])]))
    return out


for label, share, amount, r35 in (("上名馬 0.5% 加 0.3", 0.005, 0.3, False), ("排 3–5 上名馬 0.5% 加 1.0", 0.005, 1.0, True)):
    res = [R.evaluate(base, bump(share, amount, r35, s), nnull=50)["verdict"] for s in range(SEEDS)]
    print(f"{label}：PASS {res.count('PASS')}/{SEEDS}", flush=True)
