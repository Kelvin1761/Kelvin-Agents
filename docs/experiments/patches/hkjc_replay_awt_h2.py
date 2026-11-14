"""研究計劃第 6 步（泥地）：EXP-20261027-03 H2「冇泥地經驗」forward 登記嘅原封量度，喺全量回放泥地賽事判。

定義（凍結，同 EXP-20261027-03）：冇經驗 = 近 730 日、今場路程 ±200 米內冇跑過香港全天候（馬匹頁逐仗，賽日之前）。
量度（凍結）：按模型排名分三組（1–3／4–6／7+），每組「冇經驗 − 有經驗」入頭三率差，按組內馬匹數加權平均；按賽日 bootstrap 2,000。
判法（凍結）：≥ 30 場、正數而且 CI 下界 > 0 → 開排名候選（幅度要 walk-forward，見第二部分）。
第二部分（候選，預先登記）：泥地賽事入面冇經驗嘅馬 raw − δ，δ ∈ {0.5, 1.0, 1.5, 2.0}（raw 尺；現行頭三分差中位數 ~1）；
  dev 逐季 walk-forward 揀 δ（用之前季 Gold+Good 最高），holdout 用全 dev 揀出嘅 δ 一次。
第 7 步（直路賽）用同一套：--mode straight → 賽事 = 沙田草地 1000 米；經驗 = 近 730 日跑過沙田草地 1000 米（直路）。
用法：python3 hkjc_replay_awt_h2.py <base.jsonl> <replay_index.pkl> [--mode awt|straight] [--arm-out <dir>]
"""
import datetime as dt
import json
import pickle
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / ".agents/skills/shared_racing"))
from eval_metrics import race_metrics  # noqa: E402

WIN = {"dev": ("2020-09-01", "2024-07-31"), "holdout": ("2024-09-01", "2026-07-31"), "terminal": ("2026-08-01", "2099")}


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def main():
    rows = [json.loads(line) for line in open(sys.argv[1]) if '"horses"' in line]
    idx = pickle.load(open(sys.argv[2], "rb"))
    mode = sys.argv[sys.argv.index("--mode") + 1] if "--mode" in sys.argv else "awt"
    is_target = (lambda x: x.get("awt")) if mode == "awt" else \
        (lambda x: not x.get("awt") and "跑馬地" not in str(x.get("venue")) and int(x.get("distance") or 0) == 1000)
    run_ok = (lambda r, dist: "全天候" in r.get("venue_track", "") and str(r.get("distance", "")).isdigit()
              and abs(int(r["distance"]) - dist) <= 200) if mode == "awt" else \
        (lambda r, dist: r.get("venue_track", "").startswith("沙田草地") and str(r.get("distance", "")) == "1000")
    awt = [x for x in rows if is_target(x)]
    exp = {}
    for x in awt:
        sec = idx["sect"].get((x["date"], x["race"])) or {}
        no2id = {str(h.get("horse_no")): h.get("horse_id") for h in sec.get("horses", [])}
        d0 = dt.date.fromisoformat(x["date"])
        dist = int(x.get("distance") or sec.get("distance") or 0)
        for h in x["horses"]:
            hid = no2id.get(str(h["n"]))
            runs = (idx["horses"].get(hid) or {}).get("runs", []) if hid else []
            has = any(run_ok(r, dist) and r["iso"] < x["date"]
                      and (d0 - dt.date.fromisoformat(r["iso"])).days <= 730
                      and str(r.get("pos", "")).lstrip("0")[:1].isdigit() for r in runs)
            exp[(x["meeting"], x["race"], h["n"])] = has
    print(f"目標賽事（{mode}）{len(awt)} 場")
    for wname, (lo, hi) in WIN.items():
        sel = [x for x in awt if lo <= x["date"] <= hi]
        by_day = defaultdict(list)
        for x in sel:
            rank = {n: i for i, n in enumerate(x["picks"])}
            for h in x["horses"]:
                if not h["pos"]:
                    continue
                g = 0 if rank[h["n"]] < 3 else (1 if rank[h["n"]] < 6 else 2)
                by_day[x["date"]].append((g, exp[(x["meeting"], x["race"], h["n"])], h["pos"] <= 3))
        days = sorted(by_day)

        def stat(ds):
            cells = defaultdict(lambda: [[0, 0], [0, 0]])
            for d in ds:
                for g, e, p in by_day[d]:
                    cells[g][int(e)][0] += p
                    cells[g][int(e)][1] += 1
            num = den = 0.0
            for g, c in cells.items():
                if c[0][1] and c[1][1]:
                    diff = c[0][0] / c[0][1] - c[1][0] / c[1][1]     # 冇經驗 − 有經驗
                    w = c[0][1] + c[1][1]
                    num += diff * w
                    den += w
            return num / den if den else np.nan
        est = stat(days)
        rng = np.random.default_rng(0)
        bs = [stat(list(rng.choice(days, len(days)))) for _ in range(2000)]
        n_no = sum(1 for d in days for g, e, p in by_day[d] if not e)
        print(f"{wname}：{len(sel)} 場、{len(days)} 日、冇經驗 {n_no} 匹次｜冇經驗 − 有經驗（分層加權）{est * 100:+.1f}pp "
              f"[{np.nanpercentile(bs, 2.5) * 100:+.1f},{np.nanpercentile(bs, 97.5) * 100:+.1f}]")
    if "--arm-out" not in sys.argv:
        return
    out = Path(sys.argv[sys.argv.index("--arm-out") + 1])
    out.mkdir(parents=True, exist_ok=True)

    def apply(x, delta):
        if not is_target(x):
            return x
        hs = [dict(h, raw=h["raw"] - (delta if not exp[(x["meeting"], x["race"], h["n"])] else 0.0)) for h in x["horses"]]
        ns = np.array([h["n"] for h in hs])
        raw = np.array([h["raw"] for h in hs])
        return dict(x, horses=hs, picks=[int(v) for v in ns[np.lexsort((ns, -raw))]])

    def score(xs):
        s = []
        for x in xs:
            pos = {h["n"]: h["pos"] for h in x["horses"] if h["pos"]}
            top = [k for k, p in pos.items() if p <= 3]
            if len(top) >= 3:
                m = race_metrics(x["picks"], top, actual_pos=pos)
                s.append(float(m["gold"]) + float(m["good_positional"]))
        return np.mean(s) if s else 0
    deltas = (0.5, 1.0, 1.5, 2.0)
    dev = [x for x in rows if WIN["dev"][0] <= x["date"] <= WIN["dev"][1] and is_target(x)]
    picks_wf = {}
    for ts in (2021, 2022, 2023):
        train = [x for x in dev if season(x["date"]) < ts]
        picks_wf[ts] = max(deltas, key=lambda dl: score([apply(x, dl) for x in train]))
    full = max(deltas, key=lambda dl: score([apply(x, dl) for x in dev]))
    print("walk-forward 揀 δ：", picks_wf, "；全 dev 揀 δ：", full)
    with open(out / "awt_h2_wf.jsonl", "w") as fh:
        for x in rows:
            if WIN["dev"][0] <= x["date"] <= WIN["dev"][1] and season(x["date"]) in picks_wf:
                fh.write(json.dumps(apply(x, picks_wf[season(x["date"])]), ensure_ascii=False) + "\n")
    with open(out / "awt_h2_full.jsonl", "w") as fh:
        for x in rows:
            fh.write(json.dumps(apply(x, full), ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
