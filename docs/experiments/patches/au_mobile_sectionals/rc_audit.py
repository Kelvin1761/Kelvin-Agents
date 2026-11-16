"""EXP-20261116-19：RacecardWithContext 欄位洩漏審計（只量，唔開臂）。

用法：python3 -I rc_audit.py <rc json 目錄> <events.json> <allr_2026-11-17.json>

1. 舊賽事（賽後先抓）：`recentStartsThoroughbreds` 有冇包今仗日期；`total` 出賽次數同我哋
   賽前 Racecard `Career: N` 比（RC = 我哋 + 1 即係賽後更新咗）。
2. `expectedSettlingPosition` 類別 vs 我哋 Facts 嘅 `official_settle`（Speedmap 定位序）。
3. 賽前快照（11-17）各欄覆蓋率，留俾賽後再抓比較。
"""
import collections, json, re, sys
from pathlib import Path

rcdir, evs = Path(sys.argv[1]), json.load(open(sys.argv[2]))
by_id = {str(e["id"]): e for e in evs}


def sels(d):
    for m in d.get("racecardEvent", {}).get("markets", []):
        if m.get("selections"):
            for s in m["selections"]:
                yield s
            return


def norm(n):
    return re.sub(r"[^a-z]", "", (n or "").lower())


def our_career(folder, race):
    out = {}
    for f in Path(folder).glob(f"* Race {race} Racecard.md"):
        cur = None
        for line in f.read_text(errors="ignore").splitlines():
            m = re.match(r"^\d+\.\s+(.+?)\s+\(\d+\)\s*$", line)
            if m:
                cur = norm(m.group(1))
            m = re.match(r"^Career:\s*(\d+)\s*:", line)
            if m and cur:
                out[cur] = int(m.group(1))
    return out


def our_settle(folder, race):
    for f in Path(folder).glob(f"* Race {race} Facts.md"):
        m = re.search(r"official_settle:\*\*\s*\[([^\]]*)\]", f.read_text(errors="ignore"))
        if m and m.group(1).strip():
            return {int(a): int(b) for a, b in (p.split(":") for p in m.group(1).split(","))}
    return {}


C = collections.Counter()
cat_vs_rank = collections.defaultdict(list)
pre_cov = collections.Counter()
for f in sorted(rcdir.glob("rc_*.json")):
    eid = f.stem[3:]
    d = json.loads(f.read_text())
    e = by_id.get(eid)
    if e is None:  # 11-17 賽前快照
        for s in sels(d):
            st = s.get("statistics") or {}
            pre_cov["runners"] += 1
            for k in ("speed", "dryRating", "wetRating", "horseJockey", "expectedSettlingPosition", "winPercentage"):
                if st.get(k) not in (None, "", "0:0,0,0"):
                    pre_cov[k] += 1
        continue
    day = e["day"]
    dd = f"{day[8:10]}/{day[5:7]}/{day[:4]}"
    career = our_career(e["folder"], e["race"])
    settle = our_settle(e["folder"], e["race"])
    for s in sels(d):
        st = s.get("statistics") or {}
        C["past_runners"] += 1
        rs = st.get("recentStartsThoroughbreds") or []
        if any(r.get("date") == dd for r in rs):
            C["recent_starts_include_race_day"] += 1
        tot = st.get("total")
        ours = career.get(norm(s.get("name")))
        if tot and ours is not None:
            n = int(tot.split(":")[0])
            C["career_compared"] += 1
            C[f"rc_minus_ours_{n - ours:+d}"] += 1
        num = s.get("runnerNumber")
        cat = st.get("expectedSettlingPosition")
        if cat and num in settle:
            cat_vs_rank[cat].append(settle[num])

print(json.dumps({
    "past": C,
    "settle_category_vs_speedmap_rank": {k: {"n": len(v), "mean_rank": round(sum(v) / len(v), 2),
                                             "ranks": sorted(v)} for k, v in cat_vs_rank.items()},
    "pre_race_1117_coverage": pre_cov,
}, ensure_ascii=False, indent=1))
