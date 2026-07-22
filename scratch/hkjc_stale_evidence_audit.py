#!/usr/bin/env python3
"""HKJC stale-evidence audit (mirrors the AU 2026-07-17 methodology).

Per-month / per-meeting audit of every persisted feature_score across the
HK_Racing archive:
  - default-60 rate per feature (score == 60.0 exactly)
  - python_auto.version + schema_version drift
  - presence of derived_feature_scores (formline_strength_score,
    margin_trend_score, same_distance_signal_score, trackwork_trend_score)
    which form_line/stability depend on but which older engine versions did
    not persist (commit d28a9e8 added persistence)
  - presence of matrix_reasoning component sub-scores as a fallback source
  - going/track-condition persistence check (race_analysis keys)

Read-only over the Drive archive. Outputs:
  scratch/hkjc_stale_evidence_audit.json / _monthly.csv / _meetings.csv / _report.md
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from wongchoi_paths import HK_RACING  # noqa: E402

OUT = REPO / "scratch"
FEATURE_KEYS = [
    "form_score", "speed_score", "class_score", "jockey_score", "trainer_score",
    "draw_score", "distance_score", "track_going_score", "weight_score",
    "consistency_score", "risk_score", "confidence_score",
]
DERIVED_KEYS = [
    "formline_strength_score", "margin_trend_score",
    "same_distance_signal_score", "trackwork_trend_score",
]
GOING_KEY_PATTERNS = re.compile(r"going|track_condition|場地|地質", re.IGNORECASE)


def canonical_meetings():
    for d in sorted(HK_RACING.iterdir()):
        if not d.is_dir() or "(" in d.name or not d.name.startswith("2026"):
            continue
        yield d


def reasoning_component_scores(pa):
    """Fallback: pull derived sub-feature scores out of matrix_reasoning components."""
    found = {}
    mr = pa.get("matrix_reasoning")
    if not isinstance(mr, dict):
        return found
    for dim in mr.values():
        if not isinstance(dim, dict):
            continue
        for comp in dim.get("components", []) or []:
            key = comp.get("key")
            if key in DERIVED_KEYS and isinstance(comp.get("score"), (int, float)):
                found[key] = float(comp["score"])
    return found


def main():
    meeting_rows = []
    monthly = defaultdict(lambda: {
        "horses": 0, "races": 0,
        "default": defaultdict(int), "present": defaultdict(int),
        "derived_persisted": 0, "derived_in_reasoning": 0,
        "derived_default": defaultdict(int), "derived_present": defaultdict(int),
        "versions": defaultdict(int), "schema_versions": defaultdict(int),
    })
    going_persisted_meetings = 0
    going_examples = []

    for mdir in canonical_meetings():
        month = mdir.name[:7]
        logic_files = sorted(mdir.glob("Race_*_Logic.json"),
                             key=lambda p: int(re.search(r"Race_(\d+)_", p.name).group(1)))
        if not logic_files:
            continue
        m = monthly[month]
        row = {
            "meeting": mdir.name, "month": month, "races": 0, "horses": 0,
            "versions": set(), "schema_versions": set(),
            "derived_persisted_horses": 0, "derived_reasoning_horses": 0,
            "going_keys": set(),
        }
        default_counts = defaultdict(int)
        for lf in logic_files:
            try:
                data = json.loads(lf.read_text(encoding="utf-8"))
            except Exception as exc:
                print(f"SKIP {lf}: {exc}")
                continue
            row["schema_versions"].add(str(data.get("schema_version")))
            m["schema_versions"][str(data.get("schema_version"))] += 0  # counted per horse below
            ra = data.get("race_analysis") or {}
            for k in ra.keys():
                if GOING_KEY_PATTERNS.search(str(k)):
                    row["going_keys"].add(k)
            horses = data.get("horses") or {}
            race_counted = False
            for hno, h in horses.items():
                pa = h.get("python_auto")
                if not isinstance(pa, dict):
                    continue
                race_counted = True
                row["horses"] += 1
                m["horses"] += 1
                m["versions"][str(pa.get("version"))] += 1
                m["schema_versions"][str(data.get("schema_version"))] += 1
                row["versions"].add(str(pa.get("version")))
                fs = pa.get("feature_scores") or {}
                for key in FEATURE_KEYS:
                    v = fs.get(key)
                    if isinstance(v, (int, float)):
                        m["present"][key] += 1
                        if abs(float(v) - 60.0) < 1e-9:
                            m["default"][key] += 1
                            default_counts[key] += 1
                dfs = pa.get("derived_feature_scores")
                if isinstance(dfs, dict) and dfs:
                    row["derived_persisted_horses"] += 1
                    m["derived_persisted"] += 1
                    src = dfs
                else:
                    src = reasoning_component_scores(pa)
                    if src:
                        row["derived_reasoning_horses"] += 1
                        m["derived_in_reasoning"] += 1
                for key in DERIVED_KEYS:
                    v = src.get(key)
                    if isinstance(v, (int, float)):
                        m["derived_present"][key] += 1
                        if abs(float(v) - 60.0) < 1e-9:
                            m["derived_default"][key] += 1
            if race_counted:
                row["races"] += 1
                m["races"] += 1
        if row["going_keys"]:
            going_persisted_meetings += 1
            going_examples.append((mdir.name, sorted(row["going_keys"])))
        row["default_rate_worst3"] = sorted(
            ((k, default_counts[k] / row["horses"]) for k in FEATURE_KEYS if row["horses"]),
            key=lambda kv: -kv[1])[:3]
        meeting_rows.append(row)

    # --- outputs ---
    monthly_out = {}
    for month, m in sorted(monthly.items()):
        monthly_out[month] = {
            "races": m["races"], "horses": m["horses"],
            "versions": dict(m["versions"]),
            "schema_versions": dict(m["schema_versions"]),
            "derived_persisted_pct": round(100 * m["derived_persisted"] / m["horses"], 1) if m["horses"] else None,
            "derived_in_reasoning_pct": round(100 * m["derived_in_reasoning"] / m["horses"], 1) if m["horses"] else None,
            "default60_pct": {
                k: round(100 * m["default"][k] / m["present"][k], 1) if m["present"][k] else None
                for k in FEATURE_KEYS
            },
            "derived_default60_pct": {
                k: (round(100 * m["derived_default"][k] / m["derived_present"][k], 1)
                    if m["derived_present"][k] else None)
                for k in DERIVED_KEYS
            },
            "derived_coverage_pct": {
                k: round(100 * m["derived_present"][k] / m["horses"], 1) if m["horses"] else None
                for k in DERIVED_KEYS
            },
        }

    payload = {
        "generated_for": "2026-07-17 HKJC stale-evidence audit",
        "archive": str(HK_RACING),
        "monthly": monthly_out,
        "going_persisted_meetings": going_persisted_meetings,
        "going_examples": going_examples[:5],
        "meetings": [
            {**r, "versions": sorted(r["versions"]), "schema_versions": sorted(r["schema_versions"]),
             "going_keys": sorted(r["going_keys"]),
             "default_rate_worst3": [(k, round(100 * v, 1)) for k, v in r["default_rate_worst3"]]}
            for r in meeting_rows
        ],
    }
    (OUT / "hkjc_stale_evidence_audit.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    with open(OUT / "hkjc_stale_evidence_audit_monthly.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["month", "races", "horses", "versions", "derived_persisted_pct",
                    "derived_in_reasoning_pct"] + [f"d60_{k}" for k in FEATURE_KEYS]
                   + [f"d60_{k}" for k in DERIVED_KEYS])
        for month, mo in monthly_out.items():
            w.writerow([month, mo["races"], mo["horses"],
                        ";".join(f"{k}:{v}" for k, v in mo["versions"].items()),
                        mo["derived_persisted_pct"], mo["derived_in_reasoning_pct"]]
                       + [mo["default60_pct"][k] for k in FEATURE_KEYS]
                       + [mo["derived_default60_pct"][k] for k in DERIVED_KEYS])

    with open(OUT / "hkjc_stale_evidence_audit_meetings.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["meeting", "races", "horses", "versions", "schema_versions",
                    "derived_persisted_horses", "derived_reasoning_horses",
                    "going_keys", "default_rate_worst3"])
        for r in meeting_rows:
            w.writerow([r["meeting"], r["races"], r["horses"],
                        ";".join(sorted(r["versions"])), ";".join(sorted(r["schema_versions"])),
                        r["derived_persisted_horses"], r["derived_reasoning_horses"],
                        ";".join(sorted(r["going_keys"])),
                        ";".join(f"{k}={round(100*v,1)}%" for k, v in r["default_rate_worst3"])])

    lines = ["# HKJC Stale-Evidence Audit (2026-07-17)", "",
             f"Archive: `{HK_RACING}`", "",
             "## Monthly summary", "",
             "| month | races | horses | engine versions | derived persisted % | derived via reasoning % |",
             "|---|---|---|---|---|---|"]
    for month, mo in monthly_out.items():
        lines.append(f"| {month} | {mo['races']} | {mo['horses']} | "
                     f"{'; '.join(f'{k}×{v}' for k, v in mo['versions'].items())} | "
                     f"{mo['derived_persisted_pct']} | {mo['derived_in_reasoning_pct']} |")
    lines += ["", "## Monthly default-60 rates (%) — 12 persisted features", "",
              "| month | " + " | ".join(k.replace('_score', '') for k in FEATURE_KEYS) + " |",
              "|---|" + "---|" * len(FEATURE_KEYS)]
    for month, mo in monthly_out.items():
        lines.append(f"| {month} | " + " | ".join(str(mo["default60_pct"][k]) for k in FEATURE_KEYS) + " |")
    lines += ["", "## Monthly derived sub-feature coverage / default-60 (%)", "",
              "| month | " + " | ".join(f"{k.replace('_score','')} cov/d60" for k in DERIVED_KEYS) + " |",
              "|---|" + "---|" * len(DERIVED_KEYS)]
    for month, mo in monthly_out.items():
        cells = [f"{mo['derived_coverage_pct'][k]}/{mo['derived_default60_pct'][k]}" for k in DERIVED_KEYS]
        lines.append(f"| {month} | " + " | ".join(cells) + " |")
    lines += ["", f"## Going persistence: {going_persisted_meetings} meetings expose going-ish keys in race_analysis",
              "", "Examples: " + json.dumps(going_examples[:5], ensure_ascii=False), ""]
    (OUT / "hkjc_stale_evidence_audit_report.md").write_text("\n".join(lines), encoding="utf-8")
    print("meetings:", len(meeting_rows), "months:", len(monthly_out))
    for month, mo in monthly_out.items():
        print(month, mo["races"], "races", mo["versions"], "derived", mo["derived_persisted_pct"], "%")


if __name__ == "__main__":
    main()
