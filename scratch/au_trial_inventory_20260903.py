#!/usr/bin/env python3
"""Inventory every trial-derived term: does it fire, and on how many runners?

Trial signals are spread across three dimensions (trial_score inside pace_perf,
preparation_score, and jockey_horse_fit). Before rebuilding anything, count how
often each term actually fires -- a term that never fires is not a signal, and
two terms that fire on the same runners are one signal counted twice.
Read-only; runs the live engine over stored Logic and touches nothing on disk.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".agents/skills/au_racing/au_wong_choi_auto/scripts"))
sys.path.insert(0, str(ROOT))


def main() -> int:
    from au_archive_calibrator import (
        ARCHIVE_ROOT, detect_meeting_date, detect_meeting_track, parse_int)
    from au_auto_orchestrator import _build_field_summary
    from au_dump_engine_leaves import _corpus_meeting_dirs
    from au_racing_engine.engine_core import RacingEngine, backfill_prize_column

    trial_terms: Counter = Counter()
    prep_terms: Counter = Counter()
    fit_trial_terms: Counter = Counter()
    runners = with_trials = 0
    speed_present = speed_used = maiden_runners = 0
    speed_values: list[float] = []
    speed_by_distance: dict[str, list[float]] = defaultdict(list)
    both_density = Counter()  # density_bonus and trial_ok_bonus on the same runner

    for meeting_dir in _corpus_meeting_dirs(ARCHIVE_ROOT):
        logic_files = sorted(meeting_dir.glob("Race_*_Logic.json"),
                             key=lambda p: parse_int(p.stem.split("_")[1], 999))
        if not logic_files:
            continue
        date = detect_meeting_date(meeting_dir)
        sample = json.loads(logic_files[0].read_text(encoding="utf-8"))
        if not date or not detect_meeting_track(meeting_dir, sample):
            continue
        for logic_path in logic_files:
            logic = json.loads(logic_path.read_text(encoding="utf-8"))
            race_analysis = logic.get("race_analysis", {})
            race_no = (parse_int(race_analysis.get("race_number"))
                       or parse_int(logic_path.stem.split("_")[1]))
            backfill_prize_column(logic, meeting_dir, race_no, date)
            horses = logic.get("horses", {})
            ctx = dict(race_analysis)
            ctx["field_summary"] = _build_field_summary(horses)
            ctx["field_horse_names"] = [h.get("horse_name") for h in horses.values()
                                        if isinstance(h, dict) and h.get("horse_name")]
            for hnum, horse in horses.items():
                if not isinstance(horse, dict):
                    continue
                hd = dict(horse)
                hd.setdefault("horse_number", hnum)
                data = hd.get("_data") or {}
                eng = RacingEngine(hd, ctx, facts_section=data.get("facts_section", ""),
                                   facts_path=str(meeting_dir / f"{date}_dummy.md"))
                auto = eng.analyze_horse()
                runners += 1
                maiden = eng._is_maiden_race()
                maiden_runners += 1 if maiden else 0

                speed = data.get("timing_trial_600m_avg_speed")
                if speed:
                    speed_present += 1
                    speed_values.append(float(speed))
                    places = eng._trial_places()
                    if places:
                        # bucket by the most recent trial's distance when known
                        speed_by_distance["all"].append(float(speed))
                    if maiden and float(speed) >= 17.0:
                        speed_used += 1

                detail = getattr(eng, "trial_detail", None) or {}
                factors = {a["factor"] for a in (detail.get("adjustments") or [])}
                if detail.get("adjustments") is not None and eng._trial_places():
                    with_trials += 1
                for f in factors:
                    trial_terms[f] += 1
                prep = (auto.get("preparation_detail") or {}).get("adjustments") or []
                prep_factors = {a["factor"] for a in prep}
                for f in prep_factors:
                    prep_terms[f] += 1
                fit = (auto.get("jt_fit_detail") or {}).get("adjustments") or []
                for a in fit:
                    if "試閘" in a["factor"]:
                        fit_trial_terms[a["factor"]] += 1
                if "試閘密度高兼交代穩" in factors and any(
                        "試閘交代密度足夠" in f for f in prep_factors):
                    both_density["both"] += 1
                elif "試閘密度高兼交代穩" in factors:
                    both_density["trial_only"] += 1
                elif any("試閘交代密度足夠" in f for f in prep_factors):
                    both_density["prep_only"] += 1

    values = sorted(speed_values)
    out = {
        "runners": runners,
        "runners_with_trials": with_trials,
        "maiden_race_runners": maiden_runners,
        "trial_score_terms": dict(trial_terms.most_common()),
        "preparation_terms": dict(prep_terms.most_common()),
        "jockey_fit_trial_terms": dict(fit_trial_terms.most_common()),
        "density_overlap": dict(both_density),
        "trial_600m_speed": {
            "present": speed_present,
            "present_pct": round(100.0 * speed_present / max(1, runners), 2),
            "scored_maiden_and_over_17": speed_used,
            "scored_pct_of_all_runners": round(100.0 * speed_used / max(1, runners), 2),
            "min": values[0] if values else None,
            "p25": values[len(values) // 4] if values else None,
            "median": values[len(values) // 2] if values else None,
            "p75": values[3 * len(values) // 4] if values else None,
            "max": values[-1] if values else None,
            "pct_at_or_above_17_5": round(
                100.0 * sum(1 for v in values if v >= 17.5) / max(1, len(values)), 2),
            "pct_at_or_above_17_0": round(
                100.0 * sum(1 for v in values if v >= 17.0) / max(1, len(values)), 2),
        },
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
