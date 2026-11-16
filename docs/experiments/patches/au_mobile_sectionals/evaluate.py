#!/usr/bin/env python3
"""EXP-20261116-19 評估（跟預先登記）。

    PYTHONDONTWRITEBYTECODE=1 python3 evaluate.py <raw/mob 目錄> <events.json> <out 目錄>

base = live `Meeting_Auto_Scoring.csv` 嘅 final_rank_score；賽果 = AU_Historical_Raw_Race_Results.csv。
arm E／L／A：候選 = base + β·z場內(特徵)，β 逐賽日 walk-forward（只用之前賽日）。判決器 v3 evaluate_full_record。
"""
from __future__ import annotations

import collections
import csv
import json
import math
import random
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / ".agents/skills/shared_racing"))
import parse_mobile as pm  # noqa: E402
from eval_metrics import race_metrics  # noqa: E402
from model_evaluation_decision import evaluate_full_record, holm_adjust  # noqa: E402

ROOT = Path(open(REPO / ".wongchoi_au_data_root").read().strip())
STD_BEFORE = "2026-11-06"
LAST_N, WARMUP_DAYS, CLIP = 4, 2, 10.0
ARMS = ("E", "E2", "L", "A", "D")


def norm(s: str) -> str:
    return "".join(ch for ch in s.lower().replace("&amp;", "&") if ch.isalnum())


def pearson(x, y):
    mx, my = statistics.mean(x), statistics.mean(y)
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    return sxy / math.sqrt(sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y))


def bucket(d):
    return "a" if d <= 1100 else "b" if d <= 1400 else "c" if d <= 1800 else "d"


def run_values(run):
    sp = run["split"]
    v = {"A": run["distance"] / run["time"] * 3.6 if run["time"] > 0 else None}
    kh = run["kmh"]
    have = [c for c in pm.COLS if kh[c]]
    if have and run["time"] > 0:
        pre_len = run["distance"] - 200 * len(have)
        pre_t = run["time"] - sum(200 * 3.6 / kh[c] for c in have)
        if pre_len > 0 and pre_t > 0:
            v["E2"] = pre_len / pre_t * 3.6
    l6 = [sp["400m"], sp["200m"], sp["Fnsh"]]
    if all(x is not None for x in l6) and run["time"] > 0:
        l600 = sum(l6)
        v["L"] = 600 / l600 * 3.6
        k = run["kmh"]
        if all(k[c] for c in ("400m", "200m", "Fnsh")):
            v["D"] = k["Fnsh"] / ((k["400m"] + k["200m"]) / 2)
        if run["distance"] > 800 and run["time"] - l600 > 0:
            v["E"] = (run["distance"] - 600) / (run["time"] - l600) * 3.6
    return v


def load_pages(mob, evs):
    races = []
    for e in evs:
        f = mob / f"{e['id']}.html"
        if f.exists():
            races.append((e, pm.parse(f.read_text(encoding="utf-8", errors="replace"))))
    return races


def standards(races):
    """(場地,路程段)／場地／全體 嘅 mean, sd —— 只用 STD_BEFORE 之前嘅行，(馬,日,場地) 去重。"""
    seen, pools = set(), collections.defaultdict(lambda: collections.defaultdict(list))
    for _e, runners in races:
        for r in runners:
            for run in r["runs"]:
                if run.get("unparsed") or run["date"] >= STD_BEFORE:
                    continue
                k = (norm(r["name"]), run["date"], run["track"])
                if k in seen:
                    continue
                seen.add(k)
                for arm, x in run_values(run).items():
                    for key in ((run["track"], bucket(run["distance"])), (run["track"],), ()):
                        pools[arm][key].append(x)
    out = {}
    for arm, by in pools.items():
        out[arm] = {k: (statistics.mean(v), statistics.pstdev(v)) for k, v in by.items() if len(v) >= 20 and statistics.pstdev(v) > 0}
    return out, len(seen)


def zval(std, arm, run, x):
    for key in ((run["track"], bucket(run["distance"])), (run["track"],), ()):
        if key in std[arm]:
            m, s = std[arm][key]
            return (x - m) / s
    return None


def feature(std, arm, runs, day):
    zs = []
    for run in sorted((r for r in runs if not r.get("unparsed") and r["date"] < day), key=lambda r: r["date"], reverse=True):
        x = run_values(run).get(arm)
        if x is None:
            continue
        z = zval(std, arm, run, x)
        if z is not None:
            zs.append(max(-4.0, min(4.0, z)))
        if len(zs) == LAST_N:
            break
    return statistics.mean(zs) if zs else None


def load_results():
    out = collections.defaultdict(dict)
    with open(ROOT / "AU_Historical_Raw_Race_Results.csv", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            try:
                out[(row["Date"], norm(row["Track"]), int(float(row["Race"])))][norm(row["Horse"])] = int(float(row["Pos"]))
            except (ValueError, KeyError):
                continue
    return out


def load_scores(folder):
    out = collections.defaultdict(dict)
    with open(Path(folder) / "Meeting_Auto_Scoring.csv", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            out[int(row["race_number"])][norm(row["horse_name"])] = float(row["final_rank_score"])
    return out


def zs_in_race(vals):
    have = [v for v in vals if v is not None]
    if len(have) < 2 or statistics.pstdev(have) == 0:
        return [0.0] * len(vals)
    m, s = statistics.mean(have), statistics.pstdev(have)
    return [0.0 if v is None else (v - m) / s for v in vals]


def logistic_fit(X, y, iters=50, ridge=1e-4):
    """普通 logistic（含截距）Newton。X 每行唔包截距。"""
    p = len(X[0]) + 1
    w = [0.0] * p
    for _ in range(iters):
        g = [0.0] * p
        H = [[0.0] * p for _ in range(p)]
        for xi, yi in zip(X, y):
            v = [1.0, *xi]
            eta = sum(a * b for a, b in zip(w, v))
            mu = 1 / (1 + math.exp(-max(-30, min(30, eta))))
            for i in range(p):
                g[i] += (yi - mu) * v[i]
                for j in range(p):
                    H[i][j] += mu * (1 - mu) * v[i] * v[j]
        for i in range(p):
            H[i][i] += ridge
            g[i] -= ridge * w[i]
        step = solve(H, g)
        w = [a + b for a, b in zip(w, step)]
        if max(abs(s) for s in step) < 1e-8:
            break
    return w


def solve(A, b):
    n = len(b)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(M[r][c]))
        M[c], M[piv] = M[piv], M[c]
        if abs(M[c][c]) < 1e-12:
            return [0.0] * n
        for r in range(n):
            if r != c:
                f = M[r][c] / M[c][c]
                M[r] = [a - f * b for a, b in zip(M[r], M[c])]
    return [M[i][n] / M[i][i] for i in range(n)]


def loglik(w, x, y):
    eta = w[0] + sum(a * b for a, b in zip(w[1:], x))
    mu = 1 / (1 + math.exp(-max(-30, min(30, eta))))
    mu = min(max(mu, 1e-9), 1 - 1e-9)
    return math.log(mu) if y else math.log(1 - mu)


def race_auc(scores, placed):
    pos = [s for s, p in zip(scores, placed) if p]
    neg = [s for s, p in zip(scores, placed) if not p]
    if not pos or not neg:
        return None
    win = sum((a > b) + 0.5 * (a == b) for a in pos for b in neg)
    return win / (len(pos) * len(neg))


def metric_row(names, scores, pos):
    order = [n for _s, n in sorted(zip(scores, names), key=lambda t: -t[0])]
    pm_ = dict(zip(names, pos))
    top3 = {n for n, p in pm_.items() if p <= 3}
    winner = next((n for n, p in pm_.items() if p == 1), None)
    if len(top3) < 3 or winner is None:
        return None
    m = race_metrics(order, top3, winner=winner, actual_pos=pm_, field_size=len(names))
    ranks = {n: i + 1 for i, n in enumerate(order)}
    m["mean_top3_model_rank"] = statistics.mean(ranks[n] for n in top3)
    pr = []
    top5 = order[:5]
    for i in range(len(top5)):
        for j in range(i + 1, len(top5)):
            a, b = top5[i], top5[j]
            if pm_[a] != pm_[b]:
                pr.append(1.0 if pm_[a] < pm_[b] else 0.0)
    m["top5_pairwise_auc"] = statistics.mean(pr) if pr else None
    return m


def main():
    mob, evs, out = Path(sys.argv[1]), json.load(open(sys.argv[2])), Path(sys.argv[3])
    out.mkdir(parents=True, exist_ok=True)
    pages = load_pages(mob, evs)
    std, n_std = standards(pages)
    results = load_results()
    score_cache = {}
    races, cov = [], collections.Counter()
    for e, runners in pages:
        cov["pages"] += 1
        if e["folder"] not in score_cache:
            try:
                score_cache[e["folder"]] = load_scores(e["folder"])
            except FileNotFoundError:
                score_cache[e["folder"]] = {}
        sc = score_cache[e["folder"]].get(e["race"], {})
        res = results.get((e["day"], norm(e["venue"]), e["race"]), {})
        if not sc or not res:
            cov["race_missing_scores" if not sc else "race_missing_results"] += 1
            continue
        rows_by = {norm(r["name"]): r["runs"] for r in runners}
        rows = []
        for n, base in sc.items():
            if n not in res:
                continue
            runs = rows_by.get(n)
            cov["horses"] += 1
            if runs is None:
                cov["horse_not_on_page"] += 1
            f = {a: (feature(std, a, runs, e["day"]) if runs else None) for a in ARMS}
            for a in ARMS:
                cov[f"has_{a}"] += f[a] is not None
            rows.append({"n": n, "base": base, "pos": res[n], "f": f})
        if len(rows) >= 4:
            races.append({"day": e["day"], "id": e["id"], "rows": rows})
    races.sort(key=lambda r: (r["day"], r["id"]))
    days = sorted({r["day"] for r in races})
    cov["races"], cov["days"], cov["std_runs"] = len(races), len(days), n_std
    print("coverage", dict(cov))
    if "--coverage-only" in sys.argv:  # 抓取未完之前只睇覆蓋，唔睇賽果指標
        return

    # 單獨 leaf：場內 AUC（入頭三）同 base 嘅相關
    diag = {}
    for a in ARMS + ("base",):
        aucs, cors = [], []
        for r in races:
            vals = [x["base"] if a == "base" else x["f"][a] for x in r["rows"]]
            keep = [(v, x["pos"] <= 3, x["base"]) for v, x in zip(vals, r["rows"]) if v is not None]
            if len(keep) >= 3:
                au = race_auc([k[0] for k in keep], [k[1] for k in keep])
                if au is not None:
                    aucs.append(au)
                if a != "base" and len(keep) >= 4 and statistics.pstdev([k[0] for k in keep]) > 0 and statistics.pstdev([k[2] for k in keep]) > 0:
                    cors.append(pearson([k[0] for k in keep], [k[2] for k in keep]))
        diag[a] = {"leaf_auc": round(statistics.mean(aucs), 4) if aucs else None, "races": len(aucs),
                   "mean_within_race_corr_with_base": round(statistics.mean(cors), 3) if cors else None}
    # E/L 對 A 嘅場內相關
    for a in ("E", "E2", "L", "D"):
        cs = []
        for r in races:
            pr = [(x["f"][a], x["f"]["A"]) for x in r["rows"] if x["f"][a] is not None and x["f"]["A"] is not None]
            if len(pr) >= 4 and statistics.pstdev([p[0] for p in pr]) > 0 and statistics.pstdev([p[1] for p in pr]) > 0:
                cs.append(pearson([p[0] for p in pr], [p[1] for p in pr]))
        diag[a]["mean_within_race_corr_with_A"] = round(statistics.mean(cs), 3) if cs else None
    print("diag", json.dumps(diag))

    def centred(r, a):
        b = [x["base"] for x in r["rows"]]
        mb = statistics.mean(b)
        z = zs_in_race([x["f"][a] for x in r["rows"]]) if a else [0.0] * len(b)
        return [(x["base"] - mb, zi) for x, zi in zip(r["rows"], z)]

    by_day = collections.defaultdict(list)
    for r in races:
        by_day[r["day"]].append(r)

    base_rows = [metric_row([x["n"] for x in r["rows"]], [x["base"] for x in r["rows"]], [x["pos"] for x in r["rows"]]) for r in races]
    report = {"coverage": cov, "diag": diag, "arms": {}}
    pvals = {}
    for a in ARMS:
        beta, betas, ll = {}, [], []
        trainX, trainy = [], []
        for i, d in enumerate(days):
            if i < WARMUP_DAYS or not trainX:
                beta[d] = 0.0
            else:
                w = logistic_fit(trainX, trainy)
                beta[d] = 0.0 if w[1] <= 0 else max(-CLIP, min(CLIP, w[2] / w[1]))
                w0 = logistic_fit([[x[0]] for x in trainX], trainy)
                for r in by_day[d]:  # walk-forward 對數似然：今日用之前 fit
                    for (cb, z), x in zip(centred(r, a), r["rows"]):
                        y = x["pos"] <= 3
                        ll.append((d, loglik(w, [cb, z], y) - loglik(w0, [cb], y)))
            betas.append({"day": d, "beta": round(beta[d], 3), "n_train": len(trainX)})
            for r in by_day[d]:
                for (cb, z), x in zip(centred(r, a), r["rows"]):
                    trainX.append([cb, z]); trainy.append(1 if x["pos"] <= 3 else 0)
        cand_rows, dates, brow, auc_d = [], [], [], []
        for r, b0 in zip(races, base_rows):
            if b0 is None:
                continue
            z = zs_in_race([x["f"][a] for x in r["rows"]])
            sc = [x["base"] + beta[r["day"]] * zi for x, zi in zip(r["rows"], z)]
            c = metric_row([x["n"] for x in r["rows"]], sc, [x["pos"] for x in r["rows"]])
            cand_rows.append(c); brow.append(b0); dates.append(r["day"])
            pl = [x["pos"] <= 3 for x in r["rows"]]
            a0, a1 = race_auc([x["base"] for x in r["rows"]], pl), race_auc(sc, pl)
            if a0 is not None:
                auc_d.append((r["day"], a1 - a0))
        verdict = evaluate_full_record(domain="au", mode="walk_forward_oos", dates=dates,
                                       baseline_rows=brow, candidate_rows=cand_rows, leakage_audit_passed=True,
                                       ranking_metrics=("top3_capture_at5", "ndcg_at5", "competitive_recall_at5",
                                                        "mean_top3_model_rank", "top5_pairwise_auc"))

        def day_boot(pairs, n=2000, seed=7):
            byd = collections.defaultdict(list)
            for d, v in pairs:
                byd[d].append(v)
            ds = sorted(byd)
            rng = random.Random(seed)
            point = statistics.mean(v for _d, v in pairs) if pairs else None
            bs = []
            for _ in range(n):
                vals = [v for d in (rng.choice(ds) for _ in ds) for v in byd[d]]
                bs.append(statistics.mean(vals))
            bs.sort()
            return point, bs[int(0.025 * n)], bs[int(0.975 * n) - 1]

        moved = sum(1 for r in races if beta[r["day"]] != 0)
        report["arms"][a] = {
            "betas": betas, "races_with_nonzero_beta": moved,
            "loglik_delta_per_runner": day_boot(ll) if ll else None,
            "within_race_auc_delta": day_boot(auc_d) if auc_d else None,
            "verdict": verdict,
            "gold": [statistics.mean(r["gold"] for r in brow), statistics.mean(r["gold"] for r in cand_rows)],
            "good": [statistics.mean(r["good_positional"] for r in brow), statistics.mean(r["good_positional"] for r in cand_rows)],
        }
        pvals[a] = verdict.get("p_value", 1.0) if isinstance(verdict, dict) else 1.0
        print(a, json.dumps({k: v for k, v in report["arms"][a].items() if k != "betas"}, default=str)[:1500])
    report["holm"] = holm_adjust(pvals)
    (out / "report.json").write_text(json.dumps(report, indent=1, default=str, ensure_ascii=False))


if __name__ == "__main__":
    main()
