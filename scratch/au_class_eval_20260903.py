#!/usr/bin/env python3
"""EXP-20260903-01 evaluator: dev gate first, one terminal for survivors.

Baseline and candidate rows are joined per race and per horse, so the two
scorers see the same field, the same order and the same result labels; only the
feature vector differs. A candidate that comes back bit-identical is reported as
UNWIRED, never as "no effect".
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SCRIPTS))

import au_eval as ev  # noqa: E402


def merge(baseline: Path, candidate: Path) -> list[dict]:
    base = json.loads(baseline.read_text(encoding="utf-8"))["races"]
    cand = json.loads(candidate.read_text(encoding="utf-8"))["races"]
    key = lambda r: (r["date"], r["meeting"], r["race"])  # noqa: E731
    cand_by_key = {key(r): r for r in cand}
    merged = []
    for race in base:
        other = cand_by_key.get(key(race))
        if other is None or len(other["rows"]) != len(race["rows"]):
            continue
        rows = []
        for a, b in zip(race["rows"], other["rows"]):
            if a["name"] != b["name"] or a["pos"] != b["pos"]:
                raise SystemExit(f"row misalignment in {key(race)}")
            rows.append({**a, "cand": {"features": b["features"], "wet": b["wet"],
                                       "proven_class": b["proven_class"]}})
        merged.append({**race, "rows": rows})
    return merged


def cand_scorer(row):
    c = row["cand"]
    return ev.default_scorer({"features": c["features"], "wet": c["wet"],
                              "proven_class": c["proven_class"]})


def sample_hash(races) -> str:
    digest = hashlib.sha256()
    for race in races:
        digest.update(f"{race['date']}|{race['meeting']}|{race['race']}".encode())
        for row in race["rows"]:
            digest.update(f"|{row['name']}|{row['pos']}".encode())
    return digest.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--phase", choices=("dev", "terminal"), default="dev")
    args = ap.parse_args()

    races = merge(Path(args.baseline), Path(args.candidate))
    changed = sum(
        1 for r in races for row in r["rows"]
        if abs(ev.default_scorer(row) - cand_scorer(row)) > 1e-9)
    total = sum(len(r["rows"]) for r in races)
    if changed == 0:
        print(json.dumps({"label": args.label, "verdict": "UNWIRED",
                          "note": "candidate is bit-identical to baseline; "
                                  "check the patch before reporting no effect"},
                         ensure_ascii=False, indent=2))
        return 1

    dev_idx, term_idx = ev.date_partitions(races)
    dev = [races[i] for i in dev_idx]
    out = {
        "label": args.label,
        "races": len(races),
        "runners": total,
        "runners_changed": changed,
        "runners_changed_pct": round(100.0 * changed / total, 2),
        "dev_races": len(dev_idx),
        "terminal_races": len(term_idx),
        "sample_hash": sample_hash(races),
    }
    base_dev = ev._counts(dev, ev.default_scorer)
    cand_dev = ev._counts(dev, cand_scorer)
    # Metric names come from au_eval, never from a local guess: an earlier run
    # of this script asked for "good_pos"/"champ", got nothing back, and would
    # have judged the candidate on `gold` alone without saying so.
    wanted = ("gold", "good_positional", "pass", "champion", "t3prec")
    missing = [k for k in wanted if k not in base_dev or k not in cand_dev]
    if missing:
        raise SystemExit(f"evaluator asked for metrics au_eval does not report: {missing}")
    out["dev"] = {k: {"base": round(base_dev[k], 5), "cand": round(cand_dev[k], 5),
                      "delta_pp": round(cand_dev[k] - base_dev[k], 5)}
                  for k in wanted}
    primary = [out["dev"][k]["delta_pp"] for k in ("gold", "good_positional")]
    out["dev_primary_regression"] = any(d < 0 for d in primary)
    if args.phase == "dev":
        out["decision"] = ("STOP — dev primary regression; terminal stays sealed"
                           if out["dev_primary_regression"]
                           else "PROCEED — eligible for one terminal confirmation")
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    if out["dev_primary_regression"]:
        out["decision"] = "REFUSED — cannot open terminal after a dev primary regression"
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 1
    verdict = ev.compare(races, cand_scorer=cand_scorer, label=args.label)
    out["terminal"] = {
        "stage4_verdict": verdict.stage4_verdict,
        "ship": verdict.ship,
        "why": verdict.why,
        "top5_auc_dev": round(verdict.top_dev, 6),
        "top5_auc_terminal": round(verdict.top_holdout, 6),
        "top5_auc_terminal_ci": [round(x, 6) for x in verdict.top_ci],
        "counts_delta_pp": {k: round(v, 5) for k, v in (verdict.counts or {}).items()},
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
