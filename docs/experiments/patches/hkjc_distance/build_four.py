"""EXP-20261124-16 四個方向（預先登記：docs/experiments/EXP-20261124-16-hkjc-four-directions-prereg.md）。
用法：
  python3 build_four.py LO   <db_DT.jsonl> <out_prefix>
  python3 build_four.py SE   <db_DT.jsonl> <out_prefix>
  python3 build_four.py NRGs <db_DT.jsonl> <out_prefix>
  python3 build_four.py B3   <db_DT.jsonl> <out_prefix> <DG.jsonl> <AF.jsonl> <TR1.jsonl>
"""
import json
import re
import sys
from collections import defaultdict

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, "/Users/imac/Antigravity-repo")
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts")
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
sys.path.insert(0, "/Users/imac/Antigravity-repo/docs/experiments/patches/hkjc_patterns")
from hkjc_racing_engine import performance_figure as PF  # noqa: E402
import hkjc_history_replay_build as hb  # noqa: E402

SW_BETA_FIG = 4.99   # live performance_figure figW 系數


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def codes_weights(idx):
    n2c, wt = {}, {}
    for k, r in idx.items():
        for q in r.get("results") or []:
            m = re.search(r"\(([A-Z]\d{3})\)", str(q.get("horse_name") or ""))
            if m:
                n2c[(k, str(q.get("horse_no")))] = m.group(1)
                try:
                    wt[(k, str(q.get("horse_no")))] = float(q.get("actual_wt"))
                except (TypeError, ValueError):
                    pass
    return n2c, wt


def write_arm(rows, feats_or_delta, out, arm, fit=True):
    """fit=True：feats = {(date,race): ndarray n×p}，walk-forward β；fit=False：直接加 delta（n,）。"""
    by = defaultdict(list)
    for x in rows:
        by[season(x["date"])].append(x)
    models = {}
    if fit:
        p = next(iter(feats_or_delta.values())).shape[1]
        zero = lambda x: np.zeros((len(x["horses"]), p))  # noqa: E731
        for s in sorted(by):
            if s < 2020:
                continue
            Rr, Z, Y = [], [], []
            for x in (x for t in by if 2019 <= t < s for x in by[t]):
                keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
                r = np.array([h["raw"] for h in x["horses"]])
                Rr.append((r - r.mean())[keep]); Z.append(feats_or_delta.get((x["date"], x["race"]), zero(x))[keep])
                Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
            Rr, Z, Y = np.concatenate(Rr), np.vstack(Z), np.array(Y)
            sd = Z.std(axis=0); sd[sd == 0] = 1; rs = Rr.std()
            c = LogisticRegression(C=0.1, max_iter=20000).fit(np.column_stack([Rr / rs, Z / sd]), Y).coef_[0]
            models[s] = (c[1:] / sd) / (c[0] / rs)
        print(arm, "β", {s: [round(float(b), 2) for b in m] for s, m in models.items()}, flush=True)
    with open(f"{out}_{arm}.jsonl", "w") as f:
        for x in rows:
            s = season(x["date"]); k = (x["date"], x["race"]); y = dict(x, arm=f"four_{arm}")
            add = None
            if fit and s in models and k in feats_or_delta:
                add = feats_or_delta[k] @ models[s]
            elif not fit and k in feats_or_delta:
                add = feats_or_delta[k]
            if add is not None:
                new = np.array([h["raw"] for h in x["horses"]]) + add
                y["horses"] = [dict(h, raw=round(float(v), 4)) for h, v in zip(x["horses"], new)]
                y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
            f.write(json.dumps(y, ensure_ascii=False) + "\n")


def wfig(runs, today_w, need=2):
    num = den = 0.0; ok = 0
    for k, (fv, w, km) in enumerate(runs, 1):
        if fv != fv:
            continue
        ok += 1; num += (fv - PF.BETA_LB * (today_w - w) * km) / k; den += 1.0 / k
    return num / den if ok >= need else None


# ---------- A. LO ----------
def per_run_both(R, D):
    P = R[R.date < D]
    m = (P.beaten <= 3).values
    adj = (P.tkm - PF.BETA_LB * P.w).values[m]
    hs, rc = P.hs.values[m], P.race.values[m]
    rfe = np.zeros(len(adj))
    for _ in range(15):
        hfe = pd.Series(adj - rfe).groupby(hs).transform("mean").values
        rfe = pd.Series(adj - hfe).groupby(rc).transform("mean").values
    rmap = pd.Series(rfe, index=rc).groupby(level=0).first()
    base_eff = P.race.map(rmap).values
    resid = adj - hfe
    ssum = pd.Series(resid).groupby(rc).transform("sum").values
    cnt = pd.Series(resid).groupby(rc).transform("count").values
    loo = np.where(cnt > 1, (ssum - resid) / np.maximum(cnt - 1, 1), rfe)
    eff_lo = base_eff.copy()
    eff_lo[np.where(m)[0]] = loo
    f = -(P.tkm_cap.values - base_eff)
    flo = -(P.tkm_cap.values - eff_lo)
    return P.assign(fig=f - np.nanmean(f), flo=flo - np.nanmean(flo))


def arm_LO(rows, out):
    idx = hb.load_index()["results"]
    n2c, wt = codes_weights(idx)
    R = PF.load_results()
    targets = [x for x in rows if x["date"] >= "2019-09-01"]
    dates = sorted({x["date"] for x in targets})
    delta = {}
    for i, D in enumerate(dates):
        P = per_run_both(R, D)
        g = {c: grp for c, grp in P.groupby("code", sort=False)}
        if i % 50 == 0:
            print(" ", i, len(dates), D, flush=True)
        for x in (t for t in targets if t["date"] == D):
            k = (x["date"], x["race"]); d = np.zeros(len(x["horses"]))
            for j, h in enumerate(x["horses"]):
                c = n2c.get((k, str(h["n"]))); w = wt.get((k, str(h["n"])))
                if not c or c not in g or w is None:
                    continue
                tl = g[c].tail(6).iloc[::-1]
                a = wfig(list(zip(tl.fig, tl.w, tl.km)), w)
                b = wfig(list(zip(tl.flo, tl.w, tl.km)), w)
                if a is not None and b is not None:
                    d[j] = SW_BETA_FIG * (b - a)
            delta[k] = d - d.mean()
    sd = np.concatenate(list(delta.values()))
    print("LO Δraw SD", round(float(sd.std()), 4), "max", round(float(np.abs(sd).max()), 3), flush=True)
    write_arm(rows, delta, out, "LO", fit=False)


# ---------- B. SE ----------
def arm_SE(rows, out):
    idx = hb.load_index()["results"]
    n2c, _ = codes_weights(idx)
    hist = defaultdict(list)
    for k, r in idx.items():
        res = []
        for q in r.get("results") or []:
            c = n2c.get((k, str(q.get("horse_no"))))
            try:
                pos = int(str(q.get("pos")).strip()); od = float(q.get("win_odds"))
            except (TypeError, ValueError):
                continue
            if c:
                res.append((c, pos, od))
        if len(res) < 4:
            continue
        rk = pd.Series([o for _, _, o in res]).rank(method="average").values
        for (c, pos, _), rnk in zip(res, rk):
            hist[c].append((k[0], (rnk - pos) / len(res)))
    for c in hist:
        hist[c].sort()
    feats = {}
    cov = [0, 0]
    for x in rows:
        k = (x["date"], x["race"]); m = np.zeros((len(x["horses"]), 2))
        for j, h in enumerate(x["horses"]):
            c = n2c.get((k, str(h["n"])))
            past = [s for d, s in hist.get(c, []) if d < x["date"]][-6:][::-1]
            cov[1] += 1
            if past:
                cov[0] += 1
                wsum = sum(1.0 / i for i in range(1, len(past) + 1))
                m[j] = [sum(s / i for i, s in enumerate(past, 1)) / wsum, 1.0]
        feats[k] = m - m.mean(axis=0)
    print("SE 覆蓋", round(cov[0] / cov[1], 4), flush=True)
    write_arm(rows, feats, out, "SE")


# ---------- C. NRGs ----------
def arm_NRGs(rows, out):
    import features as F
    idx = hb.load_index()["results"]
    n2c, wt = codes_weights(idx)
    grp = {k: str((r.get("_header") or {}).get("RaceClass") or "").startswith("Group") for k, r in idx.items()}
    pages, _ = F.load()
    rating, recs = {}, {}
    for c, rr in pages.items():
        recs[c] = sorted((q["d"], q.get("pos")) for q in rr if q.get("d"))
        for q in rr:
            rating[(c, q["d"])] = F.num(q.get("rating"))
    feats = {}
    nst = [0, 0]
    for x in rows:
        k = (x["date"], x["race"])
        if not grp.get(k, False):
            continue
        cs = [n2c.get((k, str(h["n"]))) for h in x["horses"]]
        rat = [rating.get((c, x["date"])) if c else None for c in cs]
        have = [v for v in rat if v is not None]; mu = np.mean(have) if have else 0.0
        r = np.array([((v if v is not None else mu) - mu) / 10.0 for v in rat])
        ws = [wt.get((k, str(h["n"]))) for h in x["horses"]]
        wv = [v for v in ws if v is not None]; wm = np.mean(wv) if wv else 0.0
        w = np.array([((v if v is not None else wm) - wm) / 10.0 for v in ws])
        net = r - w
        st = []
        for c in cs:
            past = [p for d, p in recs.get(c, []) if d < x["date"]][-3:]
            ok = []
            for p in past:
                try:
                    ok.append(int(str(p).strip()) <= 3)
                except ValueError:
                    pass
            st.append(1.0 if past and not any(ok) else 0.0)
        st = np.array(st); nst[0] += int(st.sum()); nst[1] += len(st)
        m = np.column_stack([net, net * st])
        feats[k] = m - m.mean(axis=0)
    print("NRGs 級際賽場數", len(feats), "過期比例", round(nst[0] / max(nst[1], 1), 3), flush=True)
    write_arm(rows, feats, out, "NRGs")


# ---------- D. B3 ----------
def arm_B3(rows, out, paths):
    def load(p):
        return {(x["date"], x["race"]): {h["n"]: h["raw"] for h in x["horses"]} for x in map(json.loads, open(p)) if "horses" in x}
    comps = {name: load(p) for name, p in zip(("DG", "AF", "TR1"), paths)}
    deltas = {}
    for name, cmap in comps.items():
        d = {}
        for x in rows:
            k = (x["date"], x["race"]); c = cmap.get(k)
            if c is None:
                continue
            d[k] = np.array([c.get(h["n"], h["raw"]) - h["raw"] for h in x["horses"]])
        deltas[name] = d
    for arm, use in (("B3", ("DG", "AF", "TR1")), ("B3noDG", ("AF", "TR1")), ("B3noAF", ("DG", "TR1")), ("B3noTR", ("DG", "AF"))):
        tot = {}
        for x in rows:
            k = (x["date"], x["race"])
            tot[k] = sum((deltas[n].get(k, np.zeros(len(x["horses"]))) for n in use), np.zeros(len(x["horses"])))
        write_arm(rows, tot, out, arm, fit=False)


if __name__ == "__main__":
    mode, base, out = sys.argv[1], sys.argv[2], sys.argv[3]
    rows = [x for x in map(json.loads, open(base)) if "horses" in x]
    {"LO": lambda: arm_LO(rows, out), "SE": lambda: arm_SE(rows, out), "NRGs": lambda: arm_NRGs(rows, out),
     "B3": lambda: arm_B3(rows, out, sys.argv[4:7])}[mode]()
    print("DONE", mode, flush=True)
