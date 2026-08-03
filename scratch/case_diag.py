"""逐匹拆解：邊個維度／leaf 拉高拉低咗隻馬。唯讀。

用法: python3 scratch/case_diag.py "<meeting substring>" <race_no> "<horse name>" [對照馬名...]
"""
import json, sys
from pathlib import Path
S=Path('.agents/skills/au_racing/au_wong_choi_auto/scripts')
sys.path.insert(0,str(S)); sys.path.insert(0,str(S/'racing_engine'))
from au_archive_calibrator import ARCHIVE_ROOT, get_true_horse_name, parse_int
from scoring import MATRIX_WEIGHTS
from matrix_mapper import MATRIX_FORMULAS

sub, rno = sys.argv[1], int(sys.argv[2])
focus = sys.argv[3:]
md = next(p for p in sorted(ARCHIVE_ROOT.iterdir()) if p.is_dir() and sub in p.name)
d = json.loads((md/f"Race_{rno}_Logic.json").read_text(encoding="utf-8"))
rows=[]
for hn,h in (d.get("horses") or {}).items():
    if not isinstance(h,dict): continue
    pa=h.get("python_auto") or {}
    if pa.get("ability_score") is None: continue
    rows.append({"n":parse_int(hn) or 999,"name":get_true_horse_name(h),
                 "ability":float(pa["ability_score"]),"mx":pa.get("matrix_scores") or {},
                 "fs":pa.get("feature_scores") or {},"wet":float(pa.get("wet_form_feature") or 0)})
rows.sort(key=lambda r:-r["ability"])
print(f"{md.name}  R{rno}   ({len(rows)} 匹)\n")
dims=[k for k in MATRIX_WEIGHTS if MATRIX_WEIGHTS[k]>0]
print(f"{'排':>3} {'#':<4}{'馬名':<24}{'綜合':>7}" + "".join(f"{k[:9]:>10}" for k in dims) + f"{'濕地':>7}")
for i,r in enumerate(rows,1):
    mark = " ★" if r["name"] in focus else ""
    print(f"{i:>3} #{r['n']:<3}{r['name']:<24}{r['ability']:>7.2f}"
          + "".join(f"{r['mx'].get(k,60):>10.1f}" for k in dims) + f"{r['wet']:>7.2f}{mark}")

print(f"\n{'—'*100}\n維度貢獻（weight ×(分−60)，即係佢實際幫咗／拖咗幾多綜合分）")
print(f"{'#':<4}{'馬名':<24}" + "".join(f"{k[:9]:>10}" for k in dims))
for r in rows:
    if focus and r["name"] not in focus and rows.index(r)>=3: continue
    print(f"#{r['n']:<3}{r['name']:<24}"
          + "".join(f"{MATRIX_WEIGHTS[k]*(r['mx'].get(k,60)-60):>+10.2f}" for k in dims))

if focus:
    leaves=sorted({l for c in MATRIX_FORMULAS.values() for l,_ in c})
    print(f"\n{'—'*100}\nLeaf 分（★ 對比全場中位數）")
    import statistics
    print(f"{'leaf':26}" + "".join(f"{r['name'][:11]:>13}" for r in rows if r['name'] in focus) + f"{'全場中位':>10}")
    for lf in leaves:
        vals=[r["fs"].get(lf,60) for r in rows]
        print(f"{lf:26}" + "".join(f"{r['fs'].get(lf,60):>13.1f}" for r in rows if r['name'] in focus)
              + f"{statistics.median(vals):>10.1f}")
