"""Kelvin 2026-11-17「有啲馬房好鐘意泥地谷草轉嚟轉去，以前係蔡約翰」：練馬師 × 泥地轉場，現行模型（K2 轉場已入分）之上嘅殘差。

轉場 = 泥地→谷草、泥地→田草、谷草→泥地、田草→泥地（上仗 → 今仗）；殘差 = 入頭三 − p（k7_K2.jsonl，之前季校準）。
每個練馬師：全部（2020–25）、前段 2020–22、後段 2023–25；按賽日 bootstrap 95% CI。只列 ≥ 30 匹次。
用法：python3 diag_trainer_awt.py <k7_K2.jsonl> <kelvin7_feats.pkl>
"""
import json
import pickle
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
KEYS = ("7 泥地→谷草", "7 泥地→田草", "7 谷草→泥地", "7 田草→泥地")


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def main():
    import hkjc_history_replay_pit as p
    df = p.load_all_rows_extended()
    df = df[df["Rank"].notna()].assign(d=lambda x: x["Date"].astype(str).str[:10])
    trainer = {(r.d, int(r.RaceNo), int(r.Rank)): str(r.Trainer) for r in df.itertuples()}
    feats = pickle.load(open(sys.argv[2], "rb"))
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
    by = defaultdict(list)
    for x in rows:
        by[season(x["date"])].append(x)
    from sklearn.linear_model import LogisticRegression
    calib = {}
    for s in sorted(by):
        X, Y = [], []
        for x in ([x for t in by if t < s for x in by[t]] or by[s]):
            hs = [h for h in x["horses"] if h["pos"]]
            r = np.array([h["raw"] for h in hs]); X += list(r - r.mean()); Y += [h["pos"] <= 3 for h in hs]
        m = LogisticRegression(C=1e6, max_iter=5000).fit(np.array(X).reshape(-1, 1), Y)
        calib[s] = (m.intercept_[0], m.coef_[0][0])
    rec = defaultdict(list)       # trainer -> [(season, date, resid, kind)]
    allr = []
    for x in rows:
        s = season(x["date"])
        if s < 2020:
            continue
        hs = [h for h in x["horses"] if h["pos"]]
        r = np.array([h["raw"] for h in hs]); rc = r - r.mean()
        a, b = calib[s]
        for h, z in zip(hs, rc):
            k = (x["date"], x["race"], h["pos"])
            f = feats.get(k) or {}
            kind = next((q for q in KEYS if f.get(q)), None)
            if not kind:
                continue
            e = int(h["pos"] <= 3) - 1 / (1 + np.exp(-(a + b * z)))
            rec[trainer.get(k, "?")].append((s, x["date"], e, kind))
            allr.append(e)
    print(f"泥地轉場馬次 {len(allr)}，整體殘差 {100*np.mean(allr):+.1f}pp")
    rng = np.random.default_rng(0)

    def ci(v):
        days = defaultdict(list)
        for d, e in v:
            days[d].append(e)
        dk = list(days)
        bt = [np.mean([e for j in rng.integers(0, len(dk), len(dk)) for e in days[dk[j]]]) for _ in range(500)]
        return np.percentile(bt, 2.5), np.percentile(bt, 97.5)
    out = []
    for t, v in rec.items():
        if len(v) < 30:
            continue
        allv = [(d, e) for _, d, e, _ in v]
        early = [e for s, _, e, _ in v if s <= 2022]
        late = [e for s, _, e, _ in v if s >= 2023]
        lo, hi = ci(allv)
        out.append((np.mean([e for _, e in allv]), t, len(v), lo, hi,
                    np.mean(early) if len(early) >= 10 else None, len(early), np.mean(late) if len(late) >= 10 else None, len(late),
                    {k: sum(1 for *_, q in v if q == k) for k in KEYS}))
    out.sort(reverse=True)
    for m, t, n, lo, hi, e1, n1, e2, n2, kinds in out:
        f = lambda v: f"{100*v:+.1f}" if v is not None else "  .  "
        flag = "◆" if (lo > 0 or hi < 0) and e1 is not None and e2 is not None and (e1 > 0) == (e2 > 0) == (m > 0) else " "
        print(f"{flag} {t:<6} n={n:>3} {100*m:+.1f} [{100*lo:+.1f},{100*hi:+.1f}]｜前段 {f(e1)}（{n1}）後段 {f(e2)}（{n2}）｜"
              + " ".join(f"{k[2:]}:{c}" for k, c in kinds.items()))


if __name__ == "__main__":
    main()
