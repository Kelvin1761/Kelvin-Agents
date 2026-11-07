#!/usr/bin/env python3
"""EXP-20261107-01：上仗競賽主任「受阻」評語 → 今仗入位超額（診斷，唔改模型）。

預先登記：docs/experiments/EXP-20261107-01-au-stewards-trouble-protocol.md
用法：python3 au_stewards_trouble_test.py [--root <AU 資料根>] [--out result.json] [--boot 2000]
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import glob
import html
import json
import os
import random
import re
import sys
from pathlib import Path

HEADER = re.compile(r"^\[\d+\]\s+(.+?)\s+\(")
RUN = re.compile(r"^(?P<venue>.+?) R(?P<race>\d+) (?P<date>\d{4}-\d{2}-\d{2}) (?P<dist>\d+)m cond:")
FINISH = re.compile(r"finish:(\d+)/(\d+)")
MARGIN = re.compile(r"margin:([\d.]+)L")
STARTERS = re.compile(r"starters:(\d+)")
FLUCS = re.compile(r"Flucs:([^A-Za-z]*?)(?=\s\d|\s[A-Za-z]|$)")
PRICE = re.compile(r"\$(\d+(?:\.\d+)?)")

START_CTX = re.compile(r"jump|start|began|begin|away|stride", re.I)
INTERF = re.compile(r"checked|crowded|inconvenienced|held up|blocked|steadied|tightened|clipped|hampered|"
                    r"carried (out|in|wide)|squeezed|denied|unable to obtain|awkwardly placed|bumped|made contact|"
                    r"struck|lost ground|lost its footing|severely", re.I)
START = re.compile(r"slow to begin|began (awkwardly|only fairly|poorly)|slowly away|slow into stride|blundered|"
                   r"commenced awkwardly|dwelt|missed the start|bumped (on jumping|at the start|at start)|on jumping|"
                   r"crowded on jumping|hampered on jumping", re.I)
WIDE = re.compile(r"wide (and )?without cover|(three|four|3|4)[- ]wide|raced wide|very wide", re.I)
VET = re.compile(r"lame|bled|blood in|cardiac|arrhythmia|roar|respiratory|sore|abnormal", re.I)
VET_NEG = re.compile(r"no abnormalit|no abs|passed fit", re.I)


def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", html.unescape(name).lower())


def labels(text: str) -> set[str]:
    out: set[str] = set()
    for sentence in re.split(r"(?<=[.;])\s+", text):
        if START.search(sentence):
            out.add("START")
        if START_CTX.search(sentence):
            continue
        if INTERF.search(sentence):
            out.add("INTERF")
        if WIDE.search(sentence):
            out.add("WIDE")
    if WIDE.search(text):
        out.add("WIDE")
    if VET.search(text) and not VET_NEG.search(text):
        out.add("VET")
    return out


def parse(root: Path):
    stewards: dict[tuple[str, str], str] = {}
    sb: dict[tuple[str, str], dict] = {}
    files = glob.glob(str(root / "**" / "*Formguide.md"), recursive=True)
    for path in files:
        horse = None
        pending = None  # racenet run key awaiting Stewards line
        try:
            lines = open(path, encoding="utf-8", errors="ignore").read().splitlines()
        except OSError:
            continue
        for line in lines:
            h = HEADER.match(line)
            if h:
                horse = norm(h.group(1))
                pending = None
                continue
            m = RUN.match(line)
            if m and horse:
                key = (horse, m.group("date"))
                trial = "(TRIAL)" in line
                f = FINISH.search(line)
                if f:
                    pending = None
                    if trial:
                        continue
                    mg = MARGIN.search(line)
                    st = STARTERS.search(line)
                    fl = re.search(r"Flucs:(.*?)(?:\s\d+(?:st|nd|rd|th)@|\smargin:|$)", line)
                    prices = PRICE.findall(fl.group(1)) if fl else []
                    rec = {
                        "finish": int(f.group(1)),
                        "field": int(st.group(1)) if st else int(f.group(2)),
                        "margin": float(mg.group(1)) if mg else None,
                        "sp": float(prices[-1]) if prices else None,
                        "venue": m.group("venue"),
                    }
                    if key not in sb or (sb[key]["sp"] is None and rec["sp"] is not None):
                        sb[key] = rec
                else:
                    pending = None if trial else key
                continue
            if line.startswith("Stewards:") and pending:
                text = line[len("Stewards:"):].strip()
                if text:
                    if text != "None" or pending not in stewards:
                        if stewards.get(pending, "None") == "None":
                            stewards[pending] = text
                pending = None
    return files, stewards, sb


def bucket(v, edges):
    for i, e in enumerate(edges):
        if v <= e:
            return i
    return len(edges)


def build_pairs(stewards, sb):
    by_horse = collections.defaultdict(list)
    for (horse, date), rec in sb.items():
        by_horse[horse].append((date, rec))
    pairs = []
    for horse, runs in by_horse.items():
        runs.sort()
        for (pd, p), (cd, c) in zip(runs, runs[1:]):
            gap = (dt.date.fromisoformat(cd) - dt.date.fromisoformat(pd)).days
            if gap <= 0 or gap > 180:
                continue
            text = stewards.get((horse, pd))
            if text is None:
                continue
            labs = {"NONE"} if text == "None" else labels(text)
            pct = (p["finish"] - 1) / max(p["field"] - 1, 1)
            pairs.append({
                "horse": horse, "p_date": pd, "c_date": cd, "text": text, "labels": sorted(labs),
                "p_finish": p["finish"], "p_field": p["field"],
                "s1": (bucket(pct, [0.25, 0.5, 0.75]),
                       bucket(p["margin"] if p["margin"] is not None else 99, [1, 3, 6]),
                       bucket(c["field"], [8, 12])),
                "s2": (bucket(c["sp"], [3, 5, 8, 13, 21]) if c["sp"] else None, bucket(c["field"], [8, 12])),
                "placed": int(c["finish"] <= 3),
            })
    return pairs


def excess(rows, label, skey):
    ctrl = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        if "NONE" in r["labels"] and r[skey][0] is not None:
            ctrl[r[skey]][0] += r["placed"]
            ctrl[r[skey]][1] += 1
    obs = exp = n = 0
    for r in rows:
        if label in r["labels"] and r[skey][0] is not None and ctrl[r[skey]][1] >= 20:
            c = ctrl[r[skey]]
            obs += r["placed"]
            exp += c[0] / c[1]
            n += 1
    if not n:
        return None, 0
    return (obs - exp) / n * 100, n


def boot(rows, label, skey, B, seed=20261107):
    rng = random.Random(seed)
    horses = collections.defaultdict(list)
    for r in rows:
        horses[r["horse"]].append(r)
    keys = list(horses)
    vals = []
    for _ in range(B):
        sample = [r for k in (rng.choice(keys) for _ in keys) for r in horses[k]]
        v, _n = excess(sample, label, skey)
        if v is not None:
            vals.append(v)
    vals.sort()
    lo = vals[int(0.025 * len(vals))]
    hi = vals[int(0.975 * len(vals)) - 1]
    p_one = sum(v <= 0 for v in vals) / len(vals)
    return lo, hi, p_one


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--boot", type=int, default=2000)
    a = ap.parse_args()
    root = Path(a.root or Path(__file__).resolve().parents[3].joinpath(".wongchoi_au_data_root").read_text().strip())
    files, stewards, sb = parse(root)
    pairs = build_pairs(stewards, sb)
    info = {
        "formguide_files": len(files), "racenet_runs_with_stewards_field": len(stewards),
        "racenet_runs_with_text": sum(t != "None" for t in stewards.values()),
        "sportsbet_runs": len(sb), "pairs": len(pairs),
        "pairs_text": sum(p["text"] != "None" for p in pairs),
        "label_counts_all": collections.Counter(l for p in pairs for l in p["labels"]),
        "p_date_range": [min(p["p_date"] for p in pairs), max(p["p_date"] for p in pairs)] if pairs else None,
    }
    print(json.dumps(info, ensure_ascii=False, default=dict, indent=1))
    results = {}
    for pop_name, pop in (("beaten_P>=4", [p for p in pairs if p["p_finish"] >= 4]), ("all", pairs)):
        for label in ("INTERF", "START", "WIDE", "VET"):
            for skey, ename in (("s1", "E1_form"), ("s2", "E2_market")):
                v, n = excess(pop, label, skey)
                if v is None:
                    continue
                lo, hi, p = boot(pop, label, skey, a.boot)
                results[f"{pop_name}|{label}|{ename}"] = {"excess_pp": round(v, 2), "n": n,
                                                          "ci95": [round(lo, 2), round(hi, 2)], "p_one_sided": p}
                print(f"{pop_name:12s} {label:7s} {ename:10s} n={n:5d} excess={v:+6.2f}pp "
                      f"CI[{lo:+.2f},{hi:+.2f}] p={p:.4f}", flush=True)
    # Holm over primary three (beaten, E1)
    prim = sorted(((results[f"beaten_P>=4|{l}|E1_form"]["p_one_sided"], l) for l in ("INTERF", "START", "WIDE")
                   if f"beaten_P>=4|{l}|E1_form" in results))
    holm = {}
    running = 0.0
    for i, (p, l) in enumerate(prim):
        running = max(running, min(1.0, p * (len(prim) - i)))
        holm[l] = running
    print("Holm:", holm)
    if a.out:
        Path(a.out).write_text(json.dumps({"info": info, "results": results, "holm": holm,
                                           "sample": pairs[:0]}, ensure_ascii=False, default=dict, indent=1))


if __name__ == "__main__":
    sys.exit(main())
