#!/usr/bin/env python3
"""EXP-20261101-42：逐駒 L800／L600／L400／L200 段速有冇用（RQ 真值診斷）。規格見 protocol —— 唔准喺度改。

    python3 au_rq_sectionals_diag_20261101.py --out OUT.json
"""
from __future__ import annotations

import argparse
import glob
import json
import random
import re
import statistics as st
import sys
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / ".agents/skills/au_racing/au_wong_choi_auto/scripts"))
from au_racing_engine.full_time_speed import norm, seconds  # noqa: E402
from au_result_identity import normalize_venue_name  # noqa: E402

MEASURES = ("fin", "early", "L800", "L600", "L400", "L200")
TARGET_FROM, TEST_FROM = "2026-01-01", "2026-07-01"
DECAY, MAX_RUNS, MIN_FIELD = 0.8, 6, 4


def parse(root_dir):
    races = {}
    for z in glob.glob(str(Path(root_dir) / "*.zip")):
        try:
            zf = zipfile.ZipFile(z)
        except Exception:
            continue
        for name in zf.namelist():
            m = re.search(r"_R(\d+)\.xml$", name, re.I)
            if not m:
                continue
            try:
                root = ET.fromstring(zf.read(name))
            except Exception:
                continue
            if re.search(r"TRIAL|JUMP.?OUT", root.findtext("RaceName") or "", re.I):
                continue
            date = root.attrib.get("EventDate", "")[:10]
            course = normalize_venue_name(root.findtext("CourseName") or "")
            horses = []
            for h in root.findall("./Horses/HorseSummary"):
                secs = h.findall("./Sections/SectionSummary")
                try:
                    pts = [float(s.attrib["CumulatedDistance"]) for s in secs]
                    sp = [seconds(s.find("SectionTime").attrib["Time"]) for s in secs]
                    fin = seconds(h.find("FinishTime").attrib["Time"])
                except Exception:
                    continue
                if len(sp) < 5 or any(b - a != 200 for a, b in zip(pts, pts[1:])) or abs(sum(sp) - fin) > 0.05:
                    continue
                horses.append({"horse": norm(h.attrib["Name"]), "fin": fin, "L800": sum(sp[-4:]), "L600": sum(sp[-3:]),
                               "L400": sum(sp[-2:]), "L200": sp[-1], "early": fin - sum(sp[-4:])})
            if len(horses) >= 4:
                races[(course, date, int(m[1]))] = horses
    return races


def relative(races):
    """每仗：本駒 ÷ 場中位 − 1（越細越快）。"""
    runs = defaultdict(list)  # horse -> [(date, {measure: rel})]
    for (course, date, rno), horses in races.items():
        med = {k: st.median(h[k] for h in horses) for k in MEASURES}
        if min(med.values()) <= 0:  # ≤800m 賽事冇 early 段（harness 必需，唔係候選改動）
            continue
        for h in horses:
            runs[h["horse"]].append((date, {k: h[k] / med[k] - 1 for k in MEASURES}))
    for v in runs.values():
        v.sort(key=lambda x: x[0], reverse=True)
    return runs


def history(runs, horse, date):
    prior = [r for d, r in runs.get(horse, []) if d < date][:MAX_RUNS]
    if not prior:
        return None
    w = [DECAY ** k for k in range(len(prior))]
    return {k: sum(wi * r[k] for wi, r in zip(w, prior)) / sum(w) for k in MEASURES}


def build(races, runs):
    out = []
    for (course, date, rno), horses in sorted(races.items(), key=lambda x: x[0][1]):
        if date < TARGET_FROM:
            continue
        order = sorted(horses, key=lambda h: h["fin"])
        placed = {h["horse"] for h in order[:3]}
        rows = []
        for h in horses:
            hist = history(runs, h["horse"], date)
            if hist:
                rows.append({"y": int(h["horse"] in placed), **hist})
        if len(rows) >= MIN_FIELD and 0 < sum(r["y"] for r in rows) < len(rows):
            X = np.array([[r[k] for k in MEASURES] for r in rows])
            sd = X.std(axis=0); sd[sd == 0] = 1
            Z = -(X - X.mean(axis=0)) / sd  # 越大越快
            out.append({"date": date, "y": np.array([r["y"] for r in rows]), "Z": Z})
    return out


def auc(races, score):
    by_day = defaultdict(lambda: [0.0, 0])
    for r in races:
        s = score(r); pos = s[r["y"] == 1]; neg = s[r["y"] == 0]
        cmp = (pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()
        by_day[r["date"]][0] += cmp; by_day[r["date"]][1] += len(pos) * len(neg)
    return by_day


def ratio(by_day, days):
    return sum(by_day[d][0] for d in days) / sum(by_day[d][1] for d in days)


def boot_diff(a, b, per_day=False):
    days = sorted(a); rng = random.Random(7); samples = []
    point = (ratio(a, days) - ratio(b, days)) if not per_day else (sum(a[d] for d in days) - sum(b[d] for d in days)) / per_day[1]
    for _ in range(2000):
        pick = [days[rng.randrange(len(days))] for _ in days]
        if per_day:
            n = sum(per_day[0][d] for d in pick)
            samples.append((sum(a[d] for d in pick) - sum(b[d] for d in pick)) / n)
        else:
            samples.append(ratio(a, pick) - ratio(b, pick))
    samples.sort()
    return {"delta": round(point, 5), "ci": [round(samples[50], 5), round(samples[1949], 5)]}


def fit(races, cols):
    def nll(beta):
        tot = 0.0; grad = np.zeros_like(beta)
        for r in races:
            u = r["Z"][:, cols] @ beta; p = np.exp(u - u.max()); p /= p.sum()
            # 「上名」多過一匹：每匹上名馬當一次 softmax 選擇（Plackett 近似）
            tot -= (u[r["y"] == 1] - np.log(np.exp(u - u.max()).sum()) - u.max()).sum()
            grad -= (r["Z"][r["y"] == 1][:, cols].sum(axis=0) - r["y"].sum() * (p @ r["Z"][:, cols]))
        return tot, grad
    return minimize(nll, np.zeros(len(cols)), jac=True, method="L-BFGS-B").x


def test_ll(races, cols, beta):
    per_day = defaultdict(float)
    for r in races:
        u = r["Z"][:, cols] @ beta
        per_day[r["date"]] += (u[r["y"] == 1] - (np.log(np.exp(u - u.max()).sum()) + u.max())).sum()
    return per_day


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--rq", default="/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/AU_Racing_Time_Evidence")
    args = ap.parse_args()
    races = parse(args.rq)
    runs = relative(races)
    data = build(races, runs)
    idx = {k: i for i, k in enumerate(MEASURES)}
    out = {"rq_races": len(races), "target_races": len(data), "target_runners": int(sum(len(r["y"]) for r in data)),
           "dates": [data[0]["date"], data[-1]["date"]]}
    corr = np.corrcoef(np.vstack([r["Z"] for r in data]).T)
    out["corr_with_fin"] = {k: round(float(corr[0, idx[k]]), 3) for k in MEASURES}

    base = auc(data, lambda r: r["Z"][:, 0])
    out["auc"] = {k: round(ratio(auc(data, lambda r, i=idx[k]: r["Z"][:, i]), sorted(base)), 4) for k in MEASURES}
    out["auc_vs_fin"] = {k: boot_diff(auc(data, lambda r, i=idx[k]: r["Z"][:, i]), base) for k in MEASURES[1:]}

    train = [r for r in data if r["date"] < TEST_FROM]; test = [r for r in data if r["date"] >= TEST_FROM]
    out["train_races"], out["test_races"] = len(train), len(test)
    models = {"fin": ["fin"], **{f"fin+{k}": ["fin", k] for k in MEASURES[1:]}, "fin+all": list(MEASURES)}
    placed_by_day = defaultdict(int)
    for r in test:
        placed_by_day[r["date"]] += int(r["y"].sum())
    n_placed = sum(placed_by_day.values())
    fitted = {}
    for name, ms in models.items():
        cols = [idx[m] for m in ms]
        beta = fit(train, cols)
        fitted[name] = (cols, beta)
        out.setdefault("beta", {})[name] = {m: round(float(b), 3) for m, b in zip(ms, beta)}
    cols0, b0 = fitted["fin"]
    ll0 = test_ll(test, cols0, b0); auc0 = auc(test, lambda r: r["Z"][:, cols0] @ b0)
    out["test_auc_fin"] = round(ratio(auc0, sorted(auc0)), 4)
    for name, (cols, beta) in fitted.items():
        if name == "fin":
            continue
        out.setdefault("incremental", {})[name] = {
            "ll_per_placed": boot_diff(test_ll(test, cols, beta), ll0, per_day=(placed_by_day, n_placed)),
            "auc": boot_diff(auc(test, lambda r, c=cols, b=beta: r["Z"][:, c] @ b), auc0)}
    Path(args.out).write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
