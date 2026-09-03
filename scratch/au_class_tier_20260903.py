#!/usr/bin/env python3
"""EXP-20260903-01 candidate dumper. Offline; never edits the live engine.

Each variant installs a patched copy of a live method built by an anchored text
substitution on `inspect.getsource`. The anchor is asserted to appear exactly
once, so a refactor upstream makes this script fail loudly instead of silently
scoring the unpatched method.

Variants (see the experiment record for the pre-registration):
  base  no patch, reproduces the live engine
  k1    class_mult forced to 1.0
  k2    entry tier from the run's own `source_race_class`, missing -> neutral
  k3    k2 plus one tier step down for a non-metro historical venue
  k4    proven_class only: exact class level minus 5.0 for a non-metro run
"""
from __future__ import annotations

import argparse
import inspect
import json
import os
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT))

VARIANTS = ("base", "k1", "k2", "k3", "k4")
COUNTRY_LEVEL_DISCOUNT = 5.0  # pre-registered encoding, not a fitted value


def _patched_form_score(ec, variant: str):
    """Return a `_form_score` whose entry tier comes from the variant's rule."""
    source = textwrap.dedent(inspect.getsource(ec.RacingEngine._form_score))
    anchor = 'entry_tier = self._get_class_tier(entry.get("class", ""))'
    assert source.count(anchor) == 1, "form-score class anchor moved; refusing to patch"
    if variant == "k1":
        # Neutralise: today's tier compared with itself gives delta 0 -> mult 1.0.
        replacement = "entry_tier = today_tier"
    else:
        replacement = "entry_tier = _variant_entry_tier(self, entry, today_tier)"
    source = source.replace(anchor, replacement)
    namespace = dict(vars(ec))
    namespace["_variant_entry_tier"] = _make_entry_tier(ec, variant)
    exec(compile(source, f"<{variant}-form-score>", "exec"), namespace)
    return namespace["_form_score"]


def _make_entry_tier(ec, variant: str):
    metro_tokens = ec.METRO_VENUE_TOKENS

    def entry_tier(engine, entry, today_tier):
        label = str(entry.get("source_race_class") or "").strip()
        if not label:
            # No raw label is "no evidence", which must stay neutral. Scoring it
            # as a class drop would punish the sparse half of the corpus for a
            # extraction gap rather than for anything the horse did.
            return today_tier
        tier = engine._get_class_tier(label)
        if variant == "k3":
            venue = str(entry.get("venue") or "").lower()
            if venue and not any(token in venue for token in metro_tokens):
                tier = min(8, tier + 1)  # a country BM79 is not a metro BM79
        return tier

    return entry_tier


def _patched_proven_class(ec):
    """`horse_proven_class_level` with a non-metro level discount."""
    source = textwrap.dedent(inspect.getsource(ec.horse_proven_class_level))
    anchor = "        level = exact_race_class_level(source_class)"
    assert source.count(anchor) == 1, "proven-class anchor moved; refusing to patch"
    source = source.replace(
        anchor,
        "        level = exact_race_class_level(source_class)\n"
        "        if level is not None and not _is_metro_venue(cols[3]):\n"
        "            level -= COUNTRY_LEVEL_DISCOUNT",
    )
    namespace = dict(vars(ec))
    namespace["COUNTRY_LEVEL_DISCOUNT"] = COUNTRY_LEVEL_DISCOUNT
    namespace["_is_metro_venue"] = lambda v: any(
        t in str(v or "").lower() for t in ec.METRO_VENUE_TOKENS)
    exec(compile(source, "<k4-proven-class>", "exec"), namespace)
    return namespace["horse_proven_class_level"]


def install(variant: str):
    from au_racing_engine import engine_core as ec
    if variant == "base":
        return
    if variant == "k4":
        ec.horse_proven_class_level = _patched_proven_class(ec)
        return
    ec.RacingEngine._form_score = _patched_form_score(ec, variant)


def dump(variant: str, out: Path) -> dict:
    from au_archive_calibrator import (
        ARCHIVE_ROOT, HISTORICAL_RESULTS_CSV, choose_track_rows, detect_meeting_date,
        detect_meeting_track, get_true_horse_name, load_historical_results,
        normalize_horse_name, parse_int)
    from au_auto_orchestrator import _build_field_summary
    from au_dump_engine_leaves import _corpus_meeting_dirs
    from au_racing_engine.engine_core import (
        RacingEngine, backfill_pf_metrics, refresh_pf_own_l600)
    from au_racing_engine.scoring import FEATURE_KEYS

    results = load_historical_results(HISTORICAL_RESULTS_CSV)
    races_out, runners = [], 0
    mixed_tier_races = 0  # power precondition for k4 (see the record)
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
            out_rows, race_tiers = [], set()
            for hnum, horse in horses.items():
                row = lookup.get(normalize_horse_name(get_true_horse_name(horse)))
                if not row:
                    continue
                hd = dict(horse)
                hd.setdefault("horse_number", hnum)
                facts = (hd.get("_data") or {}).get("facts_section", "")
                eng = RacingEngine(hd, ctx, facts_section=facts,
                                   facts_path=str(meeting_dir / f"{date}_dummy.md"))
                res = eng.analyze_horse()
                fs = res.get("feature_scores") or {}
                runners += 1
                for entry in eng._official_entries()[:4]:
                    venue = str(entry.get("venue") or "").lower()
                    if venue:
                        race_tiers.add(any(t in venue for t in
                                           __import__("au_racing_engine.engine_core",
                                                      fromlist=["x"]).METRO_VENUE_TOKENS))
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
            if len(race_tiers) > 1:
                mixed_tier_races += 1
            if len(out_rows) >= 4:
                races_out.append({"meeting": meeting_dir.name, "date": date,
                                  "race": race_no, "field": len(out_rows),
                                  "rows": out_rows})
    races_out.sort(key=lambda r: (r["date"], r["meeting"], r["race"]))
    out.write_text(json.dumps({"races": races_out}), encoding="utf-8")
    return {"variant": variant, "races": len(races_out), "runners": runners,
            "mixed_venue_tier_races": mixed_tier_races, "out": str(out)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", required=True, choices=VARIANTS)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    install(args.variant)
    print(json.dumps(dump(args.variant, Path(args.out)), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
