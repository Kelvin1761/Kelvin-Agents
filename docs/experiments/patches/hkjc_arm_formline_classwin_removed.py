"""EXP-20261112-17b arm（訊號檢查之後加，跑 A/B 之前寫死）：剷走賽績線「對手後續更高／同／較低班再贏」+3／+1／−1。
訊號檢查：舊計法模型之上每分 −0.011 [−0.028,+0.005]；改成同原場比之後 −0.032 [−0.054,−0.011]（加分方向錯）。Fixed."""
ARM_NAME = "formline_classwin_removed"


def apply():
    import hkjc_auto_orchestrator as orch

    original = orch._load_formline_opponent_summaries

    def patched(logic_path, race_context, horses):
        summaries = original(logic_path, race_context, horses)
        for summary in summaries.values():
            for key in ("formline_higher_win_count", "formline_same_win_count", "formline_lower_win_count"):
                summary[key] = 0
        return summaries

    orch._load_formline_opponent_summaries = patched
