"""EXP-20261029-02 — trackwork v2: four new readings + walk-forward ten-feature adjustment.

    python3 hkjc_trackwork_v2.py screen base_dump.jsonl
    python3 hkjc_trackwork_v2.py walkforward base_dump.jsonl --out cand.jsonl [--current]

`walkforward` refits, for every meeting, a conditional logit on all *earlier*
meetings (offset = baseline composite / τ) and shifts that meeting's
non-debut runners by τ·xβ, then re-ranks.  The first BURN_IN meetings are left
alone.  `--current` writes the unshifted re-rank (sanity: must reproduce the
production picks).
"""
import argparse
import json
import random
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / ".agents/skills/hkjc_racing/hkjc_reflector/scripts"))
sys.path.insert(0, str(REPO / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts"))
sys.path.insert(0, str(REPO / ".agents/skills/shared_racing"))

import hkjc_screen_trackwork_readiness as v1  # noqa: E402

TAU, L2, BURN_IN = 3.0, 0.01, 10
OLD = v1.FEATS
NEW = ["trial_speed_z", "trial_finish_z", "work_accel_z", "quality_work"]
ALL = OLD + NEW


def _z(value, ref, sign=-1.0, minimum=6):
    if value is None or len(ref) < minimum:
        return None
    sd = statistics.pstdev(ref)
    return sign * (value - statistics.mean(ref)) / sd if sd > 0 else None


def new_features():
    files = v1.load_files()
    trial_pool = defaultdict(dict)    # (date, location, distance) -> {(horse, date): (final, last)}
    gallop_pool = defaultdict(dict)   # (date, location) -> {(horse, date): (last, accel)}
    per_horse = {}
    for (meeting, race), hs in files.items():
        for no, h in hs.items():
            ents = v1.clean(h.get("entries"), meeting[:10])
            per_horse[(meeting, race, no)] = ents
            for e in ents:
                key = (h.get("horseid"), e["date"])
                secs = [x for x in (e.get("sectionals") or []) if 20.0 <= x <= 40.0]
                if e["type"] == "trial":
                    dist = re.search(r"(\d{3,4})M", e.get("details") or "")
                    if dist and e.get("final_time"):
                        trial_pool[(e["date"], e.get("location") or "", dist.group(1))][key] = (
                            e["final_time"], secs[-1] if secs else None)
                elif e["type"] == "gallop" and secs:
                    accel = secs[-1] - secs[-2] if len(secs) >= 2 else None
                    gallop_pool[(e["date"], e.get("location") or "")][key] = (secs[-1], accel)
    out = {}
    for (meeting, race, no), ents in per_horse.items():
        if not ents:
            continue
        hid = files[(meeting, race)][no].get("horseid")
        f = {k: None for k in NEW}
        trials = [e for e in ents if e["type"] == "trial"]
        if trials:
            e = max(trials, key=lambda x: x["date"])
            dist = re.search(r"(\d{3,4})M", e.get("details") or "")
            if dist:
                pool = trial_pool[(e["date"], e.get("location") or "", dist.group(1))]
                mine = pool.get((hid, e["date"]))
                if mine:
                    f["trial_speed_z"] = _z(mine[0], [v[0] for v in pool.values()])
                    f["trial_finish_z"] = _z(mine[1], [v[1] for v in pool.values() if v[1] is not None])
        gallops = [e for e in ents if e["type"] == "gallop"]
        quality = 0
        latest_accel = None
        for e in sorted(gallops, key=lambda x: x["date"]):
            pool = gallop_pool[(e["date"], e.get("location") or "")]
            mine = pool.get((hid, e["date"]))
            if not mine:
                continue
            z = _z(mine[0], [v[0] for v in pool.values()], minimum=8)
            if z is not None and z >= 0.5:
                quality += 1
            if mine[1] is not None:
                latest_accel = _z(mine[1], [v[1] for v in pool.values() if v[1] is not None], minimum=8)
        f["work_accel_z"] = latest_accel
        f["quality_work"] = float(quality)
        out[(meeting, race, no)] = f
    return out


def all_features():
    old = v1.build()
    new = new_features()
    return {k: {**old[k], **new.get(k, {n: None for n in NEW})} for k in old}


def design(hs, keys):
    x = []
    for k in keys:
        col = [f[k] if f else None for _, f in hs]
        have = [v for v in col if v is not None]
        m = float(np.mean(have)) if have else 0.0
        x.append([(v if v is not None else m) for v in col])
    x = np.array(x, dtype=float).T
    return x - x.mean(0)


def screen(dump):
    feats = all_features()
    races = v1.races_from(dump, feats)
    dates = sorted({d for d, _ in races})
    cut = dates[int(len(dates) * 0.6)]
    tr, te = [r for r in races if r[0] < cut], [r for r in races if r[0] >= cut]
    rng = random.Random(7)
    res = []
    for k in NEW:
        a, b = v1.mats(tr, [k]), v1.mats(te, [k])
        w = minimize(lambda w: -v1.ll(w, a).mean() + L2 * (w ** 2).sum(), np.zeros(1), method="L-BFGS-B").x
        d = v1.ll(w, b) - v1.ll(np.zeros(1), b)
        boots = np.array([np.mean([d[rng.randrange(len(d))] for _ in d]) for _ in range(2000)])
        vals = [f[k] for _, hs in races for _, f in hs]
        cov = sum(v is not None for v in vals) / len(vals)
        res.append([k, cov, w[0], d.mean(), np.percentile(boots, 2.5), np.percentile(boots, 97.5),
                    float((boots <= 0).mean()), v1.auc_in_race(races, k)])
    order = sorted(range(len(res)), key=lambda i: res[i][6])
    run = 0.0
    for rank, i in enumerate(order):
        run = max(run, min(1.0, res[i][6] * (len(res) - rank)))
        res[i].append(run)
    print(f"races {len(races)}, fit < {cut}")
    for k, cov, beta, dll, lo, hi, p, auc, holm in res:
        print(f"{k:16s} cover {cov:4.0%} beta {beta:+.3f} OOS ΔLL {dll:+.4f} [{lo:+.4f}, {hi:+.4f}] "
              f"p {p:.3f} Holm {holm:.3f} AUC {auc:.4f}")


def walkforward(dump, out_path, current=False):
    from hkjc_weight_study import load, rank_row
    from hkjc_racing_engine import scoring

    feats = all_features()
    fit_races = v1.races_from(dump, feats)          # 非初出、有賽果、有晨操
    rows = load(dump)
    meetings = sorted({r["date"] for r in rows})
    base = dict(scoring.MATRIX_WEIGHTS)
    centred = dict(scoring.CENTRED_MATRIX_WEIGHTS)
    betas = {}
    for i, day in enumerate(meetings):
        if current or i < BURN_IN:
            continue
        train = v1.mats([r for r in fit_races if r[0] < day], ALL)
        betas[day] = minimize(lambda w: -v1.ll(w, train).mean() + L2 * (w ** 2).sum(),
                              np.zeros(len(ALL)), method="L-BFGS-B").x
    with open(out_path, "w", encoding="utf-8") as fh:
        for row in rows:
            beta = betas.get(row["date"])
            horses = [dict(h) for h in row["horses"]]
            if beta is not None:
                idx = [j for j, h in enumerate(horses)
                       if not h["debut"] and (row["meeting"], row["race"], h["n"]) in feats]
                if len(idx) >= 2:
                    hs = [(horses[j], feats[(row["meeting"], row["race"], horses[j]["n"])]) for j in idx]
                    shift = TAU * design(hs, ALL) @ beta
                    for j, s in zip(idx, shift):
                        horses[j]["raw"] = horses[j]["raw"] + float(s)
            fh.write(json.dumps(rank_row(dict(row, horses=horses), base, centred, base,
                                         "current" if current else "trackwork_v2_wf"), ensure_ascii=False) + "\n")
    if betas:
        last = betas[meetings[-1]]
        print("last-meeting β:", {k: round(float(b), 3) for k, b in zip(ALL, last)})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["screen", "walkforward"])
    ap.add_argument("dump")
    ap.add_argument("--out")
    ap.add_argument("--current", action="store_true")
    a = ap.parse_args()
    if a.cmd == "screen":
        screen(a.dump)
    else:
        walkforward(a.dump, a.out, a.current)


if __name__ == "__main__":
    main()
