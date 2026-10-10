"""EXP-20261010-10 screening: 增程／縮程 × 分段形態, 從化新鮮感 — residual over the 9D composite."""
import json, re, sys, random
from datetime import date
from pathlib import Path
import numpy as np
from scipy.optimize import minimize

ROOT = Path("/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/HK_Racing")
TAU = 3.0
rows = [json.loads(l) for l in open(sys.argv[1]) if '"error"' not in l]
rows = [r for r in rows if r.get("horses") and "speed_score" not in (r.get("meeting_dead_fields") or [])]


def blocks(facts: Path):
    text = facts.read_text(encoding="utf-8")
    out = {}
    parts = re.split(r"^### 馬號 (\d+) — ", text, flags=re.M)
    for i in range(1, len(parts), 2):
        out[int(parts[i])] = parts[i + 1]
    return out


def parse(block: str):
    dists = [int(d) for d, n in re.findall(r"(\d{3,4})m: (\d+)場", block.split("距離分佈:")[1].split("\n")[0])] if "距離分佈:" in block else []
    d1, d2, d4 = [], [], []
    if "全段速剖面" in block:
        tbl = block.split("全段速剖面")[1].split("🔧")[0]
        for line in tbl.splitlines():
            c = [x.strip() for x in line.strip().strip("|").split("|")]
            if len(c) >= 12 and c[0].isdigit():
                try:
                    t = (float(c[7]), float(c[8]), float(c[10]))
                    d1.append(t[0]); d2.append(t[1]); d4.append(t[2])
                except ValueError:
                    pass
    return dists, d1, d2, d4


def conghua(tw: Path, race_date: date):
    try:
        d = json.loads(tw.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out = {}
    hh = d.get("horses", [])
    hh = list(hh.values()) if isinstance(hh, dict) else hh
    for h in hh:
        if not isinstance(h, dict):
            continue
        ents = h.get("entries") or []
        if not ents:
            continue
        ch = [e["date"] for e in ents if "從化" in (e.get("location") or "")]
        last = max(e["date"] for e in ents)
        if ch:
            lc = max(ch)
            returned = any("從化" not in (e.get("location") or "") and e["date"] > lc for e in ents)
            gap = (race_date - date.fromisoformat(lc)).days
            stay = (date.fromisoformat(lc) - date.fromisoformat(min(ch))).days + 1
            out[int(h["horse_no"])] = {"ch_any": 1.0, "ch_returned": 1.0 if returned else 0.0, "ch_days": gap,
                                   "ch_fresh": 1.0 if returned and stay >= 7 and gap <= 14 else 0.0,
                                   "ch_stay": stay, "n_ent": len(ents)}
        else:
            out[int(h["horse_no"])] = {"ch_any": 0.0, "ch_returned": 0.0, "ch_days": None, "ch_fresh": 0.0, "ch_stay": 0, "n_ent": len(ents)}
    return out


FEATS = ["ch_fresh", "ch_days", "ch_stay", "step_up", "step_down", "up_x_lateshape", "down_x_earlyfast", "ch_any", "ch_returned", "lateshape", "earlyfast"]
races = []
for r in rows:
    md = ROOT / r["meeting"]
    mmdd = r["date"][5:]
    facts = md / f"{mmdd} Race {r['race']} Facts.md"
    if not facts.exists():
        continue
    b = blocks(facts)
    if not r.get("distance"):
        m = re.search(r"\((\d{3,4})m", facts.read_text(encoding="utf-8")[:3000])
        r["distance"] = int(m.group(1)) if m else None
    if not r.get("distance"):
        continue
    tw = conghua(md / f"{r['date']} Race {r['race']} 晨操.json", date.fromisoformat(r["date"]))
    hs = []
    for h in r["horses"]:
        if not h.get("pos"):
            continue
        f = {k: None for k in FEATS}
        if h["n"] in b:
            dists, d1, d2, d4 = parse(b[h["n"]])
            if dists:
                f["step_up"] = 1.0 if r["distance"] > max(dists) else 0.0
                f["step_down"] = 1.0 if r["distance"] < min(dists) else 0.0
            if d1:
                f["lateshape"] = float(np.mean(d1) - np.mean(d4))   # >0 = slow early, fast late
                f["earlyfast"] = float(-(np.mean(d1) + np.mean(d2)))  # >0 = fast first two sections
                if f["step_up"] is not None:
                    f["up_x_lateshape"] = f["step_up"] * f["lateshape"]
                    f["down_x_earlyfast"] = f["step_down"] * f["earlyfast"]
        if tw:
            c = tw.get(h["n"])
            if c:
                for k in ("ch_any", "ch_returned", "ch_fresh", "ch_days", "ch_stay"):
                    f[k] = c[k]
        hs.append((h, f))
    if len(hs) >= 4 and any(h["pos"] <= 3 for h, _ in hs):
        races.append((r["date"], hs))

races.sort(key=lambda x: x[0])
dates = sorted({d for d, _ in races})
cut = dates[int(len(dates) * 0.6)]
print(f"races {len(races)}, train < {cut}")

for k in FEATS:
    vals = [f[k] for _, hs in races for h, f in hs]
    have = [v for v in vals if v is not None]
    print(f"  {k:18s} coverage {len(have)/len(vals):.0%}  nonzero {sum(1 for v in have if v)}")


def mats(rs, keys):
    out = []
    for _, hs in rs:
        x = []
        for k in keys:
            col = [f[k] for _, f in hs]
            m = np.mean([v for v in col if v is not None]) if any(v is not None for v in col) else 0.0
            x.append([(v if v is not None else m) for v in col])
        x = np.array(x).T
        x = x - x.mean(0)
        off = np.array([h["raw"] for h, _ in hs]) / TAU
        y = np.array([1.0 if h["pos"] <= 3 else 0.0 for h, _ in hs]); y /= y.sum()
        out.append((x, off, y))
    return out


def ll(beta, data):
    lls = []
    for x, off, y in data:
        s = off + x @ beta; s -= s.max()
        lls.append(float(y @ (s - np.log(np.exp(s).sum()))))
    return np.array(lls)


def test(keys):
    tr = mats([r for r in races if r[0] < cut], keys)
    te = mats([r for r in races if r[0] >= cut], keys)
    res = minimize(lambda b: -ll(b, tr).mean() + 0.01 * (b ** 2).sum(), np.zeros(len(keys)), method="L-BFGS-B")
    d = ll(res.x, te) - ll(np.zeros(len(keys)), te)
    rng = random.Random(7)
    boots = sorted(np.mean([d[rng.randrange(len(d))] for _ in d]) for _ in range(500))
    print(f"{'+'.join(keys):40s} beta {np.round(res.x, 3)}  OOS ΔLL {d.mean():+.4f} CI[{boots[12]:+.4f},{boots[487]:+.4f}] n_test {len(d)}")


def cohort(name, pred):
    act = exp = n = 0
    for _, hs in races:
        s = np.array([h["raw"] for h, _ in hs]) / TAU; p = np.exp(s - s.max()); p /= p.sum()
        k = sum(1 for h, _ in hs if h["pos"] <= 3)
        for i, (h, f) in enumerate(hs):
            if pred(f):
                n += 1; act += h["pos"] <= 3; exp += p[i] * k
    if n:
        print(f"  cohort {name:34s} n {n:4d} actual {act/n:.1%} model-expected {exp/n:.1%} excess {(act-exp)/n:+.1%}")


cohort("首次增程", lambda f: f["step_up"] == 1)
cohort("首次增程 + 慢開快收 (lateshape>0)", lambda f: f["step_up"] == 1 and (f["lateshape"] or 0) > 0)
cohort("首次增程 + 快開 (lateshape<=0)", lambda f: f["step_up"] == 1 and (f["lateshape"] or 0) <= 0)
cohort("首次縮程", lambda f: f["step_down"] == 1)
cohort("首次縮程 + 頭兩段快 (earlyfast>0)", lambda f: f["step_down"] == 1 and (f["earlyfast"] or 0) > 0)
cohort("首次縮程 + 頭兩段慢", lambda f: f["step_down"] == 1 and (f["earlyfast"] or 0) <= 0)
cohort("晨操窗內有從化", lambda f: f["ch_any"] == 1)
cohort("由從化返沙田", lambda f: f["ch_returned"] == 1)
cohort("從化逗留>=7日、返沙田<=14日", lambda f: f["ch_fresh"] == 1)
cohort("返沙田 15-30 日", lambda f: f["ch_returned"] == 1 and f["ch_days"] is not None and 15 <= f["ch_days"] <= 30)
cohort("仍喺從化（最後晨操喺從化）", lambda f: f["ch_any"] == 1 and f["ch_returned"] == 0)
cohort("從化逗留>=14日", lambda f: (f["ch_stay"] or 0) >= 14)
cohort("晨操窗內冇從化", lambda f: f["ch_any"] == 0)

for keys in (["up_x_lateshape"], ["down_x_earlyfast"], ["step_up", "up_x_lateshape"], ["step_down", "down_x_earlyfast"],
             ["lateshape"], ["earlyfast"], ["ch_any"], ["ch_returned"], ["ch_fresh"],
             ["step_up", "up_x_lateshape", "step_down", "down_x_earlyfast"]):
    test(keys)
