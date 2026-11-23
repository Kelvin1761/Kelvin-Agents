"""EXP-20261123-19 預先登記（Kelvin 2026-11-23「歷史試閘資料庫（初出馬用）」）。寫喺跑之前；尺 v5.2；base = live（SW＋DT，db_DT）。

資料：`raw/trials/<日期>.html.gz`（`hkjc_trials_scrape.py`，HKJC 試閘結果頁，2019-07 起）。每組次序 = 名次。
特徵（只限初出馬；非初出 0；場內置中；只用今仗日期**之前**嘅試閘）：
  tmar   最後一次試閘輸頭馬馬位（頭馬 0；封頂 15；冇試閘 = 初出馬平均）
  tcnt   近 90 日試閘次數
  ttop3  最後一次試閘頭三
  tgap   最後一次試閘時間 − 同組頭馬時間（秒，封頂 3）
arm（線性 L2 C=0.1、每季 walk-forward β）：
  TR1  tmar【主】
  TR2  tmar ＋ tcnt ＋ ttop3 ＋ tgap
判：六季有初出馬嘅場（judge_all_group.py debut）v5.2 PASS ＋ 頭二入頭三 Δ ≥ 0；全期 dev／holdout 照報；11-22 否決另做。
用法：python3 build_debut_trials.py <db_DT.jsonl> <trials_dir> <out_prefix>
"""
import datetime as dt
import gzip
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_race_extractor/scripts")
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
import extract_trackwork as X  # noqa: E402
import hkjc_history_replay_build as hb  # noqa: E402

WORDS = (("短馬頭位", 0.1), ("Short Head", 0.1), ("馬頭位", 0.2), ("Head", 0.2), ("鼻位", 0.05), ("Nose", 0.05), ("頸位", 0.3), ("Neck", 0.3))


def lengths(t):
    t = str(t or "").replace("L", "").strip()
    if not t:
        return 0.0
    for w, v in WORDS:
        if w in t:
            return v
    m = re.fullmatch(r"(\d+)(?:-(\d+)/(\d+))?|(\d+)/(\d+)", t)
    if not m:
        return None
    if m.group(4):
        return int(m.group(4)) / int(m.group(5))
    return int(m.group(1)) + (int(m.group(2)) / int(m.group(3)) if m.group(2) else 0.0)


def secs(t):
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", str(t or "").strip())
    return int(m.group(1)) * 60 + int(m.group(2)) + int(m.group(3)) / 100 if m else None


def parse_day(path):
    p = X.TableParser(); p.feed(gzip.open(path, "rt", encoding="utf-8").read())
    out, grp = [], None
    for r in p.rows:
        c = r.get("cells") or []
        if not c:
            continue
        if re.search(r"第\s*\d+\s*組", c[0]) and len(c) <= 2:
            grp = {"id": c[0], "rows": []}; out.append(grp); continue
        m = re.search(r"\(([A-Z]\d{3})\)", c[0])
        if grp is not None and m and len(c) >= 9:
            grp["rows"].append({"code": m.group(1), "margin": lengths(c[5]), "time": secs(c[7]), "result": c[8]})
    return out


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def main():
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
    tdir = Path(sys.argv[2])
    hist = defaultdict(list)   # code -> [(date, margin, n_pos, top3, gap)]
    for f in sorted(tdir.glob("*.html.gz")):
        d = f.name[:10]
        for g in parse_day(f):
            rs = [r for r in g["rows"] if r["time"] is not None]
            if not rs:
                continue
            t0 = min(r["time"] for r in rs)
            for i, r in enumerate(rs):
                mar = r["margin"] if r["margin"] is not None else 15.0
                hist[r["code"]].append((d, min(mar, 15.0), i, int(i < 3), min(r["time"] - t0, 3.0)))
    print("試閘馬匹", len(hist), "試閘紀錄", sum(len(v) for v in hist.values()), flush=True)
    idx = hb.load_index()["results"]
    n2c = {}
    for k, r in idx.items():
        for q in r.get("results") or []:
            m = re.search(r"\(([A-Z]\d{3})\)", str(q.get("horse_name") or ""))
            if m:
                n2c[(k, str(q.get("horse_no")))] = m.group(1)
    F, cover = {}, [0, 0]
    for x in rows:
        k = (x["date"], x["race"]); m = np.full((len(x["horses"]), 4), np.nan); deb = np.zeros(len(x["horses"]), bool)
        d0 = dt.date.fromisoformat(x["date"])
        for i, h in enumerate(x["horses"]):
            if not h.get("debut"):
                continue
            deb[i] = True; cover[1] += 1
            past = [t for t in hist.get(n2c.get((k, str(h["n"]))), []) if t[0] < x["date"]]
            if not past:
                continue
            cover[0] += 1
            last = past[-1]
            cnt = sum(1 for t in past if (d0 - dt.date.fromisoformat(t[0])).days <= 90)
            m[i] = [last[1], cnt, last[3], last[4]]
        F[k] = (m, deb)
    print("初出馬有試閘", cover, flush=True)
    allm = np.vstack([m[d] for m, d in F.values() if d.any()])
    mu = np.nanmean(allm, axis=0)
    feats = {}
    for k, (m, d) in F.items():
        z = np.where(np.isnan(m), mu, m); z[~d] = 0.0
        z = np.where(d[:, None], z - mu, 0.0)
        feats[k] = z - z.mean(axis=0)
    by = defaultdict(list)
    for x in rows:
        by[season(x["date"])].append(x)
    for arm, cols in (("TR1", [0]), ("TR2", [0, 1, 2, 3])):
        models = {}
        for s in sorted(by):
            if s < 2020:
                continue
            R, Z, Y = [], [], []
            for x in (x for t in by if 2019 <= t < s for x in by[t]):
                keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
                r = np.array([h["raw"] for h in x["horses"]])
                R.append((r - r.mean())[keep]); Z.append(feats[(x["date"], x["race"])][:, cols][keep]); Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
            R, Z, Y = np.concatenate(R), np.vstack(Z), np.array(Y)
            sd = Z.std(axis=0); sd[sd == 0] = 1; rs = R.std()
            c = LogisticRegression(C=0.1, max_iter=20000).fit(np.column_stack([R / rs, Z / sd]), Y).coef_[0]
            models[s] = (c[1:] / sd) / (c[0] / rs)
        print(arm, {s: [round(float(b), 2) for b in m] for s, m in models.items()}, flush=True)
        with open(f"{sys.argv[3]}_{arm}.jsonl", "w") as f:
            for x in rows:
                s = season(x["date"]); y = dict(x, arm=f"trials_{arm}")
                if s in models:
                    new = np.array([h["raw"] for h in x["horses"]]) + feats[(x["date"], x["race"])][:, cols] @ models[s]
                    y["horses"] = [dict(h, raw=round(float(v), 4)) for h, v in zip(x["horses"], new)]
                    y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
                f.write(json.dumps(y, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
