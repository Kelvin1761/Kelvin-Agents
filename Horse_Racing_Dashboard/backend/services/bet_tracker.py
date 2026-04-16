"""
Bet Tracker — CRUD operations for bet records and ROI calculations.
"""
from datetime import datetime
from db.database import get_db
from typing import Optional


def create_bet(
    date: str, venue: str, region: str, race_number: int,
    horse_number: int, horse_name: str,
    bet_type: str = 'place', stake: float = 1, odds: Optional[float] = None,
    jockey: str = None, trainer: str = None,
    consensus_type: str = None, kelvin_grade: str = None, heison_grade: str = None,
    notes: str = None, track_type: str = None, going: str = None,
) -> dict:
    """Create a new bet record."""
    conn = get_db()
    cursor = conn.execute("""
        INSERT INTO bets (date, venue, region, race_number, horse_number, horse_name,
                          jockey, trainer, bet_type, stake, odds,
                          consensus_type, kelvin_grade, heison_grade, notes, track_type, going)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (date, venue, region, race_number, horse_number, horse_name,
          jockey, trainer, bet_type, stake, odds,
          consensus_type, kelvin_grade, heison_grade, notes, track_type, going))
    conn.commit()
    bet_id = cursor.lastrowid
    bet = dict(conn.execute("SELECT * FROM bets WHERE id = ?", (bet_id,)).fetchone())
    conn.close()
    return bet


def create_bets_batch(bets_data: list[dict]) -> dict:
    """Create multiple bet records at once."""
    if not bets_data:
        return {"count": 0}
        
    conn = get_db()
    
    # Prepare tuples for executemany
    values = []
    for b in bets_data:
        values.append((
            b.get('date'), b.get('venue'), b.get('region', 'hkjc'), 
            b.get('race_number'), b.get('horse_number'), b.get('horse_name'),
            b.get('jockey'), b.get('trainer'), b.get('bet_type', 'place'), 
            b.get('stake', 1), b.get('odds'),
            b.get('consensus_type'), b.get('kelvin_grade'), b.get('heison_grade'), 
            b.get('notes'), b.get('track_type'), b.get('going')
        ))
        
    cursor = conn.executemany("""
        INSERT INTO bets (date, venue, region, race_number, horse_number, horse_name,
                          jockey, trainer, bet_type, stake, odds,
                          consensus_type, kelvin_grade, heison_grade, notes, track_type, going)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, values)
    
    conn.commit()
    count = cursor.rowcount
    conn.close()
    return {"count": count}


def update_bet_result(bet_id: int, result_position: int, payout: float) -> dict:
    """Record the result of a bet."""
    conn = get_db()
    bet = conn.execute("SELECT * FROM bets WHERE id = ?", (bet_id,)).fetchone()
    if not bet:
        conn.close()
        return None
    
    net_profit = payout - bet['stake']
    status = 'won' if payout > 0 else 'lost'
    
    conn.execute("""
        UPDATE bets SET status = ?, result_position = ?, payout = ?, net_profit = ?
        WHERE id = ?
    """, (status, result_position, payout, net_profit, bet_id))
    conn.commit()
    result = dict(conn.execute("SELECT * FROM bets WHERE id = ?", (bet_id,)).fetchone())
    conn.close()
    return result


def get_bets_by_race(date: str, venue: str, race_number: int) -> list[dict]:
    """Get all bets for a specific race."""
    conn = get_db()
    bets = [dict(row) for row in conn.execute(
        "SELECT * FROM bets WHERE date = ? AND venue = ? AND race_number = ? ORDER BY created_at DESC",
        (date, venue, race_number)
    ).fetchall()]
    conn.close()
    return bets


def get_bets(
    region: str = None, date: str = None, status: str = None,
    limit: int = 50
) -> list[dict]:
    """Get bet records with optional filters."""
    conn = get_db()
    query = "SELECT * FROM bets WHERE 1=1"
    params = []
    
    if region:
        query += " AND region = ?"
        params.append(region)
    if date:
        query += " AND date = ?"
        params.append(date)
    if status:
        query += " AND status = ?"
        params.append(status)
    
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    
    bets = [dict(row) for row in conn.execute(query, params).fetchall()]
    conn.close()
    return bets


def get_roi_summary(region: str = None) -> dict:
    """Calculate comprehensive ROI summary."""
    conn = get_db()
    where = "WHERE region = ?" if region else "WHERE 1=1"
    params = [region] if region else []
    
    # Overall stats
    row = conn.execute(f"""
        SELECT 
            COUNT(*) as total_bets,
            SUM(stake) as total_stake,
            SUM(COALESCE(payout, 0)) as total_payout,
            SUM(COALESCE(net_profit, 0)) as total_profit,
            COUNT(CASE WHEN status = 'won' THEN 1 END) as wins,
            COUNT(CASE WHEN status = 'lost' THEN 1 END) as losses,
            COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending
        FROM bets {where}
    """, params).fetchone()
    
    total_bets = row['total_bets'] or 0
    total_stake = row['total_stake'] or 0
    total_payout = row['total_payout'] or 0
    total_profit = row['total_profit'] or 0
    wins = row['wins'] or 0
    losses = row['losses'] or 0
    settled = wins + losses
    
    roi_pct = (total_profit / total_stake * 100) if total_stake > 0 else 0
    win_rate = (wins / settled * 100) if settled > 0 else 0
    
    # Per-date breakdown
    daily = [dict(r) for r in conn.execute(f"""
        SELECT date, venue, region,
            COUNT(*) as bets,
            SUM(stake) as stake,
            SUM(COALESCE(payout, 0)) as payout,
            SUM(COALESCE(net_profit, 0)) as profit
        FROM bets {where}
        GROUP BY date, venue
        ORDER BY date DESC
    """, params).fetchall()]
    
    # Per-consensus type breakdown
    by_consensus = [dict(r) for r in conn.execute(f"""
        SELECT consensus_type,
            COUNT(*) as bets,
            SUM(stake) as stake,
            SUM(COALESCE(payout, 0)) as payout,
            SUM(COALESCE(net_profit, 0)) as profit,
            COUNT(CASE WHEN status = 'won' THEN 1 END) as wins
        FROM bets {where} AND consensus_type IS NOT NULL
        GROUP BY consensus_type
    """, params).fetchall()]
    
    # Running profit (for chart)
    running = []
    cumulative = 0
    for r in conn.execute(f"""
        SELECT id, date, horse_name, COALESCE(net_profit, 0) as profit, status
        FROM bets {where} AND status != 'pending'
        ORDER BY created_at ASC
    """, params).fetchall():
        cumulative += r['profit']
        running.append({
            "id": r['id'],
            "date": r['date'],
            "horse": r['horse_name'],
            "profit": r['profit'],
            "cumulative": round(cumulative, 2),
        })
    
    conn.close()
    
    return {
        "total_bets": total_bets,
        "total_stake": round(total_stake, 2),
        "total_payout": round(total_payout, 2),
        "total_profit": round(total_profit, 2),
        "roi_pct": round(roi_pct, 2),
        "win_rate": round(win_rate, 2),
        "wins": wins,
        "losses": losses,
        "pending": row['pending'] or 0,
        "daily_breakdown": daily,
        "by_consensus_type": by_consensus,
        "running_profit": running,
    }


def delete_bet(bet_id: int) -> bool:
    """Delete a bet record."""
    conn = get_db()
    cursor = conn.execute("DELETE FROM bets WHERE id = ?", (bet_id,))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted
