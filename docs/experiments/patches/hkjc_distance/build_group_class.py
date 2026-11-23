"""EXP-20261123-09 預先登記（Kelvin 2026-11-23：「交手訊號應唔應該上咗先」「精算暴雪咁有級數同實力點解咁低分」）。寫喺跑之前；尺 v5.2。

假設：讓磅賽嘅負磅已經抵銷大部分評分差（EXP「負磅直接效應」：抵銷約 70%），所以標準馬「評分與經驗」權重 0 冇問題；
但級際賽（Group）負磅差唔多，評分差冇嘢抵銷 —— 評分應該喺級際賽先入分。交手訊號同理（EXP-20261123-08：級際 β 大六倍）。
觸發例子：11-22 R7 精算暴雪 118 分 vs 嘉應奇兵 99 分，同磅 123，評分差 0 分入分。只用嚟提出假設。

特徵（全部場內置中）：
  h2h_grp／h2hn_grp、h2h_oth／h2hn_oth：EXP-20261123-08 交手差（最近一次同場、按負磅換算、±1 秒），分級際／其他
  rat_grp、rat_oth：今仗官方評分 ÷ 10（馬匹頁當日評分；冇評分 = 場均），分級際／其他
arm（各自獨立加落 base_live，同 J3 一樣：線性 L2 C=0.1、每季 walk-forward）：
  HG（交手分組）、RG（評分分組）、HRG（兩樣）
判：dev v5.2 PASS ＋ dev 頭二入頭三 Δ ≥ 0；過咗先睇 holdout。
  **披露**：HG 嘅分組 β 喺 holdout 睇過（EXP-20261123-07 診斷，冇睇 log-loss）→ HG 嘅 holdout 唔算獨立，只報；RG 嘅 holdout 未睇過。
  11-22 只做否決。唔調任何參數。
第二輪追加（Kelvin 2026-11-23：「有評分就要處理負磅，如果唔係一定偏高分重磅馬；嘉應高昇負多少少磅，又未完全平磅」）——
跑之前寫低，屬同一家族第二個 arm（RG 結果已經睇咗，要披露）：
  NR  淨評分 =（評分 − 場均）÷10 −（實際負磅 − 場均）÷10（1 分評分 = 1 磅，HKJC 讓磅規則，唔擬合），全部場一條式；
      讓磅賽負磅已經抵銷大部分評分 → 自然接近 0；級際賽 ≈ 評分差。實際負磅含見習騎師減磅（披露）。
  舊證據：EXP-20261112-22 喺 5,757 場讓磅賽量過 well-in（能力高過負磅）冇剩餘；今次差別係包埋級際賽同評分本身。
  判同上（dev v5.2 PASS＋頭二 Δ ≥ 0；過先開 holdout；11-22 否決）。
第三輪（Kelvin 2026-11-23：「呢個問題好大，要解決；用六季全部級際賽判」）—— 跑之前寫低：
  RGo   只喺級際賽加評分（rat_grp；讓磅賽完全唔郁）【主】
  HRGo  級際賽評分＋級際賽交手（h2h_grp、h2hn_grp、rat_grp）【副】
  判：六季級際賽（2020/21–2026/27，每季用之前季 fit β 再預測 = 全部樣本外；dev／holdout 唔再分開 —— Kelvin 決定，披露：
  RG／HG 嘅 dev 結果同 HG holdout β 已睇過）用 v5.2（全窗口 walk-forward 校準）＋頭二入頭三 Δ ≥ 0。11-22 R7–R9 只做否決。
  `judge_all_group.py` 做評估（將 v5 尺嘅 dev 窗擴到全期）。
第四輪（Kelvin 2026-11-24「級際賽評分實驗性上線，要做得啱，dig deep 點樣最好實作」）—— 跑之前寫低：
  NRGo（主）= 只喺級際賽：淨評分 =（評分 − 場均）÷10 −（實際負磅 − 場均）÷10（級際賽有性別／年齡讓磅，唔一定同磅）
  RGo（對照，第三輪已跑）= 只用評分。判：六季級際賽 160 場（judge_all_group.py）報；上線揀 NRGo，除非 NRGo 方向反而差過 RGo。
  外隊馬冇評分 = 場均（live 一樣）。
第五輪（Kelvin 2026-11-24「遨遊氣泡狀態咁差都升第 2？測兩個修正先，驚 overfit，搵到解決方法再上」）—— 跑之前寫低：
  觸發：11-22 R9 遨遊氣泡評分 126（場均 ~97）、上仗第 11、表現數字低過場均，淨評分加 +10.6 升第 2（實際第 5）—— 官方評分滯後。
  NRGc = NRGo 但淨評分封頂 ±1.5（即 ±15 分）
  NRGf = NRGo 但表現數字（figW，同 live performance_figure 定義；冇 = 場均）低過場均嘅馬，淨評分 × 0.5
  判（六季級際賽，judge_all_group.py）：Δlog-loss 唔差過 NRGo，而且首選贏唔少過 NRGo，先算好過 NRGo；兩個都唔過就唔上任何級際賽評分。
用法：python3 build_group_class.py <base.jsonl> <out_prefix>（要 <out_prefix>_h2h.pkl，由 build_h2h.py 出）
"""
import json
import pickle
import re
import sys
from collections import defaultdict

import numpy as np
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
sys.path.insert(0, "/Users/imac/Antigravity-repo/docs/experiments/patches/hkjc_patterns")
import features as F  # noqa: E402
import hkjc_history_replay_build as hb  # noqa: E402


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


FIG = {}


def main():
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
    out = sys.argv[2]
    hf = pickle.load(open(out + "_h2h.pkl", "rb"))
    import pandas as pd
    _F = pd.read_pickle("/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/j3-refine-20261123/f_fig.pkl")
    global FIG
    FIG = {(d, c): w for d, c, w in zip(_F.date, _F.code, _F.figW)}
    idx = hb.load_index()["results"]
    grp = {k: str((r.get("_header") or {}).get("RaceClass") or "").startswith("Group") for k, r in idx.items()}
    no2code, wt = {}, {}
    for k, r in idx.items():
        for q in r.get("results") or []:
            m = re.search(r"\(([A-Z]\d{3})\)", str(q.get("horse_name") or ""))
            if m:
                no2code[(k, str(q.get("horse_no")))] = m.group(1)
                try:
                    wt[(k, str(q.get("horse_no")))] = float(q.get("actual_wt"))
                except (TypeError, ValueError):
                    pass
    pages, _ = F.load()
    rating = {}
    for c, rr in pages.items():
        for q in rr:
            rating[(c, q["d"])] = F.num(q.get("rating"))
    feats = {}
    cov = [0, 0]
    for x in rows:
        k = (x["date"], x["race"])
        g = float(grp.get(k, False))
        rat = []
        for h in x["horses"]:
            c = no2code.get((k, str(h["n"])))
            rat.append(rating.get((c, x["date"])) if c else None)
        have = [v for v in rat if v is not None]
        mu = np.mean(have) if have else 0.0
        cov[0] += len(have); cov[1] += len(rat)
        r = np.array([((v if v is not None else mu) - mu) / 10.0 for v in rat])
        h = hf[k][:, :2]; h = h - h.mean(axis=0)
        ws = [wt.get((k, str(hh["n"]))) for hh in x["horses"]]
        wv = [v for v in ws if v is not None]
        wm = np.mean(wv) if wv else 0.0
        w = np.array([((v if v is not None else wm) - wm) / 10.0 for v in ws])
        net = r - w
        fw = np.array([FIG.get((x["date"], no2code.get((k, str(hh["n"]))))) for hh in x["horses"]], dtype=float)
        okf = ~np.isnan(fw)
        fmu = fw[okf].mean() if okf.any() else 0.0
        fw = np.where(okf, fw, fmu)
        weak = np.where(fw < fmu, 0.5, 1.0)
        feats[k] = np.column_stack([h * g, h * (1 - g), r * g, r * (1 - g), r - w, net * g,
                                    np.clip(net, -1.5, 1.5) * g, net * weak * g])
    print("評分覆蓋", round(cov[0] / cov[1], 4), flush=True)
    by = defaultdict(list)
    for x in rows:
        by[season(x["date"])].append(x)
    arms = sys.argv[3].split(",") if len(sys.argv) > 3 else ["HG", "RG", "HRG"]
    for arm, cols, names in (("NRGc", [8], ["net_rat_grp_cap"]), ("NRGf", [9], ["net_rat_grp_formweak"]), ("NRGo", [7], ["net_rat_grp"]), ("RGo", [4], ["rat_grp"]), ("HRGo", [0, 1, 4], ["h2h_grp", "h2hn_grp", "rat_grp"]),
                             ("NR", [6], ["net_rating"]), ("HG", [0, 1, 2, 3], ["h2h_grp", "h2hn_grp", "h2h_oth", "h2hn_oth"]),
                             ("RG", [4, 5], ["rat_grp", "rat_oth"]),
                             ("HRG", [0, 1, 2, 3, 4, 5], ["h2h_grp", "h2hn_grp", "h2h_oth", "h2hn_oth", "rat_grp", "rat_oth"])):
        if arm not in arms:
            continue
        models = {}
        for s in sorted(by):
            if s < 2020:
                continue
            R, ZZ, Y = [], [], []
            for x in (x for t in by if 2019 <= t < s for x in by[t]):
                keep = [i for i, hh in enumerate(x["horses"]) if hh["pos"]]
                r = np.array([hh["raw"] for hh in x["horses"]])
                R.append((r - r.mean())[keep]); ZZ.append(feats[(x["date"], x["race"])][:, cols][keep])
                Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
            R, ZZ, Y = np.concatenate(R), np.vstack(ZZ), np.array(Y)
            sd = ZZ.std(axis=0); sd[sd == 0] = 1
            rs = R.std()
            c = LogisticRegression(C=0.1, max_iter=20000).fit(np.column_stack([R / rs, ZZ / sd]), Y).coef_[0]
            models[s] = (c[1:] / sd) / (c[0] / rs)
        print(arm, {s: [round(float(b), 2) for b in m] for s, m in models.items() if s in (2020, 2023, 2026)}, names, flush=True)
        with open(f"{out}_{arm}.jsonl", "w") as f:
            for x in rows:
                s = season(x["date"])
                y = dict(x, arm=f"grpcls_{arm}")
                if s in models:
                    r = np.array([hh["raw"] for hh in x["horses"]])
                    new = r + feats[(x["date"], x["race"])][:, cols] @ models[s]
                    y["horses"] = [dict(hh, raw=round(float(v), 4)) for hh, v in zip(x["horses"], new)]
                    y["picks"] = [hh["n"] for hh in sorted(y["horses"], key=lambda hh: -hh["raw"])]
                f.write(json.dumps(y, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
