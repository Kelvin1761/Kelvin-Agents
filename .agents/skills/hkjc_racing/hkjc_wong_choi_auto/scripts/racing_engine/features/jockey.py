import scoring
from scoring import BaseScorer
from features.tier_loader import score_tier


def real_overseas_rows(pdf_races):
    """Drop placeholder rows (all-dash) so an empty overseas table is not treated
    as real overseas history. The PDF extractor emits stub rows of '-' that were
    spuriously bumping unknown jockeys/trainers to the 70 'overseas' tier."""
    rows = []
    for r in pdf_races or []:
        if isinstance(r, dict) and any(
            str(r.get(k, "-")).strip() not in ("-", "", "N/A", "--")
            for k in ("class_level", "rank", "time", "margin")
        ):
            rows.append(r)
    return rows


class JockeyScorer(BaseScorer):
    def compute(self):
        self.score, self.reason = score_tier("jockey", self.horse_data.get("jockey", ""), "Neutral Jockey")

        if self.score == 60.0:
            data = self.horse_data.get("_data", {}) if isinstance(self.horse_data.get("_data"), dict) else {}
            pdf_races = real_overseas_rows(data.get("pdf_overseas_races", []))
            if pdf_races:
                has_g1 = any("G1" in str(r.get("class_level", "")).upper() or "1級" in str(r.get("class_level", "")) for r in pdf_races)
                if has_g1:
                    self.score = scoring.JOCKEY_MICRO_WEIGHTS.get("overseas_g1_base", 85.0)
                    self.reason = "Overseas Jockey (G1 Level)"
                else:
                    self.score = scoring.JOCKEY_MICRO_WEIGHTS.get("overseas_base", 70.0)
                    self.reason = "Overseas Jockey"
                    
        return self.score, self.reason
