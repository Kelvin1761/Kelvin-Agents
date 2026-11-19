"""Kelvin 2026-11-19（11-18 R9 耀寶：近三仗都塞車，模型排 4、贏）：連續有藉口（塞車／走外疊／騎法被質疑）嘅馬，live 之上殘差。
殘差 = 入頭三 − p，p = live dump raw 用之前季校準（diag_full.calibrate）。只用日期嚴格早過今仗嘅賽後事件報告。
用法：python3 diag_excuse_streak.py <live dump> <old_incidents.json>
"""
import json, re, sys
from collections import defaultdict
import numpy as np
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
sys.path.insert(0, "/Users/imac/Antigravity-repo/docs/experiments/patches/hkjc_incidents")
import hkjc_history_replay_build as b  # noqa: E402
from diag import CATS, season  # noqa: E402
from diag_full import calibrate, load_runs  # noqa: E402
from diag_round3 import INSTR, RIDE_Q, RIDE_WARN  # noqa: E402

BLK = CATS["受阻／搵唔到位"]; W = CATS["走外疊冇遮擋"]; SLOW = CATS["出閘慢／失地"]
RIDE = f"{INSTR}|{RIDE_Q}|{RIDE_WARN}"
INTERF = r"被碰撞|失去平衡|受擠迫|受妨礙|被夾|窄位"
STRICT = f"{BLK}|{W}|{RIDE}"
BROAD = f"{STRICT}|{INTERF}|{SLOW}"
def has(p, s): return bool(s) and bool(re.search(p, s))

def features(prev):
    """prev = [(date, race, sentence|None, no, pos)] 舊→新；要最近兩仗都有報告。"""
    if len(prev) < 2 or prev[-1][2] is None or prev[-2][2] is None:
        return None
    l1, l2 = prev[-1], prev[-2]
    l3 = prev[-3] if len(prev) >= 3 and prev[-3][2] is not None else None
    s1, s2 = has(STRICT, l1[2]), has(STRICT, l2[2])
    b1, b2 = has(BROAD, l1[2]), has(BROAD, l2[2])
    unpl = lambda t: t[4] is None or t[4] >= 4
    return {
        "嚴格：上兩仗都有藉口": s1 and s2,
        "嚴格：上三仗都有藉口": s1 and s2 and l3 is not None and has(STRICT, l3[2]),
        "嚴格：上兩仗都有藉口＋兩仗都未入位": s1 and s2 and unpl(l1) and unpl(l2),
        "嚴格：只係上仗有（上上仗冇，對照）": s1 and not s2,
        "嚴格：只係上上仗有（上仗冇，對照）": s2 and not s1,
        "受阻：上兩仗都受阻": has(BLK, l1[2]) and has(BLK, l2[2]),
        "受阻：上三仗都受阻": has(BLK, l1[2]) and has(BLK, l2[2]) and l3 is not None and has(BLK, l3[2]),
        "闊：上兩仗都有藉口": b1 and b2,
        "闊：上兩仗都有藉口＋兩仗都未入位": b1 and b2 and unpl(l1) and unpl(l2),
        "冇藉口：上兩仗都冇（對照）": not b1 and not b2,
    }

def main():
    runs = load_runs(sys.argv[2])
    idx = b.load_index(); pos = {}
    for (d, n), race in idx["results"].items():
        for row in race.get("results", []):
            try: pos[(d, n, str(row.get("horse_no")))] = int(str(row.get("pos")).strip())
            except ValueError: pos[(d, n, str(row.get("horse_no")))] = None
    runs = {c: [(d, n, s, no, pos.get((d, n, no))) for d, n, s, no in v] for c, v in runs.items()}
    code_of = {(d, n, hn): c for c, v in runs.items() for d, n, _, hn, _ in v}
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
    calib = calibrate(rows); recs = []
    for x in rows:
        s = season(x["date"])
        if s < 2020: continue
        hs = [h for h in x["horses"] if h["pos"]]
        r = np.array([h["raw"] for h in hs]); rc = r - r.mean(); a, bb = calib[s]
        rank = {h["n"]: i + 1 for i, h in enumerate(sorted(hs, key=lambda h: -h["raw"]))}
        for h, z in zip(hs, rc):
            c = code_of.get((x["date"], x["race"], str(h["n"])))
            if not c: continue
            f = features([v for v in runs[c] if v[0] < x["date"]])
            if f is None: continue
            recs.append(dict(s=s, y=int(h["pos"] <= 3), w=int(h["pos"] == 1), p=1 / (1 + np.exp(-(a + bb * z))), f=f, rk=rank[h["n"]]))
    print("馬次", len(recs))
    rng = np.random.default_rng(0)
    for k in recs[0]["f"]:
        out = []
        for lo, hi in ((2020, 2023), (2024, 2025)):
            sub = [r for r in recs if lo <= r["s"] <= hi]
            sel = [r for r in sub if r["f"][k]]
            if len(sel) < 30: out.append(f"n={len(sel)}"); continue
            y = np.array([r["y"] - r["p"] for r in sel])
            bt = [y[rng.integers(0, len(y), len(y))].mean() for _ in range(1000)]
            mid = [r for r in sel if 3 <= r["rk"] <= 6]
            out.append(f"{100*y.mean():+.1f}[{100*np.percentile(bt,2.5):+.1f},{100*np.percentile(bt,97.5):+.1f}] n={len(sel)}({100*len(sel)/len(sub):.1f}%) "
                       f"模型排3–6:{len(mid)}匹 實{100*np.mean([r['y'] for r in mid]) if mid else 0:.0f}%/估{100*np.mean([r['p'] for r in mid]) if mid else 0:.0f}%")
        seas = [f"{100*np.mean([r['y']-r['p'] for r in recs if r['s']==s and r['f'][k]]):+.0f}" if sum(1 for r in recs if r['s']==s and r['f'][k]) >= 20 else "." for s in sorted({r['s'] for r in recs})]
        print(f"{k}\n   dev {out[0]}\n   ho  {out[1]}\n   逐季 {' '.join(seas)}")

if __name__ == "__main__":
    main()
