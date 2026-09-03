#!/usr/bin/env python3
"""EXP-20260903-02: restore the prize column the Facts table never wrote.

`horse_prize_level()` -- the live 「班次水平調整」 -- reads column 18 of the
Facts record table. That column was only added on 2026-07-31, so the adjustment
fires for 0% of runners before 2026-08 and ~95% after. The Formguide that the
Facts were generated from still carries a per-run `$prize` for 100% of rows in
every month, so this is a Facts-table gap, not a data gap.

This script rebuilds each runner's `facts_section` with the prize filled in from
its own Formguide block, then dumps leaves exactly like the live dumper. Any run
dated on or after the meeting date is dropped: 62 rows in the corpus are
post-race contamination from a re-scrape, and a class proxy built on those would
be reading the future.

Read-only with respect to the repo and the corpus: nothing on disk is rewritten.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / ".agents/skills/shared_racing/scripts"))

PRIZE_COL = 18          # cols[18] -- see engine_core.horse_prize_level
MIN_COLS = 20           # keep room for cols[19] source_race_class
HORSE_HEADER = re.compile(r"^\[(\d+)\]\s+(.+?)\s*\((\d+)\)\s*$", re.M)


def formguide_prize_maps(text: str, meeting_date: str) -> dict[str, dict]:
    """{horse number: {(date, distance_m): prize}} from one Formguide file."""
    from au_racing_engine.engine_core import _parse_formguide_entries
    out: dict[str, dict] = {}
    heads = list(HORSE_HEADER.finditer(text))
    for index, head in enumerate(heads):
        start = head.end()
        end = heads[index + 1].start() if index + 1 < len(heads) else len(text)
        block = text[start:end]
        prizes: dict[tuple[str, int], int] = {}
        for entry in _parse_formguide_entries(block, head.group(2)):
            if entry["is_trial"] or not entry["prize"]:
                continue
            if not entry["date"] or entry["date"] >= meeting_date:
                continue  # post-race contamination; never a class proxy input
            prizes[(entry["date"], int(entry["distance"]))] = int(entry["prize"])
        out[head.group(1)] = prizes
    return out


def backfill_facts(facts: str, prizes: dict) -> tuple[str, int, int]:
    """Return (facts with prize filled, rows seen, rows filled)."""
    if not prizes:
        return facts, 0, 0
    seen = filled = 0
    lines = []
    for line in facts.splitlines():
        text = line.strip()
        if not text.startswith("|") or "|---" in text:
            lines.append(line)
            continue
        cols = [c.strip() for c in text.strip("|").split("|")]
        if len(cols) < 10 or not cols or cols[0] == "#" or "試閘" in cols[1]:
            lines.append(line)
            continue
        seen += 1
        distance = re.match(r"(\d+)", cols[4] or "")
        key = (cols[2], int(distance.group(1))) if distance else None
        prize = prizes.get(key) if key else None
        if prize is None:
            lines.append(line)
            continue
        while len(cols) < MIN_COLS:
            cols.append("-")
        if not cols[PRIZE_COL] or cols[PRIZE_COL] == "-":
            cols[PRIZE_COL] = str(prize)
            filled += 1
        lines.append("| " + " | ".join(cols) + " |")
    return "\n".join(lines), seen, filled


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--audit-only", action="store_true")
    args = ap.parse_args()

    from au_archive_calibrator import (
        ARCHIVE_ROOT, HISTORICAL_RESULTS_CSV, choose_track_rows, detect_meeting_date,
        detect_meeting_track, get_true_horse_name, load_historical_results,
        normalize_horse_name, parse_int)
    from au_auto_orchestrator import _build_field_summary
    from au_dump_engine_leaves import _corpus_meeting_dirs
    from au_racing_engine.engine_core import (
        RacingEngine, backfill_pf_metrics, horse_prize_level, refresh_pf_own_l600)
    from au_racing_engine.scoring import FEATURE_KEYS

    results = load_historical_results(HISTORICAL_RESULTS_CSV)
    races_out, runners = [], 0
    rows_seen = rows_filled = 0
    cover = defaultdict(lambda: [0, 0, 0])  # month: runners, level before, level after

    for meeting_dir in _corpus_meeting_dirs(ARCHIVE_ROOT):
        logic_files = sorted(meeting_dir.glob("Race_*_Logic.json"),
                             key=lambda p: parse_int(p.stem.split("_")[1], 999))
        if not logic_files:
            continue
        sample = json.loads(logic_files[0].read_text(encoding="utf-8"))
        date = detect_meeting_date(meeting_dir)
        track = detect_meeting_track(meeting_dir, sample)
        if not date or not track:
            continue
        guides: dict[int, dict] = {}
        for path in meeting_dir.glob("*Formguide*.md"):
            race = re.search(r"Race\s*(\d+)", path.name)
            if race:
                guides[int(race.group(1))] = formguide_prize_maps(
                    path.read_text(encoding="utf-8", errors="replace"), date)

        for logic_path in logic_files:
            logic = json.loads(logic_path.read_text(encoding="utf-8"))
            race_analysis = logic.get("race_analysis", {})
            race_no = (parse_int(race_analysis.get("race_number"))
                       or parse_int(logic_path.stem.split("_")[1]))
            rows = choose_track_rows(results.get((date, race_no), []), track)
            if not rows:
                continue
            lookup = {normalize_horse_name(r["horse_slug"]): r for r in rows}
            horses = logic.get("horses", {})
            prize_map = guides.get(race_no, {})

            # Rewrite facts BEFORE the field summary: the class adjustment is
            # own-level minus the field median, and both sides must come from
            # the same measurement or the comparison is meaningless.
            patched = {}
            for hnum, horse in horses.items():
                if not isinstance(horse, dict):
                    continue
                data = dict(horse.get("_data") or {})
                facts = data.get("facts_section", "")
                month = date[:7]
                if facts:
                    cover[month][0] += 1
                    if horse_prize_level(facts) is not None:
                        cover[month][1] += 1
                    new_facts, seen, filled = backfill_facts(
                        facts, prize_map.get(str(hnum), {}))
                    rows_seen += seen
                    rows_filled += filled
                    data["facts_section"] = new_facts
                    if horse_prize_level(new_facts) is not None:
                        cover[month][2] += 1
                patched[hnum] = {**horse, "_data": data}
            horses = patched
            logic["horses"] = horses

            facts_path = meeting_dir / f"{date[5:]} Race {race_no} Facts.md"
            try:
                backfill_pf_metrics(logic, facts_path)
                refresh_pf_own_l600(logic, facts_path)
            except Exception:  # noqa: BLE001 — matches the live dumper
                pass
            ctx = dict(race_analysis)
            ctx["field_summary"] = _build_field_summary(horses)
            ctx["field_horse_names"] = [h.get("horse_name") for h in horses.values()
                                        if isinstance(h, dict) and h.get("horse_name")]
            if args.audit_only:
                continue

            out_rows = []
            for hnum, horse in horses.items():
                row = lookup.get(normalize_horse_name(get_true_horse_name(horse)))
                if not row:
                    continue
                hd = dict(horse)
                hd.setdefault("horse_number", hnum)
                eng = RacingEngine(hd, ctx,
                                   facts_section=(hd.get("_data") or {}).get("facts_section", ""),
                                   facts_path=str(meeting_dir / f"{date}_dummy.md"))
                res = eng.analyze_horse()
                fs = res.get("feature_scores") or {}
                runners += 1
                out_rows.append({
                    "n": parse_int(hnum) or 999,
                    "name": get_true_horse_name(horse),
                    "pos": int(row["pos"]),
                    "sp": row.get("sp"),
                    "features": {k: round(float(60 if fs.get(k) is None else fs[k]), 6)
                                 for k in FEATURE_KEYS},
                    "wet": float(res.get("wet_form_feature") or 0.0),
                    "proven_class": float(res.get("proven_class_feature") or 0.0),
                    "ability": float(res.get("ability_score") or 0.0),
                })
            if len(out_rows) >= 4:
                races_out.append({"meeting": meeting_dir.name, "date": date,
                                  "race": race_no, "field": len(out_rows),
                                  "rows": out_rows})

    races_out.sort(key=lambda r: (r["date"], r["meeting"], r["race"]))
    if not args.audit_only:
        Path(args.out).write_text(json.dumps({"races": races_out}), encoding="utf-8")
    print(json.dumps({
        "races": len(races_out), "runners": runners,
        "facts_rows_seen": rows_seen, "facts_rows_filled": rows_filled,
        "fill_rate_pct": round(100.0 * rows_filled / max(1, rows_seen), 2),
        "class_adjust_coverage_by_month": {
            m: {"runners": v[0], "before_pct": round(100.0 * v[1] / max(1, v[0]), 1),
                "after_pct": round(100.0 * v[2] / max(1, v[0]), 1)}
            for m, v in sorted(cover.items())},
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
