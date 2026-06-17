import scoring
from scoring import BaseScorer

class FormScorer(BaseScorer):
    def compute(self):
        data = self.horse_data.get("_data", {}) if isinstance(self.horse_data.get("_data"), dict) else {}
        form = self.horse_data.get("last_6_finishes", "N/A")
        
        scores = []
        
        # 1. Parse local form
        if form != "N/A" and form != "" and str(form).replace("-", "").replace("N/A", "").strip():
            parts = str(form).replace("-", " ").replace(",", " ").split()
            for p in parts:
                try:
                    if "/" in p:
                        rank = int(p.split("/")[0])
                    else:
                        rank = int(p)
                    if rank == 1: scores.append(scoring.FORM_MICRO_WEIGHTS.get("rank_1", 100))
                    elif rank == 2: scores.append(scoring.FORM_MICRO_WEIGHTS.get("rank_2", 85))
                    elif rank == 3: scores.append(scoring.FORM_MICRO_WEIGHTS.get("rank_3", 75))
                    elif rank <= 5: scores.append(scoring.FORM_MICRO_WEIGHTS.get("rank_4_5", 60))
                    else: scores.append(scoring.FORM_MICRO_WEIGHTS.get("rank_other", 40))
                except ValueError:
                    continue

        # 2. Add overseas form if available
        local_count = len(scores)
        pdf_races = data.get("pdf_overseas_races", [])
        if pdf_races:
            for r in pdf_races:
                rank_str = str(r.get("rank", ""))
                try:
                    rank = int(rank_str.split("/")[0]) if "/" in rank_str else int(rank_str)
                    if rank == 1: scores.append(scoring.FORM_MICRO_WEIGHTS.get("rank_1", 100))
                    elif rank == 2: scores.append(scoring.FORM_MICRO_WEIGHTS.get("rank_2", 85))
                    elif rank == 3: scores.append(scoring.FORM_MICRO_WEIGHTS.get("rank_3", 75))
                    elif rank <= 5: scores.append(scoring.FORM_MICRO_WEIGHTS.get("rank_4_5", 60))
                    else: scores.append(scoring.FORM_MICRO_WEIGHTS.get("rank_other", 40))
                except ValueError:
                    continue

        if scores:
            weighted_sum = 0
            total_weight = 0
            for i, s in enumerate(scores[:6]):
                weight = 1.0 / (i + 1)
                weighted_sum += s * weight
                total_weight += weight
            self.score = weighted_sum / total_weight
            
            if len(scores) > local_count:
                self.reason = f"Form Score calculated from {len(scores)} starts (Includes Overseas)"
            else:
                self.reason = f"Form Score calculated from {len(scores)} starts"
            return self.score, self.reason

        self.score = 60.0
        self.reason = "No recent form (Neutral)"
        return self.score, self.reason
