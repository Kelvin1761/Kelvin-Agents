"""EXP-20261117-05（預先登記見 EXP-20261117-05-hkjc-joint-refit-protocol.md）：13 個「有訊號但單獨入唔到分」特徵一齊 refit。
J1 = 線性 L2（C=0.1）、J2 = GBM；每季 walk-forward。base = live（dist_D1.jsonl）。
用法：python3 build_joint.py <dist_D1.jsonl> <old_incidents.json> <out_prefix>
"""
import json
import re
import sys
from collections import defaultdict
from datetime import date

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
sys.path.insert(0, "/Users/imac/Antigravity-repo/docs/experiments/patches/hkjc_patterns")
sys.path.insert(0, "/Users/imac/Antigravity-repo/docs/experiments/patches/hkjc_incidents")
import features as F  # noqa: E402
from diag import CATS  # noqa: E402
from diag_full import load_runs  # noqa: E402
from diag_round3 import BLK, INSTR, RIDE_Q, RIDE_WARN, SLOW, has  # noqa: E402

NAMES = ["ride_q", "wide2", "blocked2", "slow", "rb_placed", "rb_any", "drop_rb", "old_won",
         "gear_off", "gear_on", "dist_down", "class_pos", "backup10"]
RIDE = f"{INSTR}|{RIDE_Q}|{RIDE_WARN}"
WIDE = CATS["走外疊冇遮擋"]
BAND_HIGH = {5: 40, 4: 60, 3: 80}


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def gear_set(g):
    return {x for x in re.split(r"[/\s]+", str(g or "").upper()) if x and x not in ("-", "--")}


def page_feats(rr, i):
    t, past = rr[i], rr[:i]
    out = dict.fromkeys(NAMES[4:], 0.0)
    if not past:
        return out
    last = past[-1]
    tr, tc = F.num(t.get("rating")), F.num(t.get("class"))
    lc, lp = F.num(last.get("class")), F.pos(last.get("pos"))
    drop = bool(tc and lc and tc > lc)
    wins = [F.num(q.get("rating")) for q in past if F.pos(q.get("pos")) == 1 and F.num(q.get("rating")) is not None]
    if wins and tr is not None:
        back = tr <= wins[-1]
        out["rb_any"] = float(back and not drop)
        out["rb_placed"] = float(back and not drop and lp is not None and lp <= 3)
        out["drop_rb"] = float(back and drop)
    elite = (tr is not None and tr >= 95) or (tc is not None and tc <= 2)
    out["old_won"] = float(len(past) >= 35 and lp == 1 and not elite)
    gt, gl = gear_set(t.get("gear")), gear_set(last.get("gear"))
    ever = set().union(*(gear_set(q.get("gear")) for q in past))
    out["gear_off"] = float(bool(gl - gt))
    out["gear_on"] = float(bool(gt - ever))
    d, pd = F.num(t.get("distance")), F.num(last.get("distance"))
    out["dist_down"] = float(bool(d and pd and pd - d >= 400))
    out["class_pos"] = (tr - BAND_HIGH[int(tc)]) / 10.0 if (tr is not None and tc in BAND_HIGH) else 0.0
    out["backup10"] = float((date.fromisoformat(t["d"]) - date.fromisoformat(last["d"])).days <= 10)
    return out


def inc_feats(prev):
    out = dict.fromkeys(NAMES[:4], 0.0)
    rep = [v[2] for v in prev if v[2] is not None]
    if not prev or prev[-1][2] is None:
        return out
    last = prev[-1][2]
    out["ride_q"] = float(has(RIDE, last))
    out["wide2"] = float(len(rep) >= 2 and has(WIDE, rep[-2]) and not has(WIDE, last))
    out["blocked2"] = float(has(BLK, last) or (len(rep) >= 2 and has(BLK, rep[-2])))
    out["slow"] = float(has(SLOW, last))
    return out


def main():
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
    inc = load_runs(sys.argv[2])
    code_of = {(d, n, hn): c for c, v in inc.items() for d, n, _, hn in v}
    pages, _ = F.load()
    pidx = {c: {q["d"]: i for i, q in enumerate(rr)} for c, rr in pages.items()}
    X = {}
    for x in rows:
        mat = []
        for h in x["horses"]:
            c = code_of.get((x["date"], x["race"], str(h["n"])))
            f = dict.fromkeys(NAMES, 0.0)
            if c:
                f.update(inc_feats([v for v in inc[c] if v[0] < x["date"]]))
                i = pidx.get(c, {}).get(x["date"])
                if i is not None:
                    f.update(page_feats(pages[c], i))
            mat.append([f[k] for k in NAMES])
        m = np.array(mat, dtype=float)
        X[id(x)] = m - m.mean(axis=0)
    allX = np.vstack(list(X.values()))
    print("特徵非零比例", {k: round(float((allX[:, j] != 0).mean()), 4) for j, k in enumerate(NAMES)}, flush=True)
    by = defaultdict(list)
    for x in rows:
        by[season(x["date"])].append(x)

    def design(races):
        R, Z, Y = [], [], []
        for x in races:
            keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
            r = np.array([h["raw"] for h in x["horses"]])
            R.append((r - r.mean())[keep]); Z.append(X[id(x)][keep]); Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
        return np.concatenate(R), np.vstack(Z), np.array(Y)

    for arm in ("J1", "J2"):
        models = {}
        for s in sorted(by):
            if s < 2020:
                continue
            R, Z, Y = design([x for t in by if 2019 <= t < s for x in by[t]])
            if arm == "J1":
                sd = Z.std(axis=0); sd[sd == 0] = 1
                rs = R.std()
                c = LogisticRegression(C=0.1, max_iter=20000).fit(np.column_stack([R / rs, Z / sd]), Y).coef_[0]
                models[s] = (c[1:] / sd) / (c[0] / rs)
                print(arm, s, {k: round(float(b), 2) for k, b in zip(NAMES, models[s])}, flush=True)
            else:
                models[s] = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200,
                                                           min_samples_leaf=200, l2_regularization=1.0,
                                                           random_state=0).fit(np.column_stack([R, Z]), Y)
                print(arm, s, "fit", len(Y), flush=True)
        with open(f"{sys.argv[3]}_{arm}.jsonl", "w") as f:
            for x in rows:
                s = season(x["date"])
                y = dict(x, arm=f"joint_{arm}")
                if s in models:
                    r = np.array([h["raw"] for h in x["horses"]]); rc = r - r.mean()
                    if arm == "J1":
                        new = r + X[id(x)] @ models[s]
                    else:
                        p = models[s].predict_proba(np.column_stack([rc, X[id(x)]]))[:, 1].clip(1e-6, 1 - 1e-6)
                        new = np.log(p / (1 - p))
                    y["horses"] = [dict(h, raw=round(float(v), 4)) for h, v in zip(x["horses"], new)]
                    y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
                f.write(json.dumps(y, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
