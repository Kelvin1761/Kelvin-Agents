"""
PrizePicks / Underdog Fantasy PoC Scanner
專門用於繞過 Cloudflare 提取 PrizePicks 前端公開投影 (Projections) 數據。
這些基準線可以作為 NBA Wong Choi 的 "Value Line" 參考。

使用 curl_cffi 繞過指紋檢測。
"""

import json
import time
from datetime import datetime

try:
    from curl_cffi import requests as cffi_requests
except ImportError:
    print("❌ 缺少核心依賴庫。請執行：pip install curl-cffi")
    exit(1)

CFFI_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://app.prizepicks.com/",
    "Origin": "https://app.prizepicks.com"
}

def fetch_prizepicks_nba_props():
    print("🎯 [Prizepicks] 正在拉取 NBA Projections 基準線...")
    # PrizePicks API 中，NBA 通常 league_id 為 7
    # 注意：如果返回 403，可能需要進一步更新 headers 或者使用代理
    url = "https://api.prizepicks.com/projections?league_id=7&per_page=250&single_stat=true"
    
    try:
        r = cffi_requests.get(url, headers=CFFI_HEADERS, impersonate="chrome120", timeout=15)
        if r.status_code == 200:
            data = r.json()
            included = data.get("included", [])
            data_arr = data.get("data", [])
            
            # Prizepicks 的結構是 JSON:API，所以要自己聯表
            # included 裡裝著 player 的名字
            players_map = {}
            for inc in included:
                if inc.get("type") == "new_player":
                    players_map[inc["id"]] = inc["attributes"].get("name", "Unknown")
            
            props = []
            for item in data_arr:
                attr = item.get("attributes", {})
                rel = item.get("relationships", {})
                player_id = rel.get("new_player", {}).get("data", {}).get("id")
                
                player_name = players_map.get(player_id, "Unknown")
                stat_type = attr.get("stat_type", "")
                line_score = attr.get("line_score", 0)
                description = attr.get("description", "")
                
                # 只保留常見別 (Pts, Reb, Ast)
                if stat_type in ["Points", "Rebounds", "Assists", "Pts+Rebs+Asts", "3-PT Made"]:
                    props.append({
                        "player": player_name,
                        "stat": stat_type,
                        "line": line_score,
                        "team": description # 偶爾存放在這
                    })
                    
            print(f"  ✅ 成功拉取 {len(props)} 條 NBA Props 基準線。")
            return props
        else:
            print(f"  ⚠️ Prizepicks 回傳狀態碼: {r.status_code}")
            return []
    except Exception as e:
        print(f"  ⚠️ 拉取失敗: {e}")
        return []

if __name__ == "__main__":
    props = fetch_prizepicks_nba_props()
    if props:
        # 只顯示前 10 條作示範
        print("\n=== 最新 NBA 官方基準線 (Top 10) ===")
        for p in props[:10]:
            print(f"👤 {p['player']} | 📊 {p['stat']}: {p['line']}")
        
        # 儲存到本地供 Wong Choi 使用
        output_path = ".agents.agents/tmp/nba_prizepicks_baseline.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({"updated_at": datetime.now().isoformat(), "props": props}, f, ensure_ascii=False, indent=2)
        print(f"\n✅ 完整數據已備份至: {output_path}")
