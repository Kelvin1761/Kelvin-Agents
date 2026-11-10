"""EXP-20261110-04 — EXP-20261009-15 E3（檔位 × 習慣前速）前瞻驗證，唯讀、唔郁任何評分。

公式照抄未 merge 分支 `claude-hkjc-history-fix-20261009` 嘅 `_apply_early_draw_interaction`
（w = 0.5 顯示分；少過 4 匹有資料 = 整場唔做），喺 baseline 回放 dump 上面離線重排。

    H=.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py
    PYTHONDONTWRITEBYTECODE=1 python3 $H run --dump-matrix --out <scratch>/base.jsonl
    PYTHONDONTWRITEBYTECODE=1 python3 docs/experiments/patches/hkjc_e3_early_draw_forward.py <scratch>/base.jsonl 0.5
"""
import csv, json, random, re, sys, collections
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
for p in (".agents/skills/hkjc_racing/hkjc_reflector/scripts", ".agents/skills/shared_racing/scripts", "."):
    sys.path.insert(0, str(REPO / p))
import pit_backtest  # noqa: E402

SLOPE = 10.0 / 4.393
W = float(sys.argv[2]) if len(sys.argv) > 2 else 0.5
FORWARD = "2026-10-10"
rows = [r for r in (json.loads(l) for l in open(sys.argv[1]) if l.strip()) if "date" in r]

db = pit_backtest.load_all_rows()
rail = {}
fsize = {}
HK_ROOT = Path((REPO / ".wongchoi_hk_data_root").read_text(encoding="utf-8").strip())
RAIL_CSV = HK_ROOT / "HKJC_Race_Results_Database" / "comprehensive_stats" / "rail_draw_results.csv"
for r in csv.DictReader(open(RAIL_CSV, encoding="utf-8-sig")):
    key = (r["Date"], int(float(r["RaceNo"])))
    rail[(key[0], key[1], int(float(r["HorseNo"])))] = int(float(r["Draw"]))
    fsize[key] = int(float(r["FieldSize"]))

by_draw = {}
hist = collections.defaultdict(list)
for r in db.itertuples():
    d = str(r.Date)[:10]
    try:
        rn = int(float(r.RaceNo)); draw = int(float(r.Draw))
    except (TypeError, ValueError):
        continue
    hid = str(r.HorseID or "").strip() or re.sub(r"\([A-Z]\d+\)$", "", str(r.Horse)).strip()
    by_draw[(d, rn, draw)] = hid
    m = re.match(r"^\s*(\d+)", str(r.RunningPos or ""))
    if m and int(m.group(1)) > 0:
        hist[hid].append((d, rn, int(m.group(1))))
for v in hist.values():
    v.sort(reverse=True)


def habitual(hid, date):
    vals = []
    for d, rn, first in hist.get(hid, []):
        if d >= date:
            continue
        vals.append((first - 1) / max(1, (fsize.get((d, rn)) or 12) - 1))
        if len(vals) >= 6:
            break
    return sum(vals) / len(vals) if len(vals) >= 2 else None


def z(values):
    known = [v for v in values if v is not None]
    if len(known) < 2:
        return [0.0] * len(values)
    mean = sum(known) / len(known)
    sd = (sum((v - mean) ** 2 for v in known) / len(known)) ** 0.5
    return [0.0 if v is None or sd <= 0 else (v - mean) / sd for v in values]


def placed(h):
    return isinstance(h.get("pos"), int) and 1 <= h["pos"] <= 3


def metrics(race, score):
    hs = race["horses"]
    order = sorted(hs, key=lambda h: (-score[h["n"]], h["n"]))
    top = [h["n"] for h in order]
    pl = {h["n"] for h in hs if placed(h)}
    return {
        "gold": float(pl <= set(top[:4])),
        "good": float(top[0] in pl and top[1] in pl),
        "champion": float(any(h["n"] == top[0] and h.get("pos") == 1 for h in hs)),
        "p1plc": float(top[0] in pl),
        "cap5": len(pl & set(top[:5])) / max(1, len(pl)),
        "mean_rank": sum(top.index(n) + 1 for n in pl) / max(1, len(pl)),
        "order": top,
    }


out = []
cov = collections.Counter()
fid = 0
for race in rows:
    hs = race["horses"]
    base = {h["n"]: h["raw"] for h in hs}
    fid += metrics(race, base)["order"][:4] == race["picks"][:4]
    barrier, early = [], []
    for h in hs:
        b = rail.get((race["date"], race["race"], h["n"]))
        hid = by_draw.get((race["date"], race["race"], b)) if b is not None else None
        e = habitual(hid, race["date"]) if hid else None
        barrier.append(b); early.append(None if e is None else -e)
        cov["runners"] += 1; cov["barrier"] += b is not None; cov["early"] += e is not None
    active = sum(e is not None for e in early) >= 4 and sum(b is not None for b in barrier) >= 4
    if active:
        dz = [-v for v in z(barrier)]
        ez = z(early)
        terms = z([max(0.0, -d) * e for d, e in zip(dz, ez)])
    else:
        terms = [0.0] * len(hs)
    cand = {h["n"]: h["raw"] + round(W * t / SLOPE, 4) for h, t in zip(hs, terms)}
    a, b = metrics(race, base), metrics(race, cand)
    out.append({"meeting": race["meeting"], "date": race["date"], "venue": race["venue"], "active": active,
                "moved": a["order"][:5] != b["order"][:5],
                **{k: (a[k], b[k]) for k in a if k != "order"}})

print(f"w={W}  baseline top-4 reproduced {fid}/{len(rows)}  coverage barrier {100*cov['barrier']/cov['runners']:.1f}% early {100*cov['early']/cov['runners']:.1f}%")


def report(name, rs, n_boot=2000):
    if not rs:
        return
    rng = random.Random(0)
    by = collections.defaultdict(list)
    for r in rs:
        by[r["meeting"]].append(r)
    keys = sorted(by)
    print(f"\n{name}: {len(rs)} races / {len(keys)} meetings; active {sum(r['active'] for r in rs)}; top-5 changed {sum(r['moved'] for r in rs)}")
    for k in ("gold", "good", "champion", "p1plc", "cap5", "mean_rank"):
        d = lambda s, k=k: sum(r[k][1] - r[k][0] for r in s) / len(s)
        bs = sorted(d([x for kk in rng.choices(keys, k=len(keys)) for x in by[kk]]) for _ in range(n_boot))
        scale = 1 if k == "mean_rank" else 100
        base = scale * sum(r[k][0] for r in rs) / len(rs)
        print(f"  {k:9s} base {base:6.2f}  Δ {scale*d(rs):+.2f} [{scale*bs[int(.025*n_boot)]:+.2f}, {scale*bs[int(.975*n_boot)]:+.2f}]"
              + ("  (越低越好)" if k == "mean_rank" else "pp"))


fw = [r for r in out if r["date"] >= FORWARD]
report("FORWARD (>= 2026-10-10, never seen by E3)", fw)
report("  forward 沙田(含AWT)", [r for r in fw if r["venue"].startswith("沙田")])
report("  forward 跑馬地", [r for r in fw if r["venue"] == "跑馬地"])
report("SEEN (<= 2026-10-09, reference only)", [r for r in out if r["date"] < FORWARD])
report("ALL", out)
# time blocks on all
srt = sorted(out, key=lambda r: r["date"]); k = len(srt) // 6
print("\n6 time blocks (Gold Δ / Good Δ in races):", [(int(sum(r['gold'][1]-r['gold'][0] for r in srt[i*k:(i+1)*k if i<5 else None])), int(sum(r['good'][1]-r['good'][0] for r in srt[i*k:(i+1)*k if i<5 else None]))) for i in range(6)])
