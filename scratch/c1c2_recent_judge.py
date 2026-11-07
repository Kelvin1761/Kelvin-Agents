#!/usr/bin/env python3
"""Compare arms written by c1c2_recent_rescore.py (same races, paired by race).

Metrics come from eval_metrics.race_metrics via au_window_review.build_race
(gold = capture-at-4, good_positional, top3_capture_at5, champion). top-1 place is
read off the same rows (model rank 1 finished ≤3). CIs: paired bootstrap by race
(au_window_review.mean_ci, 2,000 draws). MDE ≈ 2.8 × SD(per-race diff) / √n
(two-sided α 0.05, 80% power, normal approximation).

    python3 scratch/c1c2_recent_judge.py <run dir> [--primary-from 2026-11-06]
"""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / ".agents/skills/au_racing/au_wong_choi_auto/scripts"))
import au_window_review as wr  # noqa: E402

ARMS = {"snap": "live snapshot", "a": "C2 (live)", "b": "C1", "c": "BASE"}
KEYS = ("gold", "good_positional", "top3_capture_at5", "champion", "top1_place")


def per_race(r):
    m = r["model"]
    top = min(r["rows"], key=lambda x: x["rank"])
    return {"gold": float(bool(m["gold"])), "good_positional": float(bool(m["good_positional"])),
            "top3_capture_at5": float(m["top3_capture_at5"]), "champion": float(bool(m["champion"])),
            "top1_place": float(top["pos"] <= 3)}


def load(run):
    out = {}
    for arm in ARMS:
        d = json.loads((run / f"arm_{arm}.json").read_text(encoding="utf-8"))
        out[arm] = {(r["meeting"], r["race"]): r for r in d["races"]}
        out[arm + "_skipped"] = d["skipped"]
    return out


def table(keys_, data, label):
    n = len(keys_)
    lines = [f"\n### {label} — {n} races\n",
             "| metric | C2 live | C1 | BASE | C1 − C2 [95% CI] | BASE − C2 [95% CI] | MDE (C1−C2) |",
             "|---|---|---|---|---|---|---|"]
    for k in KEYS:
        vals = {arm: [per_race(data[arm][key])[k] for key in keys_] for arm in ("a", "b", "c")}
        rate = {arm: sum(v) / n for arm, v in vals.items()}
        cells = []
        for other in ("b", "c"):
            diffs = [x - y for x, y in zip(vals[other], vals["a"])]
            pt, lo, hi = wr.mean_ci(diffs)
            cells.append(f"{100*pt:+.1f}pp [{100*lo:+.1f}, {100*hi:+.1f}]")
        d = [x - y for x, y in zip(vals["b"], vals["a"])]
        mu = sum(d) / n
        sd = math.sqrt(sum((x - mu) ** 2 for x in d) / max(1, n - 1))
        mde = 2.8 * sd / math.sqrt(n) if n else float("nan")
        lines.append(f"| {k} | {100*rate['a']:.1f}% | {100*rate['b']:.1f}% | {100*rate['c']:.1f}% | "
                     f"{cells[0]} | {cells[1]} | ±{100*mde:.1f}pp (sd {sd:.3f}) |")
    auc = {arm: wr.auc_top5([data[arm][k] for k in keys_], "model") for arm in ("a", "b", "c")}
    lines.append(f"\ntop-5 AUC: C2 {auc['a']:.4f}  C1 {auc['b']:.4f}  BASE {auc['c']:.4f}")
    return "\n".join(lines)


def main():
    run = Path(sys.argv[1])
    primary_from = sys.argv[2] if len(sys.argv) > 2 else "2026-11-06"
    data = load(run)
    common = sorted(set(data["a"]) & set(data["b"]) & set(data["c"]) & set(data["snap"]))
    out = [f"# C1 vs C2 vs BASE — {run}\n", f"common races: {len(common)}"]
    for arm in ARMS:
        out.append(f"skipped[{arm}]: {len(data[arm + '_skipped'])} "
                   + json.dumps(sorted({(s['meeting'], s['skip'].split(':')[0]) for s in data[arm + '_skipped']}),
                                ensure_ascii=False)[:600])

    # sanity: re-scored arm a vs stored snapshot ranking
    out.append("\n## Sanity: re-scored C2 (arm a) vs stored pre-race snapshot ranking, by date")
    by_day = defaultdict(lambda: [0, 0, 0, 0])
    for k in common:
        s = [x["n"] for x in sorted(data["snap"][k]["rows"], key=lambda x: x["rank"])]
        a = [x["n"] for x in sorted(data["a"][k]["rows"], key=lambda x: x["rank"])]
        c = by_day[data["a"][k]["date"]]
        c[0] += 1; c[1] += s == a; c[2] += s[0] == a[0]; c[3] += s[:4] == a[:4]
    out.append("| date | races | full order same | top1 same | top4 same |\n|---|---|---|---|---|")
    for d, c in sorted(by_day.items()):
        out.append(f"| {d} | {c[0]} | {c[1]} | {c[2]} | {c[3]} |")

    days = sorted({data["a"][k]["date"] for k in common})
    primary = [k for k in common if data["a"][k]["date"] >= primary_from]
    out.append(table(primary, data, f"PRIMARY: C2-live snapshot dates ≥ {primary_from}"))
    for d in days:
        out.append(table([k for k in common if data["a"][k]["date"] == d], data, f"day {d}"))
    fresh = [k for k in common if data["a"][k]["date"] >= "2026-11-05"]
    out.append(table(fresh, data, "POST-DECISION 2026-11-05..: dates not used by the EXP-20261105-05 §8 walk-forward (its last test window ended 2026-11-04)"))
    out.append(table(common, data, f"POOLED {days[0]}..{days[-1]} (re-scored; weights out-of-sample, refit trained ≤ 2026-10-30)"))

    # top-pick differences
    diffs = []
    for k in common:
        tops = {}
        for arm in ("a", "b", "c"):
            top = min(data[arm][k]["rows"], key=lambda x: x["rank"])
            tops[arm] = (top["name"], top["pos"], top.get("sp"))
        if len({t[0] for t in tops.values()}) > 1:
            field = data["a"][k]["field"]
            diffs.append({"date": data["a"][k]["date"], "meeting": k[0], "race": k[1], "field": field,
                          **{ARMS[a]: f"{t[0]} ({t[1]}/{field}, SP {t[2]})" for a, t in tops.items()}})
    out.append(f"\n## Races where the top pick differs between arms: {len(diffs)} of {len(common)}")
    wins = defaultdict(int)
    for row in diffs:
        for arm in ("a", "b", "c"):
            pos = int(row[ARMS[arm]].split("(")[1].split("/")[0])
            wins[(arm, "win")] += pos == 1
            wins[(arm, "place")] += pos <= 3
    out.append("in those races — top pick won / placed: " + "; ".join(
        f"{ARMS[a]} {wins[(a, 'win')]}/{wins[(a, 'place')]}" for a in ("a", "b", "c")))
    out.append("\n| date | meeting | R | C2 live | C1 | BASE |\n|---|---|---|---|---|---|")
    for row in diffs:
        if row["date"] >= primary_from:
            out.append(f"| {row['date']} | {row['meeting'][11:].split(' Race')[0]} | {row['race']} | "
                       f"{row['C2 (live)']} | {row['C1']} | {row['BASE']} |")
    (run / "top_pick_diffs.json").write_text(json.dumps(diffs, ensure_ascii=False, indent=1), encoding="utf-8")
    text = "\n".join(out)
    (run / "report.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
