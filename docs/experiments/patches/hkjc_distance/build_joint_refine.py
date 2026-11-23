"""EXP-20261123-07 預先登記（Kelvin 2026-11-23「J3 中間係咪有噪音：慢閘係咪唔應該加分、一仗兩個藉口淨係加一次；
refine 到確保有進步，同埋起碼 11-22 唔會差先上」）。寫喺跑之前；回放尺 = main 現行（v5.2，含頭二護欄）。

背景：J3（EXP-20261122-34）17 個訊號獨立加分。11-22 沙田賽前快照重算：頭四命中 21→21，但頭二入頭三 14→11、頭二有頭馬 6→4；
三場變差都係「一匹馬疊幾個加分」（R2 常嚐發財 騎法被查詢＋上上仗走外疊＋出閘慢 = +2.85；R11 極上紗瓏 降班＋評分跌返 +2.68；
R6 佰勝金龍 受阻＋出閘慢）。11-22 只用嚟揀「要測咩」，唔用嚟揀 β 或者門檻。

做法同 J3 一樣（線性 L2 C=0.1、每季 walk-forward、場內置中、base = v4/cons/base_live_20261122.jsonl），只改特徵：
  J3   重現（17 個）
  A    藉口封頂：ride_q／wide2／blocked2／slow 四個合成一個 excuse_any（任何一個 = 1），即一匹馬藉口最多加一次
  B    慢閘只計「唔係慣性」：上仗出閘慢，而之前 3 份有報告嘅賽事都冇出閘慢（慣性慢閘冇藉口價值）
  AB   A＋B（excuse_any 入面嘅 slow 用 B 版）
  另外逐個特徵剔走（leave-one-out，dev 診斷，唔判）。
第二輪（睇咗第一輪 dev 之後先加，屬 dev 揀出嚟，要喺 terminal／forward 確認，唔可以當預先登記）：
  ABL   AB 再剷 leave-one-out 入面剔走冇損失嘅四個獨立訊號：backup10、dist_down、sd_hicls、sd_locls
        （blocked2 已經喺 excuse_any 入面，照留做藉口定義嘅一部分）
  ABLH  ABL ＋ 交手訊號（EXP-20261123-08）分級際賽／其他兩組（Kelvin：「有機會淨係適用級際賽」）
判（預先寫低）：
  1. dev 用 v5.2 判（Δlog-loss CI 上界 < 0、Gold／Good 護欄、null、v5.2 頭二護欄）；唔過唔理。
  2. 過咗嘅 arm 之中揀 dev「頭二入頭三匹數」最高嘅一個；要求佢頭二入頭三 Δ（對 base）點估計 ≥ 0。
  3. 最後確認：terminal 窗（2026/27）+ 11-22 沙田賽前快照「頭二入頭三」唔少過 base（Kelvin 嘅否決條件；單日冇功效，只做否決唔做揀）。
     holdout 已經喺 J3 睇過，今次只報（標明唔獨立），唔用嚟揀。
  唔調 C、唔調門檻；leave-one-out 結果只用嚟寫記錄同提出下一輪假設。
第三輪（Kelvin 2026-11-23「J3 唔好用晒 13+4，淨係用幫到手嘅訊號」）—— 跑之前寫低：
  base 換做 SW（表現數字取代段速，EXP-20261123-10 上線版）：`<scratch>/f_SW.jsonl`。
  SEL  只留 dev leave-one-out 剔走後 log-loss 變差 ≥ 0.00005 嘅 8 個（J3 −0.00100 基準）：
       ride_q、wide2、rb_any、drop_rb、old_won、class_pos、sd_worse、sd_rate（規則只睇 dev LOO；冇睇 11-22、holdout）。
  判：dev v5.2 PASS ＋ 頭二入頭三 Δ ≥ 0；holdout 照報但唔獨立（J3 家族 holdout 已睇過）；terminal 報；
      11-22 否決：頭二入頭三唔少過 SW、頭二有頭馬唔少過 SW。
用法：python3 build_joint_refine.py <base_live.jsonl> <old_incidents.json> <out_prefix>
"""
import json
import pickle
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_joint_plus as JP  # noqa: E402

NAMES = JP.NAMES
EXC = ["ride_q", "wide2", "blocked2", "slow"]


def slow_new(prev):
    rep = [v[2] for v in prev if v[2] is not None]
    if not prev or prev[-1][2] is None:
        return 0.0
    last = prev[-1][2]
    if not JP.has(JP.SLOW, last):
        return 0.0
    return float(not any(JP.has(JP.SLOW, r) for r in rep[-4:-1]))


def build(rows, inc_path, cache):
    if Path(cache).exists():
        return pickle.load(open(cache, "rb"))
    import re
    inc = JP.load_runs(inc_path)
    code_of = {(d, n, hn): c for c, v in inc.items() for d, n, _, hn in v}
    pages, _ = JP.F.load()
    pidx = {c: {q["d"]: i for i, q in enumerate(rr)} for c, rr in pages.items()}
    import hkjc_history_replay_build as hb
    TCLS = {}
    for (d, n), race in hb.load_index()["results"].items():
        cc = str((race.get("_header") or {}).get("RaceClass") or "")
        mm = re.match(r"Class (\d)", cc)
        TCLS[(d, n)] = int(mm.group(1)) if mm else (0 if cc.startswith(("Group", "Griffin")) else None)
    X = {}
    for x in rows:
        mat = []
        for h in x["horses"]:
            c = code_of.get((x["date"], x["race"], str(h["n"])))
            f = dict.fromkeys(NAMES + ["slow_new"], 0.0)
            if c:
                prev = [v for v in inc[c] if v[0] < x["date"]]
                f.update(JP.inc_feats(prev))
                f["slow_new"] = slow_new(prev)
                i = pidx.get(c, {}).get(x["date"])
                if i is not None:
                    f.update(JP.page_feats(pages[c], i))
                    f.update(JP.sd_feats(pages[c], i, TCLS.get((x["date"], x["race"]))))
            mat.append([f[k] for k in NAMES + ["slow_new"]])
        X[(x["date"], x["race"])] = np.array(mat, dtype=float)
    pickle.dump(X, open(cache, "wb"))
    return X


ALL = NAMES + ["slow_new"]


def arm_matrix(m, arm):
    col = {k: m[:, j] for j, k in enumerate(ALL)}
    if arm == "J3":
        names = list(NAMES)
    elif arm == "SEL":
        names = ["ride_q", "wide2", "rb_any", "drop_rb", "old_won", "class_pos", "sd_worse", "sd_rate"]
    elif arm.startswith("LOO_"):
        names = [k for k in NAMES if k != arm[4:]]
    else:
        slow = col["slow_new"] if "B" in arm else col["slow"]
        col = dict(col, slow=slow)
        if "A" in arm:
            col["excuse_any"] = np.maximum.reduce([col[k] for k in EXC])
            names = ["excuse_any"] + [k for k in NAMES if k not in EXC]
        else:
            names = list(NAMES)
    if "L" in arm:
        names = [k for k in names if k not in ("backup10", "dist_down", "sd_hicls", "sd_locls")]
    z = np.column_stack([col[k] for k in names])
    return names, z - z.mean(axis=0)


def main():
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
    out = sys.argv[3]
    X = build(rows, sys.argv[2], out + "_feats.pkl")
    by = defaultdict(list)
    for x in rows:
        by[JP.season(x["date"])].append(x)
    arms = sys.argv[4].split(",") if len(sys.argv) > 4 else ["J3", "A", "B", "AB"]
    for arm in arms:
        Z = {k: arm_matrix(m, arm) for k, m in X.items()}
        if arm.endswith("H"):
            import re
            import hkjc_history_replay_build as hb
            hf = pickle.load(open(out + "_h2h.pkl", "rb"))
            grp = {k: str((r.get("_header") or {}).get("RaceClass") or "").startswith("Group")
                   for k, r in hb.load_index()["results"].items()}
            for k, (nm, z) in Z.items():
                h = hf[k][:, :2]; h = h - h.mean(axis=0); g = float(grp.get(k, False))
                Z[k] = (nm + ["h2h_grp", "h2hn_grp", "h2h_oth", "h2hn_oth"], np.column_stack([z, h * g, h * (1 - g)]))
        names = next(iter(Z.values()))[0]
        models = {}
        for s in sorted(by):
            if s < 2020:
                continue
            R, ZZ, Y = [], [], []
            for x in (x for t in by if 2019 <= t < s for x in by[t]):
                keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
                r = np.array([h["raw"] for h in x["horses"]])
                R.append((r - r.mean())[keep]); ZZ.append(Z[(x["date"], x["race"])][1][keep])
                Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
            R, ZZ, Y = np.concatenate(R), np.vstack(ZZ), np.array(Y)
            sd = ZZ.std(axis=0); sd[sd == 0] = 1
            rs = R.std()
            c = LogisticRegression(C=0.1, max_iter=20000).fit(np.column_stack([R / rs, ZZ / sd]), Y).coef_[0]
            models[s] = (c[1:] / sd) / (c[0] / rs)
        print(arm, "2026/27 β", {k: round(float(b), 2) for k, b in zip(names, models[max(models)])}, flush=True)
        with open(f"{out}_{arm}.jsonl", "w") as f:
            for x in rows:
                s = JP.season(x["date"])
                y = dict(x, arm=f"joint_{arm}")
                if s in models:
                    r = np.array([h["raw"] for h in x["horses"]])
                    new = r + Z[(x["date"], x["race"])][1] @ models[s]
                    y["horses"] = [dict(h, raw=round(float(v), 4)) for h, v in zip(x["horses"], new)]
                    y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
                f.write(json.dumps(y, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
