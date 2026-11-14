"""研究計劃第 4 步：段速候選喺全量回放語料（EXP-09 三個 arm 重跑 + §2c 負磅換算版）。

預先登記（跑之前寫死）：
  值      sect_features_v2.pkl：first_v、total_v、total_vw（全程換算到今仗負磅，0.0033 秒／400 米／磅）
  標準化  mean／SD 只用 2024-08-01 之前（burn-in + dev）
  組件    z = clip((x − mean)/SD, ±2.5)；speed' = clip(speed + b × 9.45 × z, 0, 100)；冇值唔郁；MATRIX_WEIGHTS 唔郁
  arm     FT_b50（主，同 EXP-09）、F_b50、T_b50、Tw_b50、FTw_b50（b = 0.5）；全部報，Holm 喺 5 個之內
  計分    picks = sort(raw + 0.1285 × Δspeed)；先核對 base 嘅 picks = raw 排序
  判決    hkjc_replay_compare.py dev 窗；過 dev 嘅最多 2 個去 holdout（登記簿）
用法：python3 hkjc_replay_sectional_arms.py <base.jsonl> <sect_features_v2.pkl> <replay_index.pkl> <outdir>
"""
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

W_SECT = 0.1285
SPEED_SD = 9.45
ARMS = {"FT_b50": (("first_v", "total_v"), 0.5), "F_b50": (("first_v",), 0.5), "T_b50": (("total_v",), 0.5),
        "Tw_b50": (("total_vw",), 0.5), "FTw_b50": (("first_v", "total_vw"), 0.5)}


def main():
    base_p, feat_p, idx_p, out = sys.argv[1], sys.argv[2], sys.argv[3], Path(sys.argv[4])
    out.mkdir(parents=True, exist_ok=True)
    rows = [json.loads(line) for line in open(base_p)]
    F = pd.read_pickle(feat_p)
    F["date"] = F.race.str[:10]
    hist = F[F.date < "2024-08-01"]
    st = {c: (hist[c].mean(), hist[c].std()) for c in ("first_v", "total_v", "total_vw")}
    feat = {(r.race, r.code): r for r in F.itertuples()}
    idx = pickle.load(open(idx_p, "rb"))
    bad = 0
    for x in rows:
        if "horses" not in x:
            continue
        hs = x["horses"]
        ns = np.array([h["n"] for h in hs])
        raw = np.array([h["raw"] for h in hs])
        bad += [int(v) for v in ns[np.lexsort((ns, -raw))]] != x["picks"]
    print(f"核對：base picks ≠ raw 排序 {bad} 場")
    if bad:
        sys.exit("離線重排唔成立，停")

    def z(row, c):
        v = getattr(row, c, None) if row is not None else None
        if v is None or pd.isna(v):
            return None
        m, s = st[c]
        return max(-2.5, min(2.5, (v - m) / s))

    zmap = {}
    for x in rows:
        if "horses" not in x:
            continue
        ven = "HV" if "跑馬地" in x["venue"] else "ST"
        sec = idx["sect"].get((x["date"], x["race"])) or {}
        no2code = {str(h.get("horse_no")): h.get("code") for h in sec.get("horses", [])}
        for h in x["horses"]:
            row = feat.get((f"{x['date']}|{ven}|{x['race']}", no2code.get(str(h["n"]))))
            zmap[(x["meeting"], x["race"], h["n"])] = {c: z(row, c) for c in st}
    for arm, (cols, b) in ARMS.items():
        moved = 0
        with open(out / f"sect_{arm}.jsonl", "w") as fh:
            for x in rows:
                if "horses" not in x:
                    fh.write(json.dumps(x, ensure_ascii=False) + "\n")
                    continue
                hs = []
                for h in x["horses"]:
                    zz = [zmap[(x["meeting"], x["race"], h["n"])][c] for c in cols]
                    sp = h["f"]["speed_score"]
                    if any(v is None for v in zz):
                        hs.append(h)
                        continue
                    sp2 = max(0.0, min(100.0, sp + b * SPEED_SD * float(np.mean(zz))))
                    hs.append(dict(h, raw=h["raw"] + W_SECT * (sp2 - sp)))
                ns = np.array([h["n"] for h in hs])
                raw = np.array([h["raw"] for h in hs])
                picks = [int(v) for v in ns[np.lexsort((ns, -raw))]]
                moved += picks != x["picks"]
                fh.write(json.dumps(dict(x, arm=arm, picks=picks, horses=hs), ensure_ascii=False) + "\n")
        print(f"{arm}：{moved} 場排名有郁")


if __name__ == "__main__":
    main()
