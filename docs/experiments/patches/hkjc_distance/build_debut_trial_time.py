"""EXP-20261124-17 預先登記（Kelvin 2026-11-24：「輸距冇乜嘢好睇，初出馬試閘最多睇段速同時間」「係咪應該幫初出馬試下」）。
寫喺跑之前；尺 v5.2；base = live（db_DT，同 TR1 一樣）。只限初出馬；非初出 0；場內置中；只用今仗日期**之前**嘅試閘。

資料：HKJC 試閘頁原始檔（`raw/trials/<日期>.html.gz`）。每組：「第 N 組 - <跑道> - <路程>米」、「場地狀況: X」、「分段時間: a b c」；每匹完成時間。
標準時間 std(跑道, 路程, 場地狀況) = 嗰次試閘日期**之前**全部試閘馬匹完成時間嘅中位數（樣本 < 30 就退做 (跑道, 路程)；再唔夠 = 冇數）。
  tf   = (std − 完成時間) ÷ 路程公里（秒／公里，正 = 快過標準）；完成時間封頂 std + 3 秒（放慢跑唔罰太重）
  pace = 全組分段時間：最後一段 − 前面各段平均（秒；正 = 慢收／前段快）
特徵（最後一次試閘）：冇試閘或冇數 = walk-forward 平均（季 t 用 t 之前各季初出馬平均；2019 季只做訓練用自己）
arm（線性 L2 C=0.1、每季 walk-forward β，同 TR1）：
  TT1  tf【主】
  TT2  tf ＋ pace
判：六季有初出馬嘅場（judge_all_group.py debut）v5.2 PASS ＋ 頭二入頭三 Δ ≥ 0；全期 dev／holdout 照報；11-22 否決另做。
披露：輸距版 TR1 已經 PASS（Kelvin 因為可解釋性唔上）；TT 同 TR1 用同一批馬同同一個 base。
用法：python3 build_debut_trial_time.py <db_DT.jsonl> <trials_dir> <out_prefix>
"""
import bisect
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

MIN_N = 30


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


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
        h = re.search(r"第\s*\d+\s*組\s*-\s*(.+?)\s*-\s*(\d+)\s*米", c[0])
        if h and len(c) <= 2:
            grp = {"track": h.group(1).strip(), "dist": int(h.group(2)), "going": "", "splits": [], "rows": []}
            out.append(grp); continue
        if grp is None:
            continue
        joined = " ".join(c)
        g = re.search(r"場地狀況[:：]\s*(\S+)", joined)
        if g and not grp["rows"]:
            grp["going"] = g.group(1)
        s = re.search(r"分段時間[:：]\s*([\d.\s]+)", joined)
        if s and not grp["rows"]:
            grp["splits"] = [float(v) for v in s.group(1).split() if re.fullmatch(r"\d+(\.\d+)?", v)]
            continue
        m = re.search(r"\(([A-Z]\d{3})\)", c[0])
        if m and len(c) >= 9:
            t = secs(c[7])
            if t is not None:
                grp["rows"].append({"code": m.group(1), "time": t})
    return out


class Std:
    """嚴格用之前日子嘅試閘時間計中位數。"""
    def __init__(self):
        self.by = defaultdict(list)

    def get(self, track, dist, going):
        for key in ((track, dist, going), (track, dist)):
            v = self.by.get(key)
            if v and len(v) >= MIN_N:
                return v[len(v) // 2]
        return None

    def add(self, track, dist, going, t):
        bisect.insort(self.by[(track, dist, going)], t)
        bisect.insort(self.by[(track, dist)], t)


def main():
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
    tdir = Path(sys.argv[2]); out = sys.argv[3]
    days = defaultdict(list)
    for f in sorted(tdir.glob("*.html.gz")):
        days[f.name[:10]] = parse_day(f)
    std = Std()
    hist = defaultdict(list)    # code -> [(date, tf, pace)]
    n_none = n_all = 0
    for d in sorted(days):
        groups = days[d]
        for g in groups:      # 先用之前日子嘅標準計（同日唔入）
            s = std.get(g["track"], g["dist"], g["going"])
            sp = g["splits"]
            pace = sp[-1] - float(np.mean(sp[:-1])) if len(sp) >= 2 else float("nan")
            for r in g["rows"]:
                n_all += 1
                if s is None:
                    n_none += 1
                    tf = float("nan")
                else:
                    tf = (s - min(r["time"], s + 3.0)) / (g["dist"] / 1000.0)
                hist[r["code"]].append((d, tf, pace))
        for g in groups:
            for r in g["rows"]:
                std.add(g["track"], g["dist"], g["going"], r["time"])
    print("試閘紀錄", n_all, "冇標準", n_none, "組有分段", sum(1 for v in days.values() for g in v if len(g["splits"]) >= 2),
          "/", sum(len(v) for v in days.values()), flush=True)
    idx = hb.load_index()["results"]
    n2c = {}
    for k, r in idx.items():
        for q in r.get("results") or []:
            m = re.search(r"\(([A-Z]\d{3})\)", str(q.get("horse_name") or ""))
            if m:
                n2c[(k, str(q.get("horse_no")))] = m.group(1)
    F, cover = {}, [0, 0]
    for x in rows:
        k = (x["date"], x["race"]); m = np.full((len(x["horses"]), 2), np.nan); deb = np.zeros(len(x["horses"]), bool)
        for i, h in enumerate(x["horses"]):
            if not h.get("debut"):
                continue
            deb[i] = True; cover[1] += 1
            past = [t for t in hist.get(n2c.get((k, str(h["n"]))), []) if t[0] < x["date"]]
            if past:
                cover[0] += 1
                m[i] = [past[-1][1], past[-1][2]]
        F[k] = (m, deb)
    print("初出馬有試閘", cover, flush=True)
    bys = defaultdict(list)
    for k, (m, d) in F.items():
        if d.any():
            bys[season(k[0])].append(m[d])
    mus = {}
    for t in sorted(bys):
        prev = [a for u in bys if u < t for a in bys[u]] or bys[t]
        mus[t] = np.nanmean(np.vstack(prev), axis=0)
    print("walk-forward 平均", {t: [round(float(v), 3) for v in mu] for t, mu in mus.items()}, flush=True)
    feats = {}
    for k, (m, d) in F.items():
        mu = mus.get(season(k[0]), np.zeros(2))
        z = np.where(np.isnan(m), mu, m)
        z = np.where(d[:, None], z - mu, 0.0)
        feats[k] = z - z.mean(axis=0)
    by = defaultdict(list)
    for x in rows:
        by[season(x["date"])].append(x)
    for arm, cols in (("TT1", [0]), ("TT2", [0, 1])):
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
        with open(f"{out}_{arm}.jsonl", "w") as f:
            for x in rows:
                s = season(x["date"]); y = dict(x, arm=f"trialtime_{arm}")
                if s in models:
                    new = np.array([h["raw"] for h in x["horses"]]) + feats[(x["date"], x["race"])][:, cols] @ models[s]
                    y["horses"] = [dict(h, raw=round(float(v), 4)) for h, v in zip(x["horses"], new)]
                    y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
                f.write(json.dumps(y, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
