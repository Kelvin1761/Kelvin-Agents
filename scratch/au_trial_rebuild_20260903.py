#!/usr/bin/env python3
"""EXP-20260903-03 candidate dumper: trial time, trial video, density double-count.

Each variant installs a patched copy of a live method built by an anchored text
substitution on `inspect.getsource`; the anchor is asserted to appear exactly
once so an upstream refactor fails loudly instead of silently scoring the
unpatched method. Offline: the live engine files are never written.
"""
from __future__ import annotations

import argparse
import inspect
import json
import re
import sys
import textwrap
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT))

VARIANTS = ("base", "t1", "t2", "t3")
TRIAL_SPEED_K = 4.0        # pre-registered encoding, not a fitted value
TRIAL_SPEED_CAP = 4.0      # keeps the old +4 ceiling
FIELD_KEY = "trial_600m_speed_field_median"

# Anchors are written at the indentation the source has AFTER `textwrap.dedent`
# strips the method's own level -- i.e. the method body sits at four spaces.
TIME_ANCHOR = """    # Maiden: trial speed as direct signal
    if is_maiden:
        tw_trial = self.data.get("timing_trial_600m_avg_speed")
        if tw_trial and tw_trial >= 17.5:
            add(tw.get("fast_trial_bonus", 4.0), "試閘時間快", f"試閘 L600 平均 {tw_trial:.2f} m/s（\u226517.5 屬快）")
            self.reason_codes.append("maiden_fast_trial_speed")
        elif tw_trial and tw_trial >= 17.0:
            add(tw.get("mid_trial_bonus", 2.0), "試閘時間中上", f"試閘 L600 平均 {tw_trial:.2f} m/s")"""

TIME_REPLACEMENT = """    # T1: field-relative trial speed, no maiden gate. An absolute m/s cut is
    # not a speed judgement -- 86.7% of observed values clear 17.0 and 39.8%
    # clear 17.5, so "fast" meant "above the median".
    tw_trial = self.data.get("timing_trial_600m_avg_speed")
    field_median = (self._field_summary() or {}).get(FIELD_KEY)
    if tw_trial and field_median is not None:
        raw = TRIAL_SPEED_K * (float(tw_trial) - float(field_median))
        delta = max(-TRIAL_SPEED_CAP, min(TRIAL_SPEED_CAP, raw))
        if abs(delta) >= 0.05:
            add(delta, "試閘時間對場內",
                f"試閘 L600 平均 {float(tw_trial):.2f} m/s vs 場內中位 "
                f"{float(field_median):.2f}")"""

VIDEO_ANCHOR = 'trial_signals = self.data.get("trial_video_signals") or {}'
VIDEO_REPLACEMENT = ('# T2: six terms fire on 12 of 20,882 runners because trial video\n'
                     '    # comments do not exist in this source (15 of 77,336 rows).\n'
                     '    trial_signals = {}')


def patched_trial_score(ec, variant: str):
    source = textwrap.dedent(inspect.getsource(ec.RacingEngine._trial_score))
    # `dedent` strips the method's own indent, so the anchors -- written at the
    # indentation they have in the file -- have to be dedented the same way or
    # they silently never match.
    if variant == "t1":
        assert source.count(TIME_ANCHOR) == 1, "trial-time anchor moved; refusing to patch"
        source = source.replace(TIME_ANCHOR, TIME_REPLACEMENT)
    elif variant == "t2":
        assert source.count(VIDEO_ANCHOR) == 1, "trial-video anchor moved; refusing to patch"
        source = source.replace(VIDEO_ANCHOR, VIDEO_REPLACEMENT)
    namespace = dict(vars(ec))
    namespace.update({"TRIAL_SPEED_K": TRIAL_SPEED_K, "TRIAL_SPEED_CAP": TRIAL_SPEED_CAP,
                      "FIELD_KEY": FIELD_KEY})
    exec(compile(source, f"<{variant}-trial-score>", "exec"), namespace)
    return namespace["_trial_score"]


def install(variant: str):
    from au_racing_engine import engine_core as ec
    if variant == "base":
        return
    if variant == "t3":
        # The double-counted term only; the maiden extra sits outside the overlap.
        ec.TRIAL_MICRO_WEIGHTS = {**ec.TRIAL_MICRO_WEIGHTS, "density_bonus": 0.0}
        return
    ec.RacingEngine._trial_score = patched_trial_score(ec, variant)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", required=True, choices=VARIANTS)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    install(args.variant)

    from au_archive_calibrator import (
        ARCHIVE_ROOT, HISTORICAL_RESULTS_CSV, choose_track_rows, detect_meeting_date,
        detect_meeting_track, get_true_horse_name, load_historical_results,
        normalize_horse_name, parse_int)
    from au_auto_orchestrator import _build_field_summary
    from au_dump_engine_leaves import _corpus_meeting_dirs
    from au_racing_engine.engine_core import (
        RacingEngine, backfill_pf_metrics, backfill_prize_column, refresh_pf_own_l600)
    from au_racing_engine.scoring import FEATURE_KEYS

    results = load_historical_results(HISTORICAL_RESULTS_CSV)
    races_out, runners, with_speed = [], 0, 0
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
            backfill_prize_column(logic, meeting_dir, race_no, date)
            facts_path = meeting_dir / f"{date[5:]} Race {race_no} Facts.md"
            try:
                backfill_pf_metrics(logic, facts_path)
                refresh_pf_own_l600(logic, facts_path)
            except Exception:  # noqa: BLE001 — matches the live dumper
                pass
            ctx = dict(race_analysis)
            summary = _build_field_summary(horses)
            # The T1 term is own-minus-field-median, so both sides must come
            # from the same measurement, built once for the whole field.
            speeds = [float(s) for h in horses.values() if isinstance(h, dict)
                      for s in [(h.get("_data") or {}).get("timing_trial_600m_avg_speed")]
                      if s]
            summary[FIELD_KEY] = median(speeds) if speeds else None
            ctx["field_summary"] = summary
            ctx["field_horse_names"] = [h.get("horse_name") for h in horses.values()
                                        if isinstance(h, dict) and h.get("horse_name")]

            out_rows = []
            for hnum, horse in horses.items():
                row = lookup.get(normalize_horse_name(get_true_horse_name(horse)))
                if not row:
                    continue
                hd = dict(horse)
                hd.setdefault("horse_number", hnum)
                data = hd.get("_data") or {}
                eng = RacingEngine(hd, ctx, facts_section=data.get("facts_section", ""),
                                   facts_path=str(meeting_dir / f"{date}_dummy.md"))
                res = eng.analyze_horse()
                fs = res.get("feature_scores") or {}
                runners += 1
                if data.get("timing_trial_600m_avg_speed"):
                    with_speed += 1
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
    Path(args.out).write_text(json.dumps({"races": races_out}), encoding="utf-8")
    print(json.dumps({"variant": args.variant, "races": len(races_out),
                      "runners": runners, "runners_with_trial_speed": with_speed,
                      "out": args.out}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
