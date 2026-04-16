"""
Race API endpoints — meetings, races, analysis, and consensus.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from fastapi import APIRouter, HTTPException
from services.meeting_detector import discover_meetings, load_meeting_races, get_meeting_summary
from services.consensus import find_consensus_horses, find_rating_disagreements, get_betting_suggestions
from models.race import Region

router = APIRouter()

# Cache meetings + parsed races in memory
_meetings_cache = None
_races_cache = {}  # {(date,venue): {analyst: [RaceAnalysis]}}


def _get_meetings():
    global _meetings_cache
    if _meetings_cache is None:
        _meetings_cache = discover_meetings()
    return _meetings_cache


def _refresh_meetings():
    global _meetings_cache, _races_cache
    _meetings_cache = discover_meetings()
    _races_cache = {}  # Invalidate race data cache too
    return _meetings_cache


def _get_races_cached(meeting):
    """Load races with caching — avoids re-parsing on every request."""
    key = (meeting.date, meeting.venue)
    if key not in _races_cache:
        _races_cache[key] = load_meeting_races(meeting)
    return _races_cache[key]


# ──────────────────────────────────────────────
# Meeting endpoints
# ──────────────────────────────────────────────

@router.get("/meetings")
def list_meetings():
    """List all available meetings."""
    meetings = _get_meetings()
    return {"meetings": get_meeting_summary(meetings)}


@router.post("/meetings/refresh")
def refresh_meetings():
    """Force refresh meeting discovery."""
    meetings = _refresh_meetings()
    return {"meetings": get_meeting_summary(meetings), "refreshed": True}


# ──────────────────────────────────────────────
# Race detail endpoints
# ──────────────────────────────────────────────

@router.get("/races/{date}/{venue}")
def get_races(date: str, venue: str, analyst: str = None):
    """Get all races for a meeting, optionally filtered by analyst."""
    meetings = _get_meetings()
    meeting = next(
        (m for m in meetings if m.date == date and m.venue == venue),
        None
    )
    if not meeting:
        raise HTTPException(status_code=404, detail=f"Meeting {date} {venue} not found")
    
    all_races = _get_races_cached(meeting)
    
    if analyst and analyst in all_races:
        races = all_races[analyst]
        return {
            "meeting": {"date": date, "venue": venue, "region": meeting.region.value},
            "analyst": analyst,
            "races": [_race_summary(r) for r in races],
        }
    
    # Return all analysts
    result = {
        "meeting": {
            "date": date,
            "venue": venue,
            "region": meeting.region.value,
            "analysts": [a.value for a in meeting.analysts],
        },
        "races_by_analyst": {}
    }
    for analyst_name, races in all_races.items():
        result["races_by_analyst"][analyst_name] = [_race_summary(r) for r in races]
    
    return result


@router.get("/race/{date}/{venue}/{race_number}")
def get_race_detail(date: str, venue: str, race_number: int, analyst: str = None):
    """Get full race analysis with all horse details."""
    meetings = _get_meetings()
    meeting = next(
        (m for m in meetings if m.date == date and m.venue == venue),
        None
    )
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    
    all_races = _get_races_cached(meeting)
    result = {}
    
    for analyst_name, races in all_races.items():
        if analyst and analyst != analyst_name:
            continue
        race = next((r for r in races if r.race_number == race_number), None)
        if race:
            result[analyst_name] = _race_detail(race)
    
    if not result:
        raise HTTPException(status_code=404, detail=f"Race {race_number} not found")
    
    return {
        "meeting": {"date": date, "venue": venue, "region": meeting.region.value},
        "race_number": race_number,
        "analyses": result,
    }


# ──────────────────────────────────────────────
# Consensus endpoint (HKJC only — dual analyst)
# ──────────────────────────────────────────────

@router.get("/consensus/{date}/{venue}/{race_number}")
def get_consensus(date: str, venue: str, race_number: int):
    """Get consensus / top picks for a race.
    HKJC: dual-analyst consensus (Kelvin × Heison).
    AU: single-analyst top 2 picks returned as candidates.
    """
    meetings = _get_meetings()
    meeting = next(
        (m for m in meetings if m.date == date and m.venue == venue),
        None
    )
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    
    all_races = _get_races_cached(meeting)
    
    # ── AU: single analyst → return Top 2 as candidates ──
    if meeting.region == Region.AU:
        analyst_name = list(all_races.keys())[0] if all_races else None
        if not analyst_name:
            raise HTTPException(status_code=404, detail="No analyst data found")
        races = all_races[analyst_name]
        race = next((r for r in races if r.race_number == race_number), None)
        if not race:
            raise HTTPException(status_code=404, detail=f"Race {race_number} not found")
        
        top2 = race.top_picks[:2]
        candidates = []
        for pick in top2:
            # Find horse details for jockey/trainer
            horse = next((h for h in race.horses if h.horse_number == pick.horse_number), None)
            candidates.append({
                "horse_number": pick.horse_number,
                "horse_name": pick.horse_name,
                "kelvin_rank": pick.rank,
                "heison_rank": None,
                "kelvin_grade": pick.grade,
                "heison_grade": None,
                "is_top2_consensus": True,
                "jockey": horse.jockey if horse else None,
                "trainer": horse.trainer if horse else None,
            })
        
        return {
            "race_number": race_number,
            "region": "au",
            "consensus": {
                "consensus_horses": candidates,
                "kelvin_only": [],
                "heison_only": [],
                "consensus_count": len(candidates),
                "top4_overlap_count": len(candidates),
            },
            "disagreements": [],
            "betting_suggestions": [
                {
                    "horse_number": c["horse_number"],
                    "horse_name": c["horse_name"],
                    "consensus_type": "Top 2 精選",
                    "min_odds_required": 2.0,
                    "kelvin_grade": c["kelvin_grade"],
                    "heison_grade": None,
                }
                for c in candidates
            ],
        }
    
    # ── HKJC: dual-analyst consensus ──
    kelvin_races = all_races.get("Kelvin", [])
    heison_races = all_races.get("Heison", [])
    
    kelvin_race = next((r for r in kelvin_races if r.race_number == race_number), None)
    heison_race = next((r for r in heison_races if r.race_number == race_number), None)
    
    if not kelvin_race or not heison_race:
        raise HTTPException(
            status_code=404,
            detail=f"Need both Kelvin and Heison analysis for Race {race_number}"
        )
    
    consensus = find_consensus_horses(kelvin_race, heison_race)
    disagreements = find_rating_disagreements(kelvin_race, heison_race)
    suggestions = get_betting_suggestions(consensus)
    
    # Enrich consensus horses with jockey/trainer from kelvin's data
    for horse_data in consensus.get("consensus_horses", []):
        horse = next((h for h in kelvin_race.horses if h.horse_number == horse_data["horse_number"]), None)
        if horse:
            horse_data["jockey"] = horse.jockey
            horse_data["trainer"] = horse.trainer
    
    return {
        "race_number": race_number,
        "region": "hkjc",
        "consensus": consensus,
        "disagreements": disagreements,
        "betting_suggestions": suggestions,
    }


# ──────────────────────────────────────────────
# Horse comparison endpoint
# ──────────────────────────────────────────────

@router.get("/compare/{date}/{venue}/{race_number}/{horse1}/{horse2}")
def compare_horses(date: str, venue: str, race_number: int, horse1: int, horse2: int, analyst: str = "Kelvin"):
    """Compare two horses side-by-side."""
    meetings = _get_meetings()
    meeting = next(
        (m for m in meetings if m.date == date and m.venue == venue),
        None
    )
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    
    all_races = _get_races_cached(meeting)
    races = all_races.get(analyst, [])
    race = next((r for r in races if r.race_number == race_number), None)
    if not race:
        raise HTTPException(status_code=404, detail="Race not found")
    
    h1 = next((h for h in race.horses if h.horse_number == horse1), None)
    h2 = next((h for h in race.horses if h.horse_number == horse2), None)
    
    if not h1 or not h2:
        raise HTTPException(status_code=404, detail="One or both horses not found")
    
    return {
        "horse1": h1.dict(),
        "horse2": h2.dict(),
        "analyst": analyst,
    }


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _race_summary(race):
    """Lightweight race summary for listing."""
    return {
        "race_number": race.race_number,
        "distance": race.distance,
        "race_class": race.race_class,
        "race_name": race.race_name,
        "track": race.track,
        "venue": race.venue,
        "horses_count": len(race.horses),
        "top_picks_count": len(race.top_picks),
        "top_picks": [
            {
                "rank": p.rank,
                "horse_number": p.horse_number,
                "horse_name": p.horse_name,
                "grade": p.grade,
            }
            for p in race.top_picks
        ],
        "monte_carlo_top3": [
            {
                "mc_rank": p.mc_rank,
                "horse_number": p.horse_number,
                "horse_name": p.horse_name,
                "win_pct": p.win_pct,
                "predicted_odds": p.predicted_odds,
            }
            for p in (race.monte_carlo_simulation or [])[:3]
        ],
    }


def _race_detail(race):
    """Full race analysis detail."""
    return {
        "race_number": race.race_number,
        "distance": race.distance,
        "race_class": race.race_class,
        "race_name": race.race_name,
        "track": race.track,
        "venue": race.venue,
        "going": race.going,
        "pace_prediction": race.pace_prediction,
        "battlefield_overview": race.battlefield_overview,
        "verdict_text": race.verdict_text,
        "blind_spots": race.blind_spots,
        "confidence": race.confidence,
        "key_variable": race.key_variable,
        "horses": [h.dict() for h in race.horses],
        "top_picks": [p.dict() for p in race.top_picks],
        "scenario_top_picks": {
            k: [p.dict() for p in v]
            for k, v in (race.scenario_top_picks or {}).items()
        } if race.scenario_top_picks else None,
        "monte_carlo_simulation": [
            p.dict() for p in (race.monte_carlo_simulation or [])
        ],
        "monte_carlo_results": [
            _map_mc_pick(p) for p in (race.monte_carlo_simulation or [])
        ],
        "underhorse_signals": race.underhorse_signals,
    }


def _map_mc_pick(p):
    """Map MonteCarloPick to frontend-friendly field names."""
    import re as _re
    # Parse "$6.10" → 6.1
    def _parse_odds(s):
        if not s:
            return None
        m = _re.search(r'([\d.]+)', s)
        return float(m.group(1)) if m else None

    # Parse "🥇 #1" or "#3" → int
    def _parse_rank(s):
        if not s:
            return None
        m = _re.search(r'#?(\d+)', s)
        return int(m.group(1)) if m else None

    return {
        "mc_rank": p.mc_rank,
        "horse_num": p.horse_number,
        "name": p.horse_name,
        "win_prob": p.win_pct,
        "predicted_odds": _parse_odds(p.predicted_odds),
        "predicted_odds_str": p.predicted_odds,
        "predicted_place_odds": _parse_odds(p.predicted_place_odds),
        "predicted_place_odds_str": p.predicted_place_odds,
        "top3_pct": p.top3_pct,
        "top4_pct": p.top4_pct,
        "original_rank": _parse_rank(p.forensic_rank),
        "forensic_rank_str": p.forensic_rank,
        "agreement": p.divergence,
    }
