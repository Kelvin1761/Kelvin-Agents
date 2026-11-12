"""EXP-20261112-19 B（Kelvin：「路程配合應唔應該喺同程表現」）：由段速分拎走「路程配合」，同樣分數（±1.5 leaf 分）
加落「同程表現」維度個 leaf（leaf = 60 + 調整 ÷ 權重，所以加 1.5 分 = raw 調整 + 1.5 × 同程權重）。Fixed."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
ARM_NAME = "route_fit_to_distance_dim"


def apply():
    from hkjc_racing_engine.engine_core import RacingEngine
    from hkjc_racing_engine.scoring import CENTRED_MATRIX_WEIGHTS
    from hkjc_speed_factor_strip import install

    def remember(scorer, delta):
        scorer.horse_data.setdefault("_data", {})["exp_route_fit_delta"] = delta
    install("路程配合", remember)
    original = RacingEngine._distance_suitability_adjustment

    def patched(self, feature_scores, matrix_scores):
        out = original(self, feature_scores, matrix_scores)
        delta = (self.horse_data.get("_data") or {}).pop("exp_route_fit_delta", None)
        if delta:
            out = dict(out)
            out["raw_adjustment"] = float(out.get("raw_adjustment") or 0) + delta * float(CENTRED_MATRIX_WEIGHTS.get("distance_fit") or 0)
        return out

    RacingEngine._distance_suitability_adjustment = patched
