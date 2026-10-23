#!/usr/bin/env python3
"""
build_nba_ml_dataset.py — NBA ML Dataset Builder V2

永久保存所有 NBA 賽果 + 特徵數據，供未來 ML training 使用。
即使 API 日後唔再 available，data 依然留低咗。

What it does:
1. Scan all Wong Choi NBA Analysis/ folders for nba_game_data_*.json (features)
2. For each date, fetch Results_Brief via nba_api (labels / box scores)
3. Build consolidated feature + label dataset → NBA_ML_Dataset/
4. Save every raw Results_Brief permanently in NBA_ML_Dataset/results_brief/

Output:
  NBA_ML_Dataset/
    dataset.csv              — Main feature matrix (one row per player-stat-line)
    dataset_meta.json         — Metadata / column descriptions
    per_date/                 — Per-date raw feature JSON
    results_brief/            — Permanently archived box scores (Results_Brief_*.json)

Usage:
  python .agents/scripts/nba_ml/build_nba_ml_dataset.py --output-dir <new-directory>
  python .agents/scripts/nba_ml/build_nba_ml_dataset.py --output-dir <new-directory> --date 2026-05-14
  python .agents/scripts/nba_ml/build_nba_ml_dataset.py --output-dir <new-directory> --skip-fetch
  Independent archive receipts: use build_verified_nba_dataset.py --help instead.
"""

import os
import sys
import json
import csv
import math
import argparse
import time
import io

if __name__ == '__main__' and sys.stdout.encoding != 'utf-8' and hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from pathlib import Path as _Path
PROJECT_ROOT = _Path(__file__).resolve().parents[3]
import sys as _sys; _sys.path.insert(0, str(PROJECT_ROOT))
from wongchoi_paths import NBA_ML_DATASET
from nba_corpus import nba_archive_folders
_sys.path.insert(0, str(PROJECT_ROOT / ".agents" / "skills" / "nba"))
DATASET_DIR = str(NBA_ML_DATASET)

# Stat categories we care about
STAT_CATEGORIES = ["PTS", "REB", "AST", "FG3M"]
STAT_KEY_MAP = {"PTS": "pts", "REB": "reb", "AST": "ast", "FG3M": "fg3m"}

# Lines to evaluate per stat (standard Sportsbet milestones)
SPORTSBET_LINES = {
    "PTS": [10, 15, 20, 25, 30, 35, 40],
    "REB": [3, 5, 7, 9, 11, 13, 15],
    "AST": [2, 4, 6, 8, 10, 12],
    "FG3M": [1, 2, 3, 4, 5, 6],
}

API_SLEEP = 0.8

try:
    from nba_api.stats.endpoints import scoreboardv2, boxscoretraditionalv2
    NBA_API_OK = True
except ImportError:
    NBA_API_OK = False


# ─── Results Fetching (built-in, avoids broken reflector imports) ───

def _int(v, default=0):
    """Convert to int, handling None and non-numeric values."""
    if v is None:
        return default
    try:
        return int(v)
    except (ValueError, TypeError):
        return default

def fetch_boxscore(game_id):
    """Fetch box score for a specific game using BoxScoreTraditionalV2."""
    try:
        box = boxscoretraditionalv2.BoxScoreTraditionalV2(game_id=game_id)
        time.sleep(API_SLEEP)
        data = box.get_dict()
        players = []
        for rs in data.get('resultSets', []):
            if rs.get('name') == 'PlayerStats':
                headers = rs['headers']
                h_idx = {h: i for i, h in enumerate(headers)}
                for row in rs.get('rowSet', []):
                    players.append({
                        'name': row[h_idx.get('PLAYER_NAME', 0)],
                        'team': row[h_idx.get('TEAM_ABBREVIATION', 0)],
                        'position': row[h_idx.get('START_POSITION', 0)] or '',
                        'starter': bool(row[h_idx.get('START_POSITION', 0)]),
                        'minutes': row[h_idx.get('MIN', 0)] or '0',
                        'pts': _int(row[h_idx['PTS']]),
                        'reb': _int(row[h_idx['REB']]),
                        'ast': _int(row[h_idx['AST']]),
                        'fg3m': _int(row[h_idx['FG3M']]),
                        'stl': _int(row[h_idx['STL']]),
                        'blk': _int(row[h_idx['BLK']]),
                        'tov': _int(row[h_idx['TO']]),
                        'fgm': _int(row[h_idx['FGM']]),
                        'fga': _int(row[h_idx['FGA']]),
                        'ftm': _int(row[h_idx['FTM']]),
                        'plus_minus': _int(row[h_idx['PLUS_MINUS']]),
                    })
        return {'players': players}
    except Exception as e:
        print(f"    ⚠️ BoxScore error ({game_id}): {e}")
        return None


def parse_minutes(value):
    """Unknown/DNP is zero; sub-minute played stints remain positive."""
    import re
    if isinstance(value,bool):return 0.0
    try:
        text=str(value or '').strip()
        if text.startswith('PT'):
            match=re.fullmatch(r'PT(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?',text)
            result=float(match.group(1) or 0)+float(match.group(2) or 0)/60 if match else 0.0
        elif ':' in text:
            minutes,seconds=text.split(':');result=float(minutes)+float(seconds)/60
        else:result=float(text)
        return result if math.isfinite(result) and result>0 else 0.0
    except (TypeError,ValueError):return 0.0


def _is_final(status):
    import re
    return bool(re.fullmatch(r'Final(?:/(?:OT|[2-9]OT))?(?: \([^)]+\))?',str(status or '').strip(),flags=re.I))


def fetch_results_for_date(game_date):
    """Reuse the maintained reflector finality path; preserve old source files."""
    import importlib.util
    from datetime import datetime,timezone
    from pathlib import Path
    target=Path(DATASET_DIR)/'results_brief';target.mkdir(parents=True,exist_ok=True)
    original=target/f'Results_Brief_{game_date}.json'
    verified=target/f'Results_Brief_{game_date}_Verified.json'
    for candidate in (verified,original):
        if candidate.is_file():
            data=json.loads(candidate.read_text())
            if data.get('date')==game_date and data.get('games') and all(_is_final(g.get('status')) for g in data['games']):
                return str(candidate)
    script=PROJECT_ROOT/'.agents/skills/nba/nba_reflector/scripts/fetch_nba_results.py'
    spec=importlib.util.spec_from_file_location('_nba_ml_verified_results',script)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    day=datetime.strptime(game_date,'%Y-%m-%d').date()
    games=module.fetch_scoreboard(day.strftime('%m/%d/%Y'))
    if not games:return None
    events,reachable=module.fetch_espn_events(game_date)
    espn=module.espn_index(events) if reachable else None
    safely_past=(datetime.now(timezone.utc).date()-day).days>=2
    results=[];seen=set()
    for game in games:
        if game.get('gameId') in seen:continue
        seen.add(game.get('gameId'))
        results.append(module.process_game(game,boxscore_may_settle=safely_past,espn=espn))
    payload={'_version':'RESULTS_BRIEF_V2','date':game_date,'games':results,
             'total_games':len(results),'source':'shared NBA reflector finality','retrieved_at':datetime.now(timezone.utc).isoformat()}
    temporary=Path(str(verified)+'.tmp')
    temporary.write_text(json.dumps(payload,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    os.replace(temporary,verified)
    return str(verified)


# ─── Feature Extraction ───

def find_archive_folders():
    """Find all archive folders that contain nba_game_data_*.json or equivalent."""
    folders = []
    for entry, path_obj in nba_archive_folders():
        path = str(path_obj)
        feature_files = (
            [f for f in os.listdir(path) if f.startswith("nba_game_data_") and f.endswith(".json")]
            or [f for f in os.listdir(path) if "_data.json" in f and f.startswith("Game_")]
        )
        if feature_files:
            folders.append((entry, path, feature_files))
    return folders


def extract_date_from_game_data(filepath):
    """Extract game date from nba_game_data JSON meta."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        date_str = data.get("meta", {}).get("date", "")
        if date_str:
            from nba_ml_pit import game_day
            return game_day(data.get("meta", {}))
    except Exception:
        pass
    return None


def extract_game_data(filepath, *, sportsbet=None, odds_path=None, provenance=None):
    """Build v2 features; unverified/template rows are never trainable.

    Optional independent provenance is used by the archive audit; daily data
    automatically resolve a hash-matched immutable prediction snapshot.
    """
    from pathlib import Path
    from nba_ml_features import FEATURE_CONTRACT, build_features
    from nba_ml_pit import validate_capture, sha
    from nba_schedule import canonical_team_abbr, canonical_game_tag
    from nba_identity import player_name_key
    from nba_availability import usage_from_injuries, usage_bonus_for
    path=Path(filepath)
    data=json.loads(path.read_text())
    meta=data.get('meta') or {}
    away=canonical_team_abbr((meta.get('away') or {}).get('abbr',''))
    home=canonical_team_abbr((meta.get('home') or {}).get('abbr',''))
    if not away or not home or away==home:raise ValueError('game team identities missing')
    tag=f'{away}_{home}'
    if sportsbet is None and odds_path is None:
        matches=[p for p in path.parent.glob('Sportsbet_Odds_*.json')
                 if canonical_game_tag(p.stem.removeprefix('Sportsbet_Odds_'))==tag]
        if len(matches)==1:odds_path=matches[0]
    if sportsbet is None and odds_path is not None:sportsbet=json.loads(Path(odds_path).read_text())
    evidence=validate_capture(data,path,odds_path,provenance)
    def normalize(groups):
        result={}
        for key,value in groups.items():
            key=canonical_team_abbr(key)
            if key in result:raise ValueError('ambiguous team aliases')
            result[key]=value
        return result
    players_by_team=normalize(data.get('players') or {})
    team_stats=normalize(data.get('team_stats') or {})
    defenders=normalize(data.get('key_defenders') or {})
    injuries=normalize(data.get('injuries') or {})
    usage=usage_from_injuries(players_by_team,injuries)
    categories={'PTS':'points','REB':'rebounds','AST':'assists','FG3M':'threes_made'}
    source_fields={'source_game_path':str(path.resolve()),'source_game_sha256':sha(path),
                   'source_odds_path':str(Path(odds_path).resolve()) if odds_path else None,
                   'source_odds_sha256':sha(odds_path) if odds_path else None,
                   'source_provenance':json.dumps(evidence['provenance'],sort_keys=True)}
    rows=[]
    for team in (away,home):
        opponent=away if team==home else home
        context=team_stats.get(opponent) or {}
        defender_rows=defenders.get(opponent) or []
        defender_pm=defender_rows[0].get('PCT_PLUSMINUS') if defender_rows else None
        for player in players_by_team.get(team,[]):
            name=player.get('name','');key=player_name_key(name)
            if not key:raise ValueError('player identity missing')
            for stat in STAT_CATEGORIES:
                arr=(player.get('gamelog') or {}).get(stat) or []
                if not arr:continue
                if sportsbet is not None:
                    entries=(sportsbet.get('player_props') or {}).get(categories[stat]) or {}
                    matches=[value for candidate,value in entries.items() if player_name_key(candidate)==key]
                    if len(matches)>1:raise ValueError('ambiguous priced player identity')
                    priced=(matches[0].get('lines') or {}) if matches else {}
                    lines=[]
                    for line,price in priced.items():
                        line=float(line);price=float(price)
                        if math.isfinite(line) and line>0 and line.is_integer() and math.isfinite(price) and price>1:
                            lines.append((line,price))
                else:lines=[(line,None) for line in SPORTSBET_LINES[stat]]
                for line,price in lines:
                    features=build_features(player,stat,line,int(team==home),opponent,
                        opp_def_rating=context.get('DEF_RATING'),opp_def_rank=context.get('DEF_RANK'),
                        opp_pace=context.get('PACE'),defender_pm=defender_pm,
                        usg_bonus_pct=usage_bonus_for(usage,team,name) if team in injuries else None)
                    rows.append({
                        'feature_contract':FEATURE_CONTRACT,'population':'priced_milestone' if price is not None else 'template_ladder',
                        'game_date':evidence['game_date'],'game_group':evidence['game_date']+':'+tag,
                        'game_tag':tag,'player':name,'player_key':key,'team':team,'opponent':opponent,'position':player.get('position',''),
                        'stat_category':stat,**features,'market_price':price,'n_history':len(arr),
                        'pit_status':evidence['pit_status'],'pit_flags':json.dumps(evidence['pit_flags']),
                        'event_start':evidence['event_start'],'captured_at':evidence['captured_at'],
                        **source_fields,
                        'result_status':None,'source_result_path':None,'source_result_sha256':None,
                        'actual_value':None,'hit':None,
                    })
    return rows


# ─── Label Matching ───

# ESPN → NBA standard abbreviation mapping (feature files use ESPN abbr)
ESPN_TO_STANDARD = {
    "GS": "GSW", "NO": "NOP", "NY": "NYK",
    "SA": "SAS", "UTAH": "UTA", "WSH": "WAS",
}
STANDARD_TO_ESPN = {v: k for k, v in ESPN_TO_STANDARD.items()}


def load_results_brief(filepath):
    """Only Final, internally consistent games can contribute training labels."""
    from nba_schedule import canonical_team_abbr
    from nba_identity import player_name_key
    from nba_ml_pit import sha
    data=json.loads(_Path(filepath).read_text())
    lookup={}
    for game in data.get('games') or []:
        if not _is_final(game.get('status')):continue
        away=canonical_team_abbr((game.get('away') or {}).get('team',''))
        home=canonical_team_abbr((game.get('home') or {}).get('team',''))
        if not away or not home or away==home:continue
        players={};valid=True
        for player in game.get('players') or []:
            team=canonical_team_abbr(player.get('team',''));key=(team,player_name_key(player.get('name','')))
            if team not in (away,home) or not key[1] or key in players:valid=False;break
            players[key]=player
        for side,team in (('away',away),('home',home)):
            score=(game.get(side) or {}).get('score')
            points=[p.get('pts') for (pteam,_),p in players.items() if pteam==team]
            if not points or any(not isinstance(x,(int,float)) or isinstance(x,bool) or not math.isfinite(x) for x in points):
                valid=False;break
            if score is None or sum(points)!=score:valid=False;break
        if not valid:continue
        tag=f'{away}_{home}'
        if tag in lookup:raise ValueError('ambiguous results event')
        lookup[tag]={'players':players,'game_date':data.get('date'),'status':'Final',
                     'source_path':str(_Path(filepath).resolve()),'source_sha256':sha(filepath)}
    return lookup


def match_results(rows,results_lookup):
    """Exact US date/event/team/player join; DNP/missing values are not misses."""
    from nba_identity import player_name_key
    for row in rows:
        game=results_lookup.get(row['game_tag'])
        if not game or game['game_date']!=row['game_date']:continue
        player=game['players'].get((row['team'],player_name_key(row['player'])))
        if not player or parse_minutes(player.get('minutes'))<=0:continue
        value=player.get(STAT_KEY_MAP[row['stat_category']])
        if not isinstance(value,(int,float)) or isinstance(value,bool) or not math.isfinite(value) or value<0:continue
        row.update(actual_value=value,hit=int(value>=row['line_value']),result_status='Final',
                   source_result_path=game['source_path'],source_result_sha256=game['source_sha256'])
    return rows


# ─── Main Pipeline ───

def build_consolidated_dataset(folders,skip_fetch=False,skip_verify=False):
    """Group by each event's actual US date, never by the first file/folder."""
    from collections import defaultdict
    from nba_ml_pit import capture_order
    root=_Path(DATASET_DIR)
    (root/'per_date').mkdir(parents=True,exist_ok=True)
    (root/'results_brief').mkdir(parents=True,exist_ok=True)
    rows=[];skipped=0
    for _,folder,files in folders:
        for name in files:
            extracted=extract_game_data(_Path(folder)/name)
            if not extracted:skipped+=1
            rows.extend(extracted)
    unique={};duplicates=0
    for row in sorted(rows,key=capture_order):
        key=tuple(row[name] for name in ('game_group','player_key','stat_category','line_value'))
        if key in unique:duplicates+=1
        else:unique[key]=row
    by_date=defaultdict(list);unknown_sources=set();unknown_date_rows=0
    for row in unique.values():
        if row['game_date']:by_date[row['game_date']].append(row)
        else:
            unknown_sources.add(row["source_game_path"]);unknown_date_rows+=1
    result=[]
    for day,date_rows in sorted(by_date.items()):
        if skip_fetch:
            candidates=[root/'results_brief'/f'Results_Brief_{day}_Verified.json',root/'results_brief'/f'Results_Brief_{day}.json']
            result_path=next((str(path) for path in candidates if path.is_file()),None)
        else:result_path=fetch_results_for_date(day)
        if result_path:
            date_rows=match_results(date_rows,load_results_brief(result_path))
        (root/'per_date'/f'dataset_{day}.json').write_text(json.dumps(date_rows,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
        result.extend(date_rows)
    stats={'dates_processed':len(by_date),'dates_skipped':len(unknown_sources),'files_without_rows':skipped,'unknown_date_rows':unknown_date_rows,'duplicate_rows_resolved_earliest':duplicates,
           'total_feature_rows':len(result),'labeled_rows':sum(r['hit'] is not None for r in result),
           'hits':sum(r['hit']==1 for r in result),'misses':sum(r['hit']==0 for r in result),
           'unverified_rows':sum(r['pit_status']!='verified' for r in result),
           'template_rows':sum(r['population']!='priced_milestone' for r in result)}
    return result,stats


def write_csv(rows, filepath):
    if not rows:
        print("❌ No rows to write")
        return
    fieldnames = list(rows[0].keys())
    with open(filepath, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"✅ CSV: {filepath} ({len(rows)} rows)")


def main():
    parser = argparse.ArgumentParser(description="NBA ML Dataset Builder V2")
    parser.add_argument("--skip-fetch", action="store_true",
                        help="Skip fetching Results_Brief from nba_api")
    parser.add_argument("--skip-verify", action="store_true",
                        help="Deprecated compatibility flag; mandatory source/Final validation is never skipped")
    parser.add_argument("--output-dir", required=True, help="New dataset directory; existing outputs are never overwritten")
    parser.add_argument("--date", type=str,
                        help="Process only this date (YYYY-MM-DD)")
    args = parser.parse_args()

    global DATASET_DIR
    DATASET_DIR = str(_Path(args.output_dir).resolve())
    _Path(DATASET_DIR).mkdir(parents=True,exist_ok=False)
    print("🏀 NBA ML Dataset Builder V2")
    print("=" * 60)

    folders = find_archive_folders()
    print(f"\n📂 Found {len(folders)} archive folders with feature data")

    if args.date:
        folders = [(n, p, f) for n, p, f in folders if args.date in n]
        print(f"   Filtered to {len(folders)} folders")

    if not folders:
        print("❌ No matching folders found")
        sys.exit(1)

    for name, _, ffs in folders:
        print(f"   {name}: {len(ffs)} game files")

    rows, stats = build_consolidated_dataset(folders, args.skip_fetch, args.skip_verify)

    print(f"\n{'='*60}")
    print(f"📊 DATASET BUILD COMPLETE")
    print(f"   Dates: {stats['dates_processed']}")
    print(f"   Feature rows: {stats['total_feature_rows']}")
    if not args.skip_fetch:
        print(f"   Labeled: {stats['labeled_rows']}")
        print(f"   Hits: {stats['hits']} | Misses: {stats['misses']}")
        if stats['labeled_rows'] > 0:
            hr = stats['hits'] / stats['labeled_rows'] * 100
            print(f"   Hit rate: {hr:.1f}%")
    print(f"{'='*60}")

    csv_path = os.path.join(DATASET_DIR, "dataset.csv")
    write_csv(rows, csv_path)

    meta = {
        "_version": "NBA_ML_DATASET_V2",
        "feature_contract": "nba-ml-features/v2",
        "data_quality": stats,
        "total_rows": len(rows),
        "labeled_rows": stats.get("labeled_rows", 0),
        "total_hits": stats.get("hits", 0),
        "total_misses": stats.get("misses", 0),
        "dates_processed": stats["dates_processed"],
        "stat_categories": STAT_CATEGORIES,
        "lines_per_stat": SPORTSBET_LINES,
        "feature_columns": list(rows[0].keys()) if rows else [],
        "target_column": "hit",
    }
    meta_path = os.path.join(DATASET_DIR, "dataset_meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"✅ Meta: {meta_path}")

    print(f"\n📁 All data → {DATASET_DIR}/")
    print(f"   dataset.csv (main matrix)")
    print(f"   dataset_meta.json (columns)")
    print(f"   per_date/ (raw per-date)")
    print(f"   results_brief/ (box scores — permanent)")


if __name__ == "__main__":
    main()
