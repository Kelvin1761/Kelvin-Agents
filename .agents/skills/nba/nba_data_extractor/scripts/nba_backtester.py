import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import sqlite3
import argparse
import time
from datetime import datetime
from nba_api.stats.endpoints import playergamelog
from nba_api.stats.static import players

WORKSPACE_DIR = "."
DB_PATH = os.path.join(WORKSPACE_DIR, "nba_backtest.db")

def get_player_id(name):
    # Some basic matching
    found = players.find_players_by_full_name(name)
    if found:
        return found[0]['id']
    return None

def fetch_actual_stats(player_id, date_str):
    """
    獲取球員某日的實際數據
    注意: API 需要時間轉換, game_date 格式為 'MMM DD, YYYY'
    但穩健起見，拉 L10 出來找對應日期。
    """
    try:
        log = playergamelog.PlayerGameLog(player_id=player_id)
        df = log.get_data_frames()[0]
        time.sleep(0.6)
        
        # 轉換傳入的 YYYY-MM-DD 為 API 的日期格式作簡單比對
        # 或者直接對比日期字串
        # API 格式如 'APR 02, 2026'
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        api_date_str = dt.strftime("%b %d, %Y").upper()
        
        target_row = df[df['GAME_DATE'] == api_date_str]
        if not target_row.empty:
            row = target_row.iloc[0]
            # 計算 Combo Props
            row['PRA'] = row['PTS'] + row['REB'] + row['AST']
            row['PR'] = row['PTS'] + row['REB']
            row['PA'] = row['PTS'] + row['AST']
            row['RA'] = row['REB'] + row['AST']
            row['SB'] = row['STL'] + row['BLK']
            return row
        return None
    except Exception as e:
        print(f"⚠️ Fetch error for {player_id}: {e}")
        return None

def map_stat(api_row, prop_stat):
    prop_stat = prop_stat.upper().strip()
    mapping = {
        'PTS': 'PTS', 'REB': 'REB', 'AST': 'AST', 
        'STL': 'STL', 'BLK': 'BLK', '3PM': 'FG3M', 'FG3M': 'FG3M',
        'PRA': 'PRA', 'PR': 'PR', 'PA': 'PA', 'RA': 'RA', 'SB': 'SB'
    }
    if prop_stat in mapping:
        return api_row.get(mapping[prop_stat], None)
    return None

def run_backtest(target_date=None):
    if not os.path.exists(DB_PATH):
        print("❌ 找不到數據庫")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = '''
        SELECT p.* FROM predictions p
        LEFT JOIN actual_results a ON p.id = a.prediction_id
        WHERE a.prediction_id IS NULL
    '''
    if target_date:
        query += f" AND p.game_date = '{target_date}'"

    cursor.execute(query)
    pending = cursor.fetchall()

    if not pending:
        print("✅ 沒有需要回測的預測紀錄。")
        return

    print(f"🔍 找到 {len(pending)} 筆未驗證預測，開始抓取真實賽果...")

    results = []
    
    for row in pending:
        pid = row['id']
        pname = row['player_name']
        pdate = row['game_date']
        stat = row['prop_stat']
        direction = row['direction']
        line = row['prop_line']
        tier = row['tier']

        pl_id = get_player_id(pname)
        if not pl_id:
            print(f"⚠️ 找不到球員 ID: {pname}")
            continue
            
        api_data = fetch_actual_stats(pl_id, pdate)
        if api_data is None:
            print(f"⚠️ 找不到 {pname} 於 {pdate} 的出賽紀錄 (可能休戰/缺陣/延期)")
            # 我們可以視為不結算，或標記為 Void (這裡暫且跳過)
            continue
            
        actual_val = map_stat(api_data, stat)
        if actual_val is None:
            print(f"⚠️ 無法解析數據類別: {stat}")
            continue

        actual_val = float(actual_val)
        margin = actual_val - line
        
        cleared = False
        if direction.upper() == 'OVER' and actual_val > line:
            cleared = True
        elif direction.upper() == 'UNDER' and actual_val < line:
            cleared = True

        # Write to actual_results
        now = datetime.now().isoformat()
        cursor.execute('''
            INSERT INTO actual_results (prediction_id, actual_value, cleared, margin, recorded_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (pid, actual_val, cleared, margin, now))
        
        status = "✅ 命中" if cleared else "❌ 失敗"
        print(f" {status} | {pname} {stat} {direction} {line} | 真實: {actual_val} (Margin: {margin:+.1f})")
        
        results.append({
            "tier": tier,
            "cleared": cleared
        })

    conn.commit()
    conn.close()

    # 生成簡單報告
    if results:
        total = len(results)
        hits = sum(1 for r in results if r['cleared'])
        print("\n==========================================")
        print(f"📊 回測結算完成：總計 {total} 注，命中 {hits} 注 ({hits/total*100:.1f}%)")
        print("==========================================")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=str, help="YYYY-MM-DD", default=None)
    args = parser.parse_args()
    
    run_backtest(args.date)
