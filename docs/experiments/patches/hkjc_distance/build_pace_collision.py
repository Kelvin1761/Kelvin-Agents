"""EXP-20261124-15 預先登記（Kelvin 2026-11-24「refine」→ 步速衝突；寫喺跑之前）。尺 v5.2；base = 全面重測 base。
慣性跑法：賽日之前最多 6 仗（香港，賽果索引）「第一個沿途位置 ÷ 完成匹數」平均；≤0.3 放頭 F、>0.6 後上 B（同 run_style.py 門檻）；
  少過 2 仗 = 未知（唔計）。
PC 特徵（場內置中）：fpress = F_i ×（同場其他 F 數目）；bpay = B_i ×（全場 F 數目）。線性 L2 C=0.1、每季 walk-forward β。
  預期 fpress β < 0（放頭互相消耗）、bpay β > 0。
判：全期 dev／holdout v5.2 PASS ＋ 兩窗頭二入頭三 Δ ≥ 0。
用法：python3 build_pace_collision.py <base.jsonl> <out_prefix>
"""
import json
import re
import sys
from collections import defaultdict

import numpy as np
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
import hkjc_history_replay_build as hb  # noqa: E402


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def main():
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
    idx = hb.load_index()["results"]
    runs = defaultdict(list)      # code -> [(date, frac)]
    n2c = {}
    for (d, n), r in sorted(idx.items()):
        res = r.get("results") or []
        fin = [q for q in res if str(q.get("pos") or "").strip().isdigit()]
        for q in res:
            m = re.search(r"\(([A-Z]\d{3})\)", str(q.get("horse_name") or ""))
            if not m:
                continue
            n2c[((d, n), str(q.get("horse_no")))] = m.group(1)
            rp = str(q.get("running_positions") or "").split()
            if rp and rp[0].isdigit() and fin:
                runs[m.group(1)].append((d, int(rp[0]) / len(fin)))
    feats, cnt = {}, [0, 0]
    for x in rows:
        k = (x["date"], x["race"])
        style = []
        for h in x["horses"]:
            c = n2c.get((k, str(h["n"])))
            past = [f for d, f in runs.get(c, []) if d < x["date"]][-6:] if c else []
            if len(past) < 2:
                style.append("U")
            else:
                a = sum(past) / len(past)
                style.append("F" if a <= 0.3 else "B" if a > 0.6 else "M")
        nf = sum(s == "F" for s in style)
        m = np.array([[float(s == "F") * (nf - 1), float(s == "B") * nf] for s in style])
        cnt[0] += nf; cnt[1] += 1
        feats[(x["meeting"], x["race"])] = m - m.mean(axis=0)
    print("平均每場放頭馬", round(cnt[0] / cnt[1], 2), flush=True)
    by = defaultdict(list)
    for x in rows:
        by[season(x["date"])].append(x)
    models = {}
    for s in sorted(by):
        if s < 2020:
            continue
        R, Z, Y = [], [], []
        for x in (x for t in by if 2019 <= t < s for x in by[t]):
            keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
            r = np.array([h["raw"] for h in x["horses"]])
            R.append((r - r.mean())[keep]); Z.append(feats[(x["meeting"], x["race"])][keep]); Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
        R, Z, Y = np.concatenate(R), np.vstack(Z), np.array(Y)
        sd = Z.std(axis=0); sd[sd == 0] = 1; rs = R.std()
        c = LogisticRegression(C=0.1, max_iter=20000).fit(np.column_stack([R / rs, Z / sd]), Y).coef_[0]
        models[s] = (c[1:] / sd) / (c[0] / rs)
    print("PC β（fpress, bpay）", {s: [round(float(b), 3) for b in m] for s, m in models.items()}, flush=True)
    with open(f"{sys.argv[2]}_PC.jsonl", "w") as f:
        for x in rows:
            s = season(x["date"]); y = dict(x, arm="pace_collision")
            if s in models:
                new = np.array([h["raw"] for h in x["horses"]]) + feats[(x["meeting"], x["race"])] @ models[s]
                y["horses"] = [dict(h, raw=round(float(v), 4)) for h, v in zip(x["horses"], new)]
                y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
            f.write(json.dumps(y, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
