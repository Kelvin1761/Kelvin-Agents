#!/usr/bin/env python3
"""EXP-20261105-06 診斷 D1–D3（只解釋）。  diag.py BASE_old.json C2_old.json OUT.json"""
import json, re, sys
from collections import defaultdict
from pathlib import Path
W = Path(__file__).resolve().parents[1]
S = W / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path[:0] = [str(S)]
import au_dump_engine_leaves as dl  # noqa
from au_racing_engine.engine_core import refresh_form_quality  # noqa
from au_racing_engine import stability as st  # noqa

def gstate(g):
    m = re.search(r"(Soft|Heavy)\s*([0-9]+)", str(g or ""), re.I)
    if not m: return "good/other"
    return "heavy" if m.group(1).lower() == "heavy" else ("soft7+" if int(m.group(2)) >= 7 else "soft5-6")

def top2(r): return [x["n"] for x in sorted(r["rows"], key=lambda x: (-x["ability"], x["n"]))[:2]]

base = json.loads(Path(sys.argv[1]).read_text())["races"]
c2 = json.loads(Path(sys.argv[2]).read_text())["races"]
assert [(r["meeting"], r["race"]) for r in base] == [(r["meeting"], r["race"]) for r in c2]
out = {}
# D1
d1 = defaultdict(lambda: {"races": 0, "changed": 0, "in": [0, 0], "out": [0, 0], "good_b": 0, "good_c": 0})
for b, c in zip(base, c2):
    k = gstate(b["rows"][0].get("going")); e = d1[k]; e["races"] += 1
    tb, tc = top2(b), top2(c); pos = {x["n"]: x["pos"] for x in b["rows"]}
    e["good_b"] += all(pos[n] <= 3 for n in tb); e["good_c"] += all(pos[n] <= 3 for n in tc)
    if set(tb) != set(tc):
        e["changed"] += 1
        for n in set(tc) - set(tb): e["in"][0] += 1; e["in"][1] += pos[n] <= 3
        for n in set(tb) - set(tc): e["out"][0] += 1; e["out"][1] += pos[n] <= 3
out["D1"] = d1
for k, e in d1.items():
    print(f"D1 {k:11s} races {e['races']:5d} top2變 {e['changed']:4d} 換入入三 {e['in'][1]}/{e['in'][0]} 換出入三 {e['out'][1]}/{e['out'][0]} Good {e['good_b']}→{e['good_c']}")

# D2/D3：重砌往績（C2 公式），逐匹計打折嚟自濕地往績嘅比例
from au_archive_calibrator import ARCHIVE_ROOT  # noqa
dirs = {p.name: p for p in dl._corpus_meeting_dirs(ARCHIVE_ROOT)}
d2 = defaultdict(lambda: {"horses": 0, "disc": 0.0, "disc_wet": 0.0, "wet_runs": 0, "runs": 0})
d3 = defaultdict(lambda: defaultdict(lambda: [0, 0]))
for b, c in zip(base, c2):
    k = gstate(b["rows"][0].get("going"))
    md = dirs.get(b["meeting"])
    lp = md / f"Race_{b['race']}_Logic.json" if md else None
    if not lp or not lp.exists():
        continue
    import math
    from au_racing_engine import data_prep as dp
    fg = dp._formguide_path_for_facts(md / f"{b['date'][5:]} Race {b['race']} Facts.md", int(b["race"]))
    byname = {}
    if fg and fg.exists():
        text = fg.read_text(encoding="utf-8")
        heads = list(re.finditer(r"^\[(\d+)\]\s+(.+?) \((\d+)\)\s*$", text, re.M))
        for i, h in enumerate(heads):
            sec = text[h.start(): heads[i + 1].start() if i + 1 < len(heads) else len(text)]
            ents = [e for e in dp._parse_formguide_entries(sec, h.group(2).strip())
                    if str(e.get("date") or "") < b["date"] and not e["is_trial"]]
            byname[h.group(1)] = dp._performance_quality_digest(ents, meeting_date=b["date"], max_runs=6).get("runs", [])
    cmap = {x["n"]: x for x in c["rows"]}
    for x in b["rows"]:
        runs = byname.get(str(x["n"])) or []
        e = d2[k]
        if len(runs) >= 2: e["horses"] += 1
        for r, w in zip(runs, st.RECENCY_WEIGHTS):
            fin, n = int(r.get("finish_pos") or 0), int(r.get("starters") or 0)
            if not (n >= 2 and 1 <= fin <= n):
                continue
            pct = (fin - 1) / (n - 1); zr = (math.log10(r["prize"]) - st.MU_LOG_PRIZE) / st.SD_LOG_PRIZE
            lost = zr * pct * w / 2 if zr > 0 else 0.0
            wet = st.is_heavy_going(r.get("going"))
            e["runs"] += 1; e["wet_runs"] += wet; e["disc"] += lost; e["disc_wet"] += lost * wet
        dfq = cmap[x["n"]]["features"]["form_quality_score"] - x["features"]["form_quality_score"]
        bucket = "drop>10" if dfq < -10 else "drop5-10" if dfq < -5 else "flat" if dfq <= 5 else "rise>5"
        d3[k][bucket][0] += 1; d3[k][bucket][1] += x["pos"] <= 3
out["D2"] = d2; out["D3"] = d3
for k, e in d2.items():
    print(f"D2 {k:11s} horses {e['horses']:6d} Heavy往績比例 {e['wet_runs']/max(1,e['runs']):.3f} 打折量嚟自Heavy往績 {e['disc_wet']/max(1e-9,e['disc']):.3f}")
for k, bk in d3.items():
    print(f"D3 {k:11s} " + "  ".join(f"{bb} {v[1]}/{v[0]}={v[1]/max(1,v[0]):.3f}" for bb, v in sorted(bk.items())))
Path(sys.argv[3]).write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: dict(o)))
