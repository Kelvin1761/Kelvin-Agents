"""Eligibility parity: which runners get overseas rows from PDF vs from the fsc fallback."""
import json, re, sys, collections
from pathlib import Path
WT = Path(sys.argv[1]); out = Path(sys.argv[2]); meetings = sys.argv[3:]
sys.path.insert(0, str(WT / '.agents/scripts'))
import hkjc_overseas_formsheet as fsc
sys.path.insert(0, str(WT))
from wongchoi_paths import HK_RACING as HK  # noqa: E402
rows = []
summary = collections.Counter()
for m in meetings:
    md = HK / m
    pdfs = sorted(md.glob('*全日出賽馬匹資料 (PDF).md'))
    if not pdfs: continue
    text = pdfs[0].read_text(encoding='utf-8')
    mk = re.search(r'Overseas\s+Form\s+of', text)
    listed = {fsc.normalise_brand(b) for b in re.findall(r'\([A-Z]{2,3}\)\s+([A-Z]\d+)\b.*?\b\d+\s+starts?\b', text[mk.start():])} if mk else set()
    runners = set()
    for rc in md.glob('*排位表.md'):
        runners |= {fsc.normalise_brand(b) for b in re.findall(r'烙號:\s*([A-Za-z0-9_]+)', rc.read_text(encoding='utf-8'))}
    runners.discard('')
    for b in sorted(runners):
        rule = fsc.listed_in_starter_pdf(b, m[:10])
        in_pdf = b in listed
        if in_pdf and rule:
            summary['listed_and_rule'] += 1; continue
        if not rule and not in_pdf:
            summary['old_season_not_listed'] += 1; continue
        f_rows, st = fsc.fallback_overseas_rows(b, m[:10])
        key = 'rule_but_not_listed' if rule else 'listed_but_rule_says_no'
        if key == 'rule_but_not_listed' and not f_rows:
            summary['rule_but_not_listed_fsc_empty(' + st + ')'] += 1; continue
        summary[key] += 1
        rows.append({'meeting': m, 'brand': b, 'case': key, 'status': st, 'fsc_rows': len(f_rows)})
    summary['meetings'] += 1
out.write_text(json.dumps({'summary': summary, 'rows': rows}, ensure_ascii=False, indent=1))
print(dict(summary)); print(rows[:20])
