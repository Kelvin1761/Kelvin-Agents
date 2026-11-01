#!/usr/bin/env python3
"""EXP-20261101-32 診斷：點解 point-in-time L600 標準令 leaf 準咗但排名差咗。只量度，唔改模型。

    python3 au_l600_standard_dig_20261101.py --root AU_ROOT --races races.json --arms ARMS_DIR --out OUT.json

D1 場地效應拆解：同一匹馬喺唔同場地跑（馬匹固定效應）估「純路面快慢」，對比 pooled 場地平均
   （= 情境標準學到嘅嘢）。兩者之差 = 標準吸收咗嘅「嗰度啲馬質素」。再對場地獎金水平回歸。
D2 獨有資訊：速度分喺場內對其他 leaf 殘差化之後嘅 AUC（base vs S）。
D3 邊類馬被郁：S − base 速度分差，按今場馬嘅往績場地獎金水平分組。
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import re
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / ".agents/skills/au_racing/au_wong_choi_auto/scripts"))
sys.path.insert(0, str(HERE))
from au_racing_engine.engine_core import _normalize_track_name, _STANDARD_600M  # noqa: E402
from au_l600_race_table_20261101 import going  # noqa: E402

HDR = re.compile(r"^\[(\d+)\]\s+(.+?)\s+\(\d+\)\s*$")
RUN = re.compile(r"^(.+?)\s+R(\d+)\s+(\d{4}-\d{2}-\d{2})\s+(\d+)m\s+cond:(\S+)\s+\$(\d+)")
MARGIN = re.compile(r"margin:([0-9.]+)")


def horse_runs(root, races):
    runs = {}
    for f in glob.glob(root + "/**/*Formguide.md", recursive=True):
        horse = None
        for line in open(f, encoding="utf-8"):
            line = line.rstrip("\n")
            h = HDR.match(line)
            if h:
                horse = h[2].strip().lower()
                continue
            if not horse or "L600 Delta" not in line or "TRIAL" in line.upper():
                continue
            m = RUN.match(line.strip())
            mg = MARGIN.search(line)
            if not m or not mg:
                continue
            key = f"{_normalize_track_name(m[1].strip())}|{m[3]}|{int(m[2])}"
            race = races.get(key)
            if not race or not race["reliable"]:
                continue
            runs[(horse, key)] = {"horse": horse, "key": key, "track": race["track"], "date": race["date"],
                                  "distance": race["distance"], "going": race["going"],
                                  "prize": int(m[6]), "own": race["raw"] + float(mg[1]) * 0.17,
                                  "raw": race["raw"]}
    return list(runs.values())


def curve_resid(rows, field):
    gs = sorted({r["going"] for r in rows})
    X = np.array([[1, math.log(r["distance"] / 1400), math.log(r["distance"] / 1400) ** 2]
                  + [1.0 if r["going"] == g else 0.0 for g in gs[1:]] for r in rows])
    y = np.array([r[field] for r in rows])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return y - X @ beta


def d1(rows):
    res = curve_resid(rows, "own")
    for r, e in zip(rows, res):
        r["e"] = float(e)
    by_track = defaultdict(list)
    for r in rows:
        by_track[r["track"]].append(r)
    pooled = {t: st.mean(r["e"] for r in v) for t, v in by_track.items()}
    tfe = defaultdict(float)
    hfe = defaultdict(float)
    by_horse = defaultdict(list)
    for r in rows:
        by_horse[r["horse"]].append(r)
    for _ in range(30):
        for h, v in by_horse.items():
            hfe[h] = st.mean(r["e"] - tfe[r["track"]] for r in v)
        for t, v in by_track.items():
            tfe[t] = st.mean(r["e"] - hfe[r["horse"]] for r in v)
        mu = st.mean(tfe.values())
        for t in tfe:
            tfe[t] -= mu
    pmu = st.mean(pooled.values())
    out = []
    for t, v in by_track.items():
        horses_multi = sum(1 for r in v if len({x["track"] for x in by_horse[r["horse"]]}) > 1)
        if len(v) < 150 or horses_multi < 50:
            continue
        out.append({"track": t, "n": len(v), "pooled": pooled[t] - pmu, "within": tfe[t],
                    "absorbed": (pooled[t] - pmu) - tfe[t],
                    "log_prize": math.log10(st.median(r["prize"] for r in v)),
                    "in_table": t in _STANDARD_600M})
    w = np.array([o["n"] for o in out], dtype=float)
    def wcorr(a, b):
        a, b = np.array(a), np.array(b)
        ma, mb = np.average(a, weights=w), np.average(b, weights=w)
        return float(np.average((a - ma) * (b - mb), weights=w) /
                     math.sqrt(np.average((a - ma) ** 2, weights=w) * np.average((b - mb) ** 2, weights=w)))
    def wslope(x, y):
        x, y = np.array(x), np.array(y)
        mx, my = np.average(x, weights=w), np.average(y, weights=w)
        return float(np.average((x - mx) * (y - my), weights=w) / np.average((x - mx) ** 2, weights=w))
    summary = {
        "tracks": len(out), "runs": int(w.sum()),
        "sd_pooled": float(np.sqrt(np.average(np.array([o["pooled"] for o in out]) ** 2, weights=w))),
        "sd_within": float(np.sqrt(np.average(np.array([o["within"] for o in out]) ** 2, weights=w))),
        "corr_pooled_within": wcorr([o["pooled"] for o in out], [o["within"] for o in out]),
        "slope_pooled_on_logprize": wslope([o["log_prize"] for o in out], [o["pooled"] for o in out]),
        "slope_within_on_logprize": wslope([o["log_prize"] for o in out], [o["within"] for o in out]),
        "slope_absorbed_on_logprize": wslope([o["log_prize"] for o in out], [o["absorbed"] for o in out]),
        "corr_absorbed_logprize": wcorr([o["log_prize"] for o in out], [o["absorbed"] for o in out]),
    }
    out.sort(key=lambda o: o["absorbed"])
    return summary, out[:8] + out[-8:]


OTHERS = ("form_quality_score", "rating_score", "jockey_score", "trainer_score", "jockey_horse_fit_score",
          "track_score", "preparation_score", "trial_speed_score", "class_score")


def zs(vals):
    m = st.mean(vals); s = st.pstdev(vals)
    return [(v - m) / s if s > 0 else 0.0 for v in vals]


def d2(arms_dir):
    out = {}
    for arm in ("base", "S"):
        races = [r for r in json.loads((arms_dir / f"{arm}.json").read_text())["races"]
                 if r["date"] >= "2026-08-05" and len(r["rows"]) >= 5
                 and sum(x["pos"] <= 3 for x in r["rows"]) >= 3]
        X, y, meta = [], [], []
        for ri, r in enumerate(races):
            cols = [zs([x["features"][k] for x in r["rows"]]) for k in OTHERS]
            pf = zs([x["features"]["pace_figure_score"] for x in r["rows"]])
            for i, x in enumerate(r["rows"]):
                X.append([c[i] for c in cols]); y.append(pf[i]); meta.append((ri, x["pos"] <= 3))
        X, y = np.array(X), np.array(y)
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        resid = y - X @ beta
        r2 = 1 - float(np.var(resid) / np.var(y))
        def auc(scores):
            by = defaultdict(list)
            for s, (ri, top) in zip(scores, meta):
                by[ri].append((s, top))
            hit = tot = 0.0
            for v in by.values():
                for a, pa in v:
                    for b, pb in v:
                        if pa and not pb:
                            tot += 1; hit += 1.0 if a > b else 0.5 if a == b else 0.0
            return hit / tot
        out[arm] = {"auc_raw": round(auc(list(y)), 5), "auc_unique": round(auc(list(resid)), 5),
                    "r2_explained_by_other_leaves": round(r2, 4)}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--races", required=True)
    ap.add_argument("--arms", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    races = json.loads(Path(args.races).read_text())
    rows = horse_runs(args.root, races)
    print("horse-runs", len(rows), "horses", len({r["horse"] for r in rows}), flush=True)
    s1, extremes = d1(rows)
    print("D1", json.dumps(s1, indent=1), flush=True)
    for o in extremes:
        print("  %-22s n=%5d pooled %+.3f within %+.3f absorbed %+.3f prize10^%.2f %s" % (
            o["track"], o["n"], o["pooled"], o["within"], o["absorbed"], o["log_prize"], "T" if o["in_table"] else ""))
    s2 = d2(Path(args.arms))
    print("D2", json.dumps(s2, indent=1), flush=True)
    Path(args.out).write_text(json.dumps({"D1": s1, "D1_extremes": extremes, "D2": s2}, indent=1))


if __name__ == "__main__":
    main()
