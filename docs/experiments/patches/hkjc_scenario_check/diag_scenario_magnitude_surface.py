"""Kelvin 2026-11-27「全天候場嘅預設情境幅度要分開」：EXP-20261119-10 嘅量法，按跑道（草地／全天候）分開重跑。

問：真係強偏差日（用同日、同一種跑道嘅其他場次判斷），按「慣性跑法」／「檔位區」分組嘅馬，喺 live 之上實際多咗幾多入頭三？
同原本唯一分別：日偏差只用同一種跑道嘅其他場次，結果按今場跑道分開報。

預先登記判決（跑之前定，EXP-20261127-80）：
- 全天候用自己一套情境幅度，要被利嗰類（慣性跑法 3 類、檔位區 3 類）同時符合：
  強偏差日樣本（dev＋holdout）≥ 150；全天候效應（強 − 平常）同草地相差 ≥ 2pp；dev 同 holdout 方向一致。
- 唔符合 = 保留共用數字（跑法 ±2pp、檔位 ±3pp），記錄「量唔準／冇分別」。
- 輔助（唔用嚟判）：強偏差門檻 +5pp 敏感度；按賽日 bootstrap 95% CI。

用法：PYTHONDONTWRITEBYTECODE=1 python3 diag_scenario_magnitude_surface.py <live dump>
"""
import gzip, json, re, sys
from collections import defaultdict
from pathlib import Path
import numpy as np

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "docs/experiments/patches/hkjc_incidents"))
sys.path.insert(0, str(REPO / ".agents/skills/hkjc_racing/hkjc_reflector/scripts"))
sys.path.insert(0, str(REPO / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts"))
from diag import season  # noqa: E402
from diag_full import calibrate  # noqa: E402
import hkjc_history_replay_build as b  # noqa: E402
from hkjc_racing_engine import run_style as rs  # noqa: E402

first = defaultdict(list)   # code -> [(date, race, frac)]
for line in gzip.open("/Volumes/Kelvin Hardisk 1/WongChoi-Archive/hkjc-history/parsed/sectionals.jsonl.gz", "rt", encoding="utf-8"):
    r = json.loads(line); hs = [h for h in r["horses"] if h.get("sections") and str(h.get("finish", "")).isdigit()]
    for h in hs:
        p = h["sections"][0].get("pos")
        if isinstance(p, int): first[h["code"]].append((r["date"], r["race_no"], rs.fraction(p, len(hs))))
for v in first.values(): v.sort()

idx = b.load_index(); meta = {}; surface = {}
for (d, n), race in idx["results"].items():
    # 2024/25 季 index 嘅 course 全部係 None（974 場），跑道只寫喺 sectional_times —— 兩樣都要睇，
    # 否則 168 場全天候會被當草地，holdout 全天候 n = 0（第一次跑就係咁）。
    surface[(d, int(n))] = "全天候" if "全天候" in str(race.get("course") or "") + str(race.get("sectional_times") or "") else "草地"
    for row in race.get("results", []):
        m = re.search(r"\(([A-Z]\d{3})\)", str(row.get("horse_name") or ""))
        try: dr = int(row.get("draw"))
        except (TypeError, ValueError): dr = None
        meta[(d, n, str(row.get("horse_no")))] = (m.group(1) if m else None, dr)


def bucket(d): return None if d is None else ("內" if d <= 4 else "中" if d <= 9 else "外")


rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
calib = calibrate(rows); recs = []
for x in rows:
    s = season(x["date"])
    if not 2020 <= s <= 2025: continue
    surf = surface.get((x["date"], int(x["race"])))
    if surf is None: continue
    hs = [h for h in x["horses"] if h["pos"]]
    r = np.array([h["raw"] for h in hs]); rc = r - r.mean(); a, bb = calib[s]
    for h, z in zip(hs, rc):
        code, dr = meta.get((x["date"], x["race"], str(h["n"])), (None, None))
        if not code: continue
        own = next((f for d, n, f in first[code] if d == x["date"] and n == x["race"]), None)
        prev = [f for d, n, f in first[code] if d < x["date"]][-3:]
        recs.append(dict(day=(x["date"], x.get("venue"), surf), surf=surf, race=x["race"], s=s,
                         res=int(h["pos"] <= 3) - 1 / (1 + np.exp(-(a + bb * z))),
                         actual=rs.classify(own) if own is not None else None,
                         habit=rs.classify(float(np.mean(prev))) if prev else None, draw=bucket(dr)))
print("馬次", len(recs), {k: sum(r["surf"] == k for r in recs) for k in ("草地", "全天候")})

by_day = defaultdict(list)   # (date, venue, surface) —— 日偏差只睇同一種跑道
for r in recs: by_day[r["day"]].append(r)


def other_bias(r, key, val):
    g = [o["res"] for o in by_day[r["day"]] if o["race"] != r["race"] and o[key] == val]
    return np.mean(g) if len(g) >= 8 else None


rng = np.random.default_rng(20261127)


def effect(pairs, thr):
    """pairs: [(day, other_bias, res)] → (強 − 平常, n強, CI)。CI = 按賽日 bootstrap。"""
    strong = [(d, y) for d, o, y in pairs if o >= thr]; weak = [(d, y) for d, o, y in pairs if abs(o) < 0.03]
    if len(strong) < 20 or len(weak) < 20: return None, len(strong), None
    eff = 100 * (np.mean([y for _, y in strong]) - np.mean([y for _, y in weak]))
    days = sorted({d for d, _ in strong + weak}); sd = defaultdict(list); wd = defaultdict(list)
    for d, y in strong: sd[d].append(y)
    for d, y in weak: wd[d].append(y)
    boots = []
    for _ in range(500):
        pick = rng.choice(len(days), len(days)); ss = []; ww = []
        for i in pick: ss += sd.get(days[i], []); ww += wd.get(days[i], [])
        if ss and ww: boots.append(100 * (np.mean(ss) - np.mean(ww)))
    return eff, len(strong), (np.percentile(boots, 2.5), np.percentile(boots, 97.5))


out = {}
for key_bias, key_horse, vals, lab in (("actual", "habit", ("放頭", "守中", "後上"), "跑法（日偏差用實際走位、馬用慣性）"),
                                       ("draw", "draw", ("內", "中", "外"), "檔位區")):
    print(f"\n== {lab}")
    for surf in ("草地", "全天候"):
        for v in vals:
            line = []
            for thr in (0.10, 0.05):
                for name, lo, hi in (("dev", 2020, 2023), ("ho", 2024, 2025), ("全", 2020, 2025)):
                    sel = [r for r in recs if r["surf"] == surf and lo <= r["s"] <= hi and r[key_horse] == v]
                    pairs = [(r["day"], o, r["res"]) for r in sel if (o := other_bias(r, key_bias, v)) is not None]
                    eff, n, ci = effect(pairs, thr)
                    out[(lab, surf, v, thr, name)] = (eff, n, ci)
                    txt = "n/a" if eff is None else f"{eff:+.1f}" + (f" [{ci[0]:+.1f},{ci[1]:+.1f}]" if name == "全" else "")
                    line.append(f"{name}@{int(thr*100)} {txt} (n強 {n})")
            print(f"  {surf} {v}： " + "｜".join(line))

print("\n== 預先登記判決（門檻 +10pp）")
for lab, vals, cur in (("跑法（日偏差用實際走位、馬用慣性）", ("放頭", "守中", "後上"), 2), ("檔位區", ("內", "中", "外"), 3)):
    for v in vals:
        a = out[(lab, "全天候", v, 0.10, "全")]; t = out[(lab, "草地", v, 0.10, "全")]
        ad, ah = out[(lab, "全天候", v, 0.10, "dev")][0], out[(lab, "全天候", v, 0.10, "ho")][0]
        ok_n = a[1] >= 150
        diff = None if a[0] is None or t[0] is None else a[0] - t[0]
        ok_diff = diff is not None and abs(diff) >= 2
        ok_sign = ad is not None and ah is not None and np.sign(ad) == np.sign(ah)
        verdict = "全天候另用" if (ok_n and ok_diff and ok_sign) else "保留共用"
        print(f"  {lab[:2]} {v}：全天候 {a[0] if a[0] is None else round(a[0],1)}（n強 {a[1]}）vs 草地 "
              f"{t[0] if t[0] is None else round(t[0],1)}；n≥150 {ok_n}、差≥2pp {ok_diff}、dev/ho 同向 {ok_sign} → {verdict}")
