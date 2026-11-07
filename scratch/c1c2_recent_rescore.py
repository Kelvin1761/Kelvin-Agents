#!/usr/bin/env python3
"""C1 vs C2 vs BASE on recent AU meetings — re-score the SAME pre-race snapshot inputs.

Read-only on production: every chosen pre-race snapshot is copied (copy2, keeps
mtime so the going-refresh rule behaves as live) into <out>/snaps/<snap>/<meeting>/,
then scored in memory with `au_auto_orchestrator.score_logic_data` (no writes);
the re-scored Logic is written under <out>/<arm>/<snap>/<meeting>/ only.

Arms (one process each, ARM=a|b|c):
  a  C2 formula (current main) + C2 refit weights (current main)  — live model
  b  C1 formula (prize z clipped to ±0.5/SD_PCT) + C1 §8 refit last-window weights
  c  BASE formula (no prize discount) + pre-C2 weights (rollback values in dimensions.py)

Snapshot choice and results joining reuse au_window_review (last snapshot before each
race's start time; Race_Results_Reflector.md + canonical results CSV).

    PYTHONDONTWRITEBYTECODE=1 python3 scratch/c1c2_recent_rescore.py --arm a \
        --since 2026-10-31 --until 2026-11-06 --out <dir>
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SCRIPTS))

import au_window_review as wr  # noqa: E402  (sets shared_racing paths)
from au_racing_engine import stability as stab  # noqa: E402
from au_racing_engine import scoring  # noqa: E402

SCHED = Path("/Users/imac/wongchoi-scheduler/.agents/skills/au_racing")

WEIGHTS = {
    "a": None,  # current main (C2 refit)
    "b": {"stability": 0.34370312474498765, "pace_perf": 0.10428479805064007,
          "jockey_trainer": 0.7336734540424185, "class_weight": 0.32529328225351956,
          "track": 0.10048767539790801, "preparation": 0.31631083599481424},
    "c": {"stability": 0.37099725005319806, "pace_perf": 0.12093934478578448 * 0.941744,
          "jockey_trainer": 0.6626585553070451, "class_weight": 0.3826193901797637,
          "track": 0.14114297066700832, "preparation": 0.25244110196132946},
}
Z_PLACE_MAX = 0.5 / stab.SD_PCT


def make_digest(arm):
    def prize_term(z, pct):
        if arm == "a":
            return z * (1.0 - pct) if z > 0 else z
        if arm == "b":
            return max(-Z_PLACE_MAX, min(Z_PLACE_MAX, z))
        return z

    def digest(runs):
        values = []
        for run in runs:
            finish, starters = int(run.get("finish_pos") or 0), int(run.get("starters") or 0)
            if not (starters >= 2 and 1 <= finish <= starters):
                continue
            pct = (finish - 1) / (starters - 1)
            z_place = (0.5 - pct) / stab.SD_PCT
            z_raw = (math.log10(float(run["prize"])) - stab.MU_LOG_PRIZE) / stab.SD_LOG_PRIZE
            z_prize = prize_term(z_raw, pct)
            values.append((run, (z_place + z_prize) / 2, z_place, z_prize, z_raw))
        if len(values) < stab.MIN_RUNS:
            return {}
        weights = stab.RECENCY_WEIGHTS[: len(values)]
        raw = sum(v[1] * w for v, w in zip(values, weights)) / sum(weights)
        return {"raw": round(raw, 6), "run_count": len(values),
                "runs": [{"date": r.get("date"), "finish_pos": r.get("finish_pos"),
                          "starters": r.get("starters"), "prize": r.get("prize"),
                          "distance": r.get("distance"), "value": round(v, 6),
                          "z_place": round(zp, 4), "z_prize": round(zq, 4),
                          "z_prize_raw": round(zr, 4), "weight": w}
                         for (r, v, zp, zq, zr), w in zip(values, weights)]}
    return digest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=["a", "b", "c", "snap"], required=True)
    ap.add_argument("--since", required=True)
    ap.add_argument("--until", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    if args.arm in ("a", "b", "c"):
        stab.digest = make_digest(args.arm)
        if WEIGHTS[args.arm]:
            assert set(WEIGHTS[args.arm]) == set(scoring.MATRIX_WEIGHTS), scoring.MATRIX_WEIGHTS
            scoring.MATRIX_WEIGHTS.update(WEIGHTS[args.arm])
        from au_auto_orchestrator import score_logic_data  # noqa: E402
    print("arm", args.arm, "weights", dict(scoring.MATRIX_WEIGHTS), flush=True)

    root = Path(wr.AU_RACING)
    csv_idx = wr.load_results_csv(wr.au_historical_results_csv(root), args.since, args.until)
    starts_for = wr.load_start_times(SCHED / "data/sb_archive_meeting_ids.json", SCHED / ".sportsbet_cache")
    races, skipped = [], []
    for meeting in wr.meeting_dirs(root):
        day = meeting.name[:10]
        if not (args.since <= day <= args.until):
            continue
        stamped = wr.stamped_snapshots(meeting)
        starts = starts_for(meeting.name)
        numbers = sorted({int(p.stem.split("_")[1]) for _, s in stamped for p in s.glob("Race_*_Logic.json")})
        results = wr.parse_reflector_results(meeting / "Race_Results_Reflector.md")
        for race_no in numbers:
            snap, rule, local = wr.pick_for_race(stamped, starts.get(race_no), meeting, day)
            if snap is None:
                skipped.append({"meeting": meeting.name, "race": race_no, "skip": "no_pre_race_snapshot"})
                continue
            use = snap
            if args.arm != "snap":
                base = out / "snaps" / snap.name / meeting.name
                if not base.exists():
                    tmp = base.with_name(base.name + ".tmp")
                    shutil.rmtree(tmp, ignore_errors=True)
                    shutil.copytree(snap, tmp, copy_function=shutil.copy2)
                    try:
                        tmp.rename(base)
                    except OSError:
                        shutil.rmtree(tmp, ignore_errors=True)  # another arm won the race
                src = base / f"Race_{race_no}_Logic.json"
                dest_dir = out / args.arm / snap.name / meeting.name
                dest_dir.mkdir(parents=True, exist_ok=True)
                try:
                    data = score_logic_data(src)
                except Exception as exc:  # noqa: BLE001
                    skipped.append({"meeting": meeting.name, "race": race_no, "skip": f"score_error: {exc!r}"[:300]})
                    continue
                (dest_dir / src.name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                use = dest_dir
            row = wr.build_race(meeting, use, race_no, day, results, csv_idx)
            if row is None:
                skipped.append({"meeting": meeting.name, "race": race_no, "skip": "bad_logic"})
            elif "skip" in row:
                skipped.append(row)
            else:
                row.update(snapshot=snap.name, snapshot_rule=rule, snapshot_local=local)
                for x in row["rows"]:
                    for k in ("features", "matrix", "missing", "risk_flags"):
                        x.pop(k, None)
                races.append(row)
        print(meeting.name, len(races), flush=True)
    dest = out / f"arm_{args.arm}.json"
    dest.write_text(json.dumps({"arm": args.arm, "weights": dict(scoring.MATRIX_WEIGHTS),
                                "races": races, "skipped": skipped}, ensure_ascii=False), encoding="utf-8")
    print("races", len(races), "skipped", len(skipped), "→", dest)


if __name__ == "__main__":
    main()
