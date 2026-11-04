"""EXP-20261105-03 arm A2：淨剷穩定性分，狀態與穩定性 = 100% 現行近績分。

非初出馬：`consistency_score` 最後一定等於 `form_score`，所以 5/9·近績 + 4/9·穩定性 = 近績
（晨操 10% 拆分 shim 唔使郁）。初出馬照行原本路徑（佢哋冇名次，郁咗會有常數位移）。

⚠️ live 嘅穩定性分有兩步：`_consistency_score`（簡單式）之後，`_apply_mainline_context`
會用 `_consistency_shadow_detail`（逐仗連輸距覆核）覆蓋。所以要喺第二步之後先改，
淨係 patch `_consistency_score` 喺 harness 0 場郁（第一版就係咁冇接通）。
接線證明：races_with_ranking_change > 0。
"""
ARM_NAME = "form_only"


def apply():
    from hkjc_racing_engine import engine_core

    original = engine_core.RacingEngine._apply_mainline_context

    def mainline_context(self, feature_scores, feature_notes):
        updated, notes, sources = original(self, feature_scores, feature_notes)
        if not self._is_debut():
            form = float(updated.get("form_score", 60.0))
            updated["consistency_score"] = form
            notes["consistency_score"] = f"EXP-20261105-03：穩定性分剷走，用近績分 {form:.1f}。"
            sources["consistency_score"] = "last_6_finishes"
        return updated, notes, sources

    engine_core.RacingEngine._apply_mainline_context = mainline_context
