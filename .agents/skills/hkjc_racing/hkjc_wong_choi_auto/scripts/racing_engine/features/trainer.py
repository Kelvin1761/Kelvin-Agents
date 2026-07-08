import scoring
from scoring import BaseScorer
from features.tier_loader import score_tier
from features.jockey import real_overseas_rows

class TrainerScorer(BaseScorer):
    def compute(self):
        from features.jockey import continuous_rating
        rated = continuous_rating("trainer", self.horse_data.get("trainer", ""))
        if rated is not None:
            self.score, self.reason = rated
            return self.score, self.reason
        self.score, self.reason = score_tier("trainer", self.horse_data.get("trainer", ""), "Neutral Trainer")

        if self.score == 60.0:
            data = self.horse_data.get("_data", {}) if isinstance(self.horse_data.get("_data"), dict) else {}
            pdf_races = real_overseas_rows(data.get("pdf_overseas_races", []))
            if pdf_races:
                has_g1 = any("G1" in str(r.get("class_level", "")).upper() or "1級" in str(r.get("class_level", "")) for r in pdf_races)
                if has_g1:
                    self.score = scoring.TRAINER_MICRO_WEIGHTS.get("overseas_g1_base", 85.0)
                    self.reason = "Overseas Trainer (G1 Level)"
                else:
                    has_g23 = any("G2" in str(r.get("class_level", "")).upper() or "2級" in str(r.get("class_level", "")) or "G3" in str(r.get("class_level", "")).upper() or "3級" in str(r.get("class_level", "")) for r in pdf_races)
                    if has_g23:
                        self.score = scoring.TRAINER_MICRO_WEIGHTS.get("overseas_g23_base", 75.0)
                        self.reason = "Overseas Trainer (G2/G3 Level)"
                    else:
                        jockey_score, _ = score_tier("jockey", self.horse_data.get("jockey", ""), "Neutral Jockey")
                        if jockey_score > 60.0:
                            self.score = jockey_score
                            self.reason = "Overseas Trainer (Aligns with Jockey Tier)"
                        else:
                            self.score = scoring.TRAINER_MICRO_WEIGHTS.get("overseas_base", 70.0)
                            self.reason = "Overseas Trainer"
                            
        return self.score, self.reason
