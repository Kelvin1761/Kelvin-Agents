#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REVIEW_PATH = ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_reflector" / "scripts" / "review_auto_weighting.py"
OUT = ROOT / ".scratch" / "hkjc_auto_feature_cache.json"


def load_review_module():
    spec = importlib.util.spec_from_file_location("review_auto_weighting", REVIEW_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def main() -> int:
    review = load_review_module()
    results_index = review.build_results_index(review.default_results_roots())
    rows = []
    for meeting_dir in review.hk_meeting_dirs(review.default_meeting_roots()):
        date = review.meeting_date(meeting_dir)
        result_path = results_index.get(date or "")
        if not result_path:
            continue
        actual_results = review.load_results(result_path)
        for logic_path in sorted(meeting_dir.glob("Race_*_Logic.json"), key=review.race_num_from_path):
            race_num = review.race_num_from_path(logic_path)
            actual_pos = actual_results.get(race_num)
            if not actual_pos:
                continue
            logic = review.json.loads(logic_path.read_text(encoding="utf-8"))
            race_context = logic.get("race_analysis", {})
            horses = []
            for horse_num_text, horse in logic.get("horses", {}).items():
                try:
                    horse_num = int(horse_num_text)
                except ValueError:
                    continue
                horses.append({
                    "horse_num": horse_num,
                    "features": review.compute_full_feature_scores(horse, race_context),
                })
            if horses:
                rows.append({
                    "meeting": str(meeting_dir),
                    "venue": "HappyValley" if "HappyValley" in meeting_dir.name else "ShaTin",
                    "race": race_num,
                    "actual_pos": actual_pos,
                    "horses": horses,
                })
    OUT.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT} races={len(rows)} horses={sum(len(row['horses']) for row in rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
