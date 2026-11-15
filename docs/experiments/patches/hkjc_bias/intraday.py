"""EXP-20261115-11：即場跑法偏差（Kelvin「應唔應該即場調整」）。
第 k 場賽前：同日同場地同跑道類型（草地／泥地）、場次 < k 嘅入位馬早段位置平均 = 當日偏差 m（最少 2 場、6 匹）。
匹馬習慣跑法 h = 近 3 仗早段位置平均（只用之前日子）。特徵 I = (0.5 − m) × (0.5 − h) × 4（前領著數日 × 前領馬 → 正）。
live 可行：賽日 intraday job 喺每場之間重新評分（要嗰陣有之前場次嘅走位）。
用法：python3 intraday.py <base.jsonl> <outdir>
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import build as b  # noqa: E402


def features():
    import hkjc_history_replay_pit as p
    df = p.load_all_rows_extended()
    df = df[df["Rank"].notna()].copy()
    df["d"] = df["Date"].astype(str).str[:10]
    sr = b.sectional_rails()
    df["rail"] = [sr.get((d, int(n))) or b.rail(c) for d, n, c in zip(df["d"], df["RaceNo"], df["Course"])]
    df["surf"] = np.where(df["rail"] == "AWT", "AWT", "TURF")
    df["F"] = df.groupby(["d", "RaceNo"])["Rank"].transform("count")
    df["e1"] = df["RunningPos"].map(lambda s: int(re.match(r"\s*(\d+)", str(s)).group(1)) if re.match(r"\s*(\d+)", str(s)) else None)
    df["ef"] = (df["e1"] - 1) / (df["F"] - 1).clip(lower=1)
    df = df.sort_values(["d", "RaceNo"])
    hist = defaultdict(list)
    out, pairs = {}, []
    for d, g in df.groupby("d", sort=True):
        placed = defaultdict(list)       # (venue, surf) -> [(race, ef)]
        races = sorted(g["RaceNo"].unique())
        for rn in races:
            rr = g[g["RaceNo"] == rn]
            for r in rr.itertuples():
                key = (r.Venue, r.surf)
                prior = [e for (k, e) in placed[key]]
                nr = len({k for (k, _) in placed[key]})
                m = float(np.mean(prior)) if nr >= 2 and len(prior) >= 6 else None
                past = [x for x in hist[r.HorseID] if x[0] < d and x[1] == x[1]][-3:]
                h = float(np.mean([x[1] for x in past])) if past else None
                I = (0.5 - m) * (0.5 - h) * 4 if m is not None and h is not None else None
                out.setdefault((d, int(r.RaceNo), int(r.Rank)), []).append((I, m))
            # 本場完咗：入位馬加入當日偏差
            racebias = []
            for r in rr.itertuples():
                if r.Rank <= 3 and r.ef == r.ef:
                    placed[(r.Venue, r.surf)].append((rn, r.ef)); racebias.append(r.ef)
            pk = (rr["Venue"].iloc[0], rr["surf"].iloc[0])
            prior_m = [e for (k, e) in placed[pk] if k < rn]
            if len({k for (k, _) in placed[pk] if k < rn}) >= 2 and racebias:
                pairs.append((float(np.mean(prior_m)), float(np.mean(racebias))))
        for r in g.itertuples():
            hist[r.HorseID].append((d, r.ef))
    a = np.array(pairs)
    print("當日較早場次偏差 vs 本場入位馬早段位置：corr", round(np.corrcoef(a[:, 0], a[:, 1])[0, 1], 3), "n 場", len(a))
    return out


def main():
    feat = features()
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
    out = Path(sys.argv[2])
    by = defaultdict(list)
    for x in rows:
        by[b.season(x["date"])].append(x)
    import types
    b.IDX["I"] = 0
    betas = {s: b.fit([x for t in by if t < min(s, 2024) for x in by[t]], feat, "I") for s in sorted(by) if s > 2019}
    with open(out / "bias_I.jsonl", "w") as f:
        for x in rows:
            bb = betas.get(b.season(x["date"]))
            y = dict(x, arm="bias_I")
            if bb is not None:
                add = b.race_feats(x, feat, "I") @ bb
                y["horses"] = [dict(h, raw=round(h["raw"] + float(v), 4)) for h, v in zip(x["horses"], add)]
                y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
            f.write(json.dumps(y, ensure_ascii=False) + "\n")
    print("β", {s: np.round(v, 2).tolist() for s, v in betas.items() if s <= 2024})


if __name__ == "__main__":
    main()
