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


def continuous_rating(group, raw_name):
    """兩季實績連續評分（EB shrink）——主要來源；搵唔到先退返層級表。
    香港樣本少（客串騎師／新戰力，例如布浩榮 33 騎、韋紀力 38 騎）就同
    層級先驗做 Bayesian blend，數據儲夠自動過渡去純實績。
    Returns (score, reason) or None."""
    try:
        from live_priors import get_jt_ratings, JT_RATING_PARAMS
        hit = get_jt_ratings().lookup(group, raw_name)
    except Exception:
        hit = None
    if hit is None:
        return None
    score = float(hit["score"])
    starts = float(hit["starts"])
    prior_score, _ = score_tier(group, raw_name, "")
    # 只有「有已知先驗」（層級表有列＝客串名將/新加盟戰力）嘅細樣本先 blend；
    # 無先驗嘅細樣本騎師照用純實績（backtest：無差別拉向60會蝕 good/single）。
    if starts < JT_RATING_PARAMS["blend_below"] and float(prior_score) != 60.0:
        w = starts / (starts + JT_RATING_PARAMS["blend_k"])
        score = w * score + (1 - w) * float(prior_score)
        reason = (
            f"香港樣本僅{int(starts)}仗（勝率{hit['win_rate']:.0f}%、上名率{hit['place_rate']:.0f}%），"
            f"混合層級先驗後實績評分{score:.1f}"
        )
        return score, reason
    # 練馬師舊季有衰減（trainer_w24），starts 係加權數，講明先唔誤導
    span = "兩季加權" if group == "trainer" and float(JT_RATING_PARAMS.get("trainer_w24", 1.0)) < 1.0 else "兩季"
    reason = (
        f"{span}{int(starts)}仗：勝率{hit['win_rate']:.0f}%、"
        f"上名率{hit['place_rate']:.0f}%，實績評分{score:.1f}"
    )
    return score, reason


class JockeyScorer(BaseScorer):
    def compute(self):
        rated = continuous_rating("jockey", self.horse_data.get("jockey", ""))
        if rated is not None:
            self.score, self.reason = rated
            return self.score, self.reason
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
