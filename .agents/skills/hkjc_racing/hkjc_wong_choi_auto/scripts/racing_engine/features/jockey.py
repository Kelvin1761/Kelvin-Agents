from scoring import BaseScorer
from features.tier_loader import score_tier

class JockeyScorer(BaseScorer):
    def compute(self):
        self.score, self.reason = score_tier("jockey", self.horse_data.get("jockey", ""), "Neutral Jockey")
        return self.score, self.reason
