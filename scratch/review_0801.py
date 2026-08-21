"""2026-08-01 兩個場次賽後檢討：模型排名 vs 實際賽果。唯讀。"""
import json, sys
from pathlib import Path
S=Path('.agents/skills/au_racing/au_wong_choi_auto/scripts')
sys.path.insert(0,str(S)); sys.path.insert(0,str(S))
sys.path.insert(0,'.agents/skills/shared_racing')
from au_archive_calibrator import ARCHIVE_ROOT, get_true_horse_name, parse_int
from eval_metrics import race_metrics, summarize_races, EXCLUSIVE_LABELS

FIX={("rosehill",3):[4,3,7]}   # PDF 分頁令 R3 第三名缺失，由頁頂摘要行補（#7 Debello）
tot=[]
for tag,dirpat in (("rosehill","2026-08-01 Rosehill"),("flemington","2026-08-01 Flemington")):
    res=json.loads(Path(f"scratch/results_{tag}.json").read_text())
    md=next(p for p in ARCHIVE_ROOT.iterdir() if p.is_dir() and p.name.startswith(dirpat))
    print(f"\n{'='*74}\n{md.name}\n{'='*74}")
    rows_out=[]
    for lp in sorted(md.glob("Race_*_Logic.json"), key=lambda p: parse_int(p.stem.split('_')[1],999)):
        rno=parse_int(lp.stem.split('_')[1])
        r=res.get(str(rno))
        if not r: continue
        t3 = FIX.get((tag,rno)) or [x["n"] for x in r["rows"][:3]]
        win = r["rows"][0]["n"] if r["rows"] and r["rows"][0]["pos"]==1 else t3[0]
        d=json.loads(lp.read_text(encoding="utf-8"))
        picks=[]
        for hn,h in (d.get("horses") or {}).items():
            if not isinstance(h,dict): continue
            pa=h.get("python_auto") or {}
            if pa.get("ability_score") is None: continue
            picks.append((float(pa["ability_score"]), parse_int(hn) or 999, get_true_horse_name(h)))
        picks.sort(key=lambda t:(-t[0],t[1]))
        order=[n for _,n,_ in picks]
        m=race_metrics(order, t3, winner=win, field_size=len(order))
        rows_out.append(m); tot.append(m)
        nm={n:x for _,n,x in picks}
        hit=lambda n: "✅" if n in t3 else "  "
        print(f"  R{rno:<3}{m['exclusive_label']:<6} 我哋: "
              + " | ".join(f"{hit(n)}#{n} {nm.get(n,'')[:14]}" for n in order[:3])
              + f"    實際前三 {t3}" + ("  🏆首選中頭馬" if order and order[0]==win else ""))
    s=summarize_races(rows_out)
    print(f"  → {len(rows_out)} 場：" + "  ".join(f"{k} {s['exclusive_labels'][k]}" for k in EXCLUSIVE_LABELS)
          + f"   首選=頭馬 {100*s['rates']['champion']:.0f}%   頭馬入前三 {100*s['rates']['winner_in_top3']:.0f}%")
s=summarize_races(tot)
print(f"\n{'='*74}\n兩場合計 {len(tot)} 場")
for k in EXCLUSIVE_LABELS: print(f"   {k:8}{s['exclusive_labels'][k]:>3} 場  {100*s['exclusive_labels'][k]/len(tot):>5.1f}%")
print(f"   {'至少一隻上名馬入前三':22}{100*s['rates']['pass_any1']:>5.1f}%")
print(f"   {'首選 = 頭馬':22}{100*s['rates']['champion']:>5.1f}%")
print(f"   {'頭馬入我哋前三':22}{100*s['rates']['winner_in_top3']:>5.1f}%")
print(f"   {'前三精準度':22}{100*s['top3_precision']:>5.1f}%")
