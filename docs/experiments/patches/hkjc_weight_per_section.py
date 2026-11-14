"""HKJC 研究計劃 §2c：逐段負磅效應（每磅慢幾多秒），按路程分段。

預先登記（跑之前寫死）：
  樣本    dev 季（2020/21–2023/24）；同一匹馬兩仗配對：同跑道（沙田草地／跑馬地草地／沙田全天候）、同路程、相隔 ≤ 120 日、兩仗都跑完
  依變數  每段時間對「當日同跑道同路程同段」全場中位數嘅偏差（扣當日快慢同場地），兩仗相減
  解釋    Δ實際負磅（磅）；另加 Δ評分 做控制（讓磅賽負磅同評分一齊郁，唔控制會將「評分升＝狀態好」當負磅效應）
  段      first（第一段，換算每 400 米）、mid（中段平均，≥4 段先有）、pen（倒數第二段）、l400（最後一段）、total（全程每 400 米）
  路程    ≤1200、1201–1799、≥1800
  報告    每磅係數 [95% bootstrap，按馬匹重抽 500 次]；同現行 L400 係數（0.007／0.016／0.021 秒／磅，係「全程」口徑）比較
用法：python3 hkjc_weight_per_section.py <replay_index.pkl>
"""
import pickle
import sys
from collections import defaultdict

import numpy as np

SEASONS = (2020, 2023)


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def main():
    idx = pickle.load(open(sys.argv[1], "rb"))
    # 每匹次：段時、負磅、評分
    rating = {}
    for hid, h in idx["horses"].items():
        for r in h["runs"]:
            if str(r.get("rating") or "").isdigit():
                rating[(hid, r["iso"])] = int(r["rating"])
    rows = []
    day_med = defaultdict(list)
    for (d, n), sec in idx["sect"].items():
        res = idx["results"].get((d, n)) or {}
        wt = {str(r.get("horse_no")): r.get("actual_wt") for r in res.get("results", [])}
        dist = sec.get("distance")
        if not dist:
            continue
        track = "AWT" if sec.get("surface") == "全天候" else ("HV" if "跑馬地" in str(res.get("venue")) else "ST")
        H = [h for h in sec["horses"] if h.get("horse_id") and str(h.get("finish", "")).split()[0].isdigit()]
        if not H:
            continue
        nsec = max(len(h["sections"]) for h in H)
        for h in H:
            t = [s.get("time") for s in h["sections"]]
            w = wt.get(str(h.get("horse_no")))
            if len(t) != nsec or nsec < 3 or any(x is None for x in t) or not str(w or "").isdigit():
                continue
            first_len = dist - 400 * (nsec - 1)
            parts = {"first": t[0] / (first_len / 400), "pen": t[-2], "l400": t[-1], "total": sum(t) / (dist / 400)}
            if nsec >= 4:
                parts["mid"] = float(np.mean(t[1:-2]))
            rows.append((h["horse_id"], d, track, dist, int(w), parts))
            for k, v in parts.items():
                day_med[(d, track, dist, k)].append(v)
    med = {k: float(np.median(v)) for k, v in day_med.items() if len(v) >= 5}
    by_horse = defaultdict(list)
    for hid, d, track, dist, w, parts in rows:
        by_horse[hid].append((d, track, dist, w, {k: v - med[(d, track, dist, k)] for k, v in parts.items() if (d, track, dist, k) in med}))
    band = lambda x: "≤1200" if x <= 1200 else ("1201-1799" if x < 1800 else "≥1800")
    pairs = defaultdict(list)          # (band, part) → [(hid, Δw, Δrating, Δdev)]
    import datetime as dt
    for hid, runs in by_horse.items():
        runs.sort()
        for a, b in zip(runs, runs[1:]):
            if (a[1], a[2]) != (b[1], b[2]) or not (SEASONS[0] <= season(b[0]) <= SEASONS[1]):
                continue
            if (dt.date.fromisoformat(b[0]) - dt.date.fromisoformat(a[0])).days > 120:
                continue
            ra, rb = rating.get((hid, a[0])), rating.get((hid, b[0]))
            if ra is None or rb is None:
                continue
            for k in set(a[4]) & set(b[4]):
                pairs[(band(b[2]), k)].append((hid, b[3] - a[3], rb - ra, b[4][k] - a[4][k]))
    rng = np.random.default_rng(0)
    print("路程｜段｜配對數｜每磅秒數（控制評分）[95%]｜唔控制評分")
    for key in sorted(pairs):
        P = pairs[key]
        hids = np.array([p[0] for p in P])
        X = np.array([[p[1], p[2], 1.0] for p in P])
        y = np.array([p[3] for p in P])
        coef = np.linalg.lstsq(X, y, rcond=None)[0][0]
        raw = np.linalg.lstsq(X[:, [0, 2]], y, rcond=None)[0][0]
        uh = np.unique(hids)
        grp = {h: np.where(hids == h)[0] for h in uh}
        bs = []
        for _ in range(500):
            ii = np.concatenate([grp[h] for h in rng.choice(uh, len(uh))])
            bs.append(np.linalg.lstsq(X[ii], y[ii], rcond=None)[0][0])
        print(f"{key[0]}｜{key[1]}｜{len(P)}｜{coef:+.4f} [{np.percentile(bs, 2.5):+.4f},{np.percentile(bs, 97.5):+.4f}]｜{raw:+.4f}")


if __name__ == "__main__":
    main()
