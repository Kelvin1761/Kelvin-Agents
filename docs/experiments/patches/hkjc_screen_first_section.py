"""Screen: first-section speed (S1 vs standard) and 引擎型態 variants — residual over the live 9D composite.
Method = EXP-20261010-10: within-race conditional logit, composite/3 offset, 60/40 date split, OOS ΔLL."""
import json, re, sys, random, statistics as st
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
from scipy.stats import spearmanr

ROOT = Path(open(".wongchoi_hk_data_root").read().strip())
TAU = 3.0
rows = [json.loads(l) for l in open(sys.argv[1]) if '"error"' not in l]
rows = [r for r in rows if r.get("horses") and "speed_score" not in (r.get("meeting_dead_fields") or [])]


def blocks(facts):
    parts = re.split(r"^### 馬號 (\d+) — ", facts.read_text(encoding="utf-8"), flags=re.M)
    return {int(parts[i]): parts[i + 1] for i in range(1, len(parts), 2)}


def profile(block):
    runs = []
    if "全段速剖面" not in block:
        return runs
    dcols = None
    for line in block.split("全段速剖面")[1].split("🔧")[0].splitlines():
        c = [x.strip() for x in line.strip().strip("|").split("|")]
        if c and c[0] == "#":
            dcols = [i for i, h in enumerate(c) if h.startswith("Δ")]
            continue
        if dcols and c and c[0].isdigit() and len(c) > max(dcols):
            d = [float(c[i]) for i in dcols if re.fullmatch(r"[+-]?\d+(\.\d+)?", c[i])]
            if len(d) >= 3:
                runs.append({"dist": int(c[2]) if c[2].isdigit() else None, "d": d})
    return runs


def first_calls(block):
    return []


def engine_label(block):
    m = re.search(r"引擎:\s*(\S+)", block)
    return m.group(1) if m else None


races = []
for r in rows:
    md = ROOT / r["meeting"]
    facts = sorted(md.glob(f"* Race {r['race']} Facts.md"))
    if not facts:
        continue
    bl = blocks(facts[0])
    # actual first call this race (outcome only — to test "fast S1 → good position")
    res = json.load(open(next(md.glob("*全日賽果.json"))))[str(r["race"])]["results"]
    fc = {}
    for x in res:
        rp = str(x.get("running_positions") or "").split()
        if rp and rp[0].isdigit() and str(x.get("horse_no", "")).isdigit():
            fc[int(x["horse_no"])] = int(rp[0])
    hs = []
    for h in [x for x in r["horses"] if x.get("pos")]:
        b = bl.get(h["n"], "")
        runs = profile(b)
        f = {k: None for k in ("e1_last", "e1_best", "e1_mean", "e12_last", "e12_mean", "late_last", "late_mean", "shape_dlt",
                               "eng_prog", "eng_fade", "eng_mixed")}
        if runs:
            d1 = [x["d"][0] for x in runs]
            f["e1_last"] = -d1[0]; f["e1_best"] = -min(d1); f["e1_mean"] = -st.mean(d1)
            f["e12_last"] = -(runs[0]["d"][0] + runs[0]["d"][1])
            f["e12_mean"] = -st.mean(x["d"][0] + x["d"][1] for x in runs)
            f["late_last"] = -runs[0]["d"][-1]
            f["late_mean"] = -st.mean(x["d"][-1] for x in runs)
            # Δ-based shape: positive = finishes better (vs standard) than it starts
            f["shape_dlt"] = st.mean(x["d"][0] - x["d"][-1] for x in runs)
        lab = engine_label(b)
        if lab:
            f["eng_prog"] = 1.0 if "漸進加速" in lab else 0.0
            f["eng_fade"] = 1.0 if "快開慢收" in lab else 0.0
            f["eng_mixed"] = 1.0 if "混合" in lab else 0.0
        f["fc_now"] = fc.get(h["n"])
        hs.append((h, f))
    if len(hs) >= 4 and any(h["pos"] and h["pos"] <= 3 for h, _ in hs):
        for h, f in hs:
            h["_venue"] = "HV" if "Happy" in r["meeting"] else "ST"; h["_dist"] = r.get("distance") or 0
        races.append((r["date"], hs))

races.sort(key=lambda x: x[0])
dates = sorted({d for d, _ in races}); cut = dates[int(len(dates) * 0.6)]
FEATS = ["e1_last", "e1_best", "e1_mean", "e12_last", "e12_mean", "late_last", "late_mean", "shape_dlt", "eng_prog", "eng_fade", "eng_mixed"]
print(f"races {len(races)}  runners {sum(len(h) for _, h in races)}  train < {cut}")


def auc(k, sub=None):
    num = den = 0.0
    for _, hs in races:
        xs = [(f[k], h["pos"]) for h, f in hs if f[k] is not None and (sub is None or sub(h))]
        p = [v for v, pos in xs if pos <= 3]; n = [v for v, pos in xs if pos > 3]
        for a in p:
            for b in n:
                num += 1 if a > b else .5 if a == b else 0; den += 1
    return num / den if den else float("nan")


def within_rank(k):
    """mean within-race Spearman of feature vs model raw score (how much the model already knows)."""
    out = []
    for _, hs in races:
        xs = [(f[k], h["raw"]) for h, f in hs if f[k] is not None]
        if len(xs) >= 5 and len({a for a, _ in xs}) > 1:
            out.append(spearmanr([a for a, _ in xs], [b for _, b in xs])[0])
    return st.mean(out) if out else float("nan")


def within_fc(k):
    """within-race Spearman of feature vs ACTUAL first call this race (negative = fast feature → nearer the front)."""
    out = []
    for _, hs in races:
        xs = [(f[k], f["fc_now"]) for h, f in hs if f[k] is not None and f["fc_now"]]
        if len(xs) >= 5 and len({a for a, _ in xs}) > 1:
            out.append(spearmanr([a for a, _ in xs], [b for _, b in xs])[0])
    return st.mean(out) if out else float("nan")


def mats(rs, keys):
    out = []
    for _, hs in rs:
        x = []
        for k in keys:
            col = [f[k] for _, f in hs]
            have = [v for v in col if v is not None]
            m = np.mean(have) if have else 0.0
            sd = np.std(have) if len(have) > 1 and np.std(have) > 0 else 1.0
            x.append([((v if v is not None else m) - m) / sd if not k.startswith("eng_") else (v if v is not None else m) for v in col])
        x = np.array(x).T; x = x - x.mean(0)
        off = np.array([h["raw"] for h, _ in hs]) / TAU
        y = np.array([1.0 if h["pos"] <= 3 else 0.0 for h, _ in hs]); y /= y.sum()
        out.append((x, off, y))
    return out


def ll(beta, data):
    r = []
    for x, off, y in data:
        s = off + x @ beta; s -= s.max(); r.append(float(y @ (s - np.log(np.exp(s).sum()))))
    return np.array(r)


def test(keys):
    tr = mats([r for r in races if r[0] < cut], keys); te = mats([r for r in races if r[0] >= cut], keys)
    res = minimize(lambda b: -ll(b, tr).mean() + 0.01 * (b ** 2).sum(), np.zeros(len(keys)), method="L-BFGS-B")
    d = ll(res.x, te) - ll(np.zeros(len(keys)), te)
    rng = random.Random(7); boots = sorted(np.mean([d[rng.randrange(len(d))] for _ in d]) for _ in range(1000))
    return res.x, d.mean(), boots[25], boots[974], len(d)


print(f"\n{'feature':10s} {'cover':>6s} {'AUC':>7s} {'ρ model':>8s} {'ρ 今仗首位':>10s}   OOS residual β / ΔLL [95% CI]")
for k in FEATS:
    vals = [f[k] for _, hs in races for _, f in hs]
    cov = sum(v is not None for v in vals) / len(vals)
    b, m, lo, hi, n = test([k])
    print(f"{k:10s} {cov:6.0%} {auc(k):7.4f} {within_rank(k):+8.3f} {within_fc(k):+10.3f}   β {b[0]:+.3f}  ΔLL {m:+.4f} [{lo:+.4f},{hi:+.4f}]")
for combo in (["e1_last", "late_last"], ["e1_best", "late_mean"], ["eng_prog", "eng_fade", "eng_mixed"], ["shape_dlt"], ["e1_best", "shape_dlt"]):
    b, m, lo, hi, n = test(combo)
    print(f"{'+'.join(combo):28s} β {np.round(b,3)}  ΔLL {m:+.4f} [{lo:+.4f},{hi:+.4f}]  n_test {n}")

print("\nAUC by cohort (e1_best / late_mean / model raw):")
for name, fn in {"沙田": lambda h: h["_venue"] == "ST", "跑馬地": lambda h: h["_venue"] == "HV",
                 "≤1200": lambda h: h["_dist"] <= 1200, "1400-1650": lambda h: 1400 <= h["_dist"] <= 1650, "1800+": lambda h: h["_dist"] >= 1800}.items():
    print(f"  {name:10s} e1_best {auc('e1_best', fn):.4f}  late_mean {auc('late_mean', fn):.4f}")

print("\n== control: model raw score as a free regressor (lets the offset scale float) ==")
for _, hs in races:
    rs = [h["raw"] for h, _ in hs]; m = st.mean(rs)
    for h, f in hs:
        f["model_raw"] = h["raw"] - m
for combo in (["model_raw"], ["model_raw", "late_mean"], ["model_raw", "e1_best"], ["model_raw", "e1_best", "late_mean"],
              ["model_raw", "shape_dlt"], ["model_raw", "eng_prog", "eng_fade", "eng_mixed"]):
    b, m_, lo, hi, n = test(combo)
    print(f"{'+'.join(combo):40s} β {np.round(b,3)}  ΔLL {m_:+.4f} [{lo:+.4f},{hi:+.4f}]")


def incr(extra, base=("model_raw",)):
    keys = list(base) + list(extra)
    tr0 = mats([r for r in races if r[0] < cut], list(base)); te0 = mats([r for r in races if r[0] >= cut], list(base))
    tr1 = mats([r for r in races if r[0] < cut], keys); te1 = mats([r for r in races if r[0] >= cut], keys)
    f = lambda tr, k: minimize(lambda b: -ll(b, tr).mean() + 0.01 * (b ** 2).sum(), np.zeros(k), method="L-BFGS-B").x
    b0 = f(tr0, len(base)); b1 = f(tr1, len(keys))
    d = ll(b1, te1) - ll(b0, te0)
    rng = random.Random(11); boots = sorted(np.mean([d[rng.randrange(len(d))] for _ in d]) for _ in range(2000))
    # also time-fold stability: 5 expanding folds over dates
    folds = []
    for i in range(5):
        lo_d = dates[int(len(dates) * (0.5 + 0.1 * i))]; hi_d = dates[min(int(len(dates) * (0.6 + 0.1 * i)), len(dates) - 1)]
        trf = [r for r in races if r[0] < lo_d]; tef = [r for r in races if lo_d <= r[0] < hi_d] if i < 4 else [r for r in races if r[0] >= lo_d]
        a0 = f(mats(trf, list(base)), len(base)); a1 = f(mats(trf, keys), len(keys))
        folds.append(float((ll(a1, mats(tef, keys)) - ll(a0, mats(tef, list(base)))).mean()))
    print(f"+{'+'.join(extra):28s} β {np.round(b1[len(base):],3)}  ΔΔLL {d.mean():+.4f} [{boots[50]:+.4f},{boots[1949]:+.4f}]  folds {' '.join(f'{x:+.4f}' for x in folds)}")


print("\n== incremental over recalibrated model (paired, 2000 race bootstrap; 5 expanding time folds) ==")
for ex in (["e1_best"], ["e1_mean"], ["e1_last"], ["e12_mean"], ["late_mean"], ["late_last"], ["shape_dlt"], ["eng_prog", "eng_fade", "eng_mixed"], ["e1_best", "late_mean"]):
    incr(ex)

vals = sorted(-f["e1_best"] for _, hs in races for _, f in hs if f["e1_best"] is not None)  # = min Δ1 (s vs standard; negative = fast)
q = lambda p: vals[int(p * (len(vals) - 1))]
print("\nmin Δ1 quantiles (s):", {p: round(q(p), 2) for p in (0.1, 0.25, 0.5, 0.75, 0.9)})
for lo, hi in ((-9, 0.0), (0.0, 0.3), (0.3, 0.6), (0.6, 1.0), (1.0, 9)):
    xs = [(h, f) for _, hs in races for h, f in hs if f["e1_best"] is not None and lo <= -f["e1_best"] < hi]
    top3 = sum(h["pos"] <= 3 for h, _ in xs) / len(xs) * 100
    print(f"  min Δ1 in [{lo:+.1f},{hi:+.1f}) n={len(xs):4d} 上名 {top3:.1f}%  ρ今仗首位 n/a")
