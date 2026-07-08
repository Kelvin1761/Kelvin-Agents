import scoring
from scoring import BaseScorer

class FormScorer(BaseScorer):
    def compute(self):
        data = self.horse_data.get("_data", {}) if isinstance(self.horse_data.get("_data"), dict) else {}
        form = self.horse_data.get("last_6_finishes", "N/A")
        
        scores = []
        ranks = []  # keep the actual finishing positions so the note can be specific

        # 1. Parse local form
        if form != "N/A" and form != "" and str(form).replace("-", "").replace("N/A", "").strip():
            parts = str(form).replace("-", " ").replace(",", " ").split()
            for p in parts:
                try:
                    if "/" in p:
                        rank = int(p.split("/")[0])
                    else:
                        rank = int(p)
                    ranks.append(rank)
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

            # Build a SPECIFIC Chinese note (finishes + top3/win counts). No filler
            # like 越近仗權重越高 (計法解釋唔幫到落注)。海外賽績唔混入呢句 —
            # 由 engine 嘅「海外往績判讀」獨立交代。
            used = ranks[:6]
            wins = sum(1 for r in ranks if r == 1)
            top3 = sum(1 for r in ranks if r <= 3)
            poor = sum(1 for r in ranks if r >= 8)
            bits = [f"近{len(used)}仗名次 {'-'.join(str(r) for r in used)}"] if used else []
            detail = []
            if wins:
                detail.append(f"{wins}冠")
            if top3:
                detail.append(f"{top3}次前三")
            if poor:
                detail.append(f"{poor}次八名以後")
            if detail:
                bits.append("、".join(detail))
            overseas_used = len(scores) - local_count
            if overseas_used:
                if not used:
                    bits.append(f"未有香港賽績，以{overseas_used}仗海外賽績計（見海外往績判讀）")
                else:
                    bits.append(f"另計{overseas_used}仗海外賽績（見海外往績判讀）")
            self.reason = "；".join(bits)
            return self.score, self.reason

        self.score = 60.0
        self.reason = "No recent form (Neutral)"
        return self.score, self.reason
