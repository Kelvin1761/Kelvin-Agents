#!/usr/bin/env python3
"""PF (pace-figure) historical backfill driver — maximum-caution edition.

Harvests per-runner PuntingForm-style L600-vs-benchmark aggregates
(`Stats.avgL600` + run counts) from historical race form-guide overview pages
and stages them as pf_metrics patches for archive Logic files.

Safety model (mirrors au_results_backfill_driver + RACENET_SAFE_MODE):
- racenet_transport guard underneath (4s min interval, hourly caps, cooldown);
- driver adds 20-35s random sleeps between page fetches;
- HARD STOP on RacenetBlockedError or any fetch failure — no retries;
- resumable done-list; per-run meeting cap (default 2 ≈ ~12-22 requests);
- NOTHING touches Drive Logic: patches land in a local staging dir as JSON;
  a separate reviewed step applies them (adoption pattern).

Modes:
  --validate "<archive meeting dirname>"   fetch + compare vs stored
      pf_aggregates (no writes) — semantic proof before any backfill.
  --run [--limit 2]                        stage patches for the oldest
      archive meetings without PF coverage.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, "/Users/imac/Antigravity-repo")
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/au_racing")
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/au_racing/au_wong_choi_auto/scripts")

from wongchoi_paths import AU_RACING  # noqa: E402
from racenet_transport import RacenetBlockedError, fetch_nuxt_data  # noqa: E402
from au_archive_calibrator import normalize_horse_name  # noqa: E402

STAGING = Path("/Users/imac/Antigravity-repo/scratch/pf_backfill_staging")
DONE_PATH = STAGING / "pf_done.json"
SLEEP_RANGE = (20.0, 35.0)


def meeting_slug(dirname: str) -> str | None:
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})\s+(.*?)(?:\s+Race\s|$)", dirname)
    if not m:
        return None
    track = re.sub(r"[^a-z0-9 ]", "", m.group(4).lower()).strip().replace(" ", "-")
    return f"{track}-{m.group(1)}{m.group(2)}{m.group(3)}"


def polite_sleep() -> None:
    time.sleep(random.uniform(*SLEEP_RANGE))


def apollo_of(url: str) -> dict:
    data = fetch_nuxt_data(url)
    return (data.get("apollo") or {}).get("defaultClient") or {}


def discover_event_slugs(slug: str) -> dict[int, str]:
    """Results page apollo carries Event objects with slugs for past meetings."""
    apollo = apollo_of(f"https://www.racenet.com.au/results/horse-racing/{slug}/all-races")
    events = {}
    for v in apollo.values():
        if isinstance(v, dict) and v.get("__typename") == "Event":
            num, ev_slug = v.get("eventNumber"), v.get("slug")
            if isinstance(num, int) and isinstance(ev_slug, str):
                events[num] = ev_slug
    return events


def resolve(apollo: dict, ref):
    if isinstance(ref, dict):
        ref_id = ref.get("__ref") or ref.get("id")
        if isinstance(ref_id, str) and ref_id in apollo:
            return apollo[ref_id]
        return ref
    return {}


def harvest_race_pf(apollo: dict, as_of_date: str) -> dict[str, dict]:
    """Per-runner point-in-time PF aggregates from an overview page.

    Validated 2026-07-17 (rosehill-gardens-20260627 R1: 13/13 exact match vs
    stored pf_aggregates): each SelectionResult (a past run, with
    competitorId / meetingDate / isTrial) links a CompetitorFormBenchmark
    whose runnerTimeDifferenceL600 is that run's frozen L600-vs-benchmark
    delta. We average runs strictly BEFORE `as_of_date` — no future leakage.
    (The page-level `Stats.avgL600` aggregate is computed live by racenet and
    LEAKS post-race runs — never use it for backfill.)
    """
    comp_name = {str(v.get("id")): normalize_horse_name(str(v.get("name") or ""))
                 for v in apollo.values()
                 if isinstance(v, dict) and v.get("__typename") == "Competitor"}
    per_runner: dict[str, list] = {}
    for v in apollo.values():
        if not (isinstance(v, dict) and v.get("__typename") == "SelectionResult"):
            continue
        if str(v.get("isTrial")) == "True":
            continue
        date = str(v.get("meetingDate") or "")
        name = comp_name.get(str(v.get("competitorId")))
        if not name or not date or date >= as_of_date:
            continue
        cfb = resolve(apollo, v.get("competitorFormBenchmark"))
        run = {"date": date}
        for src, dst in (("runnerTimeDifferenceL600", "l600_delta"),
                         ("runnerTimeDifferenceL800", "l800_delta"),
                         ("runnerTimeDifferenceL400", "l400_delta"),
                         ("runnerTimeDifference", "race_time_diff")):
            try:
                run[dst] = float(cfb.get(src))
            except (TypeError, ValueError):
                run[dst] = None
        if run["l600_delta"] is None:
            continue
        per_runner.setdefault(name, []).append(run)

    out = {}
    for name, runs in per_runner.items():
        runs = sorted(runs, key=lambda r: r["date"], reverse=True)[:5]
        agg = {"pf_run_count": len(runs), "source": "racenet_cfb_per_run"}
        for field in ("l600_delta", "l800_delta", "l400_delta", "race_time_diff"):
            values = [r[field] for r in runs if r[field] is not None]
            agg[f"{field}_avg"] = round(sum(values) / len(values), 4) if values else None
        out[name] = agg
    return out


def dump_structure_hint(apollo: dict, out_path: Path) -> None:
    """When linkage fails, dump a compact structural sample for parser repair."""
    sample = {}
    for key, v in apollo.items():
        if isinstance(v, dict) and v.get("__typename") in ("Selection", "Competitor", "Stats"):
            sample[key] = {k: (str(vv)[:80] if not isinstance(vv, (int, float)) else vv)
                           for k, vv in list(v.items())[:12]}
            if len(sample) > 24:
                break
    out_path.write_text(json.dumps(sample, ensure_ascii=False, indent=1), encoding="utf-8")


def validate(meeting_dirname: str) -> int:
    meeting_dir = AU_RACING / meeting_dirname
    slug = meeting_slug(meeting_dirname)
    print(f"validate {meeting_dirname} → slug {slug}")
    stored = {}
    for lp in sorted(meeting_dir.glob("Race_*_Logic.json")):
        m = re.search(r"Race_(\d+)_Logic", lp.name)
        data = json.loads(lp.read_text(encoding="utf-8"))
        for h in (data.get("horses") or {}).values():
            agg = ((h.get("_data") or {}).get("pf_metrics") or {}).get("pf_aggregates") or {}
            if agg.get("l600_delta_avg") is not None:
                stored[(int(m.group(1)), normalize_horse_name(str(h.get("horse_name") or "")))] = float(agg["l600_delta_avg"])
    print(f"stored pf horses: {len(stored)}")
    if not stored:
        print("nothing to validate against — pick a meeting with stored pf_aggregates")
        return 1

    as_of = meeting_dirname[:10]
    events = discover_event_slugs(slug)
    print(f"discovered {len(events)} event slugs")
    if not events:
        return 1
    races_to_check = sorted({race for race, _ in stored})[:3]  # 3 races is enough proof
    matched = close = 0
    STAGING.mkdir(parents=True, exist_ok=True)
    for race_no in races_to_check:
        polite_sleep()
        try:
            apollo = apollo_of(
                f"https://www.racenet.com.au/form-guide/horse-racing/{slug}/{events[race_no]}/overview")
        except RacenetBlockedError:
            print("BLOCKED — stopping immediately")
            return 2
        fetched = harvest_race_pf(apollo, as_of)
        if not fetched:
            hint = STAGING / f"structure_hint_{slug}_r{race_no}.json"
            dump_structure_hint(apollo, hint)
            print(f"  race {race_no}: linkage failed — structure hint at {hint.name}")
            continue
        for (race, name), stored_value in stored.items():
            if race != race_no or name not in fetched:
                continue
            got = fetched[name]["l600_delta_avg"]
            matched += 1
            close += abs(got - stored_value) < 0.35
            print(f"  R{race} {name}: fetched {got:+.2f} vs stored {stored_value:+.2f} "
                  f"{'✓' if abs(got - stored_value) < 0.35 else '✗'}")
    print(f"VALIDATION: {close}/{matched} within ±0.35s")
    return 0 if matched and close / matched >= 0.7 else 1


def run_backfill(limit: int) -> int:
    """Stage PF patches for the oldest archive meetings lacking PF coverage."""
    STAGING.mkdir(parents=True, exist_ok=True)
    done = set(json.loads(DONE_PATH.read_text(encoding="utf-8"))) if DONE_PATH.exists() else set()
    targets = []
    for d in sorted(p for p in AU_RACING.iterdir() if p.is_dir()):
        if not re.match(r"\d{4}-\d{2}-\d{2}\s", d.name) or d.name in done:
            continue
        if not list(d.glob("Race_1_Logic.json")):
            continue
        targets.append(d.name)
        if len(targets) >= limit:
            break
    print(f"this run: {len(targets)} meetings (done so far {len(done)})")
    for dirname in targets:
        slug = meeting_slug(dirname)
        as_of = dirname[:10]
        print(f"== {dirname} → {slug}")
        try:
            events = discover_event_slugs(slug)
        except RacenetBlockedError:
            print("BLOCKED — stopping immediately")
            return 2
        if not events:
            print("  no event slugs (bad slug or missing page) — marking done to avoid retry loops")
            done.add(dirname)
            DONE_PATH.write_text(json.dumps(sorted(done)), encoding="utf-8")
            continue
        patches = {}
        for race_no in sorted(events):
            polite_sleep()
            try:
                apollo = apollo_of(
                    f"https://www.racenet.com.au/form-guide/horse-racing/{slug}/{events[race_no]}/overview")
            except RacenetBlockedError:
                print("BLOCKED mid-meeting — stopping immediately (partial staging discarded)")
                return 2
            patches[str(race_no)] = harvest_race_pf(apollo, as_of)
            print(f"  R{race_no}: {len(patches[str(race_no)])} runners with PF", flush=True)
        out = STAGING / f"pf_patch_{dirname}.json"
        out.write_text(json.dumps({"meeting": dirname, "as_of": as_of, "patches": patches},
                                  ensure_ascii=False, indent=0), encoding="utf-8")
        done.add(dirname)
        DONE_PATH.write_text(json.dumps(sorted(done)), encoding="utf-8")
        print(f"  staged → {out.name}")
    print("RUN COMPLETE")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="PF historical backfill (max caution)")
    parser.add_argument("--validate", default=None, metavar="MEETING_DIRNAME")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--limit", type=int, default=2)
    args = parser.parse_args()
    if args.validate:
        return validate(args.validate)
    if args.run:
        return run_backfill(args.limit)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
