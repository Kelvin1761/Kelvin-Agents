"""全部維度逐個組件 dump（同 hkjc_eval_harness run 一樣嘅 PIT 回放路徑），畀「每個標籤有冇訊號」審計用。

每匹馬寫：名次、raw、每個維度嘅 components（key／label／score／weight）、段速逐項（factor／delta）、
騎練逐項調整（factor／target／delta）、檔位走位 terms（label／score／scored）、同程調整、overlays。
用法：PYTHONDONTWRITEBYTECODE=1 python3 docs/experiments/patches/hkjc_component_dump.py <out.jsonl>
"""
import contextlib
import io
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
H = REPO / ".agents/skills/hkjc_racing/hkjc_reflector/scripts"
sys.path.insert(0, str(H))
import hkjc_eval_harness as harness  # noqa: E402


def main():
    os.environ.setdefault("WC_DISABLE_HKJC_PROFILE_ENRICH", "1")
    os.environ.setdefault("WC_DISABLE_POST_SUCCESS_DEPLOY", "1")
    import hkjc_auto_orchestrator as orch
    import pit_backtest
    import rescore_backtest
    orch._atomic_write_json = lambda *a, **k: None
    orch.write_prepared_race_outputs = lambda *a, **k: (Path("x.md"), Path("x.csv"))
    orch.HKJCAutoOrchestrator._emit_event = lambda *a, **k: None
    all_rows = pit_backtest.load_all_rows()
    out = open(sys.argv[1], "w", encoding="utf-8")
    for md in harness.discover_meetings(harness._default_root()):
        day = harness.MEETING_RE.match(md.name).group(1)
        pit_backtest.inject_as_of(all_rows, day)
        actual = rescore_backtest.load_results(rescore_backtest.find_results_json(md))
        o = orch.HKJCAutoOrchestrator(md)
        for rf in sorted(md.glob("Race_*_Logic.json"), key=rescore_backtest.race_num_from_path):
            rn = rescore_backtest.race_num_from_path(rf)
            if rn not in actual:
                continue
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    logic = o.score_race(rf)
            except Exception:  # noqa: BLE001
                continue
            if not logic:
                continue
            horses = []
            for num, h in (logic.get("horses") or {}).items():
                a = (h or {}).get("python_auto") or {}
                if not a:
                    continue
                horses.append({
                    "n": int(num), "pos": actual[rn].get(int(num)), "raw": a.get("ability_score_raw"),
                    "debut": any("debut" in str(c).lower() for c in a.get("reason_codes") or []),
                    "dims": {k: [{"key": c.get("key"), "label": c.get("label"), "score": c.get("score"), "weight": c.get("weight")}
                                 for c in (v.get("components") or [])] for k, v in (a.get("matrix_reasoning") or {}).items()},
                    "m": a.get("matrix_scores"),
                    "speed": [{"factor": d.get("factor"), "delta": d.get("delta")} for d in a.get("speed_detail") or []],
                    "jt": [{"factor": d.get("factor"), "target": d.get("target"), "delta": d.get("delta")}
                           for d in ((a.get("trainer_signal_detail") or {}).get("adjustments") or [])],
                    "shape": [{"label": t.get("label"), "score": t.get("score"), "scored": t.get("scored")}
                              for t in ((a.get("race_shape_detail") or {}).get("terms") or [])],
                    "dist_adj": (a.get("distance_suitability_adjustment") or {}).get("raw_adjustment"),
                })
            out.write(json.dumps({"meeting": md.name, "race": rn, "date": day, "horses": horses}, ensure_ascii=False) + "\n")
        print(md.name, file=sys.stderr, flush=True)
    out.close()


if __name__ == "__main__":
    main()
