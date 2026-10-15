#!/usr/bin/env python3
"""EXP-20261016-02 G1／G2 量度。規格見 protocol —— 唔准喺度改門檻。

G1：同外部官方計時重疊嘅往績，估算時間 vs 實測時間（Pearson r、差距分佈）。
G2：乾淨窗場內配對 AUC（只計有 A_sb 嘅馬）、同一批馬 pace_figure AUC、
    同 pace_figure／form／performance_quality 嘅場內 Spearman ρ（逐場平均，≥4 匹）。
    停止規則：ρ(A_sb, pace_figure) ≥ 0.60。
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HERE))

from au_racing_engine import full_time_speed as fts  # noqa: E402
import au_sb_total_speed_20261016 as sb  # noqa: E402

CLEAN_SINCE = "2026-08-05"
STOP_RHO = 0.60
BOOT, SEED = 2000, 7


def ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2
        i = j + 1
    return out


def spearman(a, b):
    ra, rb = ranks(a), ranks(b)
    ma, mb = statistics.mean(ra), statistics.mean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = math.sqrt(sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb))
    return num / den if den else None


def day_auc(items):
    """items: [(day, [(score, top3)])] → {day: [conc, pairs]}."""
    out = {}
    for day, runners in items:
        hits = [s for s, t in runners if t]
        miss = [s for s, t in runners if not t]
        c = sum(1.0 if h > m else 0.5 if h == m else 0.0 for h in hits for m in miss)
        cell = out.setdefault(day, [0.0, 0])
        cell[0] += c
        cell[1] += len(hits) * len(miss)
    return out


def auc(days, keys=None):
    keys = list(days) if keys is None else keys
    n = sum(days[k][1] for k in keys)
    return sum(days[k][0] for k in keys) / n if n else float("nan")


def boot(days_a, days_b=None):
    days = sorted(days_a)
    rng = random.Random(SEED)
    samples = []
    for _ in range(BOOT):
        pick = [days[rng.randrange(len(days))] for _ in days]
        samples.append(auc(days_a, pick) - (auc(days_b, pick) if days_b else 0.0))
    samples.sort()
    return samples[int(BOOT * 0.025)], samples[int(BOOT * 0.975) - 1]


def g1(events):
    path = fts.default_bundle_path()
    obj = json.loads(path.read_text(encoding="utf-8"))
    official = {}
    for ev in obj["events"]:
        key = tuple(ev["key"])
        for row in ev["rows"]:
            official[(key, row["horse"])] = row["time"]
    est, real = [], []
    for key, ev in events.items():
        for row in ev["rows"]:
            t = official.get((key, row["horse"]))
            if t is not None:
                est.append(row["time"])
                real.append(t)
    if len(est) < 10:
        return {"matched_runs": len(est)}
    me, mr = statistics.mean(est), statistics.mean(real)
    r = (sum((a - me) * (b - mr) for a, b in zip(est, real))
         / math.sqrt(sum((a - me) ** 2 for a in est) * sum((b - mr) ** 2 for b in real)))
    diffs = sorted(a - b for a, b in zip(est, real))
    return {"official_runs": len(official), "matched_runs": len(est), "pearson_r_time": round(r, 5),
            "diff_s_median": round(statistics.median(diffs), 3),
            "diff_s_iqr": [round(diffs[len(diffs) // 4], 3), round(diffs[3 * len(diffs) // 4], 3)],
            "abs_diff_s_p90": round(sorted(abs(d) for d in diffs)[int(0.9 * len(diffs))], 3)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--asb", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    asb = json.loads(Path(args.asb).read_text(encoding="utf-8"))
    dump = json.loads(Path(args.dump).read_text(encoding="utf-8"))
    report = {"G0_audit": asb["audit"], "events": asb["events"]}

    root = Path(open(HERE.parent / ".wongchoi_au_data_root").read().strip())
    events, _hist, _audit = sb.parse_corpus(root)
    report["G1"] = g1(events)

    clean = [r for r in dump["races"] if r["date"] >= CLEAN_SINCE
             and sum(x["pos"] <= 3 for x in r["rows"]) >= 3 and any(x["pos"] == 1 for x in r["rows"])]
    covered = total = 0
    asb_items, pf_items, pf_all_items = [], [], []
    rhos = {"pace_figure_score": [], "form_score": [], "performance_quality_score": []}
    for race in clean:
        rows = []
        for r in race["rows"]:
            d = asb["asb"].get(f"{race['date']}|{race['meeting']}|{race['race']}|{r['n']}")
            total += 1
            if d and d["raw"] is not None:
                covered += 1
                rows.append((d["raw"], r))
        pf_all_items.append((race["date"], [(r["features"]["pace_figure_score"], r["pos"] <= 3)
                                            for r in race["rows"] if r["features"]["pace_figure_score"] != 60.0]))
        if len(rows) < 2:
            continue
        asb_items.append((race["date"], [(v, r["pos"] <= 3) for v, r in rows]))
        pf_items.append((race["date"], [(r["features"]["pace_figure_score"], r["pos"] <= 3) for _, r in rows]))
        if len(rows) >= 4:
            for leaf in rhos:
                rho = spearman([v for v, _ in rows], [r["features"][leaf] for _, r in rows])
                if rho is not None:
                    rhos[leaf].append(rho)
    report["G0_coverage"] = {"clean_runners": total, "with_asb": covered,
                             "share": round(covered / max(1, total), 4), "races_comparable": len(asb_items)}
    da, dp = day_auc(asb_items), day_auc(pf_items)
    report["G2"] = {
        "auc_asb": round(auc(da), 5), "auc_asb_ci": [round(x + 0, 5) for x in boot(da)],
        "auc_pace_figure_same_runners": round(auc(dp), 5),
        "asb_minus_pf": round(auc(da) - auc(dp), 5), "asb_minus_pf_ci": [round(x, 5) for x in boot(da, dp)],
        "auc_pace_figure_all_observed": round(auc(day_auc(pf_all_items)), 5),
        "rho_mean": {k: round(statistics.mean(v), 4) for k, v in rhos.items() if v},
        "rho_races": {k: len(v) for k, v in rhos.items()},
    }
    rho_pf = report["G2"]["rho_mean"].get("pace_figure_score")
    report["G2"]["stop_rule"] = {"threshold": STOP_RHO, "rho_pace_figure": rho_pf,
                                 "stop": rho_pf is None or rho_pf >= STOP_RHO}
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
