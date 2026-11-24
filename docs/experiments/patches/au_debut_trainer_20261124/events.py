#!/usr/bin/env python3
"""EXP-20261124-50 事件（見 PROTOCOL.md）。 events.py OUT.json
→ {"events": [[日期, 練馬師, 入頭三], ...]（只初出馬）, "trainer": {"meeting|race|n": 練馬師}, "debut": {"meeting|race|n": 0/1}}"""
import json, sys
from pathlib import Path
SC = Path(__file__).resolve().parents[4] / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SC)); sys.path.insert(0, str(SC.parents[2] / "shared_racing")); sys.path.insert(0, str(SC.parents[2] / "shared_racing" / "scripts"))
from au_archive_calibrator import (ARCHIVE_ROOT, HISTORICAL_RESULTS_CSV, choose_track_rows, detect_meeting_date,  # noqa: E402
                                   detect_meeting_track, get_true_horse_name, load_historical_results, normalize_horse_name)
from au_racing_engine.data_prep import refresh_career_starts  # noqa: E402
from au_racing_engine.people_overlays import norm  # noqa: E402
from corpus_paths import meeting_dirs  # noqa: E402

results = load_historical_results(HISTORICAL_RESULTS_CSV)
events, trainer, debut, n_meet = [], {}, {}, 0
for md in meeting_dirs(ARCHIVE_ROOT):
    date = detect_meeting_date(md)
    logics = sorted(md.glob("Race_*_Logic.json"))
    if not date or not logics:
        continue
    track = detect_meeting_track(md, json.loads(logics[0].read_text(encoding="utf-8")))
    n_meet += 1
    for path in logics:
        logic = json.loads(path.read_text(encoding="utf-8"))
        race_no = int(str((logic.get("race_analysis") or {}).get("race_number") or path.stem.split("_")[1]))
        refresh_career_starts(logic)
        rows = choose_track_rows(results.get((date, race_no), []), track)
        lookup = {normalize_horse_name(r["horse_slug"]): r for r in rows}
        for num, h in (logic.get("horses") or {}).items():
            if not isinstance(h, dict):
                continue
            key = f"{md.name}|{race_no}|{int(num) if str(num).isdigit() else 999}"
            tr = norm(h.get("trainer"))
            is_debut = str(h.get("career_race_starts")) == "0"
            trainer[key], debut[key] = tr, int(is_debut)
            res = lookup.get(normalize_horse_name(get_true_horse_name(h)))
            if is_debut and tr and res is not None:
                events.append([date, tr, int(int(res["pos"]) <= 3)])
events.sort()
Path(sys.argv[1]).write_text(json.dumps({"events": events, "trainer": trainer, "debut": debut}))
print("meetings", n_meet, "debut events", len(events), "first", events[0][0] if events else None,
      "pre-08-05", sum(e[0] < "2026-08-05" for e in events), "place rate", round(sum(e[2] for e in events) / max(len(events), 1), 3))
