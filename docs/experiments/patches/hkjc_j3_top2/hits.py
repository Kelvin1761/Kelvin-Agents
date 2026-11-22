"""每個候選：頭二入面入頭三匹數、首選贏、頭二有冒包尾（≥10 名）—— dev／holdout，按賽日 bootstrap。"""
import json
from collections import defaultdict
import numpy as np
V = "/Volumes/Kelvin Hardisk 1/WongChoi-Archive/hkjc-history"
def load(p): return {(x["meeting"], x["race"]): x for x in map(json.loads, open(p)) if "horses" in x}
PAIRS = {"D1 大幅增程（已上）": ("analysis/replay_all/v4/incident_I1.jsonl", "analysis/replay_all/v4/dist_D1.jsonl"),
         "V2 同程場地（已上）": ("analysis/replay_all/v4/cons/base_fixed.jsonl", "scratch/samedist_venue/cand_V2.jsonl"),
         "A2 馬齡（已上）": ("analysis/replay_all/v4/cons/base_fixed.jsonl", "scratch/samedist_venue/age_A2.jsonl"),
         "J3 聯合訊號": ("analysis/replay_all/v4/cons/base_live_20261122.jsonl", "scratch/joint_plus/jl_J3.jsonl")}
for name, (b, c) in PAIRS.items():
    B, C = load(f"{V}/{b}"), load(f"{V}/{c}")
    for w, (lo, hi) in (("dev", ("2020-09-01", "2024-07-31")), ("holdout", ("2024-09-01", "2026-07-31"))):
        rows, days = [], []
        for k, x in B.items():
            if not (lo <= x["date"] <= hi) or k not in C: continue
            pos = {h["n"]: h["pos"] for h in x["horses"] if h["pos"]}
            if sum(1 for p in pos.values() if p <= 3) < 3: continue
            def m(picks):
                p2 = [n for n in picks if n in pos][:2]
                return [sum(pos[n] <= 3 for n in p2), float(pos[p2[0]] == 1), sum(pos[n] >= 10 for n in p2)]
            rows.append(np.array(m(C[k]["picks"])) - np.array(m(x["picks"]))); days.append(x["date"])
        R = np.array(rows, float); byd = defaultdict(list)
        for i, d in enumerate(days): byd[d].append(i)
        dd = sorted(byd); rng = np.random.default_rng(0)
        bs = np.array([R[np.concatenate([byd[dd[j]] for j in rng.integers(0, len(dd), len(dd))])].sum(0) for _ in range(1000)])
        tot = R.sum(0); lo_, hi_ = np.percentile(bs, [2.5, 97.5], axis=0)
        print(f"{name}｜{w} {len(R)} 場｜頭二入頭三 {tot[0]:+.0f} 匹 [{lo_[0]:+.0f},{hi_[0]:+.0f}]｜首選贏 {tot[1]:+.0f} [{lo_[1]:+.0f},{hi_[1]:+.0f}]｜頭二有包尾級（≥10 名）{tot[2]:+.0f} [{lo_[2]:+.0f},{hi_[2]:+.0f}]")
