"""2026-08-01 兩個場次：舊排名 vs 重跑後排名。唯讀。"""
import json, sys
from pathlib import Path
S=Path('.agents/skills/au_racing/au_wong_choi_auto/scripts')
sys.path.insert(0,str(S)); sys.path.insert(0,str(S))
from au_archive_calibrator import ARCHIVE_ROOT, get_true_horse_name, parse_int

old=json.loads(Path('scratch/old_picks_0801.json').read_text())
FOCUS={"Horizons","Laurel Hill"}
for md in sorted(p for p in ARCHIVE_ROOT.iterdir() if p.is_dir() and p.name.startswith("2026-08-01")):
    print(f"\n{'='*72}\n{md.name}\n{'='*72}")
    for lp in sorted(md.glob("Race_*_Logic.json"), key=lambda p: parse_int(p.stem.split('_')[1],999)):
        d=json.loads(lp.read_text(encoding="utf-8"))
        rows=[]
        for hn,h in (d.get("horses") or {}).items():
            if not isinstance(h,dict): continue
            pa=h.get("python_auto") or {}
            if pa.get("ability_score") is None: continue
            rows.append((float(pa["ability_score"]), parse_int(hn) or 999, get_true_horse_name(h)))
        rows.sort(key=lambda t:(-t[0],t[1]))
        new=[{"n":n,"name":nm,"ability":a} for a,n,nm in rows]
        key=f"{md.name}|{lp.stem}"
        o=old.get(key,[])
        orank={r["name"]:i+1 for i,r in enumerate(o)}
        rno=parse_int(lp.stem.split('_')[1])
        changed = [r["name"] for r in new[:4]] != [r["name"] for r in o[:4]]
        print(f"\n── R{rno}{'  ⟨前四有變⟩' if changed else '  (前四不變)'}")
        print(f"   {'新':>3} {'舊':>4}  {'#':<4}{'馬名':<26}{'綜合分':>8}{'Δ排名':>8}")
        for i,r in enumerate(new[:6],1):
            ob=orank.get(r["name"])
            mv = f"{ob-i:+d}" if ob else "新"
            star = " ★" if r["name"] in FOCUS else ""
            print(f"   {i:>3} {ob if ob else '-':>4}  #{r['n']:<3}{r['name']:<26}{r['ability']:>8.2f}{mv:>8}{star}")
        for r in new:
            if r["name"] in FOCUS and new.index(r)>=6:
                ob=orank.get(r["name"])
                print(f"   {new.index(r)+1:>3} {ob if ob else '-':>4}  #{r['n']:<3}{r['name']:<26}"
                      f"{r['ability']:>8.2f}{(f'{ob-(new.index(r)+1):+d}' if ob else '新'):>8} ★")
