"""Kelvin 2026-11-20（11-14 沙田落雨，黏地／濕慢地）：匹馬場地狀況往績喺 live 模型之上有冇殘差。
殘差 = 入頭三 − p，p = live dump raw 用之前季校準（diag_full.calibrate）。往績只用日期嚴格早過今仗、同場地類型（草地／泥地）。
今仗場地狀況 = 賽果頁「場地狀況」（賽前公佈，但當日可能改；見記錄 §洩漏）。
用法：python3 diag_going.py <live dump>
"""
import json, sys, datetime
from collections import defaultdict
import numpy as np
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
sys.path.insert(0, "/Users/imac/Antigravity-repo/docs/experiments/patches/hkjc_incidents")
import hkjc_history_replay_build as b  # noqa: E402
from diag import season  # noqa: E402
from diag_full import calibrate  # noqa: E402

# 今仗（賽果頁全名）同往績（馬匹頁簡寫）都歸做 好／黏／濕
TODAY = {"好地": "好", "好地至快地": "好", "快地": "好", "好地至黏地": "黏", "黏地": "黏", "黏地至軟地": "黏", "軟地": "黏",
         "濕慢地": "濕", "濕快地": "濕", "泥濘": "濕"}
PAST = {"好": "好", "好/快": "好", "快": "好", "好/黏": "黏", "黏": "黏", "黏/軟": "黏", "軟": "黏", "大爛": "黏",
        "濕慢": "濕", "濕快": "濕", "泥濘": "濕"}

def pdate(s):
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try: return datetime.datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError: pass
    return None

def build():
    idx = b.load_index()
    hist = {}
    for hid, h in idx["horses"].items():
        rs = []
        for r in h.get("runs", []):
            d = pdate(r.get("date", "")); g = PAST.get(r.get("going"))
            try: p = int(r["pos"])
            except (ValueError, KeyError, TypeError): continue
            if d and g: rs.append((d, "全天候" in r.get("venue_track", ""), g, p))
        hist[hid.split("_")[-1]] = sorted(rs)
    race = {}
    for (d, n), v in idx["results"].items():
        res = v["results"] if isinstance(v["results"], list) else []
        code = {}
        for row in res:
            nm = row.get("horse_name", "")
            if "(" in nm: code[str(row.get("horse_no"))] = nm[nm.rindex("(") + 1:-1]
        hdr = v.get("_header") or {}
        if isinstance(hdr, str):
            import ast
            hdr = ast.literal_eval(hdr)
        going = v.get("going") or hdr.get("Going")       # 2024+ 嘅 index 只喺 _header 有（同回放 build 一樣讀法）
        course = v.get("course") or hdr.get("Course") or ""
        race[(d, int(n))] = (TODAY.get(going), "全天候" in course, code)
    return hist, race

def features(hist, today_d, awt, g):
    prev = [r for r in hist if r[0] < today_d and r[1] == awt]
    off = [r for r in prev if r[2] == g]
    good = [r for r in prev if r[2] == "好"]
    return {"n_off": len(off), "off_pl": sum(r[3] <= 3 for r in off), "n_good": len(good), "good_pl": sum(r[3] <= 3 for r in good)}

def main():
    hist, race = build()
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
    calib = calibrate(rows); recs = []; miss = 0
    for x in rows:
        s = season(x["date"])
        if s < 2020: continue
        g, awt, code = race.get((x["date"], x["race"]), (None, None, {}))
        if g in (None, "好"): continue
        hs = [h for h in x["horses"] if h["pos"]]
        r = np.array([h["raw"] for h in hs]); rc = r - r.mean(); a, bb = calib[s]
        for h, z in zip(hs, rc):
            c = code.get(str(h["n"]))
            if not c or c not in hist: miss += 1; continue
            f = features(hist[c], x["date"], awt, g)
            off_rate = f["off_pl"] / f["n_off"] if f["n_off"] else None
            good_rate = f["good_pl"] / f["n_good"] if f["n_good"] else None
            grp = {"冇經驗": f["n_off"] == 0, "跑過冇上名": f["n_off"] > 0 and f["off_pl"] == 0, "上過名": f["off_pl"] > 0,
                   "上過名≥2次": f["off_pl"] >= 2,
                   "黏／濕上名率高過好地": off_rate is not None and good_rate is not None and f["n_off"] >= 2 and off_rate > good_rate,
                   "黏／濕上名率低過好地": off_rate is not None and good_rate is not None and f["n_off"] >= 2 and off_rate < good_rate}
            recs.append(dict(s=s, awt=awt, y=int(h["pos"] <= 3), p=1 / (1 + np.exp(-(a + bb * z))), f=grp))
    print("off-going 馬次", len(recs), "對唔到馬", miss)
    rng = np.random.default_rng(0)
    for surf in (False, True):
        print("== 泥地濕" if surf else "== 草地黏")
        for k in recs[0]["f"]:
            out = []
            for lo, hi in ((2020, 2023), (2024, 2025)):
                sel = [r for r in recs if lo <= r["s"] <= hi and r["awt"] == surf and r["f"][k]]
                if len(sel) < 30: out.append(f"n={len(sel)}"); continue
                y = np.array([r["y"] - r["p"] for r in sel])
                bt = [y[rng.integers(0, len(y), len(y))].mean() for _ in range(1000)]
                out.append(f"{100*y.mean():+.1f}[{100*np.percentile(bt,2.5):+.1f},{100*np.percentile(bt,97.5):+.1f}] n={len(sel)}")
            print(f"  {k:<14} dev {out[0]:<28} ho {out[1]}")

if __name__ == "__main__":
    main()
