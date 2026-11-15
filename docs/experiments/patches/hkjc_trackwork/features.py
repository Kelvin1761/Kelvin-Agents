"""Kelvin 2026-11-15「睇下晨操點樣影響馬匹表現」（只用現役馬）。

由 raw/trackwork/*.html.gz（HKJC 晨操紀錄，現役馬全生涯）砌每一仗嘅賽前晨操特徵。
嚴格只用賽日之前（date < 賽日）嘅紀錄；「有冇紀錄」唔做特徵（退役馬頁面空 = 倖存者偏差）。
特徵：
  g14 / g28         近 14／28 日快操次數
  jg28              近 28 日由騎師（唔係助手）策騎嘅快操
  sj28              近 28 日由今仗騎師策騎嘅快操（試閘唔計）
  sw14 / tr14       近 14 日游水／踱步次數
  mach14            近 14 日跑步機＋水中步行機
  trial42           近 42 日試閘次數
  dlg               距上次快操日數（上限 60）
  fast21            近 21 日最快快操最後一段（秒）減本駒之前同地點、同段數快操嘅中位數（負 = 快過自己平時）
  g28_vs_own        g28 − 本駒之前每仗 g28 平均（「操得比平時多」）
  dlr               距上仗日數（控制用）
輸出 jsonl：{date, race, brand, ...}。用法：python3 features.py <out.jsonl>
"""
import bisect
import glob
import gzip
import json
import re
import statistics
import sys
from collections import defaultdict
from datetime import date as D

sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_race_extractor/scripts")
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
RAW = "/Volumes/Kelvin Hardisk 1/WongChoi-Archive/hkjc-history/raw/trackwork"


def days(a, b):
    return (D.fromisoformat(b) - D.fromisoformat(a)).days


def load_tw():
    import extract_trackwork as e
    out = {}
    for f in glob.glob(RAW + "/*.html.gz"):
        brand = f.rsplit("_", 1)[-1].split(".")[0]
        rows = e.parse_trackwork_rows(gzip.open(f, "rt", encoding="utf-8").read(),
                                      {"horseid": "", "horse_name": "", "trainer": ""}, None, 99999)
        rows = [r for r in rows if re.match(r"\d{4}-\d{2}-\d{2}", str(r.get("date") or ""))]
        out[brand] = sorted(rows, key=lambda r: r["date"])
    return out


def main():
    import hkjc_history_replay_pit as p
    tw = load_tw()
    df = p.load_all_rows_extended()
    df = df[df["HorseID"].isin(list(tw))].copy()
    df["d"] = df["Date"].astype(str).str[:10]
    df = df.sort_values("d")
    hist = defaultdict(list)      # brand -> 之前每仗 g28
    last_run = {}
    n = 0
    with open(sys.argv[1], "w") as fo:
        for r in df.itertuples():
            rows = tw[r.HorseID]
            dates = [x["date"] for x in rows]
            i = bisect.bisect_left(dates, r.d)          # 嚴格早過賽日
            pre = rows[:i]

            def win(k, typ=None):
                return [x for x in pre if days(x["date"], r.d) <= k and (typ is None or x["type"] in typ)]
            g28 = win(28, ("gallop",))
            jock = str(r.Jockey or "").strip()
            gal_all = [x for x in pre if x["type"] == "gallop" and x.get("sectionals")]
            fast = None
            recent = [x for x in win(21, ("gallop",)) if x.get("sectionals")]
            if recent:
                best = min(recent, key=lambda x: x["sectionals"][-1])
                key = (best["location"], len(best["sectionals"]))
                base = [x["sectionals"][-1] for x in gal_all
                        if (x["location"], len(x["sectionals"])) == key and days(x["date"], r.d) > 21]
                if len(base) >= 5:
                    fast = round(best["sectionals"][-1] - statistics.median(base), 2)
            lastg = [x for x in pre if x["type"] == "gallop"]
            own = hist[r.HorseID]
            feat = {
                "date": r.d, "race": int(r.RaceNo), "brand": r.HorseID,
                "g14": len(win(14, ("gallop",))), "g28": len(g28),
                "jg28": sum(1 for x in g28 if x.get("rider_role") not in ("助手", "未標明", "")),
                "sj28": sum(1 for x in g28 if jock and x.get("rider") == jock),
                "sw14": len(win(14, ("swimming",))), "tr14": len(win(14, ("trotting",))),
                "mach14": len(win(14, ("treadmill", "aqua_walker"))), "trial42": len(win(42, ("trial",))),
                "dlg": min(days(lastg[-1]["date"], r.d), 60) if lastg else 60,
                "fast21": fast,
                "g28_vs_own": round(len(g28) - sum(own) / len(own), 2) if len(own) >= 3 else None,
                "dlr": min(days(last_run[r.HorseID], r.d), 365) if r.HorseID in last_run else None,
                "pre_n": len(pre),
            }
            own.append(len(g28)); last_run[r.HorseID] = r.d
            fo.write(json.dumps(feat, ensure_ascii=False) + "\n"); n += 1
    print("horses", len(tw), "runs", n)


if __name__ == "__main__":
    main()
