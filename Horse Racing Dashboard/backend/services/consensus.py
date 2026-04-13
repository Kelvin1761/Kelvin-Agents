"""
Consensus Engine — Compares dual analyst picks and calculates agreement/disagreement.
For HKJC races with both Kelvin and Heison analyses.
"""
from typing import Optional
from models.race import RaceAnalysis, TopPick, HorseAnalysis


def find_consensus_horses(
    kelvin_race: RaceAnalysis,
    heison_race: RaceAnalysis,
    top_n: int = 2
) -> dict:
    """Find consensus horses between two analysts' Top picks.
    
    Consensus logic (from user's betting rules):
    - Top 2 交叉匹配: if a horse appears in BOTH analysts' Top 2  → 共識馬
    - Top 4 overlap: horses appearing in both analysts' Top 4
    
    Returns:
        dict with consensus_horses, kelvin_only, heison_only, disagreements
    """
    kelvin_top2 = {p.horse_number for p in kelvin_race.top_picks[:top_n]}
    heison_top2 = {p.horse_number for p in heison_race.top_picks[:top_n]}
    
    kelvin_top4 = {p.horse_number for p in kelvin_race.top_picks[:4]}
    heison_top4 = {p.horse_number for p in heison_race.top_picks[:4]}
    
    # Core consensus: Top 2 intersection
    top2_consensus = kelvin_top2 & heison_top2
    
    # Extended consensus: Top 4 intersection
    top4_overlap = kelvin_top4 & heison_top4
    
    # Build results with details from both analysts
    consensus_horses = []
    for horse_num in top2_consensus:
        k_pick = next((p for p in kelvin_race.top_picks if p.horse_number == horse_num), None)
        h_pick = next((p for p in heison_race.top_picks if p.horse_number == horse_num), None)
        
        consensus_horses.append({
            "horse_number": horse_num,
            "horse_name": k_pick.horse_name if k_pick else "",
            "kelvin_rank": k_pick.rank if k_pick else None,
            "heison_rank": h_pick.rank if h_pick else None,
            "kelvin_grade": k_pick.grade if k_pick else None,
            "heison_grade": h_pick.grade if h_pick else None,
            "is_top2_consensus": True,
        })
    
    # Add Top 4 overlap horses (excluding those already in top2 consensus)
    for horse_num in top4_overlap - top2_consensus:
        k_pick = next((p for p in kelvin_race.top_picks if p.horse_number == horse_num), None)
        h_pick = next((p for p in heison_race.top_picks if p.horse_number == horse_num), None)
        
        consensus_horses.append({
            "horse_number": horse_num,
            "horse_name": k_pick.horse_name if k_pick else "",
            "kelvin_rank": k_pick.rank if k_pick else None,
            "heison_rank": h_pick.rank if h_pick else None,
            "kelvin_grade": k_pick.grade if k_pick else None,
            "heison_grade": h_pick.grade if h_pick else None,
            "is_top2_consensus": False,
        })
    
    # Kelvin-only picks (in top 4 but not in Heison's top 4)
    kelvin_only = []
    for horse_num in kelvin_top4 - heison_top4:
        pick = next((p for p in kelvin_race.top_picks if p.horse_number == horse_num), None)
        if pick:
            kelvin_only.append({
                "horse_number": horse_num,
                "horse_name": pick.horse_name,
                "rank": pick.rank,
                "grade": pick.grade,
            })
    
    # Heison-only picks
    heison_only = []
    for horse_num in heison_top4 - kelvin_top4:
        pick = next((p for p in heison_race.top_picks if p.horse_number == horse_num), None)
        if pick:
            heison_only.append({
                "horse_number": horse_num,
                "horse_name": pick.horse_name,
                "rank": pick.rank,
                "grade": pick.grade,
            })
    
    return {
        "consensus_horses": consensus_horses,
        "kelvin_only": kelvin_only,
        "heison_only": heison_only,
        "consensus_count": len(top2_consensus),
        "top4_overlap_count": len(top4_overlap),
    }


def find_rating_disagreements(
    kelvin_race: RaceAnalysis,
    heison_race: RaceAnalysis,
    threshold: int = 2
) -> list[dict]:
    """Find horses where two analysts disagree by ≥ threshold grades.
    
    Grade order: S > A+ > A > A- > B+ > B > B- > C+ > C > C- > D+ > D > D-
    """
    grade_order = ['S+', 'S', 'S-', 'A+', 'A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'C-', 'D+', 'D', 'D-']
    
    def grade_index(g: Optional[str]) -> int:
        if not g:
            return -1
        return grade_order.index(g) if g in grade_order else -1
    
    disagreements = []
    
    # Build lookup by horse number
    kelvin_horses = {h.horse_number: h for h in kelvin_race.horses}
    heison_horses = {h.horse_number: h for h in heison_race.horses}
    
    for horse_num in set(kelvin_horses.keys()) & set(heison_horses.keys()):
        k = kelvin_horses[horse_num]
        h = heison_horses[horse_num]
        
        k_idx = grade_index(k.final_grade)
        h_idx = grade_index(h.final_grade)
        
        if k_idx >= 0 and h_idx >= 0 and abs(k_idx - h_idx) >= threshold:
            disagreements.append({
                "horse_number": horse_num,
                "horse_name": k.horse_name,
                "kelvin_grade": k.final_grade,
                "heison_grade": h.final_grade,
                "gap": abs(k_idx - h_idx),
                "higher_analyst": "Kelvin" if k_idx < h_idx else "Heison",
            })
    
    return sorted(disagreements, key=lambda d: d["gap"], reverse=True)


def get_betting_suggestions(
    consensus_result: dict,
    min_odds_consensus: float = 2.0,
    min_odds_extended: float = 3.0,
) -> list[dict]:
    """Generate betting suggestions based on consensus horses and odds rules.
    
    Rules:
    - Top 2 consensus horse: bet if place odds > min_odds_consensus (default 2.0)
    - Top 4 overlap horse: bet if place odds > min_odds_extended (default 3.0)
    """
    suggestions = []
    
    for horse in consensus_result["consensus_horses"]:
        min_odds = min_odds_consensus if horse["is_top2_consensus"] else min_odds_extended
        
        suggestions.append({
            "horse_number": horse["horse_number"],
            "horse_name": horse["horse_name"],
            "consensus_type": "Top 2 共識" if horse["is_top2_consensus"] else "Top 4 重疊",
            "min_odds_required": min_odds,
            "kelvin_grade": horse.get("kelvin_grade"),
            "heison_grade": horse.get("heison_grade"),
        })
    
    return suggestions
