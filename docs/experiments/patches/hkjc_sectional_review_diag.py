"""HKJC 段速表現 review diagnostics (2026-10-16). Read-only over the HK data root."""
import json, re, glob, os, statistics as st, random
from collections import defaultdict, Counter

ROOT = open("/Users/imac/Antigravity-repo/.wongchoi_hk_data_root").read().strip()
MEET = re.compile(r"^(\d{4}-\d{2}-\d{2})_(ShaTin|HappyValley)$")


def lab(text, keys):
    for k in keys:
        if k in str(text or ""):
            return k
    return "none" if not text or str(text).strip() in ("", "N/A") else "other"


rows = []
for md in sorted(os.listdir(ROOT)):
    m = MEET.match(md)
    if not m:
        continue
    res = glob.glob(os.path.join(ROOT, md, "*全日賽果.json"))
    if not res:
        continue
    results = json.load(open(res[0]))
    for lf in glob.glob(os.path.join(ROOT, md, "Race_*_Logic.json")):
        rn = re.search(r"Race_(\d+)_Logic", lf).group(1)
        r = results.get(rn)
        if not r:
            continue
        pos, early = {}, {}
        for x in r.get("results", []):
            try:
                n = int(x["horse_no"]); p = int(x["pos"])
            except (ValueError, KeyError, TypeError):
                continue
            pos[n] = p
            rp = str(x.get("running_positions") or "").split()
            if rp and rp[0].isdigit():
                early[n] = int(rp[0])
        if len(pos) < 5:
            continue
        logic = json.load(open(lf))
        dist = re.search(r"\d{3,4}", str((logic.get("race_analysis") or {}).get("distance") or ""))
        race = []
        for num, h in (logic.get("horses") or {}).items():
            try:
                n = int(num)
            except ValueError:
                continue
            if n not in pos:
                continue
            d = h.get("_data") or {}
            pa = h.get("python_auto") or {}
            fs = pa.get("feature_scores") or {}
            # pre-race early position: first call of each past run in position_window
            firsts = [int(a) for a in re.findall(r"沿途位=(\d+)-", str(d.get("position_window") or ""))]
            try:
                score = float(pa.get("ability_score_raw", pa.get("ability_score")))
            except (TypeError, ValueError):
                continue
            race.append(dict(
                meeting=md, date=m.group(1), venue=m.group(2), race=rn, n=n, pos=pos[n],
                field=len(pos), early_now=early.get(n), dist=int(dist.group()) if dist else None,
                hist_first=st.mean(firsts) if firsts else None, n_hist=len(firsts),
                lead_share=(sum(f <= 3 for f in firsts) / len(firsts)) if firsts else None,
                speed=fs.get("speed_score"), score=score,
                engine=lab(d.get("engine_type"), ["漸進加速型", "均速型", "快開慢收型", "混合型"]),
                engine_conf=lab(d.get("engine_type"), ["信心: 高", "信心: 中", "信心: 低"]),
                l4trend=lab(d.get("l400_trend"), ["上升", "穩定", "波動", "衰退中"]),
                energy=lab(d.get("energy_trend"), ["上升", "穩定", "下降"]),
                finlvl=lab(d.get("finish_time_adj_level"), ["仍具競爭力", "持續快於標準", "略快於標準", "接近平均", "仍偏慢", "明顯落後"]),
                fintrend=lab(d.get("finish_time_block"), ["進步", "退步"]),
                raw_l400=(float(d["raw_l400"]) if re.fullmatch(r"\d+(\.\d+)?", str(d.get("raw_l400") or "")) else None),
                pw=str(d.get("position_window") or ""),
                l4seq=str(d.get("l400_trend") or ""),
            ))
        race.sort(key=lambda x: -x["score"])
        for i, x in enumerate(race, 1):
            x["mrank"] = i
        rows.extend(race)

races = defaultdict(list)
for x in rows:
    races[(x["meeting"], x["race"])].append(x)
print(f"meetings={len({x['meeting'] for x in rows})} races={len(races)} runners={len(rows)}")


def auc_within(key, filt=None):
    """Within-race AUC of numeric key vs top-3 (ties = 0.5)."""
    num = den = 0.0
    for rs in races.values():
        rs = [x for x in rs if x.get(key) is not None and (filt is None or filt(x))]
        pos = [x[key] for x in rs if x["pos"] <= 3]
        neg = [x[key] for x in rs if x["pos"] > 3]
        for a in pos:
            for b in neg:
                num += 1 if a > b else 0.5 if a == b else 0
                den += 1
    return num / den if den else float("nan")


def boot_auc(key, B=300):
    keys = list(races)
    out = []
    rng = random.Random(7)
    for _ in range(B):
        samp = [races[rng.choice(keys)] for _ in keys]
        num = den = 0.0
        for rs in samp:
            rs = [x for x in rs if x.get(key) is not None]
            pos = [x[key] for x in rs if x["pos"] <= 3]; neg = [x[key] for x in rs if x["pos"] > 3]
            for a in pos:
                for b in neg:
                    num += 1 if a > b else 0.5 if a == b else 0; den += 1
        out.append(num / den)
    out.sort()
    return out[int(B * .025)], out[int(B * .975)]


def rate(xs):
    return (sum(x["pos"] <= 3 for x in xs) / len(xs) * 100) if xs else float("nan")


def expected(xs):
    return sum(3 / x["field"] for x in xs) / len(xs) * 100 if xs else float("nan")


# ---------- Q1: does early speed matter in HK, and does the model price it?
print("\n== Q1a actual early position this race (outcome, not pre-race) ==")
for lo, hi, name in [(1, 1, "領放"), (2, 3, "2-3位"), (4, 6, "4-6位"), (7, 9, "7-9位"), (10, 14, "10+位")]:
    xs = [x for x in rows if x["early_now"] and lo <= x["early_now"] <= hi]
    print(f"  {name:6s} n={len(xs):5d} 上名率 {rate(xs):5.1f}%  (隨機 {expected(xs):4.1f}%)")

for k in ("lead_share", "hist_first"):
    for x in rows:
        pass
for x in rows:
    x["neg_hist_first"] = -x["hist_first"] if x["hist_first"] is not None else None
print("\n== Q1b pre-race early-speed proxies, within-race AUC vs top-3 ==")
for k in ("neg_hist_first", "lead_share", "speed", "score"):
    print(f"  {k:15s} AUC {auc_within(k):.4f}  95%CI {boot_auc(k)}")

print("\n== Q1c same model-rank bucket, by pre-race style (leader share of past first calls) ==")
def style(x):
    if x["lead_share"] is None or x["n_hist"] < 3:
        return None
    return "前置(≥50%頭3)" if x["lead_share"] >= .5 else "中置" if x["lead_share"] > 0 else "後上(0次頭3)"
for b, (lo, hi) in {"model 1-3": (1, 3), "model 4-6": (4, 6), "model 7+": (7, 99)}.items():
    line = []
    for s in ("前置(≥50%頭3)", "中置", "後上(0次頭3)"):
        xs = [x for x in rows if style(x) == s and lo <= x["mrank"] <= hi]
        line.append(f"{s} n={len(xs)} {rate(xs):.1f}%")
    print(f"  {b}: " + " | ".join(line))
for v in ("ShaTin", "HappyValley"):
    line = []
    for s in ("前置(≥50%頭3)", "中置", "後上(0次頭3)"):
        xs = [x for x in rows if style(x) == s and x["venue"] == v]
        line.append(f"{s} n={len(xs)} 上名 {rate(xs):.1f}% (隨機 {expected(xs):.1f}%) 平均model rank {st.mean([x['mrank'] for x in xs]) if xs else 0:.2f}")
    print(f"  {v}: " + " | ".join(line))

print("\n== Q1d does 段速 (speed_score) reward closers? mean speed_score by style ==")
for s in ("前置(≥50%頭3)", "中置", "後上(0次頭3)"):
    xs = [x["speed"] for x in rows if style(x) == s and x["speed"] is not None]
    print(f"  {s}: n={len(xs)} speed_score mean {st.mean(xs):.2f}")

# ---------- Q2: engine type
print("\n== Q2 引擎型態 ==")
print("  distribution:", Counter(x["engine"] for x in rows).most_common())
print("  x style crosstab (row=engine, % of row):")
for e in ("漸進加速型", "均速型", "快開慢收型", "混合型"):
    c = Counter(style(x) for x in rows if x["engine"] == e and style(x))
    tot = sum(c.values()) or 1
    print(f"   {e}: " + ", ".join(f"{k} {v/tot*100:.0f}%" for k, v in c.most_common()))
for e in ("漸進加速型", "均速型", "快開慢收型", "混合型", "none"):
    for b, (lo, hi) in {"m1-3": (1, 3), "m4-6": (4, 6), "m7+": (7, 99)}.items():
        xs = [x for x in rows if x["engine"] == e and lo <= x["mrank"] <= hi]
        print(f"   {e:6s} {b}: n={len(xs):4d} 上名 {rate(xs):5.1f}%", end="")
    print()
print("  baseline by model bucket (all):", ", ".join(
    f"{b} {rate([x for x in rows if lo <= x['mrank'] <= hi]):.1f}%" for b, (lo, hi) in {"m1-3": (1, 3), "m4-6": (4, 6), "m7+": (7, 99)}.items()))

# ---------- Q3: other speed labels, same treatment
for key, labels in [("l4trend", ["上升", "穩定", "波動", "衰退中", "none"]), ("energy", ["上升", "穩定", "下降", "none"]),
                    ("finlvl", ["仍具競爭力", "持續快於標準", "略快於標準", "接近平均", "仍偏慢", "明顯落後", "none"]),
                    ("fintrend", ["進步", "退步", "none"])]:
    print(f"\n== Q3 {key} ==")
    for e in labels:
        out = []
        for b, (lo, hi) in {"m1-3": (1, 3), "m4-6": (4, 6), "m7+": (7, 99)}.items():
            xs = [x for x in rows if x[key] == e and lo <= x["mrank"] <= hi]
            out.append(f"{b} n={len(xs):4d} {rate(xs):5.1f}%")
        print(f"   {e:8s} " + " | ".join(out))

# ---------- Q4: L400 venue / distance confounding
print("\n== Q4 raw_l400 (latest run) — 由 position_window 第1仗場地/路程 ==")
by = defaultdict(list)
for x in rows:
    m1 = re.search(r"第1仗\(\S+ (沙田|跑馬地) (\d+)\)", x["pw"])
    if x["raw_l400"] and m1:
        d = int(m1.group(2)); band = "≤1200" if d <= 1200 else "1400-1650" if d <= 1650 else "1800+"
        by[(m1.group(1), band)].append(x["raw_l400"])
for k in sorted(by):
    v = by[k]
    print(f"  {k}: n={len(v)} mean {st.mean(v):.2f}  ≤23.6 share {sum(a<=23.6 for a in v)/len(v)*100:.0f}%  ≥24.6 share {sum(a>=24.6 for a in v)/len(v)*100:.0f}%")
x_dec = [x for x in rows if x["l4trend"] == "衰退中"]
contra = [x for x in x_dec if x["raw_l400"] and x["raw_l400"] <= 23.6]
print(f"  衰退中 n={len(x_dec)}, of which latest L400 ≤23.6 (gets abs bonus) = {len(contra)} ({len(contra)/max(len(x_dec),1)*100:.0f}%)")
mixed = 0; tot = 0
for x in rows:
    venues = re.findall(r"第\d仗\(\S+ (沙田|跑馬地) (\d+)\)", x["pw"])
    if len(venues) >= 4 and x["l4trend"] != "none":
        tot += 1
        if len({v for v, _ in venues}) > 1 or len({d for _, d in venues}) > 1:
            mixed += 1
print(f"  trend windows mixing venue or distance: {mixed}/{tot} ({mixed/max(tot,1)*100:.0f}%)")

# raw L400 AUC overall and within latest-run venue/distance cohort normalisation
for x in rows:
    x["neg_l400"] = -x["raw_l400"] if x["raw_l400"] else None
    m1 = re.search(r"第1仗\(\S+ (沙田|跑馬地) (\d+)\)", x["pw"])
    x["l400_ctx"] = (m1.group(1), int(m1.group(2))) if m1 else None
ctx_mean = defaultdict(list)
for x in rows:
    if x["raw_l400"] and x["l400_ctx"]:
        ctx_mean[x["l400_ctx"]].append(x["raw_l400"])
for x in rows:
    c = x["l400_ctx"]
    x["neg_l400_ctx"] = -(x["raw_l400"] - st.mean(ctx_mean[c])) if x["raw_l400"] and c and len(ctx_mean[c]) >= 30 else None
print("\n== Q4b L400 AUC: raw vs normalised to last-run venue+distance ==")
for k in ("neg_l400", "neg_l400_ctx"):
    print(f"  {k}: AUC {auc_within(k):.4f}  CI {boot_auc(k)}  coverage {sum(x[k] is not None for x in rows)/len(rows)*100:.0f}%")

json.dump([{k: v for k, v in x.items() if k not in ("pw", "l4seq")} for x in rows],
          open(os.environ.get("DIAG_OUT", "/dev/null"), "w"), ensure_ascii=False)
