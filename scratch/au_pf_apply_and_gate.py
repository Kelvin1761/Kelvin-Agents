#!/usr/bin/env python3
"""Apply staged PF patches to sandbox Logic copies, re-score, and gate.

Flow (adoption pattern, Drive originals untouched until approval):
  1. For each staged `pf_patch_<meeting>.json`: copy the meeting's Logic +
     Facts from Drive to a local sandbox, inject pf_metrics into horses whose
     _data lacks pf_aggregates (fill-only — never overwrite engine-era PF).
  2. Re-run the orchestrator on the sandbox copy (engine recomputes
     pace_figure + field aggregates automatically).
  3. Compare canonical labels old vs new on those meetings, and report PF
     coverage gained. Aggregated across all applied meetings; the standard
     promotion gate is evaluated on the full refreshed cache once enough
     meetings are patched (this script reports per-batch evidence).

Usage:
    python3 scratch/au_pf_apply_and_gate.py [--sandbox DIR] [--limit 10]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/Users/imac/Antigravity-repo")
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/au_racing/au_wong_choi_auto/scripts")

from wongchoi_paths import AU_RACING  # noqa: E402
from au_archive_calibrator import load_scoring_rows, normalize_horse_name  # noqa: E402

STAGING = Path("/Users/imac/Antigravity-repo/scratch/pf_backfill_staging")
ORCH = "/Users/imac/Antigravity-repo/.agents/skills/au_racing/au_wong_choi_auto/scripts/au_auto_orchestrator.py"
DEFAULT_SANDBOX = Path("/private/tmp/au_pf_apply_sandbox")


def inject(meeting_sandbox: Path, patches: dict) -> tuple[int, int]:
    injected = skipped = 0
    for lp in sorted(meeting_sandbox.glob("Race_*_Logic.json")):
        m = re.search(r"Race_(\d+)_Logic", lp.name)
        race_patch = patches.get(m.group(1)) if m else None
        if not race_patch:
            continue
        data = json.loads(lp.read_text(encoding="utf-8"))
        changed = False
        for h in (data.get("horses") or {}).values():
            name = normalize_horse_name(str(h.get("horse_name") or ""))
            patch = race_patch.get(name)
            if not patch or patch.get("l600_delta_avg") is None:
                continue
            hd = h.setdefault("_data", {})
            existing = (hd.get("pf_metrics") or {}).get("pf_aggregates") or {}
            if existing.get("l600_delta_avg") is not None:
                skipped += 1  # engine-era PF present — never overwrite
                continue
            hd["pf_metrics"] = {
                "pf_runs": [],
                "pf_aggregates": {
                    "l600_delta_avg": patch["l600_delta_avg"],
                    "l800_delta_avg": patch.get("l800_delta_avg"),
                    "l400_delta_avg": patch.get("l400_delta_avg"),
                    "race_time_diff_avg": patch.get("race_time_diff_avg"),
                    "pf_run_count": patch.get("pf_run_count", 0),
                    "source": patch.get("source", "racenet_cfb_per_run"),
                },
            }
            injected += 1
            changed = True
        if changed:
            lp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return injected, skipped


def top_n(csv_path: Path, n: int = 4) -> dict:
    rows = load_scoring_rows(csv_path)
    by_race: dict = {}
    for r in rows:
        by_race.setdefault(str(r.get("race_number")), []).append(r)
    out = {}
    for race, rs in by_race.items():
        rs.sort(key=lambda x: int(x.get("rank") or 999))
        out[race] = [str(x.get("horse_number")) for x in rs[:n]]
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sandbox", type=Path, default=DEFAULT_SANDBOX)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    patch_files = sorted(STAGING.glob("pf_patch_*.json"))[: args.limit]
    if not patch_files:
        print("no staged patches")
        return 1
    args.sandbox.mkdir(parents=True, exist_ok=True)
    for pf in patch_files:
        payload = json.loads(pf.read_text(encoding="utf-8"))
        meeting = payload["meeting"]
        src = AU_RACING / meeting
        dst = args.sandbox / meeting
        if (dst / "Meeting_Auto_Scoring.csv").exists():
            print(f"== {meeting}: already applied, skip")
            continue
        dst.mkdir(parents=True, exist_ok=True)
        for f in src.glob("Race_*_Logic.json"):
            if f.is_file() and f.stat().st_size > 0:
                shutil.copy(f, dst / f.name)
        for f in src.glob("*Facts.md"):
            if f.is_file():
                shutil.copy(f, dst / f.name)
        before = top_n(src / "Meeting_Auto_Scoring.csv") if (src / "Meeting_Auto_Scoring.csv").exists() else {}
        injected, skipped = inject(dst, payload["patches"])
        proc = subprocess.run([sys.executable, ORCH, str(dst)], capture_output=True, text=True)
        ok = (dst / "Meeting_Auto_Scoring.csv").exists()
        after = top_n(dst / "Meeting_Auto_Scoring.csv") if ok else {}
        changed = sum(1 for race in before if before[race] != after.get(race))
        print(f"== {meeting}: injected PF for {injected} horses (kept {skipped} engine-era), "
              f"rescore {'OK' if ok else 'FAILED'}, top-4 changed in {changed}/{len(before)} races")
        if not ok:
            print(proc.stderr[-300:])
    print("\nNext: review sandbox outputs, then adopt via the au_adopt_rescore pattern "
          "and rebuild the cache; run the pace_perf gate once coverage is material.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
