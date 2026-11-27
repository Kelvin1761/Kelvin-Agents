"""EXP-20261127-71: score A0 (no link) vs A1 (abbreviated-name link) on the same matches.

  python3 evaluate.py apply  --db A1.db                    # plan_abbreviated_merges + apply_merges on a COPY
  python3 evaluate.py score  --db A0.db --out A0.json [--limit N]
  python3 evaluate.py compare A0.json A1.json

`score` must run in its own process per DB: tennis_wc reads DATABASE_URL at import.
Population (protocol): Sportsbet matches 2026-10-01..2026-11-25 with a winner in
match_results and a pre-start match-winner price on both sides (earliest, MIN(id)).
Features are rebuilt as of the match date with the same code in both arms.
"""
import argparse, hashlib, json, math, os, random, sqlite3, sys
from collections import defaultdict

ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "tennis-wong-choi", "src")
START, END = "2026-10-01", "2026-11-25"
SEED, DRAWS = 20261127, 2000


def _strip(obj):
    if isinstance(obj, dict):
        return {k: _strip(v) for k, v in obj.items() if k not in ("provenance", "calculated_at", "created_at")}
    if isinstance(obj, list):
        return [_strip(v) for v in obj]
    return obj


def population(conn):
    rows = conn.execute("""
        SELECT m.id, m.match_date, m.player_a_id, m.player_b_id, coalesce(t.name, ''), r.winner_player_id,
               (SELECT o.player_a_odds || ',' || o.player_b_odds FROM odds_snapshots o
                 WHERE o.match_id = m.id AND o.player_a_odds > 1 AND o.player_b_odds > 1
                   AND (m.start_time_utc IS NULL OR o.fetched_at < m.start_time_utc) ORDER BY o.id LIMIT 1)
        FROM matches m LEFT JOIN tournaments t ON t.id = m.tournament_id
        JOIN match_results r ON r.match_id = m.id
        WHERE m.source_provider = 'sportsbet' AND m.match_date BETWEEN ? AND ?
        GROUP BY m.id""", (START, END)).fetchall()
    return [r for r in rows if r[6] and r[5] in (r[2], r[3])]


def level(name):
    n = name.lower()
    return "UTR" if "utr" in n else "CHALL" if "challenger" in n else \
        "ITF" if ("itf" in n or n[:3] in ("m15", "m25", "w15", "w35", "w50", "w75")) else "OTHER"


def cmd_apply(db):
    sys.path.insert(0, ROOT)
    from tennis_wc.sources.identity import apply_merges, plan_abbreviated_merges
    conn = sqlite3.connect(db)
    plans = plan_abbreviated_merges(conn)
    print(json.dumps(apply_merges(conn, plans)))
    conn.commit()


def cmd_score(db, out, limit):
    os.environ["DATABASE_URL"] = f"sqlite:///{db}"
    sys.path.insert(0, ROOT)
    from tennis_wc.model.features.feature_builder import assemble_match_feature_snapshot
    from tennis_wc.model.match import predict_match_probability
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = population(conn)
    if limit:
        rows = rows[:limit]
    shard = os.environ.get("SHARD")  # "i/n": score every n-th match starting at i
    if shard:
        i, n = (int(x) for x in shard.split("/"))
        rows = rows[i::n]
    res = {}
    for mid, day, a, b, tname, winner, odds in rows:
        try:
            snap, _ = assemble_match_feature_snapshot(mid, persist_derived=False)
            p = predict_match_probability(snap)["player_a_probability"]
        except Exception as exc:  # noqa: BLE001
            res[str(mid)] = {"error": f"{type(exc).__name__}: {exc}"[:200]}
            continue
        oa, ob = (float(x) for x in odds.split(","))
        fair = (1 / oa) / (1 / oa + 1 / ob)
        h = hashlib.sha256(json.dumps(_strip(snap), sort_keys=True, default=str).encode()).hexdigest()
        res[str(mid)] = {"day": day, "level": level(tname), "p": p, "y": int(winner == a), "market": fair, "hash": h}
    json.dump(res, open(out, "w"))
    print(len(res), "scored;", sum("error" in v for v in res.values()), "errors")


def ll(p, y):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return -math.log(p if y else 1 - p)


def boot(rows, fn):
    by = defaultdict(list)
    for r in rows:
        by[r["day"]].append(fn(r))
    days = sorted(by)
    rnd = random.Random(SEED)
    vals = sorted(sum(x for d in pick for x in by[d]) / sum(len(by[d]) for d in pick)
                  for pick in ([rnd.choice(days) for _ in days] for _ in range(DRAWS)))
    flat = [x for d in days for x in by[d]]
    return sum(flat) / len(flat), vals[int(0.025 * DRAWS)], vals[int(0.975 * DRAWS) - 1]


def _load(spec):
    out = {}
    for path in spec.split("+"):
        out.update(json.load(open(path)))
    return out


def cmd_compare(a0, a1):
    A, B = _load(a0), _load(a1)
    both = [k for k in A if k in B and "error" not in A[k] and "error" not in B[k]]
    affected = [k for k in both if A[k]["hash"] != B[k]["hash"]]
    print(f"scored both {len(both)}; affected {len(affected)} ({100*len(affected)/max(len(both),1):.0f}%); "
          f"errors A0 {sum('error' in v for v in A.values())} A1 {sum('error' in v for v in B.values())}")
    def rows(keys):
        return [{"day": A[k]["day"], "y": A[k]["y"], "p0": A[k]["p"], "p1": B[k]["p"], "m": A[k]["market"],
                 "level": A[k]["level"]} for k in keys]
    R = rows(affected)
    if not R:
        return
    d, lo, hi = boot(R, lambda r: ll(r["p1"], r["y"]) - ll(r["p0"], r["y"]))
    print(f"PRIMARY  affected log-loss A1 - A0: {d:+.4f} [{lo:+.4f}, {hi:+.4f}]  -> {'KEEP candidate' if hi < 0 else 'not KEEP'}")
    mean = lambda f: sum(f(r) for r in R) / len(R)  # noqa: E731
    print(f"  log-loss A0 {mean(lambda r: ll(r['p0'], r['y'])):.4f}  A1 {mean(lambda r: ll(r['p1'], r['y'])):.4f}  market {mean(lambda r: ll(r['m'], r['y'])):.4f}")
    print(f"  Brier A0 {mean(lambda r: (r['p0']-r['y'])**2):.4f}  A1 {mean(lambda r: (r['p1']-r['y'])**2):.4f}  market {mean(lambda r: (r['m']-r['y'])**2):.4f}")
    g, glo, ghi = boot(R, lambda r: (ll(r["p1"], r["y"]) - ll(r["m"], r["y"])) - (ll(r["p0"], r["y"]) - ll(r["m"], r["y"])))
    print(f"  gap to market change: {g:+.4f} [{glo:+.4f}, {ghi:+.4f}]")
    for lv in ("ITF", "UTR", "CHALL", "OTHER"):
        sub = [r for r in R if r["level"] == lv]
        if len(sub) >= 30:
            x, xl, xh = boot(sub, lambda r: ll(r["p1"], r["y"]) - ll(r["p0"], r["y"]))
            print(f"  {lv:5} n={len(sub):5} A1-A0 {x:+.4f} [{xl:+.4f}, {xh:+.4f}]  A0 {sum(ll(r['p0'],r['y']) for r in sub)/len(sub):.4f} market {sum(ll(r['m'],r['y']) for r in sub)/len(sub):.4f}")
    print(f"  mean |p1-p0| {mean(lambda r: abs(r['p1']-r['p0'])):.4f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("apply", "score", "compare"))
    ap.add_argument("files", nargs="*")
    ap.add_argument("--db"); ap.add_argument("--out"); ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    if a.cmd == "apply":
        cmd_apply(a.db)
    elif a.cmd == "score":
        cmd_score(a.db, a.out, a.limit)
    else:
        cmd_compare(*a.files)


if __name__ == "__main__":
    main()
