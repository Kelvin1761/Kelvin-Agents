from hkjc_racing_engine.scoring import BaseScorer
from hkjc_racing_engine.features.tier_loader import score_tier


class TrainerScorer(BaseScorer):
    def compute(self):
        from hkjc_racing_engine.features.jockey import continuous_rating
        rated = continuous_rating(
            "trainer",
            self.horse_data.get("trainer", ""),
            as_of_date=(self.race_context or {}).get("race_date"),
        )
        if rated is not None:
            self.score, self.reason = rated
            return self.score, self.reason
        # 本地實績同層級表都冇 → 中性 60。以前會用**匹馬**嘅海外班次（G1 85／G2-3 75／70）
        # 或者抄騎師層級代替，量嘅係匹馬／騎師唔係練馬師（EXP-20261111-12，§7）。
        as_of_date = (self.race_context or {}).get("race_date")
        self.score, self.reason = score_tier(
            "trainer", self.horse_data.get("trainer", ""), "Neutral Trainer", as_of_date=as_of_date
        )
        return self.score, self.reason
