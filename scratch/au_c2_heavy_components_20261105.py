#!/usr/bin/env python3
"""EXP-20261105-06 跟進診斷：按今場場地，近績質素各組件（場內）預測入前三嘅 AUC。只解釋，唔揀參數。
    comp.py DUMP.json OUT.json
"""
import json, math, random, re, sys
from collections import defaultdict
from pathlib import Path
W = Path(__file__).resolve().parents[1]
S = W / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path[:0] = [str(S)]
import au_dump_engine_leaves as dl  # noqa
from au_archive_calibrator import ARCHIVE_ROOT  # noqa
from au_racing_engine import data_prep as dp, stability as st  # noqa

def gstate(g):
    m = re.search(r"(Soft|Heavy)\s*([0-9]+)", str(g or ""), re.I)
    if not m: return "good/other"
    return "heavy" if m.group(1).lower() == "heavy" else ("soft7+" if int(m.group(2)) >= 7 else "soft5-6")

def feats(runs, today_heavy):
    vals = []
    for r in runs:
        fin, n = int(r.get("finish_pos") or 0), int(r.get("starters") or 0)
        if not (n >= 2 and 1 <= fin <= n): continue
        pct = (fin - 1) / (n - 1); zp = (0.5 - pct) / st.SD_PCT
        zr = (math.log10(r["prize"]) - st.MU_LOG_PRIZE) / st.SD_LOG_PRIZE
        vals.append(dict(zp=zp, zr=zr, zc2=zr * (1 - pct) if zr > 0 else zr, hv=st.is_heavy_going(r.get("going")),
                         soft=bool(re.search(r"\bSoft\b", str(r.get("going") or ""), re.I))))
    if len(vals) < 2: return None
    w = st.RECENCY_WEIGHTS[:len(vals)]; sw = sum(w)
    avg = lambda f: sum(f(v) * x for v, x in zip(vals, w)) / sw  # noqa
    out = {"place": avg(lambda v: v["zp"]), "prize": avg(lambda v: v["zr"]),
           "old": avg(lambda v: (v["zp"] + v["zr"]) / 2), "c2": avg(lambda v: (v["zp"] + v["zc2"]) / 2),
           "prize_max": max(v["zr"] for v in vals)}
    wet = [(v, x) for v, x in zip(vals, w) if v["hv"] or v["soft"]]
    dry = [(v, x) for v, x in zip(vals, w) if not (v["hv"] or v["soft"])]
    out["place_wet"] = sum(v["zp"] * x for v, x in wet) / sum(x for _, x in wet) if wet else None
    out["place_dry"] = sum(v["zp"] * x for v, x in dry) / sum(x for _, x in dry) if dry else None
    return out

races = json.loads(Path(sys.argv[1]).read_text())["races"]
dirs = {p.name: p for p in dl._corpus_meeting_dirs(ARCHIVE_ROOT)}
KEYS = ("place", "prize", "prize_max", "old", "c2", "place_wet", "place_dry")
# pairs[state][key] = list of (date, wins, total) per race
per = defaultdict(lambda: defaultdict(list))
for rc in races:
    k = gstate(rc["rows"][0].get("going")); md = dirs.get(rc["meeting"])
    if not md: continue
    fg = dp._formguide_path_for_facts(md / f"{rc['date'][5:]} Race {rc['race']} Facts.md", int(rc["race"]))
    if not fg or not fg.exists(): continue
    text = fg.read_text(encoding="utf-8")
    heads = list(re.finditer(r"^\[(\d+)\]\s+(.+?) \((\d+)\)\s*$", text, re.M))
    fmap = {}
    for i, h in enumerate(heads):
        sec = text[h.start(): heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        ents = [e for e in dp._parse_formguide_entries(sec, h.group(2).strip())
                if str(e.get("date") or "") < rc["date"] and not e["is_trial"]]
        fmap[h.group(1)] = feats(dp._performance_quality_digest(ents, meeting_date=rc["date"], max_runs=6).get("runs", []), k == "heavy")
    for key in KEYS:
        pos = [(fmap.get(str(x["n"])) or {}).get(key) for x in rc["rows"]]
        lab = [x["pos"] <= 3 for x in rc["rows"]]
        P = [p for p, l in zip(pos, lab) if l and p is not None]; N = [p for p, l in zip(pos, lab) if not l and p is not None]
        if not P or not N: continue
        win = sum((p > n) + 0.5 * (p == n) for p in P for n in N)
        per[k][key].append((rc["date"], win, len(P) * len(N)))
res = {}
for k, kk in per.items():
    for key, lst in kk.items():
        days = sorted({d for d, _, _ in lst}); byd = defaultdict(list)
        for d, a, b in lst: byd[d].append((a, b))
        rng = random.Random(7); samp = []
        for _ in range(1000):
            pick = [byd[days[rng.randrange(len(days))]] for _ in days]
            a = sum(x for p in pick for x, _ in p); b = sum(y for p in pick for _, y in p); samp.append(a / b)
        samp.sort(); auc = sum(a for _, a, _ in lst) / sum(b for _, _, b in lst)
        res[f"{k}:{key}"] = {"races": len(lst), "auc": round(auc, 4), "ci": [round(samp[25], 4), round(samp[974], 4)]}
for k in ("good/other", "soft5-6", "soft7+", "heavy"):
    print(k, "  ".join(f"{key} {res[f'{k}:{key}']['auc']:.3f}[{res[f'{k}:{key}']['ci'][0]:.3f},{res[f'{k}:{key}']['ci'][1]:.3f}] n{res[f'{k}:{key}']['races']}"
                         for key in KEYS if f"{k}:{key}" in res))
Path(sys.argv[2]).write_text(json.dumps(res, indent=1))
