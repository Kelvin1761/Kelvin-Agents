#!/usr/bin/env python3
"""EXP-20261103-11 診斷：逐匹記錄近績質素分走邊條路（場內 z／後備組合／海外代理），對齊 dump 行。

    python3 scratch/au_stability_fallback_rows_20261103.py OUT.json
→ OUT.json.dump.json（普通 dump）＋ OUT.json：{"<meeting>|<race>|<n>": {path, runs, career}}
"""
import json
import sys
from pathlib import Path

W = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(W / ".agents/skills/au_racing/au_wong_choi_auto/scripts"))
import au_dump_engine_leaves as dump  # noqa: E402
from au_racing_engine import engine_core  # noqa: E402

ROWS = {}
orig = engine_core.RacingEngine.analyze_horse


def wrapped(self):
    res = orig(self)
    meeting = Path(str(self.facts_path)).parent.name
    race = int(str(self.race_context.get("race_number") or 0) or 0)
    fqd = getattr(self, "form_quality_detail", {}) or {}
    ROWS[f"{meeting}|{race}|{self.horse_data.get('horse_number')}"] = {
        "path": self.provenance.get("form_quality_score"), "runs": fqd.get("run_count"),
        "career": self._career_starts()}
    return res


engine_core.RacingEngine.analyze_horse = wrapped
OUT = Path(sys.argv[1])
sys.argv = ["dump", "--out", str(OUT) + ".dump.json"]
dump.main()
OUT.write_text(json.dumps(ROWS))
print("rows", len(ROWS))
