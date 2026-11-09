"""Shadow profiles: counterfactual scores recorded next to production.

Nothing here changes the official ranking; each profile is a registered forward test.
"""

from .features.speed import SpeedScorer
from .live_priors import (
    get_recency_trainer_rating,
)
from .matrix_mapper import (
    map_features_to_matrix_scores,
)
from . import scoring
from .scoring import (DEBUT_MATRIX_WEIGHTS, MATRIX_KEYS_ALL, MATRIX_WEIGHTS, clip_score, compute_grade,
                      to_display_scale)


_WEIGHT_REFIT_T02 = {
    **MATRIX_WEIGHTS,
    # Frozen 7D candidate (stability 0.1183) split the same way as the 9D
    # mainline: trackwork keeps its 10% share of the old stability weight.
    "stability": 0.1183 * 0.9,
    "trackwork": 0.1183 * 0.1,
    "race_shape": 0.2537,
}
# Every profile that may run, in the order the orchestrator scores them by
# default.  Each one is a registered forward test (hkjc_forward_tracker.py) or a
# rollback comparator for something already live.  Adding a profile = one entry
# here, its builder below and a FORWARD_TESTS row.
#   incident_reliability          EXP-20260910-02  shadow, prospective
#   weight_refit_t02              EXP-20260928-10  shadow, 120 races
#   race_shape_st_draw70          EXP-20260929-02  shadow, 80 races
#   race_shape_legacy_unbounded   EXP-20261008-03  rollback comparator for winsor10
#   trainer_recency_st_early90    EXP-20261005-01  shadow, 80 races
#   distance_suitability_v2       EXP-20261007-05  shadow, prospective
SHADOW_PROFILES = (
    "incident_reliability",
    "weight_refit_t02",
    "race_shape_st_draw70",
    "race_shape_legacy_unbounded",
    "trainer_recency_st_early90",
    "distance_suitability_v2",
)
_WEIGHT_SHADOW_PROFILES = {"weight_refit_t02", "race_shape_st_draw70", "race_shape_legacy_unbounded"}


class ShadowProfiles:
    def build_shadow_profile(self, profile_name, base_auto=None):
        if profile_name == "incident_reliability":
            return self._build_incident_reliability_shadow(profile_name, "combined", base_auto=base_auto)
        if profile_name in _WEIGHT_SHADOW_PROFILES:
            return self._build_weight_race_shape_shadow(profile_name, base_auto=base_auto)
        if profile_name == "trainer_recency_st_early90":
            return self._build_trainer_recency_shadow(base_auto=base_auto)
        if profile_name == "distance_suitability_v2":
            return self._build_distance_suitability_v2_shadow(base_auto=base_auto)
        return None

    def _build_distance_suitability_v2_shadow(self, base_auto=None):
        """Return the frozen EXP-20261007-05 candidate without live effect."""
        auto = base_auto or self.analyze_horse()
        matrix_scores = auto.get("matrix_scores", {}) if isinstance(auto, dict) else {}
        if not isinstance(matrix_scores, dict) or not matrix_scores:
            return None
        v2 = self._distance_suitability_v2_component()
        if not v2["available"]:
            return None
        profile = scoring.DISTANCE_SUITABILITY_V2_PROFILES[v2["surface"]]
        weight = float(profile["weight"])
        cap = float(profile["cap"])
        component = 60.0 + max(-cap, min(cap, float(v2["score"]) - 60.0))
        clean_raw = float(self._ability_score(matrix_scores))
        candidate_raw = round((1.0 - weight) * clean_raw + weight * component, 2)
        candidate_score = round(to_display_scale(candidate_raw), 2)
        base_score = float(auto.get("ability_score", candidate_score))
        applied = bool(weight > 0)
        if v2["surface"] == "ST_AWT":
            reason = "AWT 完整表歷史 surface 覆蓋不足；只記錄證據，不改 shadow 排名。"
        elif v2["target_effective_n"] <= 0:
            reason = "冇目標路程 PIT 證據；候選以中性60作獨立 component。"
        else:
            reason = (
                f"同馬同場地目標路程後驗減全路程後驗；{v2['surface']} "
                f"weight={weight:.2f}, cap={cap:.0f}。"
            )
        return {
            "profile": "distance_suitability_v2",
            "applied": applied,
            "ability_score": candidate_score if applied else base_score,
            "ability_score_raw": candidate_raw if applied else float(auto.get("ability_score_raw", clean_raw)),
            "ability_delta": round((candidate_score if applied else base_score) - base_score, 2),
            "grade": compute_grade(candidate_score if applied else base_score),
            "matrix_scores": dict(matrix_scores),
            "distance_score": round(float(v2["score"]), 2),
            "component_score": round(component, 2),
            "surface": v2["surface"],
            "source": v2["source"],
            "target_effective_n": v2["target_effective_n"],
            "surface_effective_n": v2["surface_effective_n"],
            "candidate_profile": dict(profile),
            "reason": reason,
            "evidence_status": "prospective_shadow_pending_primary_gate",
        }

    def _build_trainer_recency_shadow(self, base_auto=None):
        """Forward-only ST early-season trainer-recency candidate.

        Only the trainer master-rating base changes.  Existing combo/distance/
        change context is preserved through the observed base→final delta.
        """
        auto = base_auto or self.analyze_horse()
        base_features = auto.get("feature_scores", {}) if isinstance(auto, dict) else {}
        base_matrix = auto.get("matrix_scores", {}) if isinstance(auto, dict) else {}
        if not isinstance(base_features, dict) or not isinstance(base_matrix, dict):
            return None
        eligible = (
            self._is_sha_tin_turf_context()
            and self._is_early_season_context()
            and not self._is_debut()
        )
        trainer = self._clean(self.horse_data.get("trainer"))
        recency = get_recency_trainer_rating(
            trainer,
            as_of_date=(self.race_context or {}).get("race_date"),
        ) if eligible and trainer else None
        matrix_scores = {
            key: float(base_matrix.get(key, 60.0))
            for key in MATRIX_WEIGHTS
        }
        base_trainer = float(base_features.get("trainer_score", 60.0) or 60.0)
        candidate_trainer = base_trainer
        context_delta = 0.0
        detail = auto.get("trainer_signal_detail") or self.trainer_signal_detail or {}
        if isinstance(detail, dict):
            try:
                context_delta = float(detail.get("trainer_final", base_trainer)) - float(
                    detail.get("trainer_base", base_trainer)
                )
            except (TypeError, ValueError):
                context_delta = 0.0
        applied = recency is not None
        if applied:
            candidate_trainer = clip_score(float(recency["score"]) + context_delta)
            trainer_delta = candidate_trainer - base_trainer
            matrix_scores["trainer_signal"] = round(
                clip_score(float(matrix_scores["trainer_signal"]) + 0.45 * trainer_delta),
                2,
            )
        ability_raw = round(self._ability_score(matrix_scores), 2)
        ability_score = round(to_display_scale(ability_raw), 2)
        base_ability = float(auto.get("ability_score", ability_score))
        if not eligible:
            reason = "只限9至12月沙田草地非初出馬；今場沿用production。"
        elif recency is None:
            reason = "90日trainer recency來源不可用；沿用production。"
        else:
            reason = (
                f"季初沙田前瞻shadow：練馬師90日半衰實績"
                f"（有效{float(recency['starts']):.1f}仗）取代master base；"
                "騎師、騎練組合、同程及其他維度不變。"
            )
        return {
            "profile": "trainer_recency_st_early90",
            "applied": applied,
            "ability_score": ability_score,
            "ability_score_raw": ability_raw,
            "ability_delta": round(ability_score - base_ability, 2),
            "grade": compute_grade(ability_score),
            "matrix_scores": matrix_scores,
            "trainer_base_score": round(base_trainer, 2),
            "trainer_candidate_score": round(candidate_trainer, 2),
            "trainer_context_delta": round(context_delta, 2),
            "recency_source": dict(recency) if recency else None,
            "reason": reason,
            "evidence_status": "prospective_shadow_only_posthoc_season_phase",
        }



    def _race_shape_st_draw70_score(self, auto):
        """Frozen Sha Tin turf-only forward candidate from EXP-20260929-02."""
        base_matrix = auto.get("matrix_scores", {}) if isinstance(auto, dict) else {}
        base_shape = float(base_matrix.get("race_shape", 60.0))
        detail = auto.get("race_shape_detail", {}) if isinstance(auto, dict) else {}
        detail = detail if isinstance(detail, dict) else {}
        draw = float(detail.get("draw", 60.0) or 60.0)
        fit = float(detail.get("fit", 60.0) or 60.0)
        trip = float(detail.get("trip", 60.0) or 60.0)
        applied = self._is_sha_tin_turf_context() and not self._is_debut()
        candidate = clip_score(0.70 * draw + 0.15 * fit + 0.15 * trip) if applied else base_shape
        return round(float(candidate), 2), {
            "venue": "ST_TURF" if applied else "OTHER",
            "draw": round(draw, 2),
            "historical_lane_fit": round(fit, 2),
            "historical_trip_consumption": round(trip, 2),
            "formula": "ST_TURF=0.70*draw+0.15*fit+0.15*trip; other=production",
        }, applied

    def _build_weight_race_shape_shadow(self, profile_name, base_auto=None):
        auto = base_auto or self.analyze_horse()
        base_matrix = auto.get("matrix_scores", {}) if isinstance(auto, dict) else {}
        if not isinstance(base_matrix, dict) or sorted(base_matrix) != sorted(MATRIX_KEYS_ALL):
            return None

        matrix_scores = {key: float(base_matrix.get(key, 60.0)) for key in MATRIX_KEYS_ALL}
        components = None
        shape_applied = False
        if profile_name == "race_shape_st_draw70":
            shape_score, components, shape_applied = self._race_shape_st_draw70_score(auto)
            matrix_scores["race_shape"] = shape_score
        elif profile_name == "race_shape_legacy_unbounded":
            components = {
                "formula": "rollback=unbounded production race-shape",
                "base_race_shape": round(float(matrix_scores["race_shape"]), 2),
                "status": "experimental_live_rollback_comparator",
            }

        uses_refit = profile_name == "weight_refit_t02"
        # The registered weight refit locked the debut formula.  Persist a
        # no-op shadow row for debutants so prospective coverage is auditable.
        weights = _WEIGHT_REFIT_T02 if uses_refit and not self._is_debut() else MATRIX_WEIGHTS
        if self._is_debut():
            weights = DEBUT_MATRIX_WEIGHTS
            matrix_scores = {key: float(base_matrix.get(key, 60.0)) for key in MATRIX_KEYS_ALL}
            shape_applied = False

        base_weights = DEBUT_MATRIX_WEIGHTS if self._is_debut() else MATRIX_WEIGHTS
        base_matrix_raw = sum(
            float(base_matrix.get(key, 60.0)) * weight for key, weight in base_weights.items()
        )
        fixed_raw_adjustment = float(auto.get("ability_score_raw", base_matrix_raw)) - base_matrix_raw
        ability_raw = round(
            sum(float(matrix_scores.get(key, 60.0)) * weight for key, weight in weights.items())
            + fixed_raw_adjustment,
            2,
        )
        ability_score = round(to_display_scale(ability_raw), 2)
        base_ability = float(auto.get("ability_score", ability_score))
        applied = (uses_refit and not self._is_debut()) or shape_applied
        reasons = []
        if uses_refit and not self._is_debut():
            reasons.append("固定將2pp由race-shape轉至stability")
        if shape_applied:
            reasons.append("沙田草地前瞻候選：draw 70%、fit 15%、trip 15%")
        if profile_name == "race_shape_legacy_unbounded":
            reasons.append("正式robust formula回退對照：保留未封頂race-shape")
        if self._is_debut():
            reasons.append("初出馬公式鎖定，候選不套用")

        return {
            "profile": profile_name,
            "applied": applied,
            "ability_score": ability_score,
            "ability_score_raw": ability_raw,
            "fixed_raw_adjustment": round(fixed_raw_adjustment, 4),
            "ability_delta": round(ability_score - base_ability, 2),
            "grade": compute_grade(ability_score),
            "matrix_scores": matrix_scores,
            "weights": {key: round(float(value), 4) for key, value in weights.items()},
            "race_shape_components": components,
            "reason": "；".join(reasons) + "。",
            "evidence_status": (
                "experimental_live_rollback_shadow"
                if profile_name == "race_shape_legacy_unbounded"
                else "prospective_shadow_only"
            ),
        }


    def _build_incident_reliability_shadow(self, profile_name, mode, base_auto=None):
        auto = base_auto or self.analyze_horse()
        base_features = auto.get("feature_scores", {}) if isinstance(auto, dict) else {}
        base_matrix = auto.get("matrix_scores", {}) if isinstance(auto, dict) else {}
        if not isinstance(base_features, dict) or not base_features or not isinstance(base_matrix, dict):
            return None

        latest_incident = self._latest_run_has_medical_incident()
        adjustments = []
        adjusted_horse = dict(self.horse_data)
        adjusted_data = dict(self.data)
        adjusted_horse["_data"] = adjusted_data
        l400_context = self._prior_l400_median()

        if latest_incident and mode in {"median", "combined"} and l400_context:
            adjusted_data["raw_l400"] = f"{l400_context['prior_median']:.2f}"
            adjustments.append({
                "factor": "raw_l400",
                "from": l400_context["raw_l400"],
                "to": l400_context["prior_median"],
                "why": f"最近一仗有醫療異常；改用之前{l400_context['prior_runs']}仗中位數",
            })

        if latest_incident and mode in {"reliability", "combined"}:
            l400_trend = self._clean(adjusted_data.get("l400_trend") or "")
            if "衰退中" in l400_trend:
                adjusted_data["l400_trend"] = "異常仗可靠度調整：中性"
                adjustments.append({"factor": "l400_trend", "from": "衰退中", "to": "中性", "why": "負面趨勢包含醫療異常仗"})
            energy_trend = self._clean(adjusted_data.get("energy_trend") or "")
            if "下降" in energy_trend and "⚠️" in energy_trend:
                adjusted_data["energy_trend"] = "異常仗可靠度調整：中性"
                adjustments.append({"factor": "energy_trend", "from": "下降", "to": "中性", "why": "負面趨勢包含醫療異常仗"})

        applied = bool(adjustments)
        if not applied:
            ability_raw = float(auto.get("ability_score_raw", self._ability_score(base_matrix)))
            ability_score = float(auto.get("ability_score", to_display_scale(ability_raw)))
            return {
                "profile": profile_name,
                "applied": False,
                "ability_score": round(ability_score, 2),
                "ability_score_raw": round(ability_raw, 2),
                "ability_delta": 0.0,
                "grade": auto.get("grade", compute_grade(ability_score)),
                "sectional_score": round(float(base_matrix.get("sectional", 60.0)), 2),
                "sectional_delta": 0.0,
                "matrix_scores": dict(base_matrix),
                "adjustments": [],
                "l400_context": l400_context,
                "reason": "最近一仗未有可安全辨認的醫療異常負面訊號，沿用主線評分。",
            }

        shadow_features = dict(base_features)
        speed_scorer = SpeedScorer(adjusted_horse, self.race_context)
        speed_score, _speed_note = speed_scorer.compute()
        shadow_features["speed_score"] = clip_score(speed_score)
        recalculated = map_features_to_matrix_scores(shadow_features, debut=self._is_debut())
        sectional = recalculated["sectional"]

        matrix_scores = dict(base_matrix)
        matrix_scores["sectional"] = round(clip_score(sectional), 2)
        ability_raw = round(self._ability_score(matrix_scores), 2)
        ability_score = round(to_display_scale(ability_raw), 2)
        base_ability = float(auto.get("ability_score", ability_score))
        return {
            "profile": profile_name,
            "applied": True,
            "ability_score": ability_score,
            "ability_score_raw": ability_raw,
            "ability_delta": round(ability_score - base_ability, 2),
            "grade": compute_grade(ability_score),
            "sectional_score": matrix_scores["sectional"],
            "sectional_delta": round(matrix_scores["sectional"] - float(base_matrix.get("sectional", 60.0)), 2),
            "speed_score": round(float(shadow_features["speed_score"]), 2),
            "adjustments": adjustments,
            "l400_context": l400_context,
            "matrix_scores": matrix_scores,
            "reason": "最近一仗有明確醫療異常；影子評分降低該仗對相關負面速度訊號的影響。",
        }
