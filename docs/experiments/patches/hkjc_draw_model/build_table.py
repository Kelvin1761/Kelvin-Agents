"""EXP-20261115-19：HKJC 檔位模型表（Kelvin 2026-11-15「要一個 proper 嘅檔位分」）。

q(格, 檔號) = 檔位入位率 ÷ 平均入位率（3 / 出賽數），用嘅係「之前季」賽果（季層 as-of；live 用全部歷史）。
格層級（分層收縮，K = 100）：
  L3 = (場地, 跑道欄位 A/A+3/B/B+2/C/C+3/AWT, 路程)
  L2 = (場地, 泥草, 路程組 ≤1200／1201–1650／≥1651)
  L1 = (泥草)
  q_L1 = (Σobs + K·1)/(Σexp + K)；q_L2 = (Σobs + K·q_L1)/(Σexp + K)；q_L3 = (Σobs + K·q_L2)/(Σexp + K)
  （obs = 入頭三數，exp = Σ 3/出賽數；比率形式嘅收縮）
檔號 13+ 合併。跑道欄位由分段頁 meta（賽果庫 Course 欄 2024-09–2026-05 壞咗，已修但用分段頁最穩）。
輸出 {"seasons": {季: {"L3|...|d": q, "L2|...|d": q, "L1|...|d": q}}, "all": {...}}。
用法：python3 build_table.py <out.json>
"""
import gzip
import json
import re
import sys
from collections import defaultdict

sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
K = 100.0


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def dband(dist):
    return "S" if dist <= 1200 else ("M" if dist <= 1650 else "L")


def rails():
    out = {}
    for line in gzip.open("/Volumes/Kelvin Hardisk 1/WongChoi-Archive/hkjc-history/parsed/sectionals.jsonl.gz", "rt", encoding="utf-8"):
        r = json.loads(line)
        c = "AWT" if r.get("surface") == "全天候" else r.get("course")
        if c:
            out[(r["date"], int(r["race_no"]))] = c
    return out


def keys(venue, rail, dist, d):
    surf = "AWT" if rail == "AWT" else "TURF"
    v = "HV" if "跑馬地" in str(venue) else "ST"
    dd = min(int(d), 13)
    return (f"L3|{v}|{rail}|{int(dist)}|{dd}", f"L2|{v}|{surf}|{dband(dist)}|{dd}", f"L1|{surf}|{dd}")


def table(acc):
    out = {}
    l1 = {k: (o + K) / (e + K) for k, (o, e) in acc.items() if k.startswith("L1|")}
    out.update(l1)
    for k, (o, e) in acc.items():
        if k.startswith("L2|"):
            _, v, surf, b, dd = k.split("|")
            prior = l1.get(f"L1|{surf}|{dd}", 1.0)
            out[k] = (o + K * prior) / (e + K)
    for k, (o, e) in acc.items():
        if k.startswith("L3|"):
            _, v, rail, dist, dd = k.split("|")
            surf = "AWT" if rail == "AWT" else "TURF"
            prior = out.get(f"L2|{v}|{surf}|{dband(int(dist))}|{dd}", l1.get(f"L1|{surf}|{dd}", 1.0))
            out[k] = (o + K * prior) / (e + K)
    return {k: round(v, 4) for k, v in out.items()}


def main():
    import hkjc_history_replay_pit as p
    df = p.load_all_rows_extended()
    df = df[df["Rank"].notna() & df["Draw"].notna() & df["Distance"].notna()].copy()
    df["d"] = df["Date"].astype(str).str[:10]
    sr = rails()
    df["rail"] = [sr.get((d, int(n))) for d, n in zip(df["d"], df["RaceNo"])]
    df = df[df["rail"].notna()]
    df["F"] = df.groupby(["d", "RaceNo"])["Rank"].transform("count")
    per = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))
    for r in df.itertuples():
        for k in keys(r.Venue, r.rail, r.Distance, r.Draw):
            a = per[season(r.d)][k]
            a[0] += float(r.Rank <= 3); a[1] += 3.0 / r.F
    seasons = sorted(per)
    out = {"K": K, "seasons": {}, "last_date": str(df["d"].max())}
    for s in seasons + [max(seasons) + 1]:
        acc = defaultdict(lambda: [0.0, 0.0])
        for t in seasons:
            if t < s:
                for k, (o, e) in per[t].items():
                    acc[k][0] += o; acc[k][1] += e
        if acc:
            out["seasons"][str(s)] = table(acc)
    allacc = defaultdict(lambda: [0.0, 0.0])
    for t in seasons:
        for k, (o, e) in per[t].items():
            allacc[k][0] += o; allacc[k][1] += e
    out["all"] = table(allacc)
    json.dump(out, open(sys.argv[1], "w"), ensure_ascii=False)
    a = out["all"]
    for g in ("L2|HV|TURF|S", "L2|ST|TURF|S", "L2|ST|TURF|M", "L2|ST|AWT|S"):
        print(g, " ".join(f"{d}:{a.get(f'{g}|{d}', float('nan')):.2f}" for d in range(1, 14)))


if __name__ == "__main__":
    main()
