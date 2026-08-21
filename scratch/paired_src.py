"""同一個練馬師／騎師，用 profile 生涯 vs 去年官方 各計一次分，睇差幾多。

呢個係決定性測試：如果配對差 ≈ 0，5.5 分嘅差距就係真實族群差異（大馬房本身
就係好啲），leaf 冇問題；如果配對差好大，就係「有冇入到我哋 cache」呢件事
漏咗入個分度，而我啱啱 fit 嘅權重就係喺度加權緊 cache 成員身份。唯讀。
"""
import json, sys, statistics
from pathlib import Path
S=Path('.agents/skills/au_racing/au_wong_choi_auto/scripts')
sys.path.insert(0,str(S)); sys.path.insert(0,str(S))
sys.path.insert(0,'.agents/skills/au_racing')
import au_profile_stats as ps
from au_archive_calibrator import ARCHIVE_ROOT, parse_int
from au_racing_engine.engine_core import RacingEngine
from au_racing_engine.scoring import clip_score

cache = ps.load_cache() or {}
K = RacingEngine._PLACE_RATE_K
SPREAD = RacingEngine._PLACE_RATE_SPREAD
PRIOR = RacingEngine._PLACE_RATE_PRIOR
MINR = RacingEngine._PLACE_RATE_MIN_RUNS

def score(places, runs, prior):
    return clip_score(60.0 + ((places + K*prior)/(runs + K) - prior) * SPREAD)

pairs = {"jockey": [], "trainer": []}
seen = set()
for md in sorted(p for p in ARCHIVE_ROOT.iterdir() if p.is_dir()):
    for lp in sorted(md.glob("Race_*_Logic.json")):
        try: logic=json.loads(lp.read_text(encoding="utf-8"))
        except Exception: continue
        for h in (logic.get("horses") or {}).values():
            if not isinstance(h,dict): continue
            data = h.get("_data") or {}
            for kind in ("jockey","trainer"):
                name=(h.get(kind) or "").strip()
                if not name: continue
                st = ps.lookup(cache, kind, name)
                ly = data.get(f"{kind}_ly") or {}
                lr = ly.get("rides"); lp_ = ly.get("places")
                if not st or lr is None: continue
                runs=float(st.get("totalRuns") or 0); pct=st.get("placePercentage")
                if not runs or runs < MINR or pct is None: continue
                try: lr=float(lr); lp_=float(lp_ or 0)
                except (TypeError,ValueError): continue
                if lr < MINR: continue
                key=(kind,name)
                if key in seen: continue
                seen.add(key)
                pairs[kind].append((name,
                                    score(pct/100.0*runs, runs, PRIOR[kind]),
                                    score(lp_, lr, PRIOR[kind]), runs, lr))

for kind in ("jockey","trainer"):
    d=[(a-b) for _,a,b,_,_ in pairs[kind]]
    if not d: print(f"{kind}: 冇配對樣本"); continue
    print(f"\n===== {kind}：{len(d)} 個人同時有兩種數據 =====")
    print(f"  profile 生涯分 平均 {statistics.mean(a for _,a,_,_,_ in pairs[kind]):.2f}")
    print(f"  去年官方分     平均 {statistics.mean(b for _,_,b,_,_ in pairs[kind]):.2f}")
    print(f"  **配對差（生涯 − 去年）平均 {statistics.mean(d):+.2f}，中位 {statistics.median(d):+.2f}，"
          f"SD {statistics.pstdev(d):.2f}**")
    big=[(n,a,b) for n,a,b,_,_ in pairs[kind] if abs(a-b)>=10]
    print(f"  差 10 分以上：{len(big)}/{len(d)} ({100*len(big)/len(d):.0f}%)")
    for n,a,b in sorted(big,key=lambda t:-abs(t[1]-t[2]))[:6]:
        print(f"     {n:32} 生涯 {a:5.1f}  去年 {b:5.1f}  ({a-b:+.1f})")
