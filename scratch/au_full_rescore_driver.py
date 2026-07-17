#!/usr/bin/env python3
"""Copy every AU archive meeting (Logic+Facts) to a sandbox and re-score it
through the current engine with the facts-refresh fix. Drive is never written.

Stale embedded facts_section blobs are cleared before scoring so the engine
re-reads the Facts file (mirrors the enrich override for pre-realignment Logic).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, "/Users/imac/Antigravity-repo")
from wongchoi_paths import AU_RACING

SP = Path("/private/tmp/claude-501/-Users-imac-Antigravity-repo/b09ea7dc-ca6d-496d-af27-41b7787ee6ae/scratchpad")
DATA_ROOT = SP / "data" / "Wong Choi Horse Race Analysis" / "AU_Racing"
ORCH = "/Users/imac/Antigravity-repo/.agents/skills/au_racing/au_wong_choi_auto/scripts/au_auto_orchestrator.py"
MARKERS = ("賽績線", "試閘", "L400")


def clear_stale_sections(meeting_dir: Path) -> int:
    cleared = 0
    for lp in meeting_dir.glob("Race_*_Logic.json"):
        if lp.stat().st_size == 0:
            continue
        try:
            data = json.loads(lp.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        changed = False
        for horse in data.get("horses", {}).values():
            hd = horse.get("_data")
            if not isinstance(hd, dict):
                continue
            section = hd.get("facts_section") or ""
            if section and not any(marker in section for marker in MARKERS):
                hd["facts_section"] = ""
                changed = True
                cleared += 1
        if changed:
            lp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return cleared


def main() -> int:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    results_csv = AU_RACING / "AU_Historical_Raw_Race_Results.csv"
    if results_csv.exists():
        shutil.copy(results_csv, DATA_ROOT / results_csv.name)

    dirs = sorted(p for p in AU_RACING.iterdir() if p.is_dir())
    done = skipped = failed = 0
    start = time.time()
    for idx, src in enumerate(dirs, 1):
        logic_files = sorted(src.glob("Race_*_Logic.json"))
        if not logic_files:
            skipped += 1
            continue
        dst = DATA_ROOT / src.name
        if (dst / "Meeting_Auto_Scoring.csv").exists():
            done += 1
            continue  # resume support
        dst.mkdir(parents=True, exist_ok=True)
        for lp in logic_files:
            if lp.is_file() and lp.stat().st_size > 0:
                shutil.copy(lp, dst / lp.name)
        for fp in src.glob("*Facts.md"):
            if fp.is_file():
                shutil.copy(fp, dst / fp.name)
        cleared = clear_stale_sections(dst)
        proc = subprocess.run(
            [sys.executable, ORCH, str(dst)],
            capture_output=True, text=True,
        )
        if (dst / "Meeting_Auto_Scoring.csv").exists():
            done += 1
            print(f"[{idx}/{len(dirs)}] OK {src.name} (stale sections cleared: {cleared})", flush=True)
        else:
            failed += 1
            print(f"[{idx}/{len(dirs)}] FAIL {src.name}: {proc.stderr[-200:]}", flush=True)
    print(f"DONE meetings={done} skipped={skipped} failed={failed} in {(time.time()-start)/60:.1f} min", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
