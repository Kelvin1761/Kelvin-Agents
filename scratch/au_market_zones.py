#!/usr/bin/env python3
"""Two-opinions / three-zones view for a meeting.

Keeps the model ODDS-BLIND and shows model rank beside market rank, surfacing:
  AGREE     — both like it (confident placer, low bet value)
  OVERLAY   — model likes, market doesn't (your value bet; Savagery Vibe)
  BLINDSPOT — market likes, model doesn't (review; model may be missing it)
  UNION shortlist = model top-2 ∪ market top-3 (keeps overlays AND rescues)

Market-rank source is pluggable:
  - Betfair BSP historical (validated / backtest)         [--source bsp]
  - racenet live day-before fixed-win odds (forward use)  [--source racenet]  (adapter)

Usage:
  python3 scratch/au_market_zones.py --meeting "2026-05-30 Eagle Farm Race 1-9" --race 9 --source bsp
"""
from __future__ import annotations
import argparse, csv, re, sys
from pathlib import Path
sys.path.insert(0, "/Users/imac/Antigravity-repo")
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/au_racing/au_wong_choi_auto/scripts")
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/au_racing")
from wongchoi_paths import AU_RACING
from au_archive_calibrator import load_scoring_rows, normalize_horse_name

MONTHS={m:i for i,m in enumerate(["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"],1)}
BSP_DIR=Path("/Users/imac/Antigravity-repo/scratch/betfair_bsp")

def _nn(n): return re.sub(r"[^a-z0-9]","",re.sub(r"^\s*\d+\.?\s*","",str(n or "")).lower())
def _ci(r,k): return r.get(k) or r.get(k.upper())

# ---------- market-rank sources ----------
def bsp_prices(meeting_date: str) -> dict:
    """{horse_norm: win_price} for a race date, from downloaded Betfair BSP files."""
    mmdd=meeting_date[5:]; out={}
    def hd(h):
        m=re.search(r"\(AUS\)\s*(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3})",h or "")
        return (f"{MONTHS.get(m.group(2)[:3].title()):02d}-{int(m.group(1)):02d}" if m and MONTHS.get(m.group(2)[:3].title()) else None)
    for fp in BSP_DIR.glob("dwbfpricesauswin*.csv"):
        for row in csv.DictReader(open(fp,encoding="utf-8-sig",errors="replace")):
            if hd(_ci(row,"menu_hint") or "")==mmdd:
                b=_ci(row,"bsp")
                try: out[_nn(_ci(row,"selection_name") or "")]=float(b)
                except (TypeError,ValueError): pass
    return out

def racenet_prices(race_url: str) -> dict:
    """{horse_norm: best fixed-win price} for a live/upcoming race overview URL.
    Live day-before market rank source (no auth). Availability depends on when
    bookmakers open fixed-odds for the meeting."""
    from racenet_transport import fetch_nuxt_data
    ap=(fetch_nuxt_data(race_url).get("apollo") or {}).get("defaultClient") or {}
    def res(ref): return ap.get(ref.get("__ref") or ref.get("id"),{}) if isinstance(ref,dict) else {}
    out={}
    for v in ap.values():
        if isinstance(v,dict) and v.get("__typename")=="Selection" and v.get("odds"):
            comp=res(v.get("competitor")); name=_nn(comp.get("name"))
            prices=[float(res(res(o).get("price")).get("value")) for o in v["odds"]
                    if res(o).get("betType")=="fixed-win" and res(res(o).get("price")).get("value")]
            if name and prices: out[name]=min(prices)
    return out

# ---------- zone builder ----------
def build(scoring_rows, market_price: dict):
    rows=[]
    for r in scoring_rows:
        nm=normalize_horse_name(str(r.get("horse_name") or ""))
        rows.append({"num":r["horse_number"],"name":r["horse_name"],
                     "model_rank":int(r["rank"]),"mp":market_price.get(nm)})
    priced=[x for x in rows if x["mp"]]
    for i,x in enumerate(sorted(priced,key=lambda z:z["mp"]),1): x["mkt_rank"]=i
    n=len(rows)
    for x in rows:
        mk=x.get("mkt_rank")
        if mk is None: x["zone"]="(no market)"
        elif x["model_rank"]<=2 and mk<=3: x["zone"]="AGREE"
        elif x["model_rank"]<=2 and mk>4:  x["zone"]="OVERLAY"   # your bet
        elif mk<=2 and x["model_rank"]>=5: x["zone"]="BLINDSPOT" # review
        else: x["zone"]="-"
    return rows

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--meeting",required=True); ap.add_argument("--race",type=int,required=True)
    ap.add_argument("--source",choices=["bsp","racenet"],default="bsp")
    ap.add_argument("--race-url",default=None)
    a=ap.parse_args()
    mdir=AU_RACING/a.meeting
    date=re.match(r"(\d{4}-\d{2}-\d{2})",a.meeting).group(1)
    scoring=[r for r in load_scoring_rows(mdir/"Meeting_Auto_Scoring.csv") if str(r["race_number"])==str(a.race)]
    scoring.sort(key=lambda r:int(r["rank"]))
    mp = bsp_prices(date) if a.source=="bsp" else racenet_prices(a.race_url)
    rows=build(scoring,mp)
    print(f"{a.meeting} R{a.race}  (source={a.source})")
    print(f"{'model':>5} {'mkt':>4} {'zone':<10} horse")
    for x in sorted(rows,key=lambda z:z["model_rank"]):
        if x["model_rank"]<=6 or x["zone"] in ("OVERLAY","BLINDSPOT"):
            print(f"{x['model_rank']:>5} {str(x.get('mkt_rank') or '-'):>4} {x['zone']:<10} {x['name']}")
    m2={x["num"] for x in sorted(rows,key=lambda z:z["model_rank"])[:2]}
    k3={x["num"] for x in sorted([x for x in rows if x.get('mkt_rank')],key=lambda z:z["mkt_rank"])[:3]}
    union=[x for x in rows if x["num"] in (m2|k3)]
    print(f"\nUNION shortlist ({len(union)}): "+", ".join(f"#{x['num']} {x['name']}" for x in sorted(union,key=lambda z:z['model_rank'])))
    bets=[x for x in rows if x["zone"]=="OVERLAY"]
    if bets: print("OVERLAY value flags: "+", ".join(f"#{x['num']} {x['name']}" for x in bets))

if __name__=="__main__":
    raise SystemExit(main())
