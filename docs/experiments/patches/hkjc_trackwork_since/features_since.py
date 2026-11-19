"""EXP-20261119-12 預先登記（Kelvin 2026-11-20「唔好睇 21 日，睇上仗至今嘅晨操，會唔會見到訊號？」）。
沿用 EXP-20261115-21 嘅數據（現役馬晨操頁，raw/trackwork）同篩選法（screen.py：揀選窗 2022/23–2025/26、確認窗 2026/27）。
窗 S = 上仗翌日 → 今仗前一日（比賽行唔計）；窗 T = 近 21 日（同定義，對照）。上仗 = 賽果庫 HKJC 上一仗；冇上仗（初出）→ S 特徵 None。
每個窗 6 個特徵：
  gal 快操次數、gpw 每 7 日快操（S 用上仗至今日數；T = gal/3）、trial 試閘次數、
  relax 放鬆課佔比（游水＋踱步＋跑步機＋水中步行機）÷ 全部課、sj 今仗騎師策騎快操＋試閘、sess 全部課數
用法：python3 features_since.py <out.jsonl>
"""
import bisect, json, sys
from collections import defaultdict
from datetime import date as D
sys.path.insert(0, "/Users/imac/Antigravity-repo/docs/experiments/patches/hkjc_trackwork")
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
from features import load_tw, days  # noqa: E402

RELAX = ("swimming", "trotting", "treadmill", "aqua_walker")
def summarise(rows, jock, span):
    gal = [x for x in rows if x["type"] == "gallop"]; tri = [x for x in rows if x["type"] == "trial"]
    rel = [x for x in rows if x["type"] in RELAX]
    return {"gal": len(gal), "gpw": round(len(gal) * 7 / max(span, 7), 3), "trial": len(tri),
            "relax": round(len(rel) / len(rows), 3) if rows else None,
            "sj": sum(1 for x in gal + tri if jock and x.get("rider") == jock), "sess": len(rows)}

def main():
    import hkjc_history_replay_pit as p
    tw = load_tw()
    df = p.load_all_rows_extended(); df = df[df["HorseID"].isin(list(tw))].copy()
    df["d"] = df["Date"].astype(str).str[:10]; df = df.sort_values("d")
    last_run = {}; n = 0
    with open(sys.argv[1], "w") as fo:
        for r in df.itertuples():
            rows = [x for x in tw[r.HorseID] if str(x.get("type_raw") or "") != "出賽"]
            dates = [x["date"] for x in rows]
            pre = rows[:bisect.bisect_left(dates, r.d)]
            jock = str(r.Jockey or "").strip()
            t = [x for x in pre if days(x["date"], r.d) <= 21]
            feat = {"date": r.d, "race": int(r.RaceNo), "brand": r.HorseID}
            feat.update({f"T_{k}": v for k, v in summarise(t, jock, 21).items()})
            lr = last_run.get(r.HorseID)
            if lr:
                s = [x for x in pre if x["date"] > lr]
                feat.update({f"S_{k}": v for k, v in summarise(s, jock, days(lr, r.d)).items()})
                feat["S_days"] = days(lr, r.d)
            else:
                feat.update({f"S_{k}": None for k in ("gal", "gpw", "trial", "relax", "sj", "sess")}); feat["S_days"] = None
            last_run[r.HorseID] = r.d
            fo.write(json.dumps(feat) + "\n"); n += 1
    print("runs", n)

if __name__ == "__main__":
    main()
