"""
Bets API — record bets, update results, view ROI.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from services.bet_tracker import create_bet, create_bets_batch, update_bet_result, get_bets, get_bets_by_race, get_roi_summary, delete_bet
from services.summary_importer import get_summary_roi

router = APIRouter()


class BetCreate(BaseModel):
    date: str
    venue: str
    region: str = 'hkjc'
    race_number: int
    horse_number: int
    horse_name: str
    jockey: Optional[str] = None
    trainer: Optional[str] = None
    bet_type: str = 'place'
    stake: float = 1
    odds: Optional[float] = None
    consensus_type: Optional[str] = None
    kelvin_grade: Optional[str] = None
    heison_grade: Optional[str] = None
    notes: Optional[str] = None
    track_type: Optional[str] = None
    going: Optional[str] = None



class BetResultUpdate(BaseModel):
    result_position: int
    payout: float


@router.post("/bets")
def place_bet(bet: BetCreate):
    """Record a new bet."""
    result = create_bet(**bet.model_dump())
    return {"bet": result, "message": "Bet recorded"}


@router.post("/bets/batch")
def place_bets_batch(bets: List[BetCreate]):
    """Record multiple bets at once."""
    bets_data = [b.model_dump() for b in bets]
    result = create_bets_batch(bets_data)
    return {"message": f"Successfully imported {result['count']} bets", "count": result['count']}


@router.patch("/bets/{bet_id}/result")
def record_result(bet_id: int, result: BetResultUpdate):
    """Record the result of a bet."""
    updated = update_bet_result(bet_id, result.result_position, result.payout)
    if not updated:
        raise HTTPException(status_code=404, detail="Bet not found")
    return {"bet": updated}


@router.get("/bets/by-race")
def bets_by_race(date: str, venue: str, race_number: int):
    """Get all bets for a specific race."""
    bets = get_bets_by_race(date=date, venue=venue, race_number=race_number)
    return {"bets": bets, "count": len(bets)}


@router.get("/bets")
def list_bets(region: str = None, date: str = None, status: str = None, limit: int = 50):
    """List bet records with filters."""
    bets = get_bets(region=region, date=date, status=status, limit=limit)
    return {"bets": bets, "count": len(bets)}


@router.get("/bets/roi")
def roi_summary(region: str = None):
    """Get comprehensive ROI summary."""
    summary = get_roi_summary(region=region)
    return summary


@router.delete("/bets/{bet_id}")
def remove_bet(bet_id: int):
    """Delete a bet record."""
    if not delete_bet(bet_id):
        raise HTTPException(status_code=404, detail="Bet not found")
    return {"deleted": True}


@router.get("/summary-roi")
def summary_roi(region: str = None):
    """Get ROI data from the .numbers summary files (HK + AU)."""
    return get_summary_roi(region=region)
