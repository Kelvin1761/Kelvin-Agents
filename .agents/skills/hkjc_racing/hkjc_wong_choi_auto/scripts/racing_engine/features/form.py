from scoring import BaseScorer

class FormScorer(BaseScorer):
    def compute(self):
        form = self.horse_data.get("last_6_finishes", "N/A")
        if form == "N/A":
            self.score = 60.0
            self.reason = "No recent form (Neutral)"
            return self.score, self.reason
            
        # Parse form (e.g., "1 2 3" or "1/14")
        scores = []
        parts = form.replace("-", " ").replace(",", " ").split()
        for p in parts:
            try:
                # Handle "1/14" format
                if "/" in p:
                    rank = int(p.split("/")[0])
                else:
                    rank = int(p)
                
                if rank == 1: scores.append(100)
                elif rank == 2: scores.append(85)
                elif rank == 3: scores.append(75)
                elif rank <= 5: scores.append(60)
                else: scores.append(40)
            except ValueError:
                continue
                
        if not scores:
            return 60.0, "Indeterminable form"
            
        # Weighted average (recent is more important)
        weighted_sum = 0
        total_weight = 0
        for i, s in enumerate(reversed(scores)):
            weight = 1.0 / (i + 1)
            weighted_sum += s * weight
            total_weight += weight
            
        self.score = weighted_sum / total_weight
        self.reason = f"Form Score calculated from {len(scores)} starts"
        return self.score, self.reason
