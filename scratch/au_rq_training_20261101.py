#!/usr/bin/env python3
"""EXP-20261101-40 訓練表：RQ 真實本駒末段 600m × Sportsbet Formguide 往績行（point-in-time 用 run_date）。

    python3 au_rq_training_20261101.py --truth rq_truth.json --races races.json --root AU_ROOT --out training.json
輸出逐匹次：date、y（真實末段 600m − Sportsbet 賽事 L600 原秒）、特徵所需欄位。
"""
import argparse, glob, json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".agents/skills/au_racing/au_wong_choi_auto/scripts"))
from au_racing_engine.full_time_speed import norm
from au_racing_engine.engine_core import _normalize_track_name

HDR = re.compile(r"^\[(\d+)\]\s+(.+?)\s+\(\d+\)\s*$")
RUN = re.compile(r"^(.+?)\s+R(\d+)\s+(\d{4}-\d{2}-\d{2})\s+(\d+)m\s+cond:(\S+)")


def key(track, date, race):
    return (re.sub(r"[^a-z]", "", track.lower()), date, int(race))


def main():
    ap = argparse.ArgumentParser()
    for a in ("--truth", "--races", "--root", "--out"):
        ap.add_argument(a, required=True)
    args = ap.parse_args()
    races = json.loads(Path(args.races).read_text())
    truth = {}
    for k, v in json.loads(Path(args.truth).read_text()).items():
        c, d, r = k.split("|")
        truth[key(c, d, r)] = {h["horse"]: h for h in v}
    recs = {}
    for f in glob.glob(args.root + "/**/*Formguide.md", recursive=True):
        horse = None
        for line in open(f, encoding="utf-8"):
            h = HDR.match(line.strip())
            if h:
                horse = norm(h[2]); continue
            if not horse or "TRIAL" in line.upper():
                continue
            m = RUN.match(line.strip())
            if not m:
                continue
            tr = _normalize_track_name(m[1].strip()); k = key(tr, m[3], m[2])
            if k not in truth or horse not in truth[k]:
                continue
            race = races.get(f"{tr}|{m[3]}|{int(m[2])}")
            mg = re.search(r"margin:([0-9.]+)", line); fin = re.search(r"finish:(\d+)/(\d+)", line)
            p8 = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)@800m", line); p4 = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)@400m", line)
            if not (race and race["reliable"] and mg and fin):
                continue
            recs[(horse, k)] = {"date": m[3], "y": truth[k][horse]["l600"] - race["raw"], "margin": float(mg[1]),
                                "pos_800": int(p8[1]) if p8 else None, "pos_400": int(p4[1]) if p4 else None,
                                "finish": int(fin[1]), "starters": int(fin[2]), "race": "|".join(map(str, k)),
                                "true": truth[k][horse]["l600"], "raw": race["raw"]}
    out = sorted(recs.values(), key=lambda r: r["date"])
    Path(args.out).write_text(json.dumps(out))
    print("training rows", len(out), "races", len({r["race"] for r in out}), out[0]["date"], "→", out[-1]["date"])


if __name__ == "__main__":
    main()
