#!/usr/bin/env python3
"""EXP-20261116-22 B 部分：QLD 官方分段（RQ XML）大樣本，同場正規化特徵 + 情境 + 對我哋模型分嘅殘差。

    PYTHONDONTWRITEBYTECODE=1 python3 rq_deep.py --out OUT.json

語料、切分、conditional logit 同 EXP-42（`scratch/au_rq_sectionals_diag_20261101.py`）一樣；只加特徵同量度（見 protocol §4）。
"""
from __future__ import annotations

import argparse
import collections
import csv
import glob
import json
import random
import re
import statistics as st
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO / ".agents/skills/au_racing/au_wong_choi_auto/scripts"))
sys.path.insert(0, str(REPO / "scratch"))
sys.path.insert(0, str(HERE))
from au_racing_engine.full_time_speed import norm, seconds  # noqa: E402
from au_result_identity import normalize_venue_name  # noqa: E402
import au_rq_sectionals_diag_20261101 as e42  # noqa: E402
import deep  # noqa: E402  (clogit／boot)

TARGET_FROM, TEST_FROM, CLEAN_FROM = "2026-01-01", "2026-07-01", "2026-08-05"
DECAY, MAX_RUNS, MIN_FIELD = 0.8, 6, 4
FEATS = ("fin", "L600", "early", "CxP", "Lpos", "ground")
AGGS = ("w6", "last", "best3")


def gfam(c):
    c = (c or "").lower()
    return "heavy" if "heavy" in c else "soft" if "soft" in c else "good"


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
            rname = root.findtext("RaceName") or ""
            if re.search(r"TRIAL|JUMP.?OUT", rname, re.I):
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
                ranks = {}
                for t in h.findall("./Ranks/SerializableTupleOfDoubleInt32"):
                    try:
                        ranks[float(t.findtext("Item1"))] = int(t.findtext("Item2"))
                    except (TypeError, ValueError):
                        pass
                dist = pts[-1]
                try:
                    trav = float(h.attrib.get("DistanceTravelled") or "nan")
                except ValueError:
                    trav = float("nan")
                horses.append({"horse": norm(h.attrib["Name"]), "fin": fin, "L600": sum(sp[-3:]), "early": fin - sum(sp[-3:]),
                               "rank600": ranks.get(dist - 600), "trav": trav, "dist": dist})
            if len(horses) >= 4:
                races[(course, date, int(m[1]))] = {"horses": horses, "going": root.findtext("TrackCondition") or "", "name": rname}
    return races


def dband(d):
    return "s" if d <= 1200 else "m" if d <= 1700 else "l"


def relative(races):
    """每仗同場相對（越大越好），之後地況族×路程段去中心、Lpos 殘差 —— 參數只用 train（< TEST_FROM）。"""
    raw = []  # (horse, date, key, dict)
    for (course, date, rno), R in races.items():
        hs = R["horses"]
        med = {k: st.median(h[k] for h in hs) for k in ("fin", "L600", "early")}
        if min(med.values()) <= 0:
            continue
        trav = [h["trav"] for h in hs if h["trav"] == h["trav"] and h["trav"] > 0]
        mt = st.median(trav) if len(trav) >= 4 else None
        n = len(hs)
        dist = hs[0]["dist"]
        pace = (dist - 600) / med["early"] * 3.6 if dist > 600 else None
        key = (dband(dist), gfam(R["going"]))
        for h in hs:
            v = {"fin": -(h["fin"] / med["fin"] - 1), "L600": -(h["L600"] / med["L600"] - 1), "early": -(h["early"] / med["early"] - 1)}
            if mt and h["trav"] == h["trav"] and h["trav"] > 0:
                v["ground"] = -(h["trav"] / mt - 1)
            if h["rank600"] and n > 1:
                v["_p600"] = (h["rank600"] - 1) / (n - 1)
            if pace is not None:
                v["_pace"] = pace
            raw.append((h["horse"], date, key, v))
    tr = [r for r in raw if r[1] < TEST_FROM]
    cent = collections.defaultdict(lambda: collections.defaultdict(list))
    pace_cell = collections.defaultdict(list)
    lp = []
    for _h, _d, key, v in tr:
        for k in ("fin", "L600", "early", "ground"):
            if k in v:
                cent[key][k].append(v[k])
        if "_pace" in v:
            pace_cell[key].append(v["_pace"])
        if "_p600" in v:
            lp.append((v["_p600"], v["L600"]))
    cm = {key: {k: st.mean(x) for k, x in d.items()} for key, d in cent.items()}
    pz = {key: (st.mean(x), st.pstdev(x)) for key, x in pace_cell.items() if len(x) >= 30 and st.pstdev(x) > 0}
    b, a = np.polyfit([p for p, _ in lp], [l for _, l in lp], 1)
    runs = collections.defaultdict(list)
    for h, d, key, v in raw:
        o = {k: v[k] - cm.get(key, {}).get(k, 0.0) for k in ("fin", "L600", "early", "ground") if k in v}
        if "_pace" in v and key in pz:
            o["CxP"] = v["L600"] * (v["_pace"] - pz[key][0]) / pz[key][1]
        if "_p600" in v:
            o["Lpos"] = v["L600"] - (a + b * v["_p600"])
        runs[h].append((d, o))
    for x in runs.values():
        x.sort(key=lambda t: t[0], reverse=True)
    return runs, {"lpos": [float(a), float(b)], "pace_cells": len(pz), "rows": len(raw)}


def history(runs, horse, date):
    prior = [r for d, r in runs.get(horse, []) if d < date][:MAX_RUNS]
    if not prior:
        return None
    out = {}
    for k in FEATS:
        vals = [(i, r[k]) for i, r in enumerate(prior) if k in r]
        if not vals:
            continue
        w = [DECAY ** i for i, _ in vals]
        out[f"{k}.w6"] = sum(wi * x for wi, (_, x) in zip(w, vals)) / sum(w)
        out[f"{k}.last"] = vals[0][1]
        out[f"{k}.best3"] = max(x for i, x in vals if i < 3) if any(i < 3 for i, _ in vals) else None
    return out


def build(races, runs, scores):
    keys = [f"{k}.{a}" for k in FEATS for a in AGGS]
    out = []
    for (course, date, rno), R in sorted(races.items(), key=lambda x: x[0][1]):
        if date < TARGET_FROM:
            continue
        order = sorted(R["horses"], key=lambda h: h["fin"])
        placed = {h["horse"] for h in order[:3]}
        winner = order[0]["horse"]
        sc = scores.get((date, course, rno), {})
        rows = []
        for h in R["horses"]:
            hist = history(runs, h["horse"], date)
            if hist:
                rows.append({"horse": h["horse"], "y": int(h["horse"] in placed), "w": int(h["horse"] == winner),
                             "pos": 1 if h["horse"] == winner else (2 if h["horse"] in placed else 9),
                             "hist": hist, "base": sc.get(h["horse"])})
        if len(rows) >= MIN_FIELD and 0 < sum(r["y"] for r in rows) < len(rows):
            z = {}
            for k in keys:
                z[k] = deep.zin([r["hist"].get(k) for r in rows])
            for i, r in enumerate(rows):
                r["z"] = {k: z[k][i] for k in keys}
            if all(r["base"] is not None for r in rows) and date >= CLEAN_FROM:
                bz = deep.zin([r["base"] for r in rows])
                for r, b in zip(rows, bz):
                    r["z"]["base"] = b
            out.append({"day": date, "rows": rows, "has_base": "base" in rows[0]["z"]})
    return out


def auc_by_day(data, key, target="y"):
    by = collections.defaultdict(list)
    for r in data:
        v = [x["z"][key] for x in r["rows"]]; y = [x[target] for x in r["rows"]]
        a = deep.ev.race_auc(v, y)
        if a is not None:
            by[r["day"]].append(a)
    return by


def mean(xs):
    return st.mean(xs) if xs else None


def test_ll_auc(train, test, cols0, cols1):
    b0 = deep.clogit(train, "place", cols0); b1 = deep.clogit(train, "place", cols1)
    ll, ad = collections.defaultdict(list), collections.defaultdict(list)
    for r in test:
        y = np.array([x["y"] for x in r["rows"]], bool)
        for cols, b, sgn in ((cols0, b0, -1), (cols1, b1, 1)):
            pass
        u0 = np.array([[x["z"][c] for c in cols0] for x in r["rows"]]) @ b0
        u1 = np.array([[x["z"][c] for c in cols1] for x in r["rows"]]) @ b1
        lse = lambda u: np.log(np.exp(u - u.max()).sum()) + u.max()
        ll[r["day"]].append(float((u1[y] - lse(u1)).sum() - (u0[y] - lse(u0)).sum()) / max(1, y.sum()))
        a0 = deep.ev.race_auc(list(u0), list(y)); a1 = deep.ev.race_auc(list(u1), list(y))
        if a0 is not None:
            ad[r["day"]].append(a1 - a0)
    return {"coef": [round(float(x), 4) for x in b1], "ll_per_placed": deep.boot_days(ll, mean), "auc_delta": deep.boot_days(ad, mean)}


def load_scores():
    """我哋 QLD 場次（≥ CLEAN_FROM）嘅 final_rank_score：{(date, course, race): {horse: score}}。"""
    root = Path(open(REPO / ".wongchoi_au_data_root").read().strip())
    out = {}
    for base in (root, root / "Archive"):
        if not base.exists():
            continue
        for d in base.iterdir():
            m = re.match(r"(\d{4}-\d{2}-\d{2}) (.+?) Race ", d.name)
            if not m or m.group(1) < CLEAN_FROM:
                continue
            p = d / "Meeting_Auto_Scoring.csv"
            if not p.exists():
                continue
            course = normalize_venue_name(m.group(2))
            with open(p, encoding="utf-8-sig") as fh:
                for row in csv.DictReader(fh):
                    try:
                        out.setdefault((m.group(1), course, int(row["race_number"])), {})[norm(row["horse_name"])] = float(row["final_rank_score"])
                    except (ValueError, KeyError):
                        pass
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--rq", default=str(Path(open(REPO / ".wongchoi_au_data_root").read().strip()).parent / "AU_Racing_Time_Evidence"))
    args = ap.parse_args()
    races = parse(args.rq)
    runs, info = relative(races)
    scores = load_scores()
    data = build(races, runs, scores)
    train = [r for r in data if r["day"] < TEST_FROM]; test = [r for r in data if r["day"] >= TEST_FROM]
    rep = {"rq_races": len(races), "target_races": len(data), "train": len(train), "test": len(test), "info": info,
           "dates": [data[0]["day"], data[-1]["day"]]}
    keys = [f"{k}.{a}" for k in FEATS for a in AGGS]
    # (i) 單獨 AUC（place、win）
    rep["standalone"] = {k: {"place_auc": deep.boot_days(auc_by_day(data, k), mean)[0], "win_auc": deep.boot_days(auc_by_day(data, k, "w"), mean)[0]}
                         for k in keys}
    # (ii) 疊加喺 fin.w6 上（EXP-42 尺）
    rep["over_fin"] = {}
    for k in keys:
        if k == "fin.w6":
            continue
        rep["over_fin"][k] = test_ll_auc(train, test, ["fin.w6"], ["fin.w6", k])
    # 互動：L600 喺快步速場（CxP）＋位置（Lpos）同時加
    rep["over_fin"]["L600+CxP+Lpos (w6)"] = test_ll_auc(train, test, ["fin.w6"], ["fin.w6", "L600.w6", "CxP.w6", "Lpos.w6"])
    # (iii) 對我哋模型分嘅殘差（≥ CLEAN_FROM、有分嘅 QLD 場）
    based = [r for r in data if r["has_base"]]
    rep["vs_our_model"] = {"races": len(based), "days": len({r["day"] for r in based})}
    if len(based) >= 30:
        base_auc = collections.defaultdict(list)
        for r in based:
            a = deep.ev.race_auc([x["z"]["base"] for x in r["rows"]], [x["y"] for x in r["rows"]])
            if a is not None:
                base_auc[r["day"]].append(a)
        rep["vs_our_model"]["base_place_auc"] = deep.boot_days(base_auc, mean)
        pv = {}
        for k in ("fin.w6", "L600.w6", "early.w6", "CxP.w6", "Lpos.w6", "ground.w6", "L600.best3", "L600.last"):
            res = deep.boot_clogit(based, "place", ["base", k], n=400)
            rep["vs_our_model"][k] = res
            if k.endswith(".w6") and k != "fin.w6":
                pv[k] = res["p_boot"]
        rep["vs_our_model"]["holm"] = deep.holm_adjust(pv)
    Path(args.out).write_text(json.dumps(rep, indent=1, default=str))
    print(json.dumps(rep, indent=1, default=str)[:6000])


if __name__ == "__main__":
    main()
