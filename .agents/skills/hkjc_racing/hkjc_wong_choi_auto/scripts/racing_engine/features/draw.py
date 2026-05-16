from scoring import BaseScorer

class DrawScorer(BaseScorer):
    def compute(self):
        draw = self.horse_data.get("barrier") or self.horse_data.get("draw")
        try:
            draw = int(draw)
        except (ValueError, TypeError):
            return 60.0, "Invalid Draw"

        if draw <= 4:
            self.score = 75.0
            self.reason = "Inside Draw (+15)"
        elif draw <= 8:
            self.score = 65.0
            self.reason = "Middle Draw (+5)"
        else:
            self.score = 50.0
            self.reason = "Outside Draw (-10)"
        return self.score, self.reason
