"""研究計劃第 8 步候選：初出馬加「練馬師初出上名率」（篩選 dev Holm 0.010、holdout CI 全正）。

預先登記（跑之前寫死）：raw' = raw + δ × z(T)，只限 debut=True 嘅馬；T 同篩選一樣（as-of、收縮 k=10）；
z 用 2024-08 前嘅初出馬 mean／SD；δ ∈ {0.25, 0.5, 0.75, 1.0}，dev 逐季 walk-forward 揀（之前季、有初出馬嘅場、Gold+Good 最高），
holdout 用全 dev 揀出嘅 δ 一次。
用法：python3 hkjc_replay_debut_trainer_arm.py <base.jsonl> <replay_index.pkl> <outdir>
"""
import json
import pickle
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / ".agents/skills/shared_racing"))
from eval_metrics import race_metrics  # noqa: E402

K = 10


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def main():
    rows = sorted((json.loads(l) for l in open(sys.argv[1]) if '"horses"' in l), key=lambda x: (x["date"], x["race"]))
    idx = pickle.load(open(sys.argv[2], "rb"))
    out = Path(sys.argv[3]); out.mkdir(parents=True, exist_ok=True)
    hist, buf, cur, T = defaultdict(lambda: [0, 0]), [], None, {}
    for x in rows:
        if x["date"] != cur:
            for tr, p in buf:
                hist[tr][0] += p; hist[tr][1] += 1
            buf.clear(); cur = x["date"]
        res = idx["results"].get((x["date"], x["race"])) or {}
        trainer = {str(r.get("horse_no")): r.get("trainer") for r in res.get("results", [])}
        for h in x["horses"]:
            if h.get("debut"):
                tr = trainer.get(str(h["n"])) or "?"
                t = hist[tr]
                T[(x["meeting"], x["race"], h["n"])] = (t[0] + 0.25 * K) / (t[1] + K)
                if h["pos"]:
                    buf.append((tr, int(h["pos"] <= 3)))
    ref = np.array([v for (m, r, n), v in T.items() if m[:10] < "2024-08-01"])
    mu, sd = ref.mean(), ref.std()

    def apply(x, d):
        hs = [dict(h, raw=h["raw"] + d * (T[(x["meeting"], x["race"], h["n"])] - mu) / sd) if h.get("debut") else h for h in x["horses"]]
        ns = np.array([h["n"] for h in hs]); raw = np.array([h["raw"] for h in hs])
        return dict(x, horses=hs, picks=[int(v) for v in ns[np.lexsort((ns, -raw))]])

    def score(xs):
        s = []
        for x in xs:
            pos = {h["n"]: h["pos"] for h in x["horses"] if h["pos"]}; top = [k for k, p in pos.items() if p <= 3]
            if len(top) >= 3:
                m = race_metrics(x["picks"], top, actual_pos=pos); s.append(float(m["gold"]) + float(m["good_positional"]))
        return np.mean(s) if s else 0
    D = (0.25, 0.5, 0.75, 1.0)
    dev = [x for x in rows if "2020-09-01" <= x["date"] <= "2024-07-31" and any(h.get("debut") for h in x["horses"])]
    wf = {ts: max(D, key=lambda d: score([apply(x, d) for x in dev if season(x["date"]) < ts])) for ts in (2021, 2022, 2023)}
    full = max(D, key=lambda d: score([apply(x, d) for x in dev]))
    print("walk-forward δ：", wf, "；全 dev δ：", full, f"；T mean {mu:.3f} SD {sd:.3f}")
    with open(out / "wf.jsonl", "w") as fh:
        for x in rows:
            if "2020-09-01" <= x["date"] <= "2024-07-31" and season(x["date"]) in wf:
                fh.write(json.dumps(apply(x, wf[season(x["date"])]), ensure_ascii=False) + "\n")
    with open(out / "full.jsonl", "w") as fh:
        for x in rows:
            fh.write(json.dumps(apply(x, full), ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
