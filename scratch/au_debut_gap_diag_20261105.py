"""初出馬差距診斷：初出馬 = prep_stage == debut。只描述，唔揀參數。"""
import csv, json, random, sys
from collections import defaultdict
from pathlib import Path
S = Path("/Users/imac/Antigravity-repo/.agents/skills/au_racing/au_wong_choi_auto/scripts"); sys.path[:0] = [str(S)]
from au_archive_calibrator import HISTORICAL_RESULTS_CSV, normalize_horse_name

races = json.loads(Path(sys.argv[1]).read_text())["races"]
meta = {}
for r in csv.DictReader(open(HISTORICAL_RESULTS_CSV, encoding="utf-8-sig")):
    try: w = float(r["Weight"].replace("kg", ""))
    except ValueError: w = None
    meta[(r["Date"], int(r["Race"]), normalize_horse_name(r["Horse"]))] = (r["Trainer"].strip(), r["Jockey"].strip(), w)
isdeb = lambda x: x.get("prep_stage") == "debut"  # noqa
def sp(x):
    try: return float(x.get("sp"))
    except (TypeError, ValueError): return None

# 練馬師初出馬入三率（point-in-time：只用今日之前嘅 dump 初出馬；k=10 收縮向全體）
tr_hist = defaultdict(list); glob = []; tr_rate = {}
for rc in sorted(races, key=lambda r: r["date"]):
    today = []
    for x in rc["rows"]:
        if not isdeb(x): continue
        m = meta.get((rc["date"], rc["race"], normalize_horse_name(x["name"])))
        t = m[0] if m else None
        h = tr_hist.get(t, []); g = (sum(glob) / len(glob)) if glob else 0.3
        tr_rate[(rc["meeting"], rc["race"], x["n"])] = ((sum(h) + 10 * g) / (len(h) + 10), len(h))
        today.append((t, (x["pos"] <= 3)))
    # 同日唔可以用（賽果同日先出）：日尾先加入 —— 用 date 分組近似：按場次排序，同日之後場次會見到之前場次，
    # 所以改為延遲一日：放入 pending
    rc["_pending"] = today
by_date = defaultdict(list)
for rc in races: by_date[rc["date"]].append(rc)
tr_hist.clear(); glob.clear(); tr_rate.clear()
for d in sorted(by_date):
    for rc in by_date[d]:
        for x in rc["rows"]:
            if not isdeb(x): continue
            m = meta.get((d, rc["race"], normalize_horse_name(x["name"])))
            t = m[0] if m else None; h = tr_hist.get(t, []); g = (sum(glob) / len(glob)) if glob else 0.3
            tr_rate[(rc["meeting"], rc["race"], x["n"])] = ((sum(h) + 10 * g) / (len(h) + 10), len(h))
    for rc in by_date[d]:
        for t, y in rc["_pending"]:
            tr_hist[t].append(y); glob.append(y)

def feats(rc, x):
    m = meta.get((rc["date"], rc["race"], normalize_horse_name(x["name"]))) or (None, None, None)
    f = dict(x["features"]); s = sp(x)
    f.update(ability=x["ability"], neg_sp=-s if s else None, neg_barrier=-(x.get("barrier") or 99),
             weight=m[2], trainer_debut_rate=tr_rate.get((rc["meeting"], rc["race"], x["n"]), (None, 0))[0],
             trainer_debut_n=tr_rate.get((rc["meeting"], rc["race"], x["n"]), (None, 0))[1])
    return f

acc = defaultdict(lambda: defaultdict(lambda: [0.0, 0])); rho = defaultdict(list)
mix = {"races": 0, "actual": 0, "model": 0, "sp": 0, "deb": 0, "field": 0}
keys = None
for rc in races:
    debs = [x for x in rc["rows"] if isdeb(x)]
    if debs and len(debs) < len(rc["rows"]) and all(sp(x) for x in rc["rows"]):
        mix["races"] += 1; mix["deb"] += len(debs); mix["field"] += len(rc["rows"])
        top = lambda key: sorted(rc["rows"], key=key)[:3]  # noqa
        mix["actual"] += sum(isdeb(x) for x in rc["rows"] if x["pos"] <= 3)
        mix["model"] += sum(isdeb(x) for x in top(lambda x: (-x["ability"], x["n"])))
        mix["sp"] += sum(isdeb(x) for x in top(lambda x: (sp(x), x["n"])))
    if len(debs) < 3 or not all(sp(x) for x in debs) or not any(x["pos"] <= 3 for x in debs) or all(x["pos"] <= 3 for x in debs):
        continue
    F = [feats(rc, x) for x in debs]
    keys = keys or [k for k in F[0] if k != "trainer_debut_n"]
    for k in keys:
        P = [f[k] for f, x in zip(F, debs) if x["pos"] <= 3 and f[k] is not None]
        N = [f[k] for f, x in zip(F, debs) if x["pos"] > 3 and f[k] is not None]
        c = acc[k][rc["date"]]; c[0] += sum((p > q) + 0.5 * (p == q) for p in P for q in N); c[1] += len(P) * len(N)
        vals = [(f[k], f["neg_sp"]) for f in F if f[k] is not None]
        if len(vals) >= 3: rho[k].append(vals)
def spear(groups):
    tot = 0; n = 0
    for g in groups:
        a = [v for v, _ in g]; b = [w for _, w in g]
        ra = {i: r for r, i in enumerate(sorted(range(len(a)), key=lambda i: a[i]))}
        rb = {i: r for r, i in enumerate(sorted(range(len(b)), key=lambda i: b[i]))}
        m = (len(a) - 1) / 2; num = sum((ra[i] - m) * (rb[i] - m) for i in range(len(a))); den = sum((ra[i] - m) ** 2 for i in range(len(a)))
        if den: tot += num / den; n += 1
    return tot / n if n else float("nan")
rows = []
for k in keys:
    days = sorted(acc[k]); tot = lambda ds: sum(acc[k][d][0] for d in ds) / max(1, sum(acc[k][d][1] for d in ds))  # noqa
    rng = random.Random(7); smp = sorted(tot([days[rng.randrange(len(days))] for _ in days]) for _ in range(1000))
    rows.append((tot(days), smp[25], smp[974], spear(rho[k]), k))
print(f"初出馬之間（≥3 匹初出、有 SP）：{len(acc['ability'])} 賽日")
for a, lo, hi, r, k in sorted(rows, reverse=True):
    print(f"  {k:26s} AUC {a:.4f} [{lo:.4f},{hi:.4f}]  場內 ρ(同市場) {r:+.3f}")
print(f"混合場（有初出又有出過賽）{mix['races']} 場：初出佔馬匹 {mix['deb']/mix['field']:.3f}；"
      f"頭三名入面初出 實際 {mix['actual']}／模型頭三 {mix['model']}／市場頭三 {mix['sp']}")
