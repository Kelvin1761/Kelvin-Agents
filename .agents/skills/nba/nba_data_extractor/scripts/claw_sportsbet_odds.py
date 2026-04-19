#!/usr/bin/env python3
import os
os.environ.setdefault('PYTHONUTF8', '1')
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from __future__ import annotations
"""
claw_sportsbet_odds.py — Sportsbet NBA Zero-Navigation Extractor (Claw Code V2)
Replaces the old manual navigation.

Architecture:
- HTTP API call to get all NBA matches for today
- curl_cffi to spoof browser TLS and fetch raw HTML
- Regex extraction of window.__PRELOADED_STATE__ Redux cache
- Direct parsing of the sportsbook objects

Runs automatically. No manual user steps.
"""
import sys
import json
import urllib.request
import re
import os
from datetime import datetime
try:
    from curl_cffi import requests
except ImportError:
    print("❌ 缺少 curl_cffi 套件。請執行: pip install curl_cffi")
    sys.exit(1)

TEAM_NAMES = {
    "Atlanta Hawks": "ATL", "Boston Celtics": "BOS", "Brooklyn Nets": "BKN", "Charlotte Hornets": "CHA",
    "Chicago Bulls": "CHI", "Cleveland Cavaliers": "CLE", "Dallas Mavericks": "DAL", "Denver Nuggets": "DEN",
    "Detroit Pistons": "DET", "Golden State Warriors": "GSW", "Houston Rockets": "HOU", "Indiana Pacers": "IND",
    "Los Angeles Clippers": "LAC", "Los Angeles Lakers": "LAL", "Memphis Grizzlies": "MEM", "Miami Heat": "MIA",
    "Milwaukee Bucks": "MIL", "Minnesota Timberwolves": "MIN", "New Orleans Pelicans": "NOP", "New York Knicks": "NYK",
    "Oklahoma City Thunder": "OKC", "Orlando Magic": "ORL", "Philadelphia 76ers": "PHI", "Phoenix Suns": "PHX",
    "Portland Trail Blazers": "POR", "Sacramento Kings": "SAC", "San Antonio Spurs": "SAS", "Toronto Raptors": "TOR",
    "Utah Jazz": "UTA", "Washington Wizards": "WSH"
}

class SportsbetNBAExtractor:
    def __init__(self, outdir="."):
        self.competition_url = "https://www.sportsbet.com.au/apigw/sportsbook-sports/Sportsbook/Sports/Competitions/6927"
        self.base_event_url = "https://www.sportsbet.com.au/betting/basketball-us/nba"
        self.outdir = outdir
        self.session = requests.Session(impersonate="chrome120")

    def fetch_daily_matches(self):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔍 正在探索 Sportsbet 當日 NBA 賽事...")
        try:
            req = urllib.request.Request(self.competition_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))
                events = data.get('events', [])
                
                urls = []
                for event in events:
                    raw_name = event.get('name', '')
                    event_id = event.get('id', '')
                    if not raw_name or not event_id:
                        continue
                    slug = re.sub(r'[^a-z0-9]+', '-', raw_name.lower()).strip('-')
                    full_url = f"{self.base_event_url}/{slug}-{event_id}"
                    urls.append((raw_name, full_url))
                
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ 成功發現 {len(urls)} 場 NBA 賽程！")
                return urls
        except Exception as e:
            print(f"❌ 獲取賽事名單失敗: {e}")
            return []

    def _parse_markets(self, raw_data):
        structured = {}
        def find_markets(obj):
            markets = []
            if isinstance(obj, dict):
                if obj.get('name') and 'selections' in obj and isinstance(obj['selections'], list):
                    markets.append(obj)
                for k, v in obj.items():
                    markets.extend(find_markets(v))
            elif isinstance(obj, list):
                for item in obj:
                    markets.extend(find_markets(item))
            return markets

        found = find_markets(raw_data)
        for m in found:
            name = m.get('name', '')
            if any(x in name for x in ['Points', 'Rebounds', 'Assists', 'Match Betting', 'Line', 'Threes Made']):
                selections = {}
                for sel in m.get('selections', []):
                    # In Redux state, selections might be dicts or strings. We rely on the initial state being hydrated.
                    if isinstance(sel, dict):
                        price_obj = sel.get('price', {})
                        price = price_obj.get('winPrice') or price_obj.get('handicap')
                        # Sometimes price is directly in selection
                        if not price:
                            price = sel.get('winPrice') or sel.get('handicap')
                        if price:
                            selections[sel.get('name', '')] = price
                if selections:
                    structured[name] = selections
        return structured

    def traverse_and_extract(self, matches):
        all_odds_data = {}
        for idx, (game_name, url) in enumerate(matches, 1):
            print(f"\n[{idx}/{len(matches)}] 🕵️ 讀取賽事: {game_name}")
            try:
                resp = self.session.get(url, timeout=15)
                html = resp.text
                
                idx_state = html.find("window.__PRELOADED_STATE__ = ")
                if idx_state == -1:
                    print(f"   ⚠️ 失敗：頁面內找不到 __PRELOADED_STATE__")
                    continue
                    
                start = idx_state + len("window.__PRELOADED_STATE__ = ")
                end = html.find("\n", start)
                state_str = html[start:end].strip()
                if state_str.endswith(";"): state_str = state_str[:-1]
                
                state = json.loads(state_str)
                sportsbook = state.get("entities", {}).get("sportsbook", {})
                
                extracted = self._parse_normalized_markets(sportsbook)
                
                if extracted:
                    # Format matching Wong Choi
                    cleaned = self._clean_markets(extracted)
                    
                    # Split game name into Away/Home
                    matchup_str = game_name.lower().replace(" at ", "|")
                    parts = matchup_str.split("|")
                    if len(parts) == 2:
                        away_name = next(k for k in TEAM_NAMES.keys() if k.lower() == parts[0].strip())
                        home_name = next(k for k in TEAM_NAMES.keys() if k.lower() == parts[1].strip())
                        away_abbr = TEAM_NAMES[away_name]
                        home_abbr = TEAM_NAMES[home_name]
                        
                        formatted = self._format_as_sportsbet(game_name, away_abbr, home_abbr, cleaned)
                        all_odds_data[f"{away_abbr}_{home_abbr}"] = formatted
                        print(f"   ✅ 成功提取 {len(cleaned)} 種類別，已格式化為 {away_abbr} @ {home_abbr}")
                    else:
                        print(f"   ⚠️ 失敗：無法解析球隊名稱 {game_name}")
                else:
                    print(f"   ⚠️ 失敗：未能解析到 Player Props 數據。")
            except Exception as e:
                print(f"   ⚠️ 讀取時發生錯誤: {e}")
                
        return all_odds_data

    def _parse_normalized_markets(self, sportsbook):
        """
        Parse normalized Redux sportsbook entities into structured market data.

        Sportsbet has TWO distinct market formats:
        ─────────────────────────────────────────────────────────────────
        TYPE A: Individual Player O/U  (e.g. "LaMelo Ball - Points")
          → Selections: "Over +22.5" / "Under +22.5"
          → Line comes from handicap object on the outcome
          → Market name format: "{Player Name} - {Category}"

        TYPE B: Multi-Player Milestone  (e.g. "To Score 5+ Points",
                "To Record 4+ Rebounds", "3+ Made Threes")
          → Selections: Player names (each a separate outcome)
          → Line comes from the market name itself  (N+)
          → Market name format: "To Score/Record N+ ..." or "N+ Made Threes"
        ─────────────────────────────────────────────────────────────────
        Both must be parsed correctly and mapped to the right prop category
        WITHOUT cross-contamination.
        """
        structured = {}
        markets = sportsbook.get("markets", {})
        outcomes_db = sportsbook.get("outcomes", {})

        for m_id, m_data in markets.items():
            name = m_data.get("name", "")
            if not any(x in name for x in ['Point', 'Rebound', 'Assist', 'Match Betting',
                                            'Line', 'Threes', 'Three']):
                continue

            sels = {}
            for out_id in m_data.get("outcomeIds", []):
                out_data = outcomes_db.get(str(out_id), {})
                s_name = out_data.get("name", "")

                price_val = None
                win_price = out_data.get("winPrice")
                if isinstance(win_price, dict) and "num" in win_price and "den" in win_price:
                    num = float(win_price["num"])
                    den = float(win_price["den"])
                    if den > 0:
                        price_val = round(1 + (num / den), 2)
                elif type(win_price) in [int, float]:
                    price_val = win_price

                hc_obj = out_data.get("handicap")
                if hc_obj and isinstance(hc_obj, dict):
                    hc = hc_obj.get("display") or hc_obj.get("value")
                    s_name = f"{s_name} {hc}"

                if price_val and s_name:
                    sels[s_name.strip()] = str(price_val)

            if sels:
                structured[name] = sels

        return structured

    # ── Market Classification Helpers ────────────────────────────────────
    # These patterns are derived from actual Sportsbet Redux state dumps.
    #
    # TYPE A (Individual Player O/U) — "{Player} - Points/Rebounds/..."
    #   Selections: "Over +22.5", "Under +22.5"
    #
    # TYPE B (Multi-Player Milestone)
    #   Points:   "To Score N+ Points"  (EXCLUDE quarter/half/minute variants)
    #   Rebounds:  "To Record N+ Rebounds"
    #   Assists:  "To Record N+ Assists"
    #   Threes:   "N+ Made Threes"
    #
    # POISON markets to EXCLUDE:
    #   "1st Quarter - To Score N+ Points"  (quarter milestone)
    #   "Player to Score N+ Points in the First 3 Minutes" (minute milestone)
    #   "1st Half Total Points", "Away Team Total Points" (team totals)
    #   "Total Points Odd / Even", "Race to N Points" (game-level)
    #   "{Player} - 1st Qtr Points" (quarter-level player prop)

    _EXCLUDE_KEYWORDS = frozenset([
        'Quarter', 'Half', 'Qtr', 'Total', 'Race to', 'Odd', 'Even',
        'First Team', 'Minute', '3 Minutes', 'Away Team', 'Home Team',
    ])

    def _is_excluded(self, m_name: str) -> bool:
        """Return True if a market name contains any exclusion keyword."""
        return any(kw in m_name for kw in self._EXCLUDE_KEYWORDS)

    def _classify_market(self, m_name: str) -> str | None:
        """
        Classify a Sportsbet market name into a canonical category.
        Returns one of: 'points', 'rebounds', 'assists', 'threes_made',
                         'match_betting', 'line', or None (skip).
        """
        # ── Game-level markets ───────────────────────────────────────
        if "Match Betting" in m_name:
            return "match_betting"
        if "Line" in m_name and not self._is_excluded(m_name):
            return "line"

        # ── Skip junk / game-level / quarter / half markets ──────────
        if self._is_excluded(m_name):
            return None

        # ── Threes MUST be checked BEFORE Points ─────────────────────
        # Multi-player: "3+ Made Threes", "1+ Made Threes"
        # Individual:   "LaMelo Ball - Made Threes"
        if "Threes" in m_name or "Three" in m_name:
            return "threes_made"

        # ── Points ───────────────────────────────────────────────────
        # Individual: "LaMelo Ball - Points"
        # Multi-player: "To Score 5+ Points"
        if "Point" in m_name:
            return "points"

        # ── Rebounds ──────────────────────────────────────────────────
        # Individual: "LaMelo Ball - Rebounds"
        # Multi-player: "To Record 4+ Rebounds"
        if "Rebound" in m_name:
            return "rebounds"

        # ── Assists ──────────────────────────────────────────────────
        # Individual: "LaMelo Ball - Assists"
        # Multi-player: "To Record 4+ Assists"
        if "Assist" in m_name:
            return "assists"

        return None

    def _clean_markets(self, raw_markets):
        """
        Classify raw sportsbet market names into canonical categories.
        Uses strict ordering (Threes before Points) to prevent cross-contamination.
        """
        cleaned = {
            "Points": {}, "Rebounds": {}, "Assists": {},
            "Threes Made": {}, "Game Lines": {}
        }
        _cat_to_key = {
            "points": "Points", "rebounds": "Rebounds", "assists": "Assists",
            "threes_made": "Threes Made", "match_betting": "Game Lines",
            "line": "Game Lines",
        }

        for m_name, sels in raw_markets.items():
            cat = self._classify_market(m_name)
            if cat is None:
                continue

            target_key = _cat_to_key[cat]
            if cat == "match_betting":
                cleaned["Game Lines"]["Match Betting"] = sels
            elif cat == "line":
                cleaned["Game Lines"]["Line"] = sels
            else:
                cleaned[target_key][m_name] = sels

        # Remove empty categories
        return {k: v for k, v in cleaned.items() if v}

    def _format_as_sportsbet(self, raw_game_name, away_abbr, home_abbr, cleaned_markets):
        """
        Converts sportsbet internal dict into the standard Sportsbet_Odds JSON
        format expected by downstream (generate_nba_reports.py).

        Handles both market formats:
        - TYPE A (Individual O/U):  "LaMelo Ball - Points"
            → selections have handicap (e.g. "Over +22.5")
            → player name is in the market name before " - "
        - TYPE B (Multi-Player Milestone):  "To Score 5+ Points"
            → line value (e.g. 5) is in the market name
            → selection names ARE the player names
        """
        import re

        formatted = {
            "source": "Sportsbet_Extractor",
            "extraction_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "matchup": f"{away_abbr} @ {home_abbr}",
            "away_team": away_abbr,
            "home_team": home_abbr,
            "game_lines": {},
            "player_props": {}
        }

        # ── Game lines ───────────────────────────────────────────────
        gl = cleaned_markets.get("Game Lines", {})
        if "Line" in gl:
            line_keys = list(gl["Line"].keys())
            if line_keys:
                for k in line_keys:
                    match = re.search(r"([+-]\d+\.5)", k)
                    if match:
                        formatted["game_lines"]["spread_away"] = match.group(1)
                        break
        if "Match Betting" in gl:
            for k, v in gl["Match Betting"].items():
                if away_abbr in TEAM_NAMES.get(k, k):
                    formatted["game_lines"]["ml_away"] = str(v)
                elif home_abbr in TEAM_NAMES.get(k, k):
                    formatted["game_lines"]["ml_home"] = str(v)

        # ── Player Props ─────────────────────────────────────────────
        pp = {"points": {}, "rebounds": {}, "assists": {}, "threes_made": {}}
        cat_map = {
            "Points": "points", "Rebounds": "rebounds",
            "Assists": "assists", "Threes Made": "threes_made",
        }

        for sp_cat, mapped_cat in cat_map.items():
            cat_data = cleaned_markets.get(sp_cat, {})
            for market_name, selections in cat_data.items():

                # ─── Detect market TYPE ──────────────────────────────
                # TYPE A: "{Player Name} - {Category}"
                #   e.g. "LaMelo Ball - Points", "Bam Adebayo - Rebounds"
                #   Selections: "Over +22.5" @1.85, "Under +22.5" @1.95
                type_a_match = re.match(r'^(.+?)\s*-\s*(Points|Rebounds|Assists|Made Threes)', market_name)

                # TYPE B: "To Score N+ Points", "To Record N+ Rebounds",
                #          "N+ Made Threes"
                #   Selections: player names
                type_b_match = re.search(r'(\d+)\+', market_name)

                if type_a_match:
                    # ─── TYPE A: Individual Player O/U ────────────────
                    player_name = type_a_match.group(1).strip()
                    for sel_name, odds in selections.items():
                        # Only take "Over" lines, skip "Under"
                        if "Under" in sel_name:
                            continue
                        # Extract line from selection name: "Over +22.5" → "22.5"
                        line_match = re.search(r'([+-]?\d+\.5)', sel_name)
                        if line_match:
                            line_val = line_match.group(1).replace("+", "")
                            if player_name not in pp[mapped_cat]:
                                pp[mapped_cat][player_name] = {"lines": {}}
                            pp[mapped_cat][player_name]["lines"][str(line_val)] = str(odds)

                elif type_b_match:
                    # ─── TYPE B: Multi-Player Milestone ───────────────
                    line_val = type_b_match.group(1)
                    for player_name, odds in selections.items():
                        # Clean player name (remove any trailing handicap artifacts)
                        clean_player = re.sub(r'\s*[+-]?\d+\.5\s*$', '', player_name).strip()
                        clean_player = clean_player.replace(" Over", "").replace(" Under", "")
                        if not clean_player:
                            continue
                        if clean_player not in pp[mapped_cat]:
                            pp[mapped_cat][clean_player] = {"lines": {}}
                        pp[mapped_cat][clean_player]["lines"][str(line_val)] = str(odds)

        formatted["player_props"] = pp
        return formatted

    def run(self):
        matches = self.fetch_daily_matches()
        if not matches:
            print("❌ 沒有發現任何 NBA 賽事，程式終止。")
            return
            
        print(f"\n--- 開始逐場萃取 Player Props ---")
        odds_data = self.traverse_and_extract(matches)
        
        try:
            # Write individual files
            os.makedirs(self.outdir, exist_ok=True)
            count = 0
            for match_key, data in odds_data.items():
                out_path = os.path.join(self.outdir, f"Sportsbet_Odds_{match_key}.json")
                with open(out_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                count += 1
            print(f"\n🎉 完美！所有賠率已成功導出至 {self.outdir}/Sportsbet_Odds_*.json")
            print(f"   總共捕獲: {count} 場賽事數據")
        except Exception as e:
            print(f"\n❌ 儲存 JSON 失敗: {e}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--outdir', default='.', help="Directory to save the Sportsbet_Odds_*.json files")
    args = parser.parse_args()
    
    extractor = SportsbetNBAExtractor(outdir=args.outdir)
    extractor.run()
