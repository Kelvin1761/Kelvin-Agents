#!/usr/bin/env python3
"""
bet365_parser.py — Bet365 DOM Raw Text → Structured JSON Parser

Parses the raw innerText captured by MCP Playwright from Bet365 player props
into a structured JSON file compatible with generate_nba_reports.py.

Bet365 DOM structure (innerText):
  - Player section: jersey, name, L5 stats (per player)
  - Odds grid: line markers (5, 10, 15...) followed by odds for each player

Key parsing rules:
  - Line markers appear as plain integers WITHOUT decimals: "5", "10", "15"
  - Odds values ALWAYS have decimals: "1.01", "10.00", "36.00"
  - Bet365 "10" means "10 or above" (>=10), NOT "Over 10.5"
  - Not all players have all lines (lower lines may only appear for lower scorers)

Usage:
  python bet365_parser.py --raw raw_points.txt --category points --players "Sexton,Jones,..." --output out.json
  
  OR (preferred): Import and call parse_props_section() directly from Playwright extraction code.

Version: 1.0.0
"""
import json, re, sys, os, argparse

# Known Bet365 line markers for player props
# BUG FIX: Must include ALL possible line values across all categories:
#   Points:  5, 10, 15, 20, 25, 30, 35, 40, 45, 50
#   Rebounds: 1, 2, 3, 5, 7, 10, 13, 15, 17, 20
#   Assists:  1, 2, 3, 5, 7, 10, 13, 15
#   3PM:     1, 2, 3, 5, 7, 10
ALL_LINE_MARKERS = {1, 2, 3, 5, 7, 10, 13, 15, 17, 20, 25, 30, 35, 40, 45, 50}
# Points-only markers (used during player section parsing to avoid
# confusing low markers like 1,2,3 with jersey numbers)
POINTS_LINE_MARKERS = {5, 10, 15, 20, 25, 30, 35, 40, 45, 50}
# For non-points categories, the first odds grid marker is typically 1 or 3
VALID_LINE_MARKERS = ALL_LINE_MARKERS  # Keep backward compat


def is_line_marker(value_str, marker_set=None):
    """Check if a raw text line is a line marker (integer, no decimal)."""
    if marker_set is None:
        marker_set = ALL_LINE_MARKERS
    value_str = value_str.strip()
    if not value_str:
        return False
    # Line markers are plain integers WITHOUT decimal points
    # e.g. "5", "10", "15" — NOT "10.00" or "1.50"
    if '.' in value_str:
        return False
    try:
        val = int(value_str)
        return val in marker_set
    except ValueError:
        return False


def is_odds_value(value_str):
    """Check if a raw text line is an odds value."""
    value_str = value_str.strip()
    try:
        val = float(value_str)
        return val > 0
    except ValueError:
        return False


def parse_players_section(lines):
    """
    Parse the player header section to extract player list with jersey + L5.
    Returns (players_list, remaining_lines_index).
    
    Uses a state machine:
      STATE_JERSEY → STATE_NAME → STATE_L5 (×5) → STATE_JERSEY ...
    
    After a player name, ALWAYS consume the next 5 integer values as L5 stats,
    regardless of whether they look like line markers (e.g. '5', '10').
    """
    players = []
    i = 0
    
    # Skip until we find "Player / Last 5"
    while i < len(lines):
        if 'Player' in lines[i] and 'Last' in lines[i]:
            i += 1
            break
        i += 1
    
    # State machine
    STATE_JERSEY = "jersey"
    STATE_NAME = "name"
    STATE_L5 = "l5"
    
    state = STATE_JERSEY
    current_player = None
    l5_values = []
    l5_count = 0
    
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        
        if state == STATE_JERSEY:
            # Expect a jersey number (integer 0-99) or "00"
            if line.isdigit() or line == '00':
                val = int(line)
                if val < 100:
                    # LOOK-AHEAD: if this number could be a line marker (5,10,15...)
                    # check if the NEXT non-empty line is a player name (has letters).
                    # If not, this is the start of the odds grid, not a jersey.
                    if val in VALID_LINE_MARKERS and len(players) > 0:
                        # Peek ahead for a name
                        peek = i + 1
                        while peek < len(lines) and not lines[peek].strip():
                            peek += 1
                        if peek < len(lines):
                            next_line = lines[peek].strip()
                            if not any(c.isalpha() for c in next_line):
                                # Next line is NOT a name → this is odds grid start
                                if current_player and current_player['name']:
                                    current_player['last5'] = l5_values
                                    players.append(current_player)
                                return players, i
                    # It's a real jersey number
                    # Save previous player
                    if current_player and current_player['name']:
                        current_player['last5'] = l5_values
                        players.append(current_player)
                    current_player = {'jersey': line, 'name': '', 'last5': []}
                    l5_values = []
                    l5_count = 0
                    state = STATE_NAME
                    i += 1
                    continue
            
            # If it's not a jersey, check if we've hit the odds grid
            # The odds grid starts with a decimal number (like "1.01")
            if '.' in line:
                # We've left the player section — save last player and return
                if current_player and current_player['name']:
                    current_player['last5'] = l5_values
                    players.append(current_player)
                return players, i
            
            # It might be a line marker that indicates end of player section
            if is_line_marker(line) and len(players) > 0:
                if current_player and current_player['name']:
                    current_player['last5'] = l5_values
                    players.append(current_player)
                return players, i
            
            i += 1
            continue
        
        elif state == STATE_NAME:
            # Expect a player name (contains letters)
            if any(c.isalpha() for c in line):
                current_player['name'] = line
                state = STATE_L5
                l5_count = 0
                l5_values = []
                i += 1
                continue
            i += 1
            continue
        
        elif state == STATE_L5:
            # Consume exactly 5 integer values as L5 stats
            # These can be ANY integer (including 5, 10, etc.)
            try:
                val = int(line)
                l5_values.append(val)
                l5_count += 1
                if l5_count >= 5:
                    state = STATE_JERSEY  # Back to looking for next jersey
                i += 1
                continue
            except ValueError:
                # Not an integer — might be end of section
                if current_player and current_player['name']:
                    current_player['last5'] = l5_values
                    players.append(current_player)
                return players, i
    
    # Save last player
    if current_player and current_player['name']:
        current_player['last5'] = l5_values
        players.append(current_player)
    
    return players, i


def parse_odds_grid(lines, start_idx, num_players):
    """
    Parse the odds grid section.
    Returns dict: {line_value: [odds_per_player]}
    
    Rules:
    - Line markers are integers without decimals (5, 10, 15...)
    - Between markers, odds values appear one per line
    - Number of odds values between markers <= num_players
    """
    grid = {}
    current_line = None
    current_odds = []
    i = start_idx
    
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        
        if is_line_marker(line):
            # Save previous line's odds
            if current_line is not None and current_odds:
                grid[current_line] = current_odds
            current_line = int(line)
            current_odds = []
            i += 1
            continue
        
        if is_odds_value(line) and current_line is not None:
            current_odds.append(float(line))
            i += 1
            continue
        
        # If we hit something unexpected (like "Threes Made"), stop
        if any(c.isalpha() for c in line):
            break
        
        i += 1
    
    # Save last line
    if current_line is not None and current_odds:
        grid[current_line] = current_odds
    
    return grid, i


def map_odds_to_players(players, odds_grid):
    """
    Map odds to players. When a line has fewer odds than players,
    the FIRST players (higher scorers) don't have that line.
    Bet365 doesn't show very low lines for high scorers.
    
    Returns: {player_name: {line_value: odds}}
    """
    num_players = len(players)
    result = {}
    
    for player in players:
        result[player['name']] = {
            'jersey': player['jersey'],
            'last5': player['last5'],
            'lines': {}
        }
    
    for line_val, odds_list in sorted(odds_grid.items()):
        n_odds = len(odds_list)
        if n_odds == num_players:
            # 1:1 mapping
            for idx, player in enumerate(players):
                result[player['name']]['lines'][str(line_val)] = str(odds_list[idx])
        elif n_odds < num_players:
            # Bet365 orders players from highest to lowest output in each category.
            # When a low line (e.g. PTS 5+, REB 3+) has fewer odds than players,
            # it means the TOP players (first in list) don't have that line opened
            # because it's a near-certainty for them. The odds map to the LAST N players.
            offset = num_players - n_odds
            for idx, odds in enumerate(odds_list):
                player_idx = idx + offset
                if player_idx < num_players:
                    result[players[player_idx]['name']]['lines'][str(line_val)] = str(odds_list[idx])
        # If n_odds > num_players, something went wrong — skip
    
    return result


def parse_full_props_text(raw_text, category="points"):
    """
    Parse a complete props tab raw text (from Playwright innerText).
    Returns structured dict with all players and their odds.
    """
    lines = raw_text.strip().split('\n')
    
    # Parse players
    players, odds_start_idx = parse_players_section(lines)
    
    if not players:
        return {"error": "No players found", "category": category}
    
    # Parse odds grid
    odds_grid, _ = parse_odds_grid(lines, odds_start_idx, len(players))
    
    # Map odds to players
    player_odds = map_odds_to_players(players, odds_grid)
    
    return {
        "category": category,
        "player_count": len(players),
        "line_count": len(odds_grid),
        "players": player_odds
    }


def parse_full_game_page(raw_text):
    """
    Parse the entire game page raw text that contains all tabs
    (Points, Threes Made, Rebounds, Assists).
    
    Returns the full Bet365 odds JSON structure.
    """
    # Split into sections by known tab names
    sections = {}
    tab_markers = [
        ("Points", "points"),
        ("Threes Made", "threes_made"),
        ("Assists", "assists"),
        ("Rebounds", "rebounds"),
    ]
    
    # Find section boundaries
    boundaries = []
    for marker_text, cat_key in tab_markers:
        # Look for "Points\nSGM\nPlayer / Last 5" pattern
        pattern = f"{marker_text}\nSGM\nPlayer / Last 5"
        idx = raw_text.find(pattern)
        if idx >= 0:
            boundaries.append((idx, marker_text, cat_key))
    
    if not boundaries:
        # Try simpler pattern
        for marker_text, cat_key in tab_markers:
            idx = raw_text.find(f"{marker_text}\n")
            if idx >= 0:
                boundaries.append((idx, marker_text, cat_key))
    
    boundaries.sort(key=lambda x: x[0])
    
    result = {
        "source": "Bet365_MCP_Playwright",
        "player_props": {}
    }
    
    for i, (start_idx, marker_text, cat_key) in enumerate(boundaries):
        end_idx = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(raw_text)
        section_text = raw_text[start_idx:end_idx]
        
        parsed = parse_full_props_text(section_text, cat_key)
        if "players" in parsed:
            result["player_props"][cat_key] = parsed["players"]
    
    return result


# ─── CLI ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Bet365 DOM Raw Text → Structured JSON Parser")
    parser.add_argument("--raw", required=True, help="Path to raw text file from Playwright")
    parser.add_argument("--output", required=True, help="Output JSON path")
    parser.add_argument("--game", default="", help="Game tag e.g. CHI_WSH")
    args = parser.parse_args()
    
    if not os.path.exists(args.raw):
        print(f"❌ Raw text file not found: {args.raw}")
        sys.exit(1)
    
    with open(args.raw, 'r', encoding='utf-8') as f:
        raw_text = f.read()
    
    result = parse_full_game_page(raw_text)
    result["game_tags"] = [args.game] if args.game else []
    
    # Summary
    for cat, players in result.get("player_props", {}).items():
        print(f"📊 {cat}: {len(players)} 球員")
        for pname, pdata in players.items():
            lines_str = ", ".join(f"{l}+@{o}" for l, o in sorted(pdata.get('lines', {}).items(), key=lambda x: int(x[0])))
            print(f"  {pname}: L5={pdata.get('last5', [])} | {lines_str}")
    
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Bet365 JSON 已生成: {args.output}")


if __name__ == "__main__":
    main()
