#!/usr/bin/env python3
"""Rich per-horse dump of the whole AU archive, scored once with today's engine.

Everything downstream (competitiveness metrics, catastrophic-miss cohorts,
big-field weight tuning) reads this file so we never re-score per experiment.
Captures the 7 matrix dimensions, the raw feature scores, data coverage, and the
race context needed to slice by field size / venue / class.
"""
import json, re, sys
from pathlib import Path
sys.path.insert(0, "/Users/imac/Antigravity-repo")
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/au_racing/au_wong_choi_auto/scripts")
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/au_racing/au_wong_choi_auto/scripts/racing_engine")
from wongchoi_paths import AU_RACING
from au_racing_engine.engine_core import RacingEngine
from au_racing_engine.matrix_mapper import map_features_to_matrix_scores

OUT = Path("/Users/imac/Antigravity-repo/scratch/au_bigfield_dump.json")
HEADERS = Path("/Users/imac/Antigravity-repo/scratch/au_racecard_headers.json")


def main() -> None:
    out = json.loads(OUT.read_text()) if OUT.exists() else {}
    headers = json.loads(HEADERS.read_text()) if HEADERS.exists() else {}
    dirs = [d for d in sorted(AU_RACING.iterdir())
            if d.is_dir() and re.match(r"\d{4}-\d{2}-\d{2}\s", d.name)]
    for d in dirs:
        if d.name in out:
            continue
        venue_m = re.match(r"(\d{4}-\d{2}-\d{2})\s+(.+?)\s+Race", d.name) or \
                  re.match(r"(\d{4}-\d{2}-\d{2})\s+(.+)$", d.name)
        date = venue_m.group(1) if venue_m else d.name[:10]
        venue = (venue_m.group(2) if venue_m else "").strip()
        meeting = {}
        for lp in sorted(d.glob("Race_*_Logic.json")):
            m = re.search(r"Race_(\d+)_Logic", lp.name)
            if not m or lp.stat().st_size < 1000:
                continue
            try:
                data = json.loads(lp.read_text(encoding="utf-8"))
            except Exception:
                continue
            ctx = dict(data.get("race_analysis") or {})
            horses = data.get("horses") or {}
            ctx.setdefault("field_summary", {"count": len(horses)})
            rno = m.group(1)
            hdr = headers.get(f"{d.name}|{rno}", "")
            rows = {}
            for num, h in horses.items():
                hh = dict(h)
                hh.setdefault("horse_number", num)
                try:
                    auto = RacingEngine(hh, ctx).analyze_horse()
                except Exception:
                    continue
                fs = dict(auto["feature_scores"])
                mx = map_features_to_matrix_scores(fs)
                cov = auto.get("data_coverage") or {}
                rows[num] = {
                    "name": h.get("horse_name"),
                    "ability": auto.get("ability_score"),
                    "wet": auto.get("wet_form_feature", 0.0),
                    "mx": {k: round(v, 3) for k, v in mx.items()},
                    "fs": {k: round(v, 2) for k, v in fs.items()},
                    "cov": cov.get("coverage_pct"),
                    "cov_missing": cov.get("missing_features") or [],
                    "barrier": h.get("barrier"),
                    "trainer": h.get("trainer"),
                    "jockey": h.get("jockey"),
                }
            if rows:
                meeting[rno] = {
                    "field": len(rows),
                    "header": hdr,
                    "distance": ctx.get("distance"),
                    "going": (ctx.get("meeting_intelligence") or {}).get("going"),
                    "horses": rows,
                }
        if meeting:
            out[d.name] = {"date": date, "venue": venue, "races": meeting}
            OUT.write_text(json.dumps(out), encoding="utf-8")
            print(f"[{len(out)}] {d.name} ({len(meeting)} races)", flush=True)
    print(f"DONE meetings={len(out)}")


if __name__ == "__main__":
    main()
