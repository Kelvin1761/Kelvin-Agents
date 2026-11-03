#!/usr/bin/env python3
"""EXP-20261103-09 診斷：狀態與穩定性每條計算路喺全語料行幾多次（唔改分）。

    python3 scratch/au_stability_path_scan_20261103.py OUT.json
"""
import collections
import json
import sys
from pathlib import Path

W = Path(__file__).resolve().parents[1]
S = W / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(S))
import au_dump_engine_leaves as dump  # noqa: E402
from au_racing_engine import engine_core  # noqa: E402

C = collections.Counter()
orig = engine_core.RacingEngine.analyze_horse


def wrapped(self):
    res = orig(self)
    p = self.provenance
    fs = res.get("feature_scores") or {}
    C["horses"] += 1
    C["fq:" + str(p.get("form_quality_score"))] += 1
    C["pq:" + str(p.get("performance_quality_score"))] += 1
    C["form:" + str(p.get("form_score"))] += 1
    C["cons:" + str(p.get("consistency_score"))] += 1
    fqd = getattr(self, "form_quality_detail", {}) or {}
    if fqd.get("trip_change"):
        C["trip_change"] += 1
    if p.get("form_quality_score") == "form_quality_fallback_composite":
        C["fallback_pq:" + str(p.get("performance_quality_score"))] += 1
        C["fallback_form_ne60"] += abs(fs.get("form_score", 60) - 60) > 1e-9
        C["fallback_pq_ne60"] += abs(fs.get("performance_quality_score", 60) - 60) > 1e-9
        C["fallback_score_ne60"] += abs(fs.get("form_quality_score", 60) - 60) > 1e-9
        why = []
        if fqd.get("raw") is None: why.append("raw_none")
        elif (fqd.get("run_count") or 0) < 2: why.append("runs<2")
        if (fqd.get("field_count") or 0) < 3: why.append("field<3")
        if not fqd.get("field_stdev"): why.append("sd0")
        C["fallback_why:" + "+".join(why)] += 1
    for note_key in ("form_score", "consistency_score"):
        if "小收 −4" in str((res.get("feature_notes") or {}).get(note_key, "")):
            C["minus4:" + note_key] += 1
    return res


engine_core.RacingEngine.analyze_horse = wrapped
OUT = Path(sys.argv[1])
sys.argv = ["dump", "--out", str(OUT) + ".dump.json"]
dump.main()
OUT.write_text(json.dumps(dict(C.most_common()), ensure_ascii=False, indent=1))
print(json.dumps(dict(C.most_common()), ensure_ascii=False, indent=1))
