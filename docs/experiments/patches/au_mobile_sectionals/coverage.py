"""EXP-20261116-17 覆蓋率：python3 -I coverage.py <raw/mob 目錄> <events.json> <out.json>"""
import collections, html, json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import parse_mobile as pm

mob, evs, out = Path(sys.argv[1]), json.load(open(sys.argv[2])), Path(sys.argv[3])
ev = {str(e["id"]): e for e in evs}
C = collections.Counter(); col = collections.Counter(); rows_per = []
by_dist = collections.defaultdict(collections.Counter)
seen = {}; mism = []; trial_hits = collections.Counter()


def longform_trials(page):
    t = re.sub(r"\s+", " ", page)
    out = set()
    for m in re.finditer(r'long-form__form-race long-form__form-race--trial".*?history-name">([^<]*)<.*?history-date">(\d\d)/(\d\d)/(\d{4})', t):
        out.add((m.group(4) + "-" + m.group(3) + "-" + m.group(2)))
    return out


for f in sorted(mob.glob("*.html")):
    e = ev.get(f.stem)
    page = f.read_text(encoding="utf-8", errors="replace")
    runners = pm.parse(page)
    C["pages"] += 1
    if not runners:
        C["pages_no_sectionals"] += 1
        continue
    C["runners"] += len(runners)
    day = e["day"] if e else None
    trials = longform_trials(page)
    for r in runners:
        rows_per.append(len(r["runs"]))
        if not r["runs"]:
            C["runners_no_rows"] += 1
        has_prior = False
        for run in r["runs"]:
            if run.get("unparsed"):
                C["rows_unparsed"] += 1; continue
            C["rows"] += 1
            if day and run["date"] >= day:
                C["rows_on_or_after_race_day"] += 1
                continue
            has_prior = True
            sp = run["split"]
            for c in pm.COLS:
                if sp[c] is not None:
                    col[c] += 1
            d = pm.derived(run)
            b = "<=1100" if run["distance"] <= 1100 else "1101-1400" if run["distance"] <= 1400 else "1401-1800" if run["distance"] <= 1800 else ">1800"
            by_dist[b]["rows"] += 1
            for k in ("l400", "l600", "l800", "l1000"):
                if d.get(k) is not None:
                    C["rows_" + k] += 1; by_dist[b][k] += 1
            if all(v is None for v in sp.values()):
                C["rows_all_blank"] += 1
            if r["number"] == 1 and run["date"] in trials:
                trial_hits["runner_row_matches_longform_trial_date"] += 1
            key = (r["name"].lower(), run["date"], run["track"])
            if key in seen and seen[key] != (run["time"], tuple(sp.values())):
                mism.append([*key, seen[key], (run["time"], tuple(sp.values()))])
            seen.setdefault(key, (run["time"], tuple(sp.values())))
        C["runners_with_prior_row" if has_prior else "runners_without_prior_row"] += 1
    trial_hits["longform_trials_runner_url"] += len(trials)
    one = [r for r in runners if r["number"] == 1]
    if one:
        trial_hits["runner1_sectional_rows"] += len(one[0]["runs"])

res = {"counts": C, "columns_nonnull_prior_rows": col, "by_distance": by_dist,
       "rows_per_runner_hist": collections.Counter(rows_per),
       "trial_check": trial_hits, "distinct_runs": len(seen), "dup_mismatch": mism[:20], "dup_mismatch_n": len(mism)}
out.write_text(json.dumps(res, indent=1, ensure_ascii=False, default=dict))
print(json.dumps(res, ensure_ascii=False, default=dict)[:3000])
