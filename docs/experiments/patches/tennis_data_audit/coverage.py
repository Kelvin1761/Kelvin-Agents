"""Weekly field coverage of the priced tennis population (Sportsbet matches), by level. Read-only."""
import sqlite3, json, collections, sys
c = sqlite3.connect("file:/Users/imac/Antigravity-repo/tennis-wong-choi/tennis_wc.db?mode=ro", uri=True)
lvl = {}
for tid, level, surface in c.execute("select tournament_id, upper(level), surface from tournament_levels"):
    lvl[tid] = (level, surface)
rows = c.execute("""select m.id, m.match_date, m.tournament_id, m.round, t.name from matches m left join tournaments t on t.id=m.tournament_id
                    where m.source_provider='sportsbet' and m.match_date >= '2026-08-03'""").fetchall()
meta = {r[0]: r for r in rows}
def val(d, *path):
    for p in path:
        if not isinstance(d, dict): return None
        d = d.get(p)
    if isinstance(d, dict) and "value" in d: return d["value"]
    return d
def bucket(name, level):
    n = (name or "").lower()
    if level in ("CHALLENGER",) or "challenger" in n: return "CHALL"
    if level == "ITF" or "itf" in n or n.startswith(("m15", "m25", "w15", "w35", "w50", "w75", "w100")): return "ITF"
    if level and level.startswith(("ATP", "WTA", "GRAND")): return "TOUR"
    return "UNK"
stats = collections.defaultdict(lambda: collections.Counter())
q = "select match_id, player_id, features_json, data_quality_score from feature_snapshots where match_id in (%s)"
ids = list(meta)
seen = set()
for i in range(0, len(ids), 900):
    chunk = ids[i:i+900]
    for mid, pid, fj, dq in c.execute(q % ",".join("?"*len(chunk)), chunk):
        if (mid, pid) in seen: continue
        seen.add((mid, pid))
        _, d, tid, rnd, tname = meta[mid]
        level, surface = lvl.get(tid, (None, None))
        wk = d[:8] + ("0" + str((int(d[8:10]) - 1) // 7 * 7 + 1))[-2:]
        b = bucket(tname, level)
        s = stats[(d[:7], b)]
        try:
            f = json.loads(fj)
        except (TypeError, ValueError):
            s["cleared"] += 1
            continue
        s["n"] += 1
        s["surface_known"] += bool(surface and surface.upper() not in ("UNKNOWN", ""))
        s["level_known"] += bool(level and level != "UNKNOWN")
        s["round_known"] += bool(rnd and rnd.upper() != "UNKNOWN")
        s["rank"] += val(f, "current_rank") is not None
        oe, se = val(f, "overall_elo"), val(f, "surface_elo")
        s["elo"] += oe is not None
        s["surface_elo_distinct"] += (se is not None and oe is not None and abs(se - oe) > 1e-9)
        s["hold_rate"] += val(f, "tournament_level_stats", "hold_rate") is not None
        s["bp_save"] += val(f, "pressure_stats", "break_point_save_rate") is not None
        s["h2h>0"] += (val(f, "head_to_head", "matches") or 0) > 0
        s["history>=10"] += (val(f, "bo_format_stats", "matches") or 0) >= 10
        s["fatigue_known"] += val(f, "fatigue", "status") == "KNOWN"
        s["dq>65"] += (dq or 0) > 65
cols = ["surface_known", "level_known", "round_known", "rank", "elo", "surface_elo_distinct", "hold_rate", "bp_save", "h2h>0", "history>=10", "fatigue_known", "dq>65"]
print("cleared bodies:", {k: v["cleared"] for k, v in stats.items() if v["cleared"]})
print("month    lvl      n  " + " ".join(f"{x[:10]:>10}" for x in cols))
for (m, b), s in sorted(stats.items()):
    print(f"{m} {b:6} {s['n']:6}  " + " ".join(f"{100*s[x]/s['n']:9.0f}%" for x in cols))
