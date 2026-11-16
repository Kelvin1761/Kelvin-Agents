#!/usr/bin/env python3
"""EXP-20261116-22 A 部分 + arm P（跟預先登記，唔准喺度改規則）。

    PYTHONDONTWRITEBYTECODE=1 python3 deep.py <raw/mob> <events.json> <outdir> [--semantics-only]

手機往績行 join 返今仗 Formguide 往績行（同馬同日），砌同場正規化特徵；量單獨、殘差（控制 final_rank_score）、
dev 揀 k、分層、功效；arm P = pace_figure 換真 L600（用引擎 speed.py 原 code）。
"""
from __future__ import annotations

import collections
import json
import math
import random
import re
import statistics
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / ".agents/skills/shared_racing"))
sys.path.insert(0, str(REPO / ".agents/skills/au_racing/au_wong_choi_auto/scripts"))
import evaluate as ev  # noqa: E402  (EXP-19 loaders／metric_row)
import parse_mobile as pm  # noqa: E402
from au_racing_engine import speed  # noqa: E402
from au_racing_engine.data_prep import _parse_formguide_pf_metrics  # noqa: E402
from model_evaluation_decision import evaluate_full_record, holm_adjust  # noqa: E402

STD_BEFORE = "2026-11-06"
DEV_LAST = "2026-11-12"
K_GRID = (0.25, 0.5, 1.0, 2.0, 4.0)
PF_COEF = 0.08792517389716135
SIGNALS = ("Lr", "Ls", "Er", "CxP", "Lpos")
AGGS = ("avg4", "last", "best3")
RANK_METRICS = ("top3_capture_at5", "ndcg_at5", "competitive_recall_at5", "mean_top3_model_rank", "top5_pairwise_auc")
norm = ev.norm


# ---------------------------------------------------------------- Formguide
def secs(t):
    if not t:
        return None
    p = t.split(":")
    try:
        return float(p[0]) * 60 + float(p[1]) if len(p) == 2 else float(p[0])
    except ValueError:
        return None


HDR = re.compile(r"^\[(\d+)\]\s+(.+?)\s+\((\d+)\)\s*$", re.M)


def going_family(c):
    c = (c or "").lower()
    return "heavy" if "heavy" in c else "soft" if "soft" in c else "good"


def parse_fg(path):
    """→ ({馬名: {日期: 往績 dict}}, 今仗路程, 今仗地況, 今仗名)。"""
    text = path.read_text(encoding="utf-8", errors="replace")
    head = text.splitlines()[0] if text else ""
    m = re.search(r"—\s*(\d+)m\s*\|\s*(.*)$", head)
    today_dist, today_name = (int(m.group(1)), m.group(2)) if m else (None, head)
    g = re.search(r"^Track:\s*([^|]+)", text, re.M)
    today_going = g.group(1).strip() if g else ""
    hs = list(HDR.finditer(text))
    out = {}
    for i, h in enumerate(hs):
        body = text[h.end(): hs[i + 1].start() if i + 1 < len(hs) else len(text)]
        runs = {}
        for line in body.splitlines():
            dm = re.search(r"\bR\d+\s+(\d{4}-\d{2}-\d{2})\s+(\d{3,4})m\s+cond:(\S+)", line)
            if not dm or "(TRIAL)" in line:
                continue
            g8 = re.search(r"(\d+)(?:st|nd|rd|th)@800m", line)
            st = re.search(r"starters:(\d+)", line)
            fi = re.search(r"finish:(\d+)/", line)
            mg = re.search(r"margin:\s*(-?[\d.]+)", line)
            wt = re.search(r"WinningTime:([\d:.]+)", line)
            rl = re.search(r"RaceL600:([\d.]+)", line)
            ld = re.search(r"L600 Delta:\s*([-\d.]+)", line)
            rc = re.search(r"RaceClass:\[([^\]]*)\]", line)
            runs[dm.group(1)] = {
                "dist": int(dm.group(2)), "cond": dm.group(3),
                "pos800": int(g8.group(1)) if g8 else None, "starters": int(st.group(1)) if st else None,
                "finish": int(fi.group(1)) if fi else None, "margin": float(mg.group(1)) if mg else None,
                "wt": secs(wt.group(1)) if wt else None, "race_l600": float(rl.group(1)) if rl else None,
                "l600_delta": float(ld.group(1)) if ld else None, "cls": rc.group(1) if rc else "",
            }
        out[norm(h.group(2))] = runs
    return out, today_dist, today_going, today_name


def own_l600(run):
    k = run["kmh"]
    if not all(k[c] for c in ("400m", "200m", "Fnsh")):
        return None
    return sum(200 * 3.6 / k[c] for c in ("400m", "200m", "Fnsh"))


# ---------------------------------------------------------------- join + per-run raw values
def joined_runs(pages, fg_cache):
    """→ list of (event, runner, [ (mob_run, fg_run) ... ]) 只保留日期 < 今仗。"""
    out, C = [], collections.Counter()
    for e, runners in pages:
        fg = fg_cache.get((e["folder"], e["race"]))
        if fg is None:
            files = list(Path(e["folder"]).glob(f"* Race {e['race']} Formguide.md"))
            fg = parse_fg(files[0]) if files else ({}, None, "", "")
            fg_cache[(e["folder"], e["race"])] = fg
        horses = fg[0]
        for r in runners:
            fr = horses.get(norm(r["name"]))
            pairs = []
            for run in r["runs"]:
                if run.get("unparsed") or run["date"] >= e["day"]:
                    continue
                C["mob_rows"] += 1
                if fr is None:
                    C["horse_not_in_fg"] += 1
                    continue
                f = fr.get(run["date"])
                if f is None:
                    C["row_not_in_fg"] += 1
                    continue
                C["joined"] += 1
                pairs.append((run, f))
            if fr is not None:
                C["fg_rows_on_or_after_race_day"] += sum(d >= e["day"] for d in fr)
            out.append((e, r, pairs))
    return out, C


def raw_values(run, f):
    """逐仗原始量（秒）。冇就唔出。"""
    v = {}
    ol = own_l600(run)
    if ol is None or f["race_l600"] is None or run["time"] <= 0:
        return v, ol
    v["lr"] = -(ol - f["race_l600"])
    if f["l600_delta"] is not None:
        v["ls_raw"] = -(ol - f["race_l600"] + f["l600_delta"])  # = −(本駒 − 標準)
    if f["wt"] and f["wt"] > f["race_l600"] and run["distance"] > 800:
        race_to600 = f["wt"] - f["race_l600"]
        v["er"] = -((run["time"] - ol) - race_to600)
        v["pace"] = (run["distance"] - 600) / race_to600 * 3.6
    if f["pos800"] and f["starters"] and f["starters"] > 1:
        v["p800"] = (f["pos800"] - 1) / (f["starters"] - 1)
    return v, ol


def dbucket(d):
    return "s" if d <= 1200 else "m" if d <= 1700 else "l"


def build_standards(J):
    """全部只用 11-06 之前行：地況族 Ls 平均、步速 (路程段,地況族) mean/sd、Lpos 線性係數。"""
    seen = set()
    ls_g, pace_g, lp = collections.defaultdict(list), collections.defaultdict(list), []
    for e, r, pairs in J:
        for run, f in pairs:
            key = (norm(r["name"]), run["date"])
            if run["date"] >= STD_BEFORE or key in seen:
                continue
            seen.add(key)
            v, _ = raw_values(run, f)
            gf = going_family(f["cond"])
            if "ls_raw" in v:
                ls_g[gf].append(v["ls_raw"])
            if "pace" in v:
                pace_g[(dbucket(run["distance"]), gf)].append(v["pace"])
            if "lr" in v and "p800" in v:
                lp.append((v["p800"], v["lr"]))
    xs, ys = np.array([a for a, _ in lp]), np.array([b for _, b in lp])
    b, a = np.polyfit(xs, ys, 1)
    return {"ls_going": {k: statistics.mean(x) for k, x in ls_g.items()},
            "pace": {k: (statistics.mean(x), statistics.pstdev(x)) for k, x in pace_g.items() if len(x) >= 20},
            "lpos": (float(a), float(b)), "n_rows": len(seen)}


def run_signals(run, f, S):
    v, _ = raw_values(run, f)
    out = {}
    if "lr" in v:
        out["Lr"] = v["lr"]
        if "p800" in v:
            a, b = S["lpos"]
            out["Lpos"] = v["lr"] - (a + b * v["p800"])
    if "ls_raw" in v:
        out["Ls"] = v["ls_raw"] - S["ls_going"].get(going_family(f["cond"]), 0.0)
    if "er" in v:
        out["Er"] = v["er"]
    if "pace" in v and "lr" in v:
        ms = S["pace"].get((dbucket(run["distance"]), going_family(f["cond"])))
        if ms and ms[1] > 0:
            out["CxP"] = v["lr"] * (v["pace"] - ms[0]) / ms[1]
    return out


def horse_features(pairs, S):
    per = collections.defaultdict(list)  # sig -> [(date, value)]
    for run, f in pairs:
        for k, x in run_signals(run, f, S).items():
            per[k].append((run["date"], x))
    out = {}
    for k in SIGNALS:
        vals = [x for _d, x in sorted(per.get(k, []), reverse=True)]
        out[(k, "avg4")] = statistics.mean(vals[:4]) if vals else None
        out[(k, "last")] = vals[0] if vals else None
        out[(k, "best3")] = max(vals[:3]) if vals else None
    return out


# ---------------------------------------------------------------- stats helpers
def zin(vals):
    have = [v for v in vals if v is not None]
    if len(have) < 2 or statistics.pstdev(have) == 0:
        return [0.0] * len(vals)
    m, s = statistics.mean(have), statistics.pstdev(have)
    return [0.0 if v is None else (v - m) / s for v in vals]


def spearman(a, b):
    ra, rb = rank(a), rank(b)
    if statistics.pstdev(ra) == 0 or statistics.pstdev(rb) == 0:
        return None
    return ev.pearson(ra, rb)


def rank(x):
    order = sorted(range(len(x)), key=lambda i: x[i])
    r = [0.0] * len(x)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and x[order[j + 1]] == x[order[i]]:
            j += 1
        for t in range(i, j + 1):
            r[order[t]] = (i + j) / 2 + 1
        i = j + 1
    return r


def resid(y, x):
    x, y = np.array(x, float), np.array(y, float)
    if x.std() == 0:
        return y - y.mean()
    b = np.polyfit(x, y, 1)
    return y - np.polyval(b, x)


def boot_days(byday, stat, n=2000, seed=11):
    ds = sorted(byday)
    rng = random.Random(seed)
    point = stat([v for d in ds for v in byday[d]])
    bs = []
    for _ in range(n):
        pick = [v for d in (rng.choice(ds) for _ in ds) for v in byday[d]]
        bs.append(stat(pick))
    bs = sorted(b for b in bs if b is not None)
    return point, bs[int(0.025 * len(bs))], bs[int(0.975 * len(bs)) - 1]


def clogit(races, target, cols, ridge=1e-3):
    """每場 softmax；target='place'：每匹頭三馬一次選擇（同 EXP-42）；'win'：頭馬。"""
    Xs, Ys, G = [], [], []
    for gi, r in enumerate(races):
        X = [[x["z"][c] for c in cols] for x in r["rows"]]
        y = [float((x["pos"] <= 3) if target == "place" else (x["pos"] == 1)) for x in r["rows"]]
        if 0 < sum(y) < len(y):
            Xs.extend(X); Ys.extend(y); G.extend([gi] * len(y))
    X, y, G = np.array(Xs), np.array(Ys), np.array(G)
    _, gidx = np.unique(G, return_inverse=True)
    ng = gidx.max() + 1
    ny = np.bincount(gidx, weights=y, minlength=ng)

    def nll(b):
        u = X @ b
        m = np.full(ng, -np.inf); np.maximum.at(m, gidx, u)
        e = np.exp(u - m[gidx]); s = np.bincount(gidx, weights=e, minlength=ng)
        lse = np.log(s) + m
        p = e / s[gidx]
        tot = -(u[y == 1].sum() - (ny * lse).sum())
        pX = np.zeros((ng, X.shape[1])); np.add.at(pX, gidx, p[:, None] * X)
        g = -(X[y == 1].sum(0) - (ny[:, None] * pX).sum(0))
        return tot + ridge * (b @ b), g + 2 * ridge * b
    return minimize(nll, np.zeros(len(cols)), jac=True, method="L-BFGS-B").x


def boot_clogit(races, target, cols, n=400, seed=5):
    byday = collections.defaultdict(list)
    for r in races:
        byday[r["day"]].append(r)
    ds = sorted(byday)
    rng = random.Random(seed)
    point = clogit(races, target, cols)
    bs = []
    for _ in range(n):
        pick = [r for d in (rng.choice(ds) for _ in ds) for r in byday[d]]
        bs.append(clogit(pick, target, cols))
    bs = np.array(bs)
    c = bs[:, -1]
    p = 2 * min((c <= 0).mean(), (c >= 0).mean())
    return {"coef": [round(float(v), 4) for v in point], "c_ci": [round(float(np.quantile(c, .025)), 4), round(float(np.quantile(c, .975)), 4)],
            "p_boot": round(float(max(p, 1 / n)), 4)}


# ---------------------------------------------------------------- main
def main():
    mob, evs, out = Path(sys.argv[1]), json.load(open(sys.argv[2])), Path(sys.argv[3])
    out.mkdir(parents=True, exist_ok=True)
    pages = ev.load_pages(mob, evs)
    J, C = joined_runs(pages, {})
    S = build_standards(J)
    rep = {"join": dict(C), "standards": {"n_rows": S["n_rows"], "ls_going": S["ls_going"], "lpos": S["lpos"],
                                          "pace_cells": len(S["pace"])}}

    # RaceL600 語義：頭馬嘅手機 L600 − RaceL600（唔睇今仗賽果）
    diffs, second = [], []
    for e, r, pairs in J:
        for run, f in pairs:
            ol = own_l600(run)
            if ol is None or f["race_l600"] is None or f["finish"] is None:
                continue
            (diffs if f["finish"] == 1 else second).append(ol - f["race_l600"])
    q = lambda v: [round(float(np.quantile(v, p)), 3) for p in (.1, .25, .5, .75, .9)] if v else None
    rep["racel600_semantics"] = {"winner_own_minus_race_q10_25_50_75_90": q(diffs), "n_winner_rows": len(diffs),
                                 "nonwinner_own_minus_race_q": q(second), "n_nonwinner": len(second)}
    print(json.dumps(rep, indent=1, default=str))
    if "--semantics-only" in sys.argv:
        (out / "semantics.json").write_text(json.dumps(rep, indent=1, default=str))
        return

    # ---------------- 組場：base、賽果、特徵、P
    results = ev.load_results()
    sc_cache, fg_cache = {}, {}
    feats = {}
    for e, r, pairs in J:
        feats[(e["id"], norm(r["name"]))] = (horse_features(pairs, S), {run["date"]: own_l600(run) for run, _f in pairs})
    races, cov = [], collections.Counter()
    for e, _runners in pages:
        if e["folder"] not in sc_cache:
            sc_cache[e["folder"]] = load_rows(e["folder"])
        sc = sc_cache[e["folder"]].get(e["race"], {})
        res = results.get((e["day"], norm(e["venue"]), e["race"]), {})
        if not sc or not res:
            cov["skip_no_scores_or_results"] += 1
            continue
        files = list(Path(e["folder"]).glob(f"* Race {e['race']} Formguide.md"))
        fgtext = files[0].read_text(encoding="utf-8", errors="replace") if files else ""
        _fg, tdist, tgoing, tname = parse_fg(files[0]) if files else ({}, None, "", "")
        pf_old, pf_new, pfinfo = arm_p(fgtext, e, feats)
        cov["pf_reproduced"] += pfinfo["reproduced"]; cov["pf_compared"] += pfinfo["compared"]
        cov["pf_runs_replaced"] += pfinfo["replaced"]; cov["pf_runs_total"] += pfinfo["runs"]
        rows = []
        for n, row in sc.items():
            if n not in res:
                continue
            f = feats.get((e["id"], n), ({}, {}))[0]
            num = row["num"]
            rows.append({"n": n, "base": row["final"], "pos": res[n], "f": f,
                         "pf_csv": row["pf"], "pf_old": pf_old.get(num), "pf_new": pf_new.get(num)})
        if len(rows) >= 4:
            races.append({"day": e["day"], "id": e["id"], "rows": rows, "dist": tdist, "going": tgoing, "name": tname})
    races.sort(key=lambda r: (r["day"], r["id"]))
    rep["coverage"] = dict(cov) | {"races": len(races), "days": sorted({r["day"] for r in races})}
    for r in races:  # base z + signal z（冇值 = 0）
        bz = zin([x["base"] for x in r["rows"]])
        for x, b in zip(r["rows"], bz):
            x["z"] = {"base": b}
        for k in SIGNALS:
            for agg in AGGS:
                for x, z in zip(r["rows"], zin([x["f"].get((k, agg)) for x in r["rows"]])):
                    x["z"][f"{k}.{agg}"] = z

    # ---------------- 1. 單獨
    stand = {}
    for k in SIGNALS:
        for agg in AGGS:
            key = f"{k}.{agg}"
            sp, wa, pa, ps = (collections.defaultdict(list) for _ in range(4))
            n_h = 0
            for r in races:
                have = [x for x in r["rows"] if x["f"].get((k, agg)) is not None]
                n_h += len(have)
                if len(have) < 4:
                    continue
                v = [x["f"][(k, agg)] for x in have]; pos = [x["pos"] for x in have]
                s = spearman(v, [-p for p in pos])
                if s is not None:
                    sp[r["day"]].append(s)
                w = ev.race_auc(v, [p == 1 for p in pos]); a = ev.race_auc(v, [p <= 3 for p in pos])
                if w is not None:
                    wa[r["day"]].append(w)
                if a is not None:
                    pa[r["day"]].append(a)
                rb = resid(rank([-p for p in pos]), [x["base"] for x in have]); rv = resid(rank(v), [x["base"] for x in have])
                if rb.std() > 0 and rv.std() > 0:
                    ps[r["day"]].append(float(np.corrcoef(rb, rv)[0, 1]))
            mean = lambda xs: statistics.mean(xs) if xs else None
            stand[key] = {"horses_with_value": n_h, "spearman_vs_finish": boot_days(sp, mean), "win_auc": boot_days(wa, mean),
                          "place_auc": boot_days(pa, mean), "partial_spearman_given_base": boot_days(ps, mean)}
    base_auc = collections.defaultdict(list)
    for r in races:
        a = ev.race_auc([x["base"] for x in r["rows"]], [x["pos"] <= 3 for x in r["rows"]])
        if a is not None:
            base_auc[r["day"]].append(a)
    rep["base_place_auc"] = boot_days(base_auc, lambda xs: statistics.mean(xs))
    rep["standalone"] = stand

    # ---------------- 2. 殘差（主判：avg4，place）
    resid_rep, pv = {}, {}
    for k in SIGNALS:
        for agg in AGGS:
            key = f"{k}.{agg}"
            pl = boot_clogit(races, "place", ["base", key])
            wi = boot_clogit(races, "win", ["base", key], n=200)
            resid_rep[key] = {"place": pl, "win": wi}
            if agg == "avg4":
                pv[key] = pl["p_boot"]
    rep["residual"] = resid_rep
    rep["holm_primary_place"] = holm_adjust(pv)

    # ---------------- 3. 配權（dev 揀 k，test v3）+ 5. 功效
    rep["integration"] = {k: integrate(races, f"{k}.avg4") for k in SIGNALS}
    rep["power"] = power(races)

    # ---------------- 4. 分層（探索）
    sub = {}
    groups = {
        "dist": lambda r: None if r["dist"] is None else dbucket(r["dist"]),
        "going": lambda r: "wet" if going_family(r["going"]) != "good" else "dry",
        "class": lambda r: klass(r["name"]),
    }
    for gname, fn in groups.items():
        for k in SIGNALS:
            key = f"{k}.avg4"
            for gv in sorted({fn(r) for r in races} - {None}):
                rs = [r for r in races if fn(r) == gv]
                if len(rs) < 25:
                    sub[f"{gname}={gv}|{key}"] = {"races": len(rs), "note": "<25 races, skipped"}
                    continue
                c = clogit(rs, "place", ["base", key])
                sub[f"{gname}={gv}|{key}"] = {"races": len(rs), "c_place": round(float(c[-1]), 4)}
    rep["subgroups_exploratory"] = sub

    # ---------------- arm P
    rep["arm_P"] = arm_p_eval(races)
    (out / "deep_report.json").write_text(json.dumps(rep, indent=1, default=str, ensure_ascii=False))
    print(json.dumps({k: rep[k] for k in ("coverage", "holm_primary_place", "arm_P")}, indent=1, default=str)[:4000])


def klass(name):
    n = (name or "").lower()
    if "maiden" in n:
        return "maiden"
    if re.search(r"class\s*[1-3]|cl[1-3]\b|rst\s*\d|restricted", n):
        return "class1-3"
    if re.search(r"bm\s*\d|benchmark|rating\s*\d|\bhcp\b|handicap", n):
        return "bm/hcp"
    if re.search(r"group|listed|stakes|open|quality|cup", n):
        return "open+"
    return "other"


def load_rows(folder):
    import csv
    out = collections.defaultdict(dict)
    p = Path(folder) / "Meeting_Auto_Scoring.csv"
    if not p.exists():
        return out
    with open(p, encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            try:
                out[int(row["race_number"])][norm(row["horse_name"])] = {
                    "final": float(row["final_rank_score"]), "pf": float(row["pace_figure_score"] or 60),
                    "num": str(int(float(row["horse_number"])))}
            except (ValueError, KeyError):
                continue
    return out


def arm_p(fgtext, e, feats):
    """→ (pf_old, pf_new) {馬號: 分}，同用 speed.py；P：有手機 L600 嗰仗 margin' = (手機 − RaceL600)/0.17。"""
    info = collections.Counter()
    if not fgtext:
        return {}, {}, info
    parsed = _parse_formguide_pf_metrics(Path("x"), formguide_text=fgtext, target_date=e["day"])
    names = {m.group(1): norm(m.group(2)) for m in HDR.finditer(fgtext)}
    old_f, new_f = {}, {}
    for num, d in parsed.items():
        runs = d["pf_runs"]
        src = "sportsbet_race_context" if {r.get("source") for r in runs if r.get("source")} == {"sportsbet_race_context"} else (
            "mixed_formguide_pf" if any(r.get("source") for r in runs) else "sportsbet_race_context")
        own_by_date = feats.get((e["id"], names.get(num)), ({}, {}))[1]
        new_runs = []
        rl = race_l600_by_date(fgtext, num)
        for run in runs:
            nr = dict(run)
            info["runs"] += 1
            ol = own_by_date.get(run.get("run_date"))
            r600 = rl.get(run.get("run_date"))
            if ol is not None and r600 is not None and run.get("l600_delta") is not None and run.get("run_kind") == "formal":
                nr["margin"] = (ol - r600) / speed.SEC_PER_LENGTH
                info["replaced"] += 1
            new_runs.append(nr)
        old_f[num] = speed.horse_speed(runs, src)
        new_f[num] = speed.horse_speed(new_runs, src)
    old = {k: v.score for k, v in speed.field_scores(old_f).items()}
    new = {k: v.score for k, v in speed.field_scores(new_f).items()}
    return old, new, info


def race_l600_by_date(fgtext, num):
    hs = list(HDR.finditer(fgtext))
    for i, h in enumerate(hs):
        if h.group(1) != num:
            continue
        body = fgtext[h.end(): hs[i + 1].start() if i + 1 < len(hs) else len(fgtext)]
        out = {}
        for line in body.splitlines():
            dm = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", line)
            rl = re.search(r"RaceL600:([\d.]+)", line)
            if dm and rl:
                out[dm.group(1)] = float(rl.group(1))
        return out
    return {}


def rows_metrics(races, scorer):
    rows, dates, base = [], [], []
    for r in races:
        names = [x["n"] for x in r["rows"]]; pos = [x["pos"] for x in r["rows"]]
        b = ev.metric_row(names, [x["base"] for x in r["rows"]], pos)
        if b is None:
            continue
        c = ev.metric_row(names, scorer(r), pos)
        rows.append(c); base.append(b); dates.append(r["day"])
    return dates, base, rows


def v3(dates, base, rows):
    return evaluate_full_record(domain="au", mode="walk_forward_oos", dates=dates, baseline_rows=base, candidate_rows=rows,
                                leakage_audit_passed=True, ranking_metrics=RANK_METRICS)


def summarise(verdict):
    d = verdict.get("detail", {})
    out = {"verdict": verdict.get("verdict"), "reason": verdict.get("reason")}
    for g in ("primary", "ranking"):
        for m, s in (d.get(g) or {}).items():
            out[m] = [round(s["delta"], 4), round(s["ci_low"], 4), round(s["ci_high"], 4)]
    return out


def k_scorer(key, k):
    def f(r):
        sd = statistics.pstdev([x["base"] for x in r["rows"]]) or 1.0
        return [x["base"] + k * sd * x["z"][key] for x in r["rows"]]
    return f


def place_auc_delta(races, scorer):
    by = collections.defaultdict(list)
    for r in races:
        pl = [x["pos"] <= 3 for x in r["rows"]]
        a0 = ev.race_auc([x["base"] for x in r["rows"]], pl); a1 = ev.race_auc(scorer(r), pl)
        if a0 is not None:
            by[r["day"]].append(a1 - a0)
    return boot_days(by, lambda xs: statistics.mean(xs) if xs else None)


def integrate(races, key):
    dev = [r for r in races if r["day"] <= DEV_LAST]; test = [r for r in races if r["day"] > DEV_LAST]
    scan, ok = {}, []
    for k in K_GRID:
        d, b, c = rows_metrics(dev, k_scorer(key, k))
        g = statistics.mean(x["gold"] for x in c) - statistics.mean(x["gold"] for x in b)
        gp = statistics.mean(x["good_positional"] for x in c) - statistics.mean(x["good_positional"] for x in b)
        au = place_auc_delta(dev, k_scorer(key, k))[0]
        scan[k] = {"gold": round(g, 4), "good": round(gp, 4), "auc": round(au, 5)}
        if g >= 0 and gp >= 0 and au > 0:
            ok.append(k)
    out = {"dev_races": len(dev), "test_races": len(test), "dev_scan": scan, "qualified": ok}
    if ok:
        k = statistics.median(ok)
        out["k"] = k
        out["test_v3"] = summarise(v3(*rows_metrics(test, k_scorer(key, k))))
        out["test_auc_delta"] = place_auc_delta(test, k_scorer(key, k))
    return out


def power(races):
    """固定 k = 0.25（細）喺全期：Gold／Good Δ 嘅賽日 bootstrap SE → 80% 功效 MDE ≈ 2.8 SE。用 Lr.avg4 同 Ls.avg4。"""
    out = {}
    for key in ("Lr.avg4", "Ls.avg4"):
        d, b, c = rows_metrics(races, k_scorer(key, 0.25))
        out[f"{key}@k0.25"] = summarise(v3(d, b, c))
        for m in ("gold", "good_positional"):
            byd = collections.defaultdict(list)
            for day, bb, cc in zip(d, b, c):
                byd[day].append(cc[m] - bb[m])
            _p, lo, hi = boot_days(byd, lambda xs: statistics.mean(xs))
            se = (hi - lo) / 3.92
            out[f"{key}@k0.25"][f"{m}_se"] = round(se, 4)
            out[f"{key}@k0.25"][f"{m}_mde80"] = round(2.8 * se, 4)
    # 獨立於候選嘅 MDE：基線 Gold／Good 嘅逐場 SD → 配對差 SD 未知，用「一半場次轉向」嘅上界
    g = [x["gold"] for x in rows_metrics(races, lambda r: [x["base"] for x in r["rows"]])[1]]
    out["baseline_gold_rate"] = round(statistics.mean(g), 4)
    out["races"] = len(g)
    return out


def arm_p_eval(races):
    rs = [r for r in races if all(x["pf_old"] is not None and x["pf_new"] is not None for x in r["rows"])]
    def scorer(r):
        return [x["base"] + PF_COEF * (x["pf_new"] - x["pf_old"]) for x in r["rows"]]
    moved = sum(1 for r in rs if any(abs(x["pf_new"] - x["pf_old"]) > 1e-9 for x in r["rows"]))
    repro = [abs(x["pf_old"] - x["pf_csv"]) < 0.06 for r in rs for x in r["rows"]]
    d, b, c = rows_metrics(rs, scorer)
    leaf = collections.defaultdict(list)
    for r in rs:
        pl = [x["pos"] <= 3 for x in r["rows"]]
        a0 = ev.race_auc([x["pf_old"] for x in r["rows"]], pl); a1 = ev.race_auc([x["pf_new"] for x in r["rows"]], pl)
        if a0 is not None:
            leaf[r["day"]].append((a0, a1))
    mean0 = statistics.mean(a for v in leaf.values() for a, _ in v); mean1 = statistics.mean(b for v in leaf.values() for _, b in v)
    diff = {d_: [b - a for a, b in v] for d_, v in leaf.items()}
    return {"races": len(rs), "races_moved": moved, "pf_old_reproduces_csv": round(statistics.mean(repro), 4),
            "leaf_place_auc_old": round(mean0, 4), "leaf_place_auc_new": round(mean1, 4),
            "leaf_auc_delta": boot_days(diff, lambda xs: statistics.mean(xs)),
            "composite_auc_delta": place_auc_delta(rs, scorer),
            "v3": summarise(v3(d, b, c))}


if __name__ == "__main__":
    main()
