"""EXP-20261113-08 特徵：歷史逐匹分段（HKJC 分段時間及位置頁，2019-09 起）→ 賽前 as-of 段速特徵。

預先登記（跑之前寫死）：
  標準    每季 s 嘅標準分段 = s 之前所有季、同場地跑道（沙田草地／跑馬地草地／沙田全天候）、同路程、同班次、同段，
          入頭三馬匹嘅分段中位數（n ≥ 20；唔夠就用唔分班次）。2019/20 季冇標準 → 該季只做 burn-in。
          比較時一律用「今仗班次」嘅標準（Kelvin 定義，令唔同班次往績可比）；今仗班次冇就用嗰仗班次。
  當日快慢 每個賽日 × 場地跑道 × 段類（第一段／中段／L400）：當日所有馬匹（對嗰仗自己班次標準）偏差中位數，按段長換算每 400 米。
          只用喺往績（賽後先知），唔用喺今仗。
  每匹    近 6 仗（賽日之前），1/k 加權，最少 2 仗；全部「每 400 米慢幾多秒」取負（越大越好）：
          first（第一段，按段長換算）、mid（第二段至倒數第二段之前，只計 ≥ 4 段嘅仗）、pen（倒數第二段）、l400、total（全程）
          各有 raw 同 _v（減當日快慢）兩版；style = 第一段走位百分位（0 = 領放）取負
  唔換算負磅（Kelvin：前段負磅影響好細；EXP-07 相關 0.99）
輸出：sect_features.pkl（race, code, 特徵…），race = "YYYY-MM-DD|ST/HV|N"（同 concept_features 一樣）
"""
import gzip
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / ".agents/skills/hkjc_racing/hkjc_race_extractor/scripts"))
import backfill_history as b  # noqa: E402

CLS = {"第一班": "C1", "第二班": "C2", "第三班": "C3", "第四班": "C4", "第五班": "C5"}


def season_of(d):
    y, m = int(d[:4]), int(d[5:7])
    return y if m >= 9 else y - 1


def load_runs():
    rows = []
    src = b.PARSED / "sectionals.jsonl.gz"
    for line in gzip.open(src, "rt", encoding="utf-8"):
        r = json.loads(line)
        n_sec = len(r["horses"][0]["sections"]) if r["horses"] else 0
        dist = r["distance"]
        if not dist or n_sec < 3:
            continue
        ven = "HV" if "Happy" in str(r.get("venue")) or "跑馬地" in str(r.get("venue")) else "ST"
        track = "AWT" if r["surface"] == "全天候" else ven
        lens = [dist - 400 * (n_sec - 1)] + [400] * (n_sec - 1)
        field = len(r["horses"])
        for h in r["horses"]:
            secs = [s["time"] for s in h["sections"]]
            if len(secs) != n_sec or not h["code"]:
                continue
            fin = int(h["finish"]) if str(h["finish"]).isdigit() else None
            p1 = h["sections"][0]["pos"]
            rows.append({"race": f"{r['date']}|{ven}|{r['race_no']}", "date": r["date"], "season": season_of(r["date"]),
                         "track": track, "dist": dist, "cls": CLS.get(r["class"] or "", "OT"), "code": h["code"],
                         "fin": fin, "secs": secs, "lens": lens, "field": field,
                         "p1": (p1 - 1) / max(field - 1, 1) if p1 else np.nan})
    return pd.DataFrame(rows)


def standards(R):
    """{season: {(track, dist, cls, idx): median}}，只用之前季、入頭三。"""
    out = {}
    seasons = sorted(R.season.unique())
    for s in seasons:
        prior = R[(R.season < s) & (R.fin <= 3)]
        if prior.empty:
            continue
        cell, cell_all = defaultdict(list), defaultdict(list)
        for t, d, c, secs in zip(prior.track, prior.dist, prior.cls, prior.secs):
            for i, v in enumerate(secs):
                cell[(t, d, c, i)].append(v)
                cell_all[(t, d, "ALL", i)].append(v)
        std = {k: float(np.median(v)) for k, v in cell.items() if len(v) >= 20}
        std.update({k: float(np.median(v)) for k, v in cell_all.items() if len(v) >= 20})
        out[s] = std
    return out


def main():
    out = Path(sys.argv[1])
    R = load_runs().sort_values(["date", "race"]).reset_index(drop=True)
    STD = standards(R)
    print(f"{len(R)} 匹次、{R.race.nunique()} 場；有標準嘅季：{sorted(STD)}")

    def std_for(season, track, dist, cls, n):
        st = STD.get(season)
        if not st:
            return None
        v = [st.get((track, dist, cls, i)) or st.get((track, dist, "ALL", i)) for i in range(n)]
        return None if any(x is None for x in v) else v

    # 每匹次偏差（對自己班次標準）→ 當日快慢
    devs_own = []
    for row in R.itertuples():
        st = std_for(row.season, row.track, row.dist, row.cls, len(row.secs))
        devs_own.append(None if st is None else [a - b_ for a, b_ in zip(row.secs, st)])
    R["dev_own"] = devs_own
    var = defaultdict(lambda: defaultdict(list))
    for row in R.itertuples():
        if row.dev_own is None:
            continue
        d, L = row.dev_own, row.lens
        var[(row.date, row.track)]["first"].append(d[0] / (L[0] / 400))
        var[(row.date, row.track)]["l400"].append(d[-1])
        if len(d) >= 4:
            var[(row.date, row.track)]["mid"].append(float(np.mean(d[1:-2])))
        var[(row.date, row.track)]["pen"].append(d[-2])
    VAR = {k: {kk: float(np.median(vv)) for kk, vv in v.items()} for k, v in var.items()}

    # 每匹往績索引
    by_code = defaultdict(list)
    for i, row in enumerate(R.itertuples()):
        by_code[row.code].append(i)
    feats = []
    races = R.groupby("race").first()[["date", "season", "cls"]]
    for race, rr in R.groupby("race"):
        date, season, today_cls = races.loc[race, "date"], races.loc[race, "season"], races.loc[race, "cls"]
        for code in rr.code:
            prev = [i for i in by_code[code] if R.at[i, "date"] < date][-6:][::-1]
            acc = defaultdict(list)
            for i in prev:
                row = R.loc[i]
                st = std_for(season, row.track, row.dist, today_cls, len(row.secs)) or \
                    std_for(season, row.track, row.dist, row.cls, len(row.secs))
                if st is None:
                    continue
                d = [a - b_ for a, b_ in zip(row.secs, st)]
                L = row.lens
                v = VAR.get((row.date, row.track), {})
                parts = {"first": d[0] / (L[0] / 400), "l400": d[-1], "pen": d[-2],
                         "total": sum(d) / (row.dist / 400)}
                if len(d) >= 4:
                    parts["mid"] = float(np.mean(d[1:-2]))
                for k, x in parts.items():
                    acc[k].append(x)
                    adj = v.get(k) if k != "total" else (np.mean([v.get("first", 0), v.get("l400", 0)]) if v else None)
                    if adj is not None:
                        acc[k + "_v"].append(x - adj)
                if not np.isnan(row.p1):
                    acc["style"].append(row.p1)
            f = {"race": race, "code": code}
            for k, xs in acc.items():
                if len(xs) >= 2:
                    w = 1.0 / np.arange(1, len(xs) + 1)
                    f[k] = -float(np.dot(xs, w) / w.sum())
            feats.append(f)
    F = pd.DataFrame(feats)
    F.to_pickle(out)
    print(f"寫入 {out}：{len(F)} 行；覆蓋 " + "、".join(f"{c} {F[c].notna().mean()*100:.0f}%" for c in F.columns if c not in ("race", "code")))


if __name__ == "__main__":
    main()
