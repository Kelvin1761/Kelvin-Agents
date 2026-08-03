"""比較兩份 dump（真引擎 ability 排名）。dev 85% / 未碰過 holdout 15%。唯讀。"""
import json, sys
from pathlib import Path
sys.path.insert(0,'.agents/skills/shared_racing')
from eval_metrics import race_metrics, summarize_races
KEYS=("gold","good_pos","any2","pass1","champ","winT3","t3prec","mrr","blowout","compet","ndcg5")
def digest(s):
    r,c=s["rates"],s["competitiveness"]
    return {"gold":100*r["gold"],"good_pos":100*r["good_positional"],"any2":100*r["good_any2"],
            "pass1":100*r["pass_any1"],"champ":100*r["champion"],"winT3":100*r["winner_in_top3"],
            "t3prec":100*s["top3_precision"],"mrr":100*s["mrr"],
            "blowout":100*c["top_pick_blowout"]["rate"],"compet":100*c["top_pick_competitive"]["rate"],
            "ndcg5":100*c["mean_ndcg_at5"]}
def ev(races, lo, hi):
    out=[]
    for rc in races[lo:hi]:
        pos={h["n"]:h["pos"] for h in rc["rows"]}
        picks=[h["n"] for h in sorted(rc["rows"], key=lambda h:(-h["ability"], h["n"]))]
        t3=[n for n,p in pos.items() if p<=3]; w=[n for n,p in pos.items() if p==1]
        out.append(race_metrics(picks,t3,winner=w[0] if w else None,actual_pos=pos,field_size=rc["field"]))
    return digest(summarize_races(out))
base=json.loads(Path(sys.argv[1]).read_text())["races"]
for f in sys.argv[2:]:
    cand=json.loads(Path(f).read_text())["races"]
    n=len(base); split=int(n*0.85)
    print(f"\n########## {Path(f).stem} ##########")
    for name,(lo,hi) in (("dev",(0,split)),("holdout 未碰過",(split,n))):
        b,c=ev(base,lo,hi),ev(cand,lo,hi)
        print(f"  {name} ({hi-lo} 場)")
        print(f"    {'':8}"+"".join(f"{k:>11}" for k in KEYS))
        print(f"    {'delta':8}"+"".join(f"{c[k]-b[k]:>+11.2f}" for k in KEYS))
