"""研究計劃第 9b 步候選：「換上頂級騎師」（篩選 dev Holm 0.040、holdout +0.036 [+0.006,+0.065]；EXP-20261027-12 P1 舊候選）。

預先登記：jockey_up 定義同 hkjc_replay_intent_screen.py（頂級 = 賽日前 365 日騎師入頭三率頭 5 名、≥50 騎；上仗騎師唔係頂級、今仗係）；
raw' = raw + δ（jockey_up 嘅非初出馬）；δ ∈ {0.25, 0.5, 0.75, 1.0}，dev 逐季 walk-forward 揀（Gold+Good），holdout 用全 dev δ 一次。
用法：python3 hkjc_replay_jockey_up_arm.py <base.jsonl> <replay_index.pkl> <outdir>
"""
import datetime as dt, json, pickle, re, sys
from collections import defaultdict, deque
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / ".agents/skills/shared_racing"))
from eval_metrics import race_metrics  # noqa: E402

def season(d): return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1

def main():
    rows = sorted((json.loads(l) for l in open(sys.argv[1]) if '"horses"' in l), key=lambda x: (x["date"], x["race"]))
    idx = pickle.load(open(sys.argv[2], "rb")); out = Path(sys.argv[3]); out.mkdir(parents=True, exist_ok=True)
    jrows = defaultdict(list)
    for (d, n), r in idx["results"].items():
        for x in r.get("results", []):
            p = str(x.get("pos") or "")
            if p[:1].isdigit(): jrows[d].append((x.get("jockey"), int(re.match(r"\d+", p).group()) <= 3))
    agg, window, top = defaultdict(lambda: [0, 0]), deque(), {}
    for d in sorted({d for d, _ in idx["results"]}):
        cut = (dt.date.fromisoformat(d) - dt.timedelta(days=365)).isoformat()
        while window and window[0][0] < cut:
            _, j, p = window.popleft(); agg[j][0] -= p; agg[j][1] -= 1
        top[d] = {j for _, j in sorted(((a[0] / a[1], j) for j, a in agg.items() if a[1] >= 50), reverse=True)[:5]}
        for j, p in jrows[d]:
            window.append((d, j, int(p))); agg[j][0] += p; agg[j][1] += 1
    flag = {}
    for x in rows:
        sec = idx["sect"].get((x["date"], x["race"])) or {}; res = idx["results"].get((x["date"], x["race"])) or {}
        no2id = {str(h.get("horse_no")): h.get("horse_id") for h in sec.get("horses", [])}
        jk = {str(r.get("horse_no")): r.get("jockey") for r in res.get("results", [])}
        T = top.get(x["date"], set())
        for h in x["horses"]:
            if h.get("debut"): continue
            runs = (idx["horses"].get(no2id.get(str(h["n"]))) or {}).get("runs", [])
            past = [r for r in runs if r["iso"] < x["date"] and str(r.get("pos", ""))[:1].isdigit()]
            if past and jk.get(str(h["n"])) in T and past[0].get("jockey") not in T:
                flag[(x["meeting"], x["race"], h["n"])] = True
    def apply(x, d):
        hs = [dict(h, raw=h["raw"] + d) if flag.get((x["meeting"], x["race"], h["n"])) else h for h in x["horses"]]
        ns = np.array([h["n"] for h in hs]); raw = np.array([h["raw"] for h in hs])
        return dict(x, horses=hs, picks=[int(v) for v in ns[np.lexsort((ns, -raw))]])
    def score(xs):
        s = []
        for x in xs:
            pos = {h["n"]: h["pos"] for h in x["horses"] if h["pos"]}; tp = [k for k, p in pos.items() if p <= 3]
            if len(tp) >= 3:
                m = race_metrics(x["picks"], tp, actual_pos=pos); s.append(float(m["gold"]) + float(m["good_positional"]))
        return np.mean(s)
    D = (0.25, 0.5, 0.75, 1.0)
    dev = [x for x in rows if "2020-09-01" <= x["date"] <= "2024-07-31"]
    wf = {ts: max(D, key=lambda d: score([apply(x, d) for x in dev if season(x["date"]) < ts])) for ts in (2021, 2022, 2023)}
    full = max(D, key=lambda d: score([apply(x, d) for x in dev]))
    print("walk-forward δ：", wf, "；全 dev δ：", full, "；jockey_up 匹次", len(flag))
    with open(out / "wf.jsonl", "w") as fh:
        for x in dev:
            if season(x["date"]) in wf: fh.write(json.dumps(apply(x, wf[season(x["date"])]), ensure_ascii=False) + "\n")
    with open(out / "full.jsonl", "w") as fh:
        for x in rows: fh.write(json.dumps(apply(x, full), ensure_ascii=False) + "\n")

if __name__ == "__main__":
    main()
