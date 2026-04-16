"""
Summary Importer — Read ROI data from HK/AU Horse Race Summary .numbers files.
Returns structured data for the ROI dashboard.
"""
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from numbers_parser import Document

import config

logger = logging.getLogger(__name__)


def _safe_float(val) -> float:
    """Convert a value to float, returning 0.0 on failure."""
    if val is None:
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def _safe_int(val) -> Optional[int]:
    """Convert to int or return None."""
    if val is None:
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def _safe_str(val) -> str:
    """Convert to string, return empty string for None."""
    if val is None:
        return ''
    s = str(val).strip()
    return '' if s == 'None' else s


def _read_cell(table, row, col):
    """Safely read a cell value."""
    try:
        cell = table.cell(row, col)
        return cell.value
    except Exception:
        return None


def _normalize_date(date_str: str) -> str:
    """
    Normalize date strings from the Numbers files.
    
    Formats encountered:
    1. "2025-12-03" → keep as-is (already YYYY-MM-DD)
    2. "2026-12-03" → fix to "2025-12-03" (typo in source)
    3. "1.1", "3.29", "4.06" → M.D format → "2026-01-01", "2026-03-29", "2026-04-06"
    4. "20.12", "23.12", "27.12" → D.M format → "2025-12-20" etc.
    
    HK racing season: ~Sep-Jul. November/December → 2025, Jan-Oct → 2026.
    """
    if not date_str:
        return date_str
    
    # Fix specific YYYY-MM-DD corrections
    DATE_FIXES = {
        '2026-12-03': '2025-12-03',
    }
    if date_str in DATE_FIXES:
        return DATE_FIXES[date_str]
    
    # Already YYYY-MM-DD format
    if '-' in date_str and len(date_str) >= 8:
        return date_str.split(' ')[0]  # Strip time if present
    
    # Handle M.D / D.M ambiguity
    if '.' in date_str:
        # Fix floating point errors (e.g. 3.6999999999999997 → 3.7)
        try:
            rounded = round(float(date_str), 2)
            date_str = str(rounded)
            # Remove trailing .0 for whole numbers
            if date_str.endswith('.0'):
                date_str = date_str[:-2] + '.0'  # Keep as X.0 for proper parsing
        except ValueError:
            pass
        parts = date_str.split('.')
        if len(parts) == 2:
            try:
                a, b = int(parts[0]), int(parts[1])
                if a > 12 and b <= 12:
                    # D.M format (e.g., 20.12 = Dec 20)
                    month, day = b, a
                elif a <= 12:
                    # M.D format (e.g., 1.1 = Jan 1, 4.06 = Apr 6)
                    month, day = a, b
                else:
                    return date_str
                
                # Racing season year assignment
                year = 2025 if month >= 11 else 2026
                return f"{year}-{month:02d}-{day:02d}"
            except ValueError:
                pass
    
    return date_str


# Venue name normalization — unify inconsistent names from .numbers
VENUE_ALIASES = {
    'ShaTin': 'Sha Tin',
    'Sha TIn': 'Sha Tin',
    'Rose Hill': 'Rosehill Gardens',
    'Sandown': 'Sandown Lakeside',
    'Caulfield Health': 'Caulfield',
}

def _normalize_venue(venue: str) -> str:
    """Normalize venue names to canonical form."""
    if not venue:
        return venue
    v = venue.strip()
    return VENUE_ALIASES.get(v, v)


def parse_numbers_roi(file_path: Path, region: str) -> Dict[str, Any]:
    """
    Parse a .numbers ROI file and return structured data.
    
    Returns:
        {
            "region": "hkjc" | "au",
            "bets": [...],           # Individual bet records
        }
    """
    if not file_path.exists():
        logger.warning(f"ROI file not found: {file_path}")
        return {"region": region, "bets": []}
    
    try:
        doc = Document(str(file_path))
    except Exception as e:
        logger.error(f"Failed to open {file_path}: {e}")
        return {"region": region, "bets": []}
    
    result = {
        "region": region,
        "bets": [],
    }
    
    for sheet in doc.sheets:
        if sheet.name == "ROI":
            result["bets"] = _parse_roi_sheet(sheet, region)
            # We don't need to parse Side ROI or Total ROI sheets because
            # we compute them internally from the raw bets to ensure accuracy.
            break
            
    return result


def _parse_roi_sheet(sheet, region: str) -> List[Dict]:
    """Parse the main ROI sheet with individual bet records."""
    bets = []
    table = sheet.tables[0]
    
    # Find header row (row 2 based on analysis)
    header_row = 2
    headers = []
    for c in range(table.num_cols):
        val = _safe_str(_read_cell(table, header_row, c))
        headers.append(val)
    
    # Map column indices
    col_map = {}
    for i, h in enumerate(headers):
        if h:
            col_map[h] = i
    
    # Determine column positions based on region
    # HK has: Date, 馬場, 賽事編號, Class, Range, Type, Weather, Jockey, Trainer, Horse Number, 馬匹名稱, 投注本金, 位置賠率, Final Result, 總派彩回報, 單場淨利潤
    # AU has: Date, 馬場, 賽事編號, Class, Range, Horse Number, 馬匹名稱, 投注本金, 位置賠率, Final Result, 總派彩回報, 單場淨利潤
    
    date_col = col_map.get('Date', 0)
    venue_col = col_map.get('馬場', 1)
    race_col = col_map.get('賽事編號', 2)
    class_col = col_map.get('Class', 3)
    range_col = col_map.get('Range', 4)
    
    # Columns differ between HK and AU
    if region == 'hkjc':
        type_col = col_map.get('Type', 5)
        weather_col = col_map.get('Weather', 6)
        jockey_col = col_map.get('Jockey', 7)
        trainer_col = col_map.get('Trainer', 8)
        horse_num_col = col_map.get('Horse Number', 9)
        horse_name_col = col_map.get('馬匹名稱', 10)
        stake_col = col_map.get('投注本金 (S)', 11)
        odds_col = col_map.get('位置賠率 (P)', 12)
        result_col = col_map.get('Final Result', 13)
        payout_col = col_map.get('總派彩回報', 14)
        profit_col = col_map.get('單場淨利潤', 15)
    else:
        horse_num_col = col_map.get('Horse Number', 5)
        horse_name_col = col_map.get('馬匹名稱', 6)
        stake_col = col_map.get('投注本金 (S)', 7)
        odds_col = col_map.get('位置賠率 (P)', 8)
        result_col = col_map.get('Final Result', 9)
        payout_col = col_map.get('總派彩回報', 10)
        profit_col = col_map.get('單場淨利潤', 11)
        jockey_col = None
        trainer_col = None
        type_col = None
        weather_col = None
    
    # Track current date (date may be on first row of a meeting group)
    current_date = ''
    
    for r in range(header_row + 1, table.num_rows):
        # Read date (may be empty for grouped rows)
        date_val = _safe_str(_read_cell(table, r, date_col))
        if date_val and date_val != '':
            # Clean date: "2025-11-28 00:00:00" -> "2025-11-28"
            current_date = date_val.split(' ')[0] if ' ' in date_val else date_val
            current_date = _normalize_date(current_date)
        
        venue = _normalize_venue(_safe_str(_read_cell(table, r, venue_col)))
        race_num = _safe_int(_read_cell(table, r, race_col))
        horse_num = _safe_int(_read_cell(table, r, horse_num_col))
        horse_name = _safe_str(_read_cell(table, r, horse_name_col))
        
        # Skip rows without essential data
        if not venue or not horse_name or race_num is None:
            continue
        
        stake = _safe_float(_read_cell(table, r, stake_col))
        odds = _safe_float(_read_cell(table, r, odds_col))
        result_pos = _safe_int(_read_cell(table, r, result_col))
        payout = _safe_float(_read_cell(table, r, payout_col))
        
        # Calculate profit correctly:
        # The Numbers file leaves payout/profit EMPTY for lost bets.
        # We must compute: profit = payout - stake
        # Won: payout = odds * stake → profit = payout - stake (positive)
        # Lost: payout = 0 → profit = 0 - stake = -stake (negative)
        profit = payout - stake if stake > 0 else 0
        
        race_class = _safe_str(_read_cell(table, r, class_col))
        distance = _safe_str(_read_cell(table, r, range_col))
        
        # Determine status — no pending, all non-wins are losses
        if payout > 0:
            status = 'won'
        else:
            status = 'lost'
        
        bet = {
            "date": current_date,
            "venue": venue,
            "region": region,
            "race_number": race_num,
            "horse_number": horse_num,
            "horse_name": horse_name,
            "stake": stake,
            "odds": odds,
            "result_position": result_pos,
            "payout": payout,
            "net_profit": profit,
            "status": status,
            "race_class": race_class,
            "distance": distance,
        }
        
        # Add HK-specific fields
        if region == 'hkjc':
            bet["jockey"] = _safe_str(_read_cell(table, r, jockey_col)) if jockey_col is not None else ''
            bet["trainer"] = _safe_str(_read_cell(table, r, trainer_col)) if trainer_col is not None else ''
            bet["track_type"] = _safe_str(_read_cell(table, r, type_col)) if type_col is not None else ''
            bet["weather"] = _safe_str(_read_cell(table, r, weather_col)) if weather_col is not None else ''
        
        bets.append(bet)
    
    return bets





def get_summary_roi(region: Optional[str] = None) -> Dict[str, Any]:
    """
    Get ROI data from the Numbers summary files.
    Computes all breakdowns directly from individual bet records.
    """
    all_bets = []
    
    sources = []
    if region is None or region == 'hkjc':
        sources.append(('hkjc', config.HKJC_ROI_PATH))
    if region is None or region == 'au':
        sources.append(('au', config.AU_ROI_PATH))
    
    for rgn, path in sources:
        data = parse_numbers_roi(path, rgn)
        all_bets.extend(data["bets"])
    
    # Supplement bets with jockey/trainer from SQLite DB (AU Numbers lacks these columns)
    try:
        import sqlite3
        db_path = config.DB_PATH
        if db_path.exists():
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT date, venue, race_number, horse_number, jockey, trainer FROM bets WHERE jockey IS NOT NULL AND jockey != ''"
            ).fetchall()
            # Build lookup: (date, venue, race_num, horse_num) -> (jockey, trainer)
            jt_lookup = {}
            for r in rows:
                key = (r["date"], r["race_number"], r["horse_number"])
                jt_lookup[key] = (r["jockey"] or '', r["trainer"] or '')
            conn.close()
            
            for bet in all_bets:
                if not bet.get("jockey"):
                    key = (bet.get("date"), bet.get("race_number"), bet.get("horse_number"))
                    if key in jt_lookup:
                        bet["jockey"] = jt_lookup[key][0]
                        bet["trainer"] = jt_lookup[key][1]
    except Exception as e:
        logger.warning(f"Could not supplement jockey/trainer from DB: {e}")
    
    # Sort all bets by date
    all_bets.sort(key=lambda b: b.get("date", ""))
    
    # Calculate totals from bet data directly
    total_stake = sum(b.get("stake", 0) for b in all_bets)
    total_revenue = sum(b.get("payout", 0) for b in all_bets)
    total_profit = sum(b.get("net_profit", 0) for b in all_bets)
    
    total_bets = len(all_bets)
    wins = sum(1 for b in all_bets if b["status"] == "won")
    losses = total_bets - wins
    win_rate = round(float(wins / total_bets * 100), 1) if total_bets > 0 else 0
    roi_pct = round(float(total_profit / total_stake * 100), 1) if total_stake > 0 else 0
    
    # Compute side breakdowns from individual bets
    TRACK_RENAMES = {'泥地': '全天候賽道'}
    VENUE_RENAMES = {
        'ShaTin': 'Sha Tin',
        'Sha TIn': 'Sha Tin',
        'Rose Hill': 'Rosehill Gardens',
        'Caulfield Health': 'Caulfield',
    }
    CLASS_RENAMES = {
        '三級賽': 'Group 3',
        '二級賽': 'Group 2',
        '一級賽': 'Group 1',
        'Groupo 3': 'Group 3',
        'Featured': 'Feature',
        'LR': 'Listed',
        'RI': 'Listed',
        'C1': '第一班',
        'C3': '第三班',
        '第三班（條件限制）': '第三班',
        'Hcp 66': 'BM66',
    }
    side_roi = {
        "by_venue": _compute_breakdown(all_bets, "venue", renames=VENUE_RENAMES),
        "by_distance": _compute_breakdown(all_bets, "distance"),
        "by_class": _compute_breakdown(all_bets, "race_class", renames=CLASS_RENAMES),
        "by_track": _compute_breakdown(all_bets, "track_type", renames=TRACK_RENAMES),
        "by_jockey": _compute_breakdown(all_bets, "jockey"),
        "by_trainer": _compute_breakdown(all_bets, "trainer"),
    }
    
    # Build running profit (cumulative P&L)
    running_profit = []
    cumulative = 0.0
    for bet in all_bets:
        cumulative += bet.get("net_profit", 0)
        running_profit.append({
            "date": bet["date"],
            "venue": bet["venue"],
            "race_number": bet["race_number"],
            "horse_name": bet["horse_name"],
            "profit": bet.get("net_profit", 0),
            "cumulative": round(cumulative, 2),
        })
    
    # Build daily breakdown
    daily_map: Dict[str, Dict] = {}
    for bet in all_bets:
        key = f"{bet['date']}-{bet['venue']}"
        if key not in daily_map:
            daily_map[key] = {
                "date": bet["date"],
                "venue": bet["venue"],
                "region": bet["region"],
                "bets": 0,
                "stake": 0.0,
                "payout": 0.0,
                "profit": 0.0,
                "wins": 0,
            }
        entry = daily_map[key]
        entry["bets"] += 1
        entry["stake"] += bet.get("stake", 0)
        entry["payout"] += bet.get("payout", 0)
        entry["profit"] += bet.get("net_profit", 0)
        if bet["status"] == "won":
            entry["wins"] += 1
    
    daily_breakdown = list(daily_map.values())
    for d in daily_breakdown:
        d["profit"] = round(d["profit"], 2)
        d["payout"] = round(d["payout"], 2)
    daily_breakdown.sort(key=lambda d: d["date"], reverse=True)
    
    return {
        "total_bets": total_bets,
        "total_stake": round(total_stake, 2),
        "total_payout": round(total_revenue, 2),
        "total_profit": round(total_profit, 2),
        "roi_pct": roi_pct,
        "win_rate": win_rate,
        "wins": wins,
        "losses": losses,
        "running_profit": running_profit,
        "daily_breakdown": daily_breakdown,
        "side_roi": side_roi,
        "bets": all_bets,
    }


def _compute_breakdown(bets: List[Dict], field: str, renames: Optional[Dict[str, str]] = None) -> List[Dict]:
    """
    Group bets by a field and compute stats for each group.
    Returns a list sorted by total bets descending.
    """
    groups: Dict[str, Dict] = {}
    for bet in bets:
        name = bet.get(field, '') or ''
        name = name.replace('\t', '').strip()
        if not name:
            continue
        # Clean up distance names: "1300.0" → "1300m", "1200" → "1200m"
        if field == 'distance':
            try:
                num = float(name.replace('m', '').replace('M', '').strip())
                name = f"{int(num)}m"
            except (ValueError, TypeError):
                pass
        if renames:
            name = renames.get(name, name)
        
        if name not in groups:
            groups[name] = {"bets": 0, "wins": 0, "stake": 0.0, "profit": 0.0}
        g = groups[name]
        g["bets"] += 1
        g["stake"] += bet.get("stake", 0)
        g["profit"] += bet.get("net_profit", 0)
        if bet["status"] == "won":
            g["wins"] += 1
    
    result = []
    for name, g in groups.items():
        grp_stake = g["stake"]
        grp_profit = g["profit"]
        roi = round(float(grp_profit / grp_stake * 100), 1) if grp_stake > 0 else 0
        wr = round(float(g["wins"] / g["bets"] * 100), 1) if g["bets"] > 0 else 0
        result.append({
            "name": name,
            "total_bets": g["bets"],
            "wins": g["wins"],
            "win_rate": wr,
            "total_stake": round(grp_stake, 2),
            "total_profit": round(grp_profit, 2),
            "roi_pct": roi,
        })
    
    result.sort(key=lambda x: x["total_profit"], reverse=True)
    return result

