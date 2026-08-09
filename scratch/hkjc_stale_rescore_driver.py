#!/usr/bin/env python3
"""HKJC stale-evidence re-score driver (mirrors AU au_full_rescore_driver.py).

The stale-evidence audit found that every meeting with schema_version==None
(all six April 2026 meetings + 2026-05-03) was scored by an OLD skeleton
extractor that never populated the sectional / L400 primitives into
horse._data, even though the same Facts.md files carry them. Result:
speed_score defaulted to 60 for ~99-100% of horses, so the whole sectional
matrix dimension was blind on those 71 races.

This driver re-scores those meetings through the CURRENT pipeline:
  1. source meeting is READ-ONLY; every input is copied to an isolated /tmp
     sandbox (Facts.md, 排位表.md, 晨操.md/json, 全日賽果.json)
  2. for each race, enumerate the field from Facts.md (### 馬號 N) and rebuild
     a fresh Race_N_Logic.json skeleton with create_hkjc_logic_skeleton.py
     (this is where the current extractor recovers the sectional primitives)
  3. run the current hkjc_auto_orchestrator on the sandbox meeting
  4. read the fresh python_auto.ability_score, rank, and evaluate against the
     historical results on the canonical ruler (eval_metrics)

Results are compared OLD (archive stored ability_score) vs NEW (re-scored) at
meeting and archive level. Historical finish positions are used only to score;
they never enter the engine.

Usage:
    python3 scratch/hkjc_stale_rescore_driver.py [--meeting 2026-04-19_ShaTin] \
        [--limit N] [--out scratch/hkjc_stale_rescore]
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from wongchoi_paths import HK_RACING  # noqa: E402

AUTO_DIR = ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_wong_choi_auto" / "scripts"
WONG_CHOI_DIR = ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_wong_choi" / "scripts"
SHARED = ROOT / ".agents" / "skills" / "shared_racing"
sys.path.insert(0, str(AUTO_DIR))
sys.path.insert(0, str(SHARED))

from eval_metrics import race_metrics, summarize_races  # noqa: E402

SKELETON = WONG_CHOI_DIR / "create_hkjc_logic_skeleton.py"
ORCH = AUTO_DIR / "hkjc_auto_orchestrator.py"

SUPPORT_SUFFIXES = ("Facts.md", "排位表.md", "晨操.md", "晨操.json")


def blind_meetings() -> list[Path]:
    """Meetings whose stored Logic has schema_version==None (sectional-blind)."""
    out = []
    for d in sorted(HK_RACING.iterdir()):
        if not d.is_dir() or "(" in d.name or not d.name.startswith("2026"):
            continue
        logic = sorted(d.glob("Race_*_Logic.json"))
        if not logic:
            continue
        try:
            schema = json.loads(logic[0].read_text(encoding="utf-8")).get("schema_version")
        except Exception:
            continue
        if schema is None and list(d.glob("*全日賽果.json")):
            out.append(d)
    return out


def facts_files(meeting: Path) -> dict[int, Path]:
    """race_number -> Facts.md path."""
    out = {}
    for p in meeting.glob("*Facts.md"):
        m = re.search(r"Race (\d+) Facts\.md$", p.name)
        if m:
            out[int(m.group(1))] = p
    return out


def horses_in_facts(facts_path: Path) -> list[int]:
    text = facts_path.read_text(encoding="utf-8")
    return sorted({int(m.group(1)) for m in re.finditer(r"### 馬號 (\d+) —", text)})


def load_results(meeting: Path) -> dict[int, dict[int, int]]:
    files = sorted(meeting.glob("*全日賽果.json"))
    if not files:
        return {}
    data = json.loads(files[0].read_text(encoding="utf-8"))
    out = {}
    for race_key, race_data in data.items():
        try:
            rn = int(race_key)
        except (TypeError, ValueError):
            continue
        pos = {}
        for row in race_data.get("results", []):
            try:
                pos[int(row["horse_no"])] = int(row["pos"])
            except (KeyError, TypeError, ValueError):
                continue
        if pos:
            out[rn] = pos
    return out


def stage_meeting(meeting: Path, sandbox: Path) -> None:
    sandbox.mkdir(parents=True, exist_ok=True)
    for p in meeting.iterdir():
        if not p.is_file():
            continue
        if p.name.endswith(SUPPORT_SUFFIXES) or p.name.endswith("全日賽果.json") \
                or "全日出賽馬匹資料" in p.name:
            shutil.copy2(p, sandbox / p.name)


def build_skeletons(sandbox: Path, facts: dict[int, Path]) -> list[int]:
    """Rebuild Race_N_Logic.json skeletons from staged Facts. Returns races built."""
    built = []
    for rn, src_facts in sorted(facts.items()):
        staged_facts = sandbox / src_facts.name
        horses = horses_in_facts(staged_facts)
        if not horses:
            continue
        logic_out = sandbox / f"Race_{rn}_Logic.json"
        if logic_out.exists():
            logic_out.unlink()
        for hn in horses:
            proc = _run([sys.executable, str(SKELETON), str(staged_facts), str(rn), str(hn),
                         "--output", str(logic_out)])
            if proc != 0:
                # skeleton refused this horse (header validation) — skip, keep going
                pass
        if logic_out.exists():
            built.append(rn)
    return built


def _run(cmd: list[str]) -> int:
    import subprocess
    env = dict(os.environ, PYTHONUTF8="1")
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    return r.returncode


def run_orchestrator(sandbox: Path) -> str:
    import hkjc_auto_orchestrator as orch
    orch._HAS_PROFILE_SCRAPER = False  # display-only scraper off → fully offline
    runner = orch.HKJCAutoOrchestrator(sandbox, scoring_profile="stale_rescore")
    runner._validate_engine_requested = False
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        runner.run()
    return buf.getvalue()


def rank_from_logic(logic_path: Path) -> list[int]:
    data = json.loads(logic_path.read_text(encoding="utf-8"))
    scored = []
    for hn_text, horse in data.get("horses", {}).items():
        try:
            hn = int(hn_text)
        except ValueError:
            continue
        auto = horse.get("python_auto", {})
        if not auto.get("feature_scores"):
            continue
        scored.append((hn, float(auto.get("ability_score", 60.0))))
    return [hn for hn, _ in sorted(scored, key=lambda kv: (-kv[1], kv[0]))]


def stored_rank_from_archive(meeting: Path, rn: int) -> list[int]:
    logic_path = meeting / f"Race_{rn}_Logic.json"
    if not logic_path.exists():
        return []
    return rank_from_logic(logic_path)


def eval_meeting(meeting: Path, sandbox: Path, results: dict[int, dict[int, int]]) -> dict:
    old_rows, new_rows, race_detail = [], [], []
    for rn, pos in sorted(results.items()):
        top3 = [h for h, p in pos.items() if p <= 3]
        if sum(1 for p in pos.values() if p <= 3) < 3 or not top3:
            continue
        new_logic = sandbox / f"Race_{rn}_Logic.json"
        if not new_logic.exists():
            continue
        new_picks = rank_from_logic(new_logic)
        old_picks = stored_rank_from_archive(meeting, rn)
        if len(new_picks) < 4 or len(old_picks) < 4:
            continue
        old_eval = race_metrics(old_picks, top3, actual_pos=pos)
        new_eval = race_metrics(new_picks, top3, actual_pos=pos)
        old_rows.append(old_eval)
        new_rows.append(new_eval)
        race_detail.append({
            "race": rn,
            "actual_top3": sorted(top3),
            "old_top2": old_picks[:2], "new_top2": new_picks[:2],
            "old_hits": old_eval["hits"], "new_hits": new_eval["hits"],
            "old_good_pos": old_eval["good_positional"], "new_good_pos": new_eval["good_positional"],
            "old_winner_top3": old_eval["winner_in_top3"], "new_winner_top3": new_eval["winner_in_top3"],
        })
    return {"old": summarize_races(old_rows), "new": summarize_races(new_rows),
            "races": race_detail, "old_rows": old_rows, "new_rows": new_rows}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--meeting", default="")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default=str(ROOT / "scratch" / "hkjc_stale_rescore"))
    ap.add_argument("--keep-sandbox", default="")
    args = ap.parse_args()

    meetings = blind_meetings()
    if args.meeting:
        meetings = [m for m in meetings if m.name == args.meeting]
    if args.limit:
        meetings = meetings[: args.limit]
    print(f"Re-scoring {len(meetings)} sectional-blind meetings")

    all_old, all_new, per_meeting = [], [], []
    tmp_root = Path(args.keep_sandbox) if args.keep_sandbox else Path(tempfile.mkdtemp(prefix="hkjc_stale_rescore_"))
    tmp_root.mkdir(parents=True, exist_ok=True)
    try:
        for meeting in meetings:
            sandbox = tmp_root / meeting.name
            stage_meeting(meeting, sandbox)
            facts = facts_files(sandbox)
            built = build_skeletons(sandbox, facts)
            run_orchestrator(sandbox)
            results = load_results(sandbox)
            summary = eval_meeting(meeting, sandbox, results)
            all_old.extend(summary.pop("old_rows"))
            all_new.extend(summary.pop("new_rows"))
            per_meeting.append({"meeting": meeting.name, "races_built": len(built),
                                "summary": summary})
            o, n = summary["old"], summary["new"]
            print(f"{meeting.name}: {len(summary['races'])} races | "
                  f"OLD good_pos {o['counts']['good_positional']} "
                  f"W-in-T3 {o['rates']['winner_in_top3']:.3f} | "
                  f"NEW good_pos {n['counts']['good_positional']} "
                  f"W-in-T3 {n['rates']['winner_in_top3']:.3f}")
    finally:
        archive_old = summarize_races(all_old)
        archive_new = summarize_races(all_new)
        payload = {
            "cohort": "schema_version==None (sectional-blind)",
            "archive_old": archive_old,
            "archive_new": archive_new,
            "meetings": per_meeting,
        }
        Path(args.out + ".json").write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                                            encoding="utf-8")
        if not args.keep_sandbox:
            shutil.rmtree(tmp_root, ignore_errors=True)
    print(f"\n=== ARCHIVE-WIDE ({len(all_old)} races) ===")
    for label, s in (("OLD (stored)", archive_old), ("NEW (re-scored)", archive_new)):
        c, r = s["counts"], s["rates"]
        print(f"{label}: good_pos {c['good_positional']}/{s['races']} "
              f"({100*r['good_positional']:.1f}%) | "
              f"any2 {100*r['good_any2']:.1f}% | "
              f"W-in-T3 {100*r['winner_in_top3']:.1f}% | "
              f"Top1 {100*r['champion']:.1f}% | Gold {c['gold']}")
    print(f"Wrote {args.out}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
