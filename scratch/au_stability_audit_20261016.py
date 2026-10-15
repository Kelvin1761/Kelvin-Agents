#!/usr/bin/env python3
"""EXP-20261016-04 量度 M1–M3。規格見 protocol —— 唔准喺度改門檻。唯讀。"""
from __future__ import annotations

import argparse
import json
import math
import random
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
for p in (SCRIPTS, SCRIPTS.parents[2] / "shared_racing", SCRIPTS.parents[2] / "shared_racing" / "scripts", HERE):
    sys.path.insert(0, str(p))

from au_eval import _counts, _stage4_metric_rows  # noqa: E402
from au_racing_engine import full_time_speed as fts  # noqa: E402
from au_racing_engine.scoring import MATRIX_WEIGHTS  # noqa: E402
from au_walkforward_refit import exact_score  # noqa: E402
from model_evaluation_decision import evaluate_full_record  # noqa: E402
import au_sb_total_speed_gates_20261016 as g  # noqa: E402

CLEAN_SINCE = "2026-08-05"
BOOT, SEED = 2000, 7
WEIGHTS = (1.0, 0.8, 0.6, 0.4)


def tier(text):
    """`_get_class_tier` with a flag: did a rule match, or did it fall to the default 7?"""
    t = str(text).lower()
    if "group 1" in t or "g1" in t: return 1, True
    if "group 2" in t or "g2" in t or "group 3" in t or "g3" in t: return 2, True
    if "listed" in t or "lr" in t or "open" in t: return 3, True
    m = re.search(r"bm\s*(\d+)", t)
    if m:
        r = int(m[1])
        return (4 if r >= 88 else 5 if r >= 72 else 6 if r >= 64 else 7), True
    if "class 6" in t or "class 5" in t: return 5, True
    if "class 4" in t or "class 3" in t: return 6, True
    if "class 2" in t or "class 1" in t: return 7, True
    if "maiden" in t: return 8, True
    return 7, False


def evaluable(r):
    return sum(x["pos"] <= 3 for x in r["rows"]) >= 3 and any(x["pos"] == 1 for x in r["rows"])


# ── M1 ────────────────────────────────────────────────────────────────────
def m1(races):
    by_day = defaultdict(lambda: [0, 0, 0])   # rows, labelled, parsed
    labels = Counter()
    for race in races:
        for row in race["rows"]:
            for e in row.get("form_entries") or []:
                if e.get("placing") in (None, ""):
                    continue
                cell = by_day[race["date"]]
                cell[0] += 1
                lab = str(e.get("source_race_class") or "").strip()
                if lab:
                    cell[1] += 1
                    _t, ok = tier(lab)
                    cell[2] += ok
                    labels[lab if len(labels) < 40 or lab in labels else "…"] += 1
    days = sorted(by_day)
    full = [d for d in days if by_day[d][0] and by_day[d][2] / by_day[d][0] >= 0.95]
    run = best = 0
    for d in days:
        run = run + 1 if d in full else 0
        best = max(best, run)
    months = defaultdict(lambda: [0, 0, 0])
    for d, (n, lab, ok) in by_day.items():
        m = months[d[:7]]
        m[0] += n; m[1] += lab; m[2] += ok
    return {"by_month": {k: {"rows": v[0], "labelled": round(v[1] / v[0], 4), "parsed": round(v[2] / v[0], 4)}
                         for k, v in sorted(months.items())},
            "meeting_days": len(days), "full_coverage_days": len(full),
            "first_full_day": full[0] if full else None, "longest_consecutive_full_run": best,
            "top_labels": labels.most_common(15)}


# ── M2 ────────────────────────────────────────────────────────────────────
def with_scores(races, bump):
    out = []
    for race in races:
        rows = []
        for r in race["rows"]:
            feats = dict(r["features"])
            if bump and r.get("minus4"):
                feats["form_score"] = min(100.0, feats["form_score"] + 4.0)
            rows.append({**r, "features": feats, "ability": exact_score({**r, "features": feats}, MATRIX_WEIGHTS)})
        out.append({**race, "rows": rows})
    return out


def m2(races):
    base, removed = with_scores(races, False), with_scores(races, True)
    replica = max(abs(a["ability"] - b["ability"]) for ra, rb in zip(races, base)
                  for a, b in zip(ra["rows"], rb["rows"]))
    score = lambda r: r["ability"]  # noqa: E731
    dates = [r["date"] for r in races]
    verdict = evaluate_full_record(domain="au", mode="fixed_rule", dates=dates,
                                   baseline_rows=_stage4_metric_rows(base, score),
                                   candidate_rows=_stage4_metric_rows(removed, score),
                                   leakage_audit_passed=True,
                                   ranking_metrics=("top3_capture_at5", "ndcg_at5", "top5_pairwise_auc"))
    trig, hot = [], []
    for race in races:
        n = len(race["rows"])
        for r in race["rows"]:
            ex = (1.0 if r["pos"] <= 3 else 0.0) - min(3, n) / n
            if r.get("minus4"):
                trig.append((race["date"], ex))
            elif r["features"]["form_score"] >= 72:
                hot.append((race["date"], ex))
    def ci(vals):
        days = sorted({d for d, _ in vals})
        by = defaultdict(list)
        for d, e in vals:
            by[d].append(e)
        rng = random.Random(SEED)
        s = sorted(statistics.mean([e for d in [days[rng.randrange(len(days))] for _ in days] for e in by[d]])
                   for _ in range(BOOT))
        return [round(100 * s[int(BOOT * .025)], 2), round(100 * s[int(BOOT * .975) - 1], 2)]
    runners = sum(len(r["rows"]) for r in races)
    return {"replica_max_abs_diff": replica, "triggered": len(trig), "trigger_rate": round(len(trig) / runners, 4),
            "changed_races": sum(any(r.get("minus4") for r in race["rows"]) for race in races),
            "excess_triggered_pp": round(100 * statistics.mean(e for _, e in trig), 2) if trig else None,
            "excess_triggered_ci": ci(trig) if trig else None,
            "excess_form72_not_triggered_pp": round(100 * statistics.mean(e for _, e in hot), 2),
            "excess_form72_not_triggered_ci": ci(hot), "n_form72_not_triggered": len(hot),
            "counts_base": _counts(base, score), "counts_removed": _counts(removed, score),
            "verdict_remove_rule": verdict}


# ── M3 ────────────────────────────────────────────────────────────────────
FINISH = re.compile(r"\bfinish:(\d+)/(\d+)")
MARGIN = re.compile(r"margin:\s*(-?[\d.]+)\s*L?\b")


def second_place_margins(root):
    """{(venue_norm, date, race_no): margin of the runner that finished 2nd}; conflicts dropped."""
    from corpus_paths import meeting_dirs
    seen = defaultdict(set)
    for meeting in meeting_dirs(root):
        for fg in meeting.glob("*Race * Formguide.md"):
            for line in fg.read_text(encoding="utf-8", errors="replace").splitlines():
                run = fts.RUN.match(line)
                if not run:
                    continue
                f, m = FINISH.search(line), MARGIN.search(line)
                if f and m and int(f[1]) == 2:
                    seen[(fts.normalize_venue_name(run[1]), run[3], int(run[2]))].add(float(m[1]))
    return {k: next(iter(v)) for k, v in seen.items() if len(v) == 1}, sum(len(v) > 1 for v in seen.values())


def pq_raw(runs, m2map, candidate):
    if len(runs) < 2:
        return None, 0, 0
    total = wsum = 0.0
    winners = known = 0
    for run, w in zip(runs, WEIGHTS):
        q = float(run["quality"])
        if int(run.get("finish_pos") or 0) == 1:
            winners += 1
            vm = re.match(r"(.+?)\s+R(\d+)$", str(run.get("venue") or ""))
            margin = m2map.get((fts.normalize_venue_name(vm[1]), run["date"], int(vm[2]))) if vm else None
            if margin is not None:
                known += 1
                if candidate:
                    q += min(20.0, abs(margin))
        total += q * w
        wsum += w
    return total / wsum, winners, known


def field_leaf(values):
    obs = [v for v in values if v is not None]
    if len(obs) < 3 or statistics.pstdev(obs) <= 0:
        return [None] * len(values)
    mu, sd = statistics.mean(obs), statistics.pstdev(obs)
    return [None if v is None else max(0.0, min(100.0, 60 + 20 * (v - mu) / sd)) for v in values]


def m3(races, root):
    m2map, conflicts = second_place_margins(root)
    winners = known = 0
    base_items, cand_items, sub_b, sub_c = [], [], [], []
    for race in races:
        b_raw, c_raw, has_known = [], [], []
        for r in race["rows"]:
            runs = r.get("pq_runs") or [] if r.get("pq_source") == "class_adjusted_margin_field_relative" else []
            rb, w, k = pq_raw(runs, m2map, False)
            rc, _w, _k = pq_raw(runs, m2map, True)
            winners += w; known += k
            b_raw.append(rb); c_raw.append(rc); has_known.append(k > 0)
        bl, cl = field_leaf(b_raw), field_leaf(c_raw)
        pairs_b = [(s, r["pos"] <= 3) for s, r in zip(bl, race["rows"]) if s is not None]
        pairs_c = [(s, r["pos"] <= 3) for s, r in zip(cl, race["rows"]) if s is not None]
        base_items.append((race["date"], pairs_b))
        cand_items.append((race["date"], pairs_c))
        sub_b.append((race["date"], [(s, r["pos"] <= 3) for s, r, k in zip(bl, race["rows"], has_known) if s is not None and k]))
        sub_c.append((race["date"], [(s, r["pos"] <= 3) for s, r, k in zip(cl, race["rows"], has_known) if s is not None and k]))
    share = known / winners if winners else 0.0
    out = {"second_place_races": len(m2map), "conflict_races_dropped": conflicts,
           "winner_rows": winners, "winner_rows_margin_known": known, "known_share": round(share, 4)}
    if share < 0.5:
        out["stop"] = "known winning margin < 50% — no AUC conclusion (protocol)"
        return out
    db, dc = g.day_auc(base_items), g.day_auc(cand_items)
    out.update({"auc_base": round(g.auc(db), 5), "auc_cand": round(g.auc(dc), 5),
                "delta": round(g.auc(dc) - g.auc(db), 5), "delta_ci": [round(x, 5) for x in g.boot(dc, db)]})
    sb_, sc_ = g.day_auc(sub_b), g.day_auc(sub_c)
    out["subset_known_winner"] = {"auc_base": round(g.auc(sb_), 5), "auc_cand": round(g.auc(sc_), 5),
                                  "delta_ci": [round(x, 5) for x in g.boot(sc_, sb_)]}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    races = [r for r in json.loads(Path(args.dump).read_text(encoding="utf-8"))["races"]
             if r["date"] >= CLEAN_SINCE and evaluable(r)]
    root = Path((HERE.parent / ".wongchoi_au_data_root").read_text().strip())
    report = {"races": len(races), "M1": m1(races), "M2": m2(races), "M3": m3(races, root)}
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    v = report["M2"].pop("verdict_remove_rule")
    report["M2"]["verdict"] = {"verdict": v["verdict"], "reason": v["reason"],
                               "primary": {k: {kk: (round(vv, 5) if isinstance(vv, float) else vv)
                                               for kk, vv in e.items() if kk in ("delta", "ci_low", "ci_high", "p_value")}
                                           for k, e in v["detail"]["primary"].items()},
                               "ranking": {k: {kk: (round(vv, 5) if isinstance(vv, float) else vv)
                                               for kk, vv in e.items() if kk in ("delta", "ci_low", "ci_high", "p_value")}
                                           for k, e in v["detail"]["ranking"].items()}}
    print(json.dumps(report, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
