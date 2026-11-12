"""EXP-20261112-17 arm：賽績線「對手後續更高／同／較低班再贏」改為同**原場班次**比（定義見 hkjc_label_fix_common.py）。
只換 formline_higher／same／lower_win_count（入分 +3／+1／−1，上限 +8）；文字摘要唔郁。Fixed, nothing fitted."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
ARM_NAME = "formline_original_class"


def apply():
    import hkjc_auto_orchestrator as orch
    from hkjc_label_fix_common import formline_counts_vs_original

    original = orch._load_formline_opponent_summaries

    def patched(logic_path, race_context, horses):
        summaries = original(logic_path, race_context, horses)
        facts_path = orch._facts_path_for_logic(logic_path, race_context.get("race_number"))
        if not facts_path or not facts_path.exists():
            return summaries
        text = facts_path.read_text(encoding="utf-8")
        for num, summary in summaries.items():
            horse = horses.get(num) if num in horses else next((h for k, h in horses.items() if str(k) == str(num)), None)
            if not isinstance(horse, dict):
                continue
            section = orch._section_for_horse(text, num)
            counts = formline_counts_vs_original(section or "", (horse.get("_data") or {}).get("recent_6_detail"),
                                                 orch._class_rank, orch.CLASS_RANK_MAP)
            summary["formline_higher_win_count"] = counts["higher"]
            summary["formline_same_win_count"] = counts["same"]
            summary["formline_lower_win_count"] = counts["lower"]
        return summaries

    orch._load_formline_opponent_summaries = patched
