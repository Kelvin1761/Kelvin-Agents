"""Independent production-path check of the pre-registered fallback rule."""
import copy
import re

ARM_NAME = "fallback_same_scale"


def apply():
    from hkjc_racing_engine.engine_core import RacingEngine

    original = RacingEngine._consistency_score

    def same_scale(self, features):
        if self._is_debut() or self._consistency_shadow_detail() is not None:
            return original(self, features)
        ranks = [int(x) for x in re.findall(r"\b\d+\b", str(self.horse_data.get("last_6_finishes") or ""))[:6] if int(x) > 0]
        if not ranks:
            return original(self, features)
        horse = copy.deepcopy(self.horse_data)
        horse.setdefault("_data", {})["recent_6_detail"] = " | ".join(
            f"第{i+1}仗: {rank}名 N/A" for i, rank in enumerate(ranks))
        detail = RacingEngine(horse, self.race_context)._consistency_shadow_detail()
        return detail["score"], "按已知名次套用同一穩定性公式，輸距維持缺值。", "audit_fallback_same_scale"

    RacingEngine._consistency_score = same_scale
