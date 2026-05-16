from scoring import BaseScorer
from features.tier_loader import score_tier

class TrainerScorer(BaseScorer):
    def compute(self):
        self.score, self.reason = score_tier("trainer", self.horse_data.get("trainer", ""), "Neutral Trainer")
        return self.score, self.reason
