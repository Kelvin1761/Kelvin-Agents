"""研究計劃第 1 步：現行模型喺回放語料嘅分段表現（描述，唔係判決）。

分段：泥地（AWT）、沙田直路 1000、初出馬場次（場內 ≥1 匹初出）、國際賽日（場內有外隊馬：分段頁冇馬匹 ID 嘅出賽馬）、
班次（C1–C5／分級賽）、路程（≤1200／1201–1799／≥1800）、場地（沙田草地／跑馬地）、季
每段：場數、Gold、Good、capture@5、頭二選有中、首選上名率；對照「市場熱門」（獨贏賠率最低）首選上名率 —— 賠率只做對照，唔入模型。
用法：python3 hkjc_replay_segments.py <replay_dump.jsonl> <replay_index.pkl> [--since YYYY-MM-DD]
"""
import json
import pickle
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, __import__("pathlib").Path(__file__).resolve().parents[3].joinpath(".agents/skills/shared_racing").as_posix())
from eval_metrics import race_metrics  # noqa: E402


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def main():
    rows = [json.loads(line) for line in open(sys.argv[1])]
    idx = pickle.load(open(sys.argv[2], "rb"))
    since = sys.argv[sys.argv.index("--since") + 1] if "--since" in sys.argv else "0000"
    seg = defaultdict(list)
    for x in rows:
        if "horses" not in x or x["date"] < since:
            continue
        hs = x["horses"]
        pos = {h["n"]: h["pos"] for h in hs if h["pos"]}
        top = [k for k, p in pos.items() if p <= 3]
        if len(top) < 3:
            continue
        m = race_metrics(x["picks"], top, actual_pos=pos)
        res = idx["results"].get((x["date"], x["race"])) or {}
        sec = idx["sect"].get((x["date"], x["race"])) or {}
        odds = {}
        for r in res.get("results", []):
            try:
                odds[int(r["horse_no"])] = float(r.get("win_odds"))
            except (TypeError, ValueError, KeyError):
                pass
        fav = min(odds, key=odds.get) if odds else None
        v = [float(m["gold"]), float(m["good_positional"]), float(m["top3_capture_at5"]), float(m["top2_any_hit"]),
             float(pos.get(x["picks"][0], 99) <= 3), float(pos.get(fav, 99) <= 3) if fav else np.nan]
        cls = str(sec.get("class") or "?")
        dist = int(x.get("distance") or sec.get("distance") or 0)
        keys = ["全部", f"季 {season(x['date'])}/{(season(x['date']) + 1) % 100:02d}",
                "泥地" if x.get("awt") else ("跑馬地" if "跑馬地" in str(x.get("venue")) else "沙田草地"),
                "≤1200" if dist <= 1200 else ("1201-1799" if dist < 1800 else "≥1800"),
                {"第一班": "C1", "第二班": "C2", "第三班": "C3", "第四班": "C4", "第五班": "C5"}.get(cls, "分級／其他")]
        if dist == 1000 and not x.get("awt") and "跑馬地" not in str(x.get("venue")):
            keys.append("沙田直路1000")
        if any(h.get("debut") for h in hs):
            keys.append("有初出馬嘅場")
        if any(not h.get("horse_id") for h in sec.get("horses", [])):
            keys.append("有外隊馬（國際賽）")
        for k in keys:
            seg[k].append(v)
    order = ["全部"] + sorted(k for k in seg if k.startswith("季")) + ["沙田草地", "跑馬地", "泥地", "沙田直路1000", "≤1200", "1201-1799", "≥1800",
                                                                   "C1", "C2", "C3", "C4", "C5", "分級／其他", "有初出馬嘅場", "有外隊馬（國際賽）"]
    print("分段｜場數｜Gold｜Good｜capture@5｜頭二選有中｜首選上名｜市場熱門上名（對照）")
    for k in order:
        if k not in seg:
            continue
        a = np.array(seg[k], dtype=float)
        print(f"{k}｜{len(a)}｜" + "｜".join(f"{np.nanmean(a[:, i]) * 100:.1f}%" for i in range(6)))


if __name__ == "__main__":
    main()
