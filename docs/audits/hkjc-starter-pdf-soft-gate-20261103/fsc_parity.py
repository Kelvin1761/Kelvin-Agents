"""Corpus parity: starter-PDF overseas rows vs fsc fallback rows, field by field."""
import importlib.util, json, re, sys, collections
from pathlib import Path
WT = Path(sys.argv[1]); out = Path(sys.argv[2]); meetings = sys.argv[3:]
sys.path.insert(0, str(WT / '.agents/scripts'))
import hkjc_overseas_formsheet as fsc
spec = importlib.util.spec_from_file_location('facts', WT / '.agents/scripts/inject_hkjc_fact_anchors.py')
facts = importlib.util.module_from_spec(spec); spec.loader.exec_module(facts)
sys.path.insert(0, str(WT))
from wongchoi_paths import HK_RACING as HK  # noqa: E402
SCORE_FIELDS = ['Date','Distance','Surface','Placing','Field_Size','Weight','Finish_Time_Raw','Margin','Going','Direction','Region','Grade']
def grade(rt):
    u=str(rt or '').upper(); return next((g for g in ('G1','G2','G3') if g in u or g[1]+'級' in u), '')
results = []
pairs = collections.defaultdict(collections.Counter)
for mname in meetings:
    md = HK / mname
    pdfs = sorted(md.glob('*全日出賽馬匹資料 (PDF).md'))
    if not pdfs: continue
    pdf = pdfs[0]; text = pdf.read_text(encoding='utf-8')
    race_date = mname[:10]
    mk = re.search(r'Overseas\s+Form\s+of', text)
    if not mk: continue
    brands = re.findall(r'\([A-Z]{2,3}\)\s+([A-Z]\d+)\b.*?\b\d+\s+starts?\b', text[mk.start():])
    for b in dict.fromkeys(brands):
        s_rows = facts.parse_pdf_overseas_races(pdf, b, '')
        f_rows, st = fsc.fallback_overseas_rows(b, race_date)
        rec = {'meeting': mname, 'brand': b, 'status': st, 'n_pdf': len(s_rows), 'n_fsc': len(f_rows), 'diffs': []}
        for i in range(max(len(s_rows), len(f_rows))):
            s = s_rows[i] if i < len(s_rows) else {}
            f = f_rows[i] if i < len(f_rows) else {}
            for k in SCORE_FIELDS:
                sv = grade(s.get('Race_Type')) if k=='Grade' else s.get(k)
                fv = grade(f.get('Race_Type')) if k=='Grade' else f.get(k)
                if sv != fv:
                    rec['diffs'].append({'i': i, 'field': k, 'pdf': sv, 'fsc': fv,
                                         'pdf_raw': s.get('Raw_Line'), 'fsc_raw': f.get('Raw_Line')})
            if s and f:
                for k in ('Racecourse','Race_Type','Gear'):
                    pairs[k][(f.get(k), s.get(k))] += 1
        results.append(rec)
out.write_text(json.dumps({'results': results, 'pairs': {k: [[a,b,c] for (a,b),c in v.most_common()] for k,v in pairs.items()}}, ensure_ascii=False, indent=1))
n = len(results); clean = sum(1 for r in results if not r['diffs'])
rows = sum(r['n_pdf'] for r in results)
print(f'horses={n} clean={clean} pdf_rows={rows} fsc_rows={sum(r["n_fsc"] for r in results)}')
c = collections.Counter(d['field'] for r in results for d in r['diffs']); print(c)
print(collections.Counter(r['status'] for r in results))
