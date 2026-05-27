import scoring
from scoring import BaseScorer
from features.tier_loader import score_tier

class JockeyScorer(BaseScorer):
    def compute(self):
        self.score, self.reason = score_tier("jockey", self.horse_data.get("jockey", ""), "Neutral Jockey")
        
        if self.score == 60.0:
            data = self.horse_data.get("_data", {}) if isinstance(self.horse_data.get("_data"), dict) else {}
            pdf_races = data.get("pdf_overseas_races", [])
            if pdf_races:
                has_g1 = any("G1" in str(r.get("class_level", "")).upper() or "1級" in str(r.get("class_level", "")) for r in pdf_races)
                if has_g1:
                    self.score = scoring.JOCKEY_MICRO_WEIGHTS.get("overseas_g1_base", 85.0)
                    self.reason = "Overseas Jockey (G1 Level)"
                else:
                    self.score = scoring.JOCKEY_MICRO_WEIGHTS.get("overseas_base", 70.0)
                    self.reason = "Overseas Jockey"
                    
        return self.score, self.reason
