"""EXP-20261112-16 arm：引擎型態改用「分段 − 馬會標準分段」分類（定義見 hkjc_label_fix_common.py）。
段速分讀嘅 `engine_type` 字串換成新版；冇賽績檔或者冇標準嘅馬保留原本。Fixed, nothing fitted."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
ARM_NAME = "engine_type_vs_standard"


def apply():
    import hkjc_auto_orchestrator as orch
    from hkjc_label_fix_common import engine_type_vs_standard, run_classes_from_recent
    from hkjc_racing_engine import past_runs
    from hkjc_racing_engine.features.speed import SpeedScorer

    original = orch._attach_past_runs

    def patched(logic_path, race_context, horses, meeting_date):
        n = original(logic_path, race_context, horses, meeting_date)
        path = orch._formguide_path_for_logic(logic_path, race_context.get("race_number"))
        if not path or not path.exists() or meeting_date is None:
            return n
        parsed = past_runs.parse_formguide(path.read_text(encoding="utf-8"))
        today_class = past_runs.class_code(race_context.get("race_class"))
        for num, horse in horses.items():
            entry = parsed.get(int(num)) if isinstance(horse, dict) and str(num).isdigit() else None
            if not entry:
                continue
            data = horse.setdefault("_data", {})
            runs = sorted([r for r in entry["runs"] if r["date"] < meeting_date], key=lambda r: r["date"], reverse=True)
            classes = {d: past_runs.class_code(c) for d, c in run_classes_from_recent(data.get("recent_6_detail")).items()}
            new = engine_type_vs_standard(runs, today_class, classes)
            if new:
                data["exp1112_engine_type"] = new
        return n

    orch._attach_past_runs = patched
    base_data = SpeedScorer._data

    def _data(self):
        data = base_data(self)
        new = data.get("exp1112_engine_type")
        if not new:
            return data
        out = dict(data)
        out["engine_type"] = new
        return out

    SpeedScorer._data = _data
