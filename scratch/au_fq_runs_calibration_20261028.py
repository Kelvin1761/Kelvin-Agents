"""EXP-20261028-11 更正：按出賽場數睇模型有冇低估／高估（只描述，唔改模型）。

超額 = 實際入前三 − 同一個模型名次（1..12+）× 同一個馬群大小（≤8／9–12／13+）嘅平均入前三率。
即係逐格對齊名次，唔再好似原記錄咁將 7+ 名成個層一齊比（嗰個會混入層內名次分佈唔同）。
CI = 按場 bootstrap 1,000 次、seed 7。只用 2026-08-05 起、全場有賽果嘅場次。

    python3 scratch/au_fq_runs_calibration_20261028.py <dump_new.json>
"""
import collections
import json
import random
import sys


def cohort(x):
    f = x.get("fq") or {}
    c = x.get("career_starts")
    rc = 0 if f.get("raw") is None else f.get("run_count")
    if c is None:
        return None
    if c == 0:
        return "0 初出"
    if c == 1:
        return "1 仗"
    if 2 <= c <= 5:
        return f"{c} 仗（{'全部' if rc == c else '部分'}計分）"
    if c <= 9:
        return "6-9 仗"
    return "10-19 仗" if c <= 19 else "20+ 仗"


def main(path):
    races = [r for r in json.load(open(path))["races"]
             if r["date"] >= "2026-08-05" and all(x.get("pos") for x in r["rows"])]
    cell, rows = collections.defaultdict(list), []
    for i, r in enumerate(races):
        ranked = sorted(r["rows"], key=lambda x: -x["ability"])
        n = len(ranked)
        fb = "<=8" if n <= 8 else "9-12" if n <= 12 else "13+"
        for k, x in enumerate(ranked, 1):
            cell[(min(k, 12), fb)].append(x["pos"] <= 3)
            rows.append((i, k, fb, x))
    exp = {k: sum(v) / len(v) for k, v in cell.items()}
    by = collections.defaultdict(list)
    for i, k, fb, x in rows:
        c = cohort(x)
        if c:
            by[c].append((i, k, (x["pos"] <= 3) - exp[(min(k, 12), fb)]))
    random.seed(7)
    print(f"場次 {len(races)}")
    for c in sorted(by):
        v = by[c]
        idx = collections.defaultdict(list)
        for i, _k, e in v:
            idx[i].append(e)
        keys = list(idx)
        boots = []
        for _ in range(1000):
            s = [e for _ in keys for e in idx[random.choice(keys)]]
            boots.append(sum(s) / len(s))
        boots.sort()
        tiers = collections.defaultdict(list)
        for _i, k, e in v:
            tiers["1-3" if k <= 3 else "4-6" if k <= 6 else "7+"].append(e)
        print(f"{c:14s} n={len(v):5d} 超額 {100 * sum(e for *_, e in v) / len(v):+5.1f}pp "
              f"[{100 * boots[25]:+.1f}, {100 * boots[975]:+.1f}] | "
              + " ".join(f"{t}:{100 * sum(tiers[t]) / max(1, len(tiers[t])):+.1f}" for t in ("1-3", "4-6", "7+")))


if __name__ == "__main__":
    main(sys.argv[1])
