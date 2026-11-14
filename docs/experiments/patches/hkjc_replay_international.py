"""研究計劃第 9 步（國際賽日）：描述性分析（樣本細，唔做統計判決，見計劃 §2）。
外隊馬 = 烙號數字 ≥ 800（HKJC 畀訪港馬嘅編號，例如 J816）。
報：有外隊馬場次嘅模型表現 vs 市場熱門；外隊馬模型排名 vs 實際入頭三率（同本地馬同排名比）；市場對外隊馬嘅定價。
用法：python3 hkjc_replay_international.py <base.jsonl> <replay_index.pkl>
"""
import json, pickle, re, sys
from collections import defaultdict
import numpy as np
sys.path.insert(0, __import__("pathlib").Path(__file__).resolve().parents[3].joinpath(".agents/skills/shared_racing").as_posix())
from eval_metrics import race_metrics  # noqa: E402

def main():
    rows = [json.loads(l) for l in open(sys.argv[1]) if '"horses"' in l]
    idx = pickle.load(open(sys.argv[2], "rb"))
    races, by_rank = [], defaultdict(lambda: {"f": [0, 0], "l": [0, 0]})
    fav_hit_f = [0, 0]
    for x in rows:
        if x["date"] < "2020-09-01":
            continue
        sec = idx["sect"].get((x["date"], x["race"])) or {}
        res = idx["results"].get((x["date"], x["race"])) or {}
        foreign = {int(h["horse_no"]) for h in sec.get("horses", []) if str(h.get("horse_no", "")).isdigit()
                   and (m := re.search(r"[A-Z](\d{3})$", h.get("code") or "")) and int(m.group(1)) >= 800}
        if not foreign:
            continue
        pos = {h["n"]: h["pos"] for h in x["horses"] if h["pos"]}
        top = [k for k, p in pos.items() if p <= 3]
        if len(top) < 3:
            continue
        m = race_metrics(x["picks"], top, actual_pos=pos)
        odds = {}
        for r in res.get("results", []):
            try: odds[int(r["horse_no"])] = float(r["win_odds"])
            except (TypeError, ValueError, KeyError): pass
        fav = min(odds, key=odds.get) if odds else None
        races.append([float(m["gold"]), float(m["good_positional"]), float(m["top3_capture_at5"]),
                      float(pos.get(x["picks"][0], 99) <= 3), float(pos.get(fav, 99) <= 3) if fav else np.nan,
                      len(foreign), float(fav in foreign) if fav else np.nan])
        for i, n in enumerate(x["picks"]):
            g = "1–3" if i < 3 else ("4–6" if i < 6 else "7+")
            k = "f" if n in foreign else "l"
            by_rank[g][k][0] += int(pos.get(n, 99) <= 3); by_rank[g][k][1] += 1
    a = np.array(races)
    print(f"有外隊馬嘅場次（2020/21 起）：{len(a)} 場；平均每場外隊馬 {np.nanmean(a[:, 5]):.1f} 匹；市場熱門係外隊馬 {np.nanmean(a[:, 6]) * 100:.0f}%")
    print(f"模型：Gold {a[:, 0].mean() * 100:.1f}%、Good {a[:, 1].mean() * 100:.1f}%、capture@5 {a[:, 2].mean() * 100:.1f}%、首選上名 {a[:, 3].mean() * 100:.1f}%｜市場熱門上名 {np.nanmean(a[:, 4]) * 100:.1f}%")
    print("模型排名組｜外隊馬入頭三率（n）｜本地馬入頭三率（n）")
    for g in ("1–3", "4–6", "7+"):
        f, l = by_rank[g]["f"], by_rank[g]["l"]
        print(f"{g}｜{f[0] / max(f[1], 1) * 100:.1f}%（{f[1]}）｜{l[0] / max(l[1], 1) * 100:.1f}%（{l[1]}）")

if __name__ == "__main__":
    main()
