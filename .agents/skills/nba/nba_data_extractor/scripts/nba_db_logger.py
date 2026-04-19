os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import sqlite3
import argparse
import re
import os
import json
from datetime import datetime

# ==========================================
# 工作區根目錄設定
# ==========================================
WORKSPACE_DIR = "."
DB_PATH = os.path.join(WORKSPACE_DIR, "nba_backtest.db")

def init_db():
    """初始化 SQLite 數據庫"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 建立 predictions 表 (紀錄賽前預測)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_date TEXT,
            game_matchup TEXT,
            tier TEXT,
            player_name TEXT,
            team_abbr TEXT,
            prop_stat TEXT,
            direction TEXT,
            prop_line REAL,
            predicted_hit_rate REAL,
            edge REAL,
            confidence_score INTEGER,
            created_at TEXT
        )
    ''')
    
    # 建立 actual_results 表 (紀錄實際賽果)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS actual_results (
            prediction_id INTEGER PRIMARY KEY,
            actual_value REAL,
            cleared BOOLEAN,
            margin REAL,
            recorded_at TEXT,
            FOREIGN KEY(prediction_id) REFERENCES predictions(id)
        )
    ''')
    
    conn.commit()
    conn.close()

def parse_report_and_log(report_path):
    """解析 Markdown 報告並寫入數據庫"""
    if not os.path.exists(report_path):
        print(f"❌ 找不到報告檔案: {report_path}")
        return

    with open(report_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    game_date = "YYYY-MM-DD"
    game_matchup = "UNKNOWN"
    current_tier = "UNKNOWN"
    
    # Regex 提取規則
    date_regex = re.compile(r"📅 數據鎖定：([0-9]{4}-[0-9]{2}-[0-9]{2})")
    matchup_regex = re.compile(r"單場分析 — (.+)")
    tier_regex = re.compile(r"組合 [0-9]+：(.+) —")
    # Leg 1｜Devin Booker (PHX) — PTS Over 24.5
    leg_regex = re.compile(r"Leg [0-9]+[｜|](.+?)\s*\((.+?)\)\s*[—-]\s*([A-Za-z0-9_]+)\s*(Over|Under)\s*([0-9.]+)", re.IGNORECASE)
    # 命中率：L10=70% L5=80% L3=100% | 信心分：8/10
    stats_regex = re.compile(r"命中率：.*L10=([0-9.]+)%.*信心分：([0-9.]+)/10", re.IGNORECASE)
    # +EV 篩選：隱含勝率=X% | 預估勝率=X% | Edge=15.4%
    edge_regex = re.compile(r"Edge=([+\-0-9.]+)", re.IGNORECASE)

    predictions = []
    
    current_leg = {}

    for line in lines:
        line = line.strip()
        
        # 提取全域資訊
        if match := date_regex.search(line):
            game_date = match.group(1)
        if match := matchup_regex.search(line):
            game_matchup = match.group(1).strip()
        if match := tier_regex.search(line):
            current_tier = match.group(1).split("SGM")[0].strip()

        # 提取 Leg 資訊
        if match := leg_regex.search(line):
            if current_leg:
                predictions.append(current_leg)
            
            p_name = match.group(1).strip()
            # Handle possible Markdown bolding
            p_name = p_name.replace('**', '')
            
            current_leg = {
                "game_date": game_date,
                "game_matchup": game_matchup,
                "tier": current_tier,
                "player_name": p_name,
                "team_abbr": match.group(2).strip().replace('**', ''),
                "prop_stat": match.group(3).strip(),
                "direction": match.group(4).capitalize(),
                "prop_line": float(match.group(5).strip()),
                "predicted_hit_rate": 0.0,
                "edge": 0.0,
                "confidence_score": 0
            }
            continue

        if current_leg and (match := stats_regex.search(line)):
            current_leg["predicted_hit_rate"] = float(match.group(1))
            current_leg["confidence_score"] = int(float(match.group(2)))
            
        if current_leg and (match := edge_regex.search(line)):
            current_leg["edge"] = float(match.group(1).replace('+', ''))

    if current_leg:
        predictions.append(current_leg)

    # 寫入 SQLite
    if predictions:
        print(f"✅ 解析完成：共 {len(predictions)} 個預測 Legs")
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        
        for p in predictions:
            cursor.execute('''
                INSERT INTO predictions 
                (game_date, game_matchup, tier, player_name, team_abbr, prop_stat, direction, prop_line, predicted_hit_rate, edge, confidence_score, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                p["game_date"], p["game_matchup"], p["tier"], p["player_name"], p["team_abbr"], 
                p["prop_stat"], p["direction"], p["prop_line"], p["predicted_hit_rate"], 
                p["edge"], p["confidence_score"], now
            ))
            print(f"  📝 已寫入: {p['player_name']} {p['prop_stat']} {p['direction']} {p['prop_line']}")
            
        conn.commit()
        conn.close()
    else:
        print("⚠️ 未能在報告中找到規範格式的 Leg 記錄")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NBA Wong Choi DB Logger")
    parser.add_argument("--init", action="store_true", help="初始化數據庫")
    parser.add_argument("--parse", type=str, help="解析指定 Markdown 分析報告並入庫")
    
    args = parser.parse_args()
    
    if args.init:
        init_db()
        print("✅ 數據庫已初始化。")
        
    if args.parse:
        init_db() # 確保有庫
        parse_report_and_log(args.parse)
