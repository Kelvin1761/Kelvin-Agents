import sys
sys.path.insert(0,'.agents/skills/au_racing')
from claw_sportsbet_form import SportsbetFormFetcher, parse_race, parse_runner_blocks, write_meeting
RACES=[(1,"3393728"),(2,"3393729"),(3,"3393733"),(4,"3393734"),(5,"3393735"),
       (6,"3394294"),(7,"3393737"),(8,"3394295"),(9,"3393739")]
f=SportsbetFormFetcher(delay=12, verbose=True)
out=[]
for rno, rid in RACES:
    h=f.get(f"https://www.sportsbetform.com.au/446234/{rid}/")
    if not h:
        print(f"   ❌ R{rno} 攞唔到"); continue
    p=parse_race(h); b=parse_runner_blocks(h)
    out.append((rno,p,b))
    print(f"   R{rno}: {len(p['overview'])} 匹, {sum(len(x['runs']) for x in b)} 場往績")
if out:
    write_meeting(out, "scratch/sb_full_meeting", "2026-08-01", "Flemington")
print(f"完成 {len(out)}/9 場")
