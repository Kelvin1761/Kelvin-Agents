"""Kelvin 決定 5／7：分段專屬訊號排名候選（篩選過關：直路 S3、泥地 A1、A2）。

預先登記：只限該分段賽事，raw' = raw + δ × z(特徵)（z 用 dev 非缺失值 mean／SD；缺失 = 0）；
δ ∈ {0.25, 0.5, 0.75, 1.0}，dev 逐季 walk-forward 揀（之前季、該分段、Gold+Good），holdout 用全 dev δ 一次。
用法：python3 hkjc_replay_segment_arm.py <base.jsonl> <features.pkl> <feature> <outdir>
"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / ".agents/skills/shared_racing"))
from eval_metrics import race_metrics  # noqa: E402

def season(d): return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1

def main():
    base, fp, feat, out = sys.argv[1], sys.argv[2], sys.argv[3], Path(sys.argv[4]); out.mkdir(parents=True, exist_ok=True)
    D = pd.read_pickle(fp)
    dev = D[(D.date >= "2020-09-01") & (D.date <= "2024-07-31")][feat].dropna()
    mu, sd = dev.mean(), dev.std()
    zmap = {(r.race[0], r.race[1], r.n): (getattr(r, feat) - mu) / sd for r in D.itertuples() if not pd.isna(getattr(r, feat))}
    seg_races = {tuple(r) for r in D.race}
    rows = [json.loads(l) for l in open(base) if '"horses"' in l]
    def apply(x, d):
        if (x["meeting"], x["race"]) not in seg_races: return x
        hs = [dict(h, raw=h["raw"] + d * zmap.get((x["meeting"], x["race"], h["n"]), 0.0)) for h in x["horses"]]
        ns = np.array([h["n"] for h in hs]); raw = np.array([h["raw"] for h in hs])
        return dict(x, horses=hs, picks=[int(v) for v in ns[np.lexsort((ns, -raw))]])
    def score(xs):
        s = []
        for x in xs:
            pos = {h["n"]: h["pos"] for h in x["horses"] if h["pos"]}; tp = [k for k, p in pos.items() if p <= 3]
            if len(tp) >= 3:
                m = race_metrics(x["picks"], tp, actual_pos=pos); s.append(float(m["gold"]) + float(m["good_positional"]))
        return np.mean(s)
    Ds = (0.25, 0.5, 0.75, 1.0)
    devr = [x for x in rows if "2020-09-01" <= x["date"] <= "2024-07-31" and (x["meeting"], x["race"]) in seg_races]
    wf = {ts: max(Ds, key=lambda d: score([apply(x, d) for x in devr if season(x["date"]) < ts])) for ts in (2021, 2022, 2023)}
    full = max(Ds, key=lambda d: score([apply(x, d) for x in devr]))
    print(f"{feat}：walk-forward δ {wf}；全 dev δ {full}")
    with open(out / f"{feat}_wf.jsonl", "w") as fh:
        for x in devr:
            if season(x["date"]) in wf: fh.write(json.dumps(apply(x, wf[season(x["date"])]), ensure_ascii=False) + "\n")
    with open(out / f"{feat}_base.jsonl", "w") as fh:
        for x in rows:
            if (x["meeting"], x["race"]) in seg_races: fh.write(json.dumps(x, ensure_ascii=False) + "\n")
    with open(out / f"{feat}_full.jsonl", "w") as fh:
        for x in rows:
            if (x["meeting"], x["race"]) in seg_races: fh.write(json.dumps(apply(x, full), ensure_ascii=False) + "\n")

if __name__ == "__main__":
    main()
