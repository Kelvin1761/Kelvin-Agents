#!/usr/bin/env python3
"""EXP-20261124-60（見 PROTOCOL.md）。 analyse.py BASE.json OUT.json BSP_DIR [BSP_DIR...]"""
import collections, importlib.util, json, re, sys
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
REPO = Path(__file__).resolve().parents[4]
spec = importlib.util.spec_from_file_location("ds", REPO / "scratch/au_betting_edge_dataset_20261104.py")
DS = importlib.util.module_from_spec(spec); spec.loader.exec_module(DS)
CUT, WARM = "2026-11-03", 20
races = json.loads(Path(sys.argv[1]).read_text())["races"]
by_key, by_horse = {}, collections.defaultdict(list)
for d in sys.argv[3:]:
    k, h = DS.load_bsp(d); by_key.update(k)
    for kk, v in h.items(): by_horse[kk].extend(v)
stats = collections.Counter(); R = []
for r in races:
    venue = re.sub(r"^\d{4}-\d{2}-\d{2}[ _]", "", r["meeting"]).split(" Race")[0].split("_Race")[0]
    rows = []
    for x in r["rows"]:
        bf = by_key.get((r["date"], DS.norm(venue), r["race"], DS.norm(x["name"])))
        if bf is None:
            c = [rec for kk, rec in by_horse.get((r["date"], DS.norm(x["name"])), []) if kk[2] == r["race"]]
            bf = c[0] if len(c) == 1 else None
        stats["hit" if bf else "miss"] += 1
        rows.append((x, bf or {}))
    if not rows or any(not bf.get("win") for _, bf in rows):
        stats["race_incomplete"] += 1; continue
    n = len(rows); places = 3 if n >= 8 else (2 if n >= 5 else 1)
    ab = np.array([x["ability"] for x, _ in rows]); z = (ab - ab.mean()) / (ab.std() or 1)
    pw = np.array([1 / bf["win"] for _, bf in rows]); pw /= pw.sum()
    pp = np.array([1 / bf["place"] if bf.get("place") else np.nan for _, bf in rows])
    pp = pp / np.nansum(pp) * places if np.isfinite(pp).any() else pp
    R.append({"date": r["date"], "z": z, "pw": pw, "pp": np.clip(np.nan_to_num(pp, nan=places / n), 1e-4, 1 - 1e-4),
              "won": np.array([x["pos"] == 1 for x, _ in rows]), "placed": np.array([x["pos"] <= places for x, _ in rows]),
              "bw": np.array([bf["win"] for _, bf in rows]), "bp": np.array([bf.get("place") or np.nan for _, bf in rows]),
              "order": np.argsort(-ab)})
print("bsp match", dict(stats), "races usable", len(R), flush=True)
days = sorted({r["date"] for r in R}); byday = collections.defaultdict(list)
for i, r in enumerate(R): byday[r["date"]].append(i)

def win_nll(th, idx, use_b):
    a, b = th[0], (th[1] if use_b else 0.0); t = 0.0
    for i in idx:
        r = R[i]; s = a * np.log(r["pw"]) + b * r["z"]; s -= s.max()
        t -= s[r["won"]].sum() - np.log(np.exp(s).sum())
    return t

def place_nll(th, idx, use_b):
    c, a, b = th[0], th[1], (th[2] if use_b else 0.0); t = 0.0
    for i in idx:
        r = R[i]; lg = np.log(r["pp"] / (1 - r["pp"])); s = c + a * lg + b * r["z"]
        p = np.clip(1 / (1 + np.exp(-s)), 1e-9, 1 - 1e-9); y = r["placed"]
        t -= (y * np.log(p) + (1 - y) * np.log(1 - p)).sum()
    return t

def walk(fn, x0b, x0m):
    out = []   # (date, Δll per race: model − market；正 = 模型版好)
    thb = thm = None
    for j, d in enumerate(days):
        if j >= WARM:
            if thb is None or (j - WARM) % 7 == 0:
                train = [i for dd in days[:j] for i in byday[dd]]
                thb = minimize(lambda t: fn(t, train, True), x0b, method="Nelder-Mead").x
                thm = minimize(lambda t: fn(t, train, False), x0m, method="Nelder-Mead").x
            for i in byday[d]:
                out.append((d, fn(thm, [i], False) - fn(thb, [i], True)))
    return out, (list(thb), list(thm))

def boot(vals_by_day, f):
    ds = sorted(vals_by_day); rng = np.random.default_rng(0); bs = []
    for _ in range(2000):
        pick = [vals_by_day[ds[k]] for k in rng.integers(0, len(ds), len(ds))]
        bs.append(f([v for p in pick for v in p]))
    return [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))]

out = {"bsp_match": dict(stats), "races": len(R)}
for name, fn, x0b, x0m in (("Q1_win", win_nll, [1.0, 0.0], [1.0]), ("Q1_place", place_nll, [0.0, 1.0, 0.0], [0.0, 1.0])):
    rows, th = walk(fn, x0b, x0m)
    for seg, keep in (("dev", lambda d: d <= CUT), ("new", lambda d: d > CUT)):
        sub = [(d, v) for d, v in rows if keep(d)]; vd = collections.defaultdict(list)
        for d, v in sub: vd[d].append(v)
        m = float(np.mean([v for _, v in sub])) if sub else None
        out[f"{name}_{seg}"] = {"races": len(sub), "dll_per_race": m, "ci": boot(vd, np.mean) if sub else None}
        print(name, seg, len(sub), m, out[f"{name}_{seg}"]["ci"], flush=True)
    out[f"{name}_theta_last"] = th

def rule_bets(r, rule):
    o = r["order"]
    if rule == "R1": return [(o[0], "w")]
    if rule == "R2": return [(o[0], "p")]
    return [(o[0], "p"), (o[1], "p")]

for comm in (0.05, 0.08):
    for rule in ("R1", "R2", "R3"):
        for seg, keep in (("dev", lambda d: d <= CUT), ("new", lambda d: d > CUT)):
            vd = collections.defaultdict(list)
            for r in R:
                if not keep(r["date"]): continue
                for i, kind in rule_bets(r, rule):
                    price = r["bw"][i] if kind == "w" else r["bp"][i]
                    if not np.isfinite(price): continue
                    hit = r["won"][i] if kind == "w" else r["placed"][i]
                    vd[r["date"]].append((price - 1) * (1 - comm) if hit else -1.0)
            allv = [v for vs in vd.values() for v in vs]
            if not allv: continue
            roi = float(np.mean(allv)); ci = boot(vd, np.mean)
            out[f"{rule}_{seg}_c{int(comm*100)}"] = {"bets": len(allv), "roi": roi, "ci": ci}
            print(f"{rule} {seg} comm{int(comm*100)}% bets {len(allv)} ROI {roi:+.2%} CI [{ci[0]:+.2%}, {ci[1]:+.2%}]", flush=True)
Path(sys.argv[2]).write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float))
