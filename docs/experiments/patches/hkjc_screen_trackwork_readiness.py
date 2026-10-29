"""EXP-20261029-01 B — pre-registered trackwork readiness screen (residual over the composite).

    python3 hkjc_screen_trackwork_readiness.py base_dump.jsonl

Every feature uses only rows dated before race day, race rows (出賽) dropped,
treadmill by type_raw.  Method as EXP-20261010-11: conditional logit with the
baseline composite (raw/τ) as offset, first 60% of dates fit, last 40% test,
race bootstrap CI; Holm across the six pre-registered features.
"""
import json
import random
import re
import statistics
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / ".agents/skills/hkjc_racing/hkjc_race_extractor/scripts"))
import extract_trackwork as xt  # noqa: E402

ROOT = Path("/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/HK_Racing")
TAU = 3.0
FEATS = ["trial_any", "days_since_work", "post_race_load", "work_speed_z", "habit_dev", "jockey_work"]


def clean(entries, race_date):
    out = []
    for e in entries or []:
        if not isinstance(e, dict) or e.get("type_raw") == "出賽" or str(e.get("date")) >= race_date:
            continue
        e = dict(e)
        if "final_time" not in e:
            t = xt.parse_work_times(e.get("details") or "")
            e["sectionals"], e["final_time"] = t["sectionals"], t["final_time"]
        if "跑步機" in str(e.get("type_raw") or ""):
            e["type"] = "treadmill"
        out.append(e)
    return out


def load_files():
    """{(meeting, race): {horse_no: horse}}, plus race date per meeting."""
    out = {}
    for f in ROOT.glob("20*_*/* Race * 晨操.json"):
        if not re.match(r"\d{4}-\d{2}-\d{2}_(ShaTin|HappyValley)$", f.parent.name):
            continue
        m = re.search(r"Race (\d+) 晨操", f.name)
        d = json.loads(f.read_text(encoding="utf-8"))
        hs = d.get("horses") or {}
        hs = hs.values() if isinstance(hs, dict) else hs
        out[(f.parent.name, int(m.group(1)))] = {int(h["horse_no"]): h for h in hs if isinstance(h, dict)}
    return out


def serious(e):
    return e["type"] in ("gallop", "trial")


def last_split(e):
    s = [x for x in (e.get("sectionals") or []) if 20.0 <= x <= 30.0]
    return s[-1] if s else None


def build():
    files = load_files()
    # 參照群體：同日同地點所有快操嘅最後一段（操練本身喺賽前發生）
    pool = defaultdict(dict)
    for (meeting, _), hs in files.items():
        for h in hs.values():
            for e in clean(h.get("entries"), meeting[:10]):
                if e["type"] == "gallop" and last_split(e) is not None:
                    pool[(e["date"], e.get("location") or "")][(h.get("horseid"), e["date"])] = last_split(e)
    # 每匹馬之前嘅窗口課數（habit）
    history = defaultdict(list)  # horseid -> [(race_date, serious_count)]
    for (meeting, _), hs in sorted(files.items()):
        for h in hs.values():
            ents = clean(h.get("entries"), meeting[:10])
            if ents:
                history[h.get("horseid")].append((meeting[:10], sum(1 for e in ents if serious(e))))
    feats = {}
    for (meeting, race), hs in files.items():
        rd = meeting[:10]
        for no, h in hs.items():
            raw = [e for e in h.get("entries") or [] if isinstance(e, dict)]
            ents = clean(raw, rd)
            if not ents:
                continue
            ser = [e for e in ents if serious(e)]
            last_ser = max((e["date"] for e in ser), default=None)
            days = (date.fromisoformat(rd) - date.fromisoformat(last_ser)).days if last_ser else 22
            prev_races = [e["date"] for e in raw if e.get("type_raw") == "出賽" and str(e.get("date")) < rd]
            since = max(prev_races) if prev_races else min(e["date"] for e in ents)
            span = max(1, (date.fromisoformat(rd) - date.fromisoformat(since)).days)
            load = sum((2 if e["type"] == "trial" else 1) for e in ser if e["date"] > since or not prev_races)
            gal = [e for e in ents if e["type"] == "gallop" and last_split(e) is not None]
            z = None
            if gal:
                e = max(gal, key=lambda x: x["date"])
                ref = list(pool[(e["date"], e.get("location") or "")].values())
                if len(ref) >= 8:
                    sd = statistics.pstdev(ref)
                    if sd > 0:
                        z = -(last_split(e) - statistics.mean(ref)) / sd
            prior = [c for d, c in history[h.get("horseid")] if d < rd]
            habit = (len(ser) - statistics.mean(prior)) if prior else 0.0
            jk = xt.normalize_person_name(h.get("jockey") or "")
            jw = bool(jk) and any(jk in xt.normalize_person_name(f"{e.get('rider', '')} {e.get('details', '')}") for e in ents)
            feats[(meeting, race, no)] = {
                "trial_any": 1.0 if any(e["type"] == "trial" for e in ents) else 0.0,
                "days_since_work": float(min(days, 22)),
                "post_race_load": load * 7.0 / span,
                "work_speed_z": z,
                "habit_dev": float(habit),
                "jockey_work": 1.0 if jw else 0.0,
                "_has_prior": bool(prior),
            }
    return feats


def races_from(dump, feats):
    races = []
    for line in open(dump):
        r = json.loads(line)
        if "error" in r or not r.get("horses") or "speed_score" in (r.get("meeting_dead_fields") or []):
            continue
        hs = []
        for h in r["horses"]:
            if not h.get("pos") or h["debut"]:
                continue
            f = feats.get((r["meeting"], r["race"], h["n"]))
            if f is None:
                continue
            hs.append((h, f))
        if len(hs) >= 4 and any(h["pos"] <= 3 for h, _ in hs):
            races.append((r["date"], hs))
    return sorted(races, key=lambda x: x[0])


def mats(rs, keys):
    out = []
    for _, hs in rs:
        x = []
        for k in keys:
            col = [f[k] for _, f in hs]
            have = [v for v in col if v is not None]
            m = float(np.mean(have)) if have else 0.0
            x.append([(v if v is not None else m) for v in col])
        x = np.array(x, dtype=float).T
        x = x - x.mean(0)
        off = np.array([h["raw"] for h, _ in hs]) / TAU
        y = np.array([1.0 if h["pos"] <= 3 else 0.0 for h, _ in hs]); y /= y.sum()
        out.append((x, off, y))
    return out


def ll(beta, data):
    res = []
    for x, off, y in data:
        s = off + x @ beta; s -= s.max()
        res.append(float(y @ (s - np.log(np.exp(s).sum()))))
    return np.array(res)


def auc_in_race(races, key):
    """場內 AUC（前三 vs 其他），只計有值嘅馬。"""
    num = den = 0.0
    for _, hs in races:
        pos = [f[key] for h, f in hs if h["pos"] <= 3 and f[key] is not None]
        neg = [f[key] for h, f in hs if h["pos"] > 3 and f[key] is not None]
        for a in pos:
            for b in neg:
                den += 1; num += 1.0 if a > b else 0.5 if a == b else 0.0
    return num / den if den else float("nan")


def main():
    feats = build()
    races = races_from(sys.argv[1], feats)
    dates = sorted({d for d, _ in races})
    cut = dates[int(len(dates) * 0.6)]
    tr, te = [r for r in races if r[0] < cut], [r for r in races if r[0] >= cut]
    print(f"races {len(races)} (meetings {len(dates)}), fit < {cut}: {len(tr)}, test: {len(te)}")
    rng = random.Random(7)
    results = []
    for k in FEATS:
        vals = [f[k] for _, hs in races for _, f in hs]
        have = [v for v in vals if v is not None]
        a, b = mats(tr, [k]), mats(te, [k])
        fit = minimize(lambda w: -ll(w, a).mean() + 0.01 * (w ** 2).sum(), np.zeros(1), method="L-BFGS-B")
        d = ll(fit.x, b) - ll(np.zeros(1), b)
        boots = np.array([np.mean([d[rng.randrange(len(d))] for _ in d]) for _ in range(2000)])
        p = float((boots <= 0).mean())
        results.append((k, len(have) / len(vals), float(np.mean(have)), fit.x[0], d.mean(),
                        np.percentile(boots, 2.5), np.percentile(boots, 97.5), p, auc_in_race(races, k)))
    # Holm（單邊 p = bootstrap ≤ 0 比例）
    order = sorted(range(len(results)), key=lambda i: results[i][7])
    holm, running = {}, 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, results[i][7] * (len(results) - rank)))
        holm[i] = running
    print(f"{'feature':16s} cover   mean    beta    OOS ΔLL  95% CI              p    Holm  AUC")
    for i, (k, cov, mean, beta, dll, lo, hi, p, auc) in enumerate(results):
        print(f"{k:16s} {cov:5.0%} {mean:7.2f} {beta:+7.3f} {dll:+.4f} [{lo:+.4f}, {hi:+.4f}] {p:.3f} {holm[i]:.3f} {auc:.4f}")
    # cohort 超額（模型預期 vs 實際上名）
    def cohort(name, pred):
        act = exp = n = 0
        for _, hs in races:
            s = np.array([h["raw"] for h, _ in hs]) / TAU; pr = np.exp(s - s.max()); pr /= pr.sum()
            kk = sum(1 for h, _ in hs if h["pos"] <= 3)
            for i, (h, f) in enumerate(hs):
                if pred(f):
                    n += 1; act += h["pos"] <= 3; exp += pr[i] * kk
        if n:
            print(f"  cohort {name:28s} n {n:5d} actual {act / n:6.1%} expected {exp / n:6.1%} excess {(act - exp) / n:+6.1%}")
    cohort("有試閘", lambda f: f["trial_any"] == 1)
    cohort("最後一課 ≤3 日", lambda f: f["days_since_work"] <= 3)
    cohort("最後一課 ≥8 日", lambda f: f["days_since_work"] >= 8)
    cohort("上仗後負荷 ≥3/週", lambda f: f["post_race_load"] >= 3)
    cohort("上仗後負荷 <1/週", lambda f: f["post_race_load"] < 1)
    cohort("最近快操 z ≥ +1", lambda f: f["work_speed_z"] is not None and f["work_speed_z"] >= 1)
    cohort("最近快操 z ≤ −1", lambda f: f["work_speed_z"] is not None and f["work_speed_z"] <= -1)
    cohort("課數高過平時 ≥2", lambda f: f["_has_prior"] and f["habit_dev"] >= 2)
    cohort("課數低過平時 ≤−2", lambda f: f["_has_prior"] and f["habit_dev"] <= -2)
    cohort("騎師真係有操（剔出賽）", lambda f: f["jockey_work"] == 1)


if __name__ == "__main__":
    main()
