import os
import glob
import json
import argparse
from datetime import datetime

def parse_data_briefs(target_dir):
    files = glob.glob(os.path.join(target_dir, "Data_Brief_*.json"))
    if not files:
        print(f"⚠️ No Data Brief JSONs found in {target_dir}")
        return []

    value_bets = []
    
    for fpath in files:
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            meta = data.get("meta", {})
            away_team = meta.get("away", {}).get("abbr", "AWAY")
            home_team = meta.get("home", {}).get("abbr", "HOME")
            matchup_str = f"{away_team}@{home_team}"
            
            # Only parse V7 Data Brief Schema
            players = data.get("players", {})
            for player_name, pdata in players.items():
                props = pdata.get("props", {})
                for cat, cdata in props.items(): # PTS, AST, REB, 3PM
                    lines = cdata.get("lines", {})
                    for line_key, ldata in lines.items():
                        edge = ldata.get("edge", 0.0)
                        if edge > 0:
                            odds = float(ldata.get("odds", 0.0))
                            if odds < 1.4:
                                continue
                            implied = ldata.get("implied_prob", 0.0)
                            l10_hit_str = ldata.get("l10_hit", "")
                            l10_pct = ldata.get("l10_pct", 0)
                            expected_prob = ldata.get("adjusted_prob", 0)
                            verdict = "💎" if edge >= 10.0 else "✅" if edge >= 5.0 else "⚠️"
                            
                            value_bets.append({
                                "matchup": matchup_str,
                                "player": player_name,
                                "category": cat,
                                "line": line_key,
                                "odds": odds,
                                "implied": implied,
                                "l10_str": f"{l10_pct}% ({l10_hit_str})",
                                "expected": expected_prob,
                                "edge": edge,
                                "verdict": verdict
                            })
                            
        except Exception as e:
            print(f"❌ 解析失敗 {fpath}: {e}")

    # 按照 Edge 由高至低排序
    value_bets.sort(key=lambda x: x["edge"], reverse=True)
    return value_bets

def generate_markdown(value_bets, target_dir):
    today = datetime.now().strftime("%Y-%m-%d")
    
    tier_1 = [b for b in value_bets if b["edge"] >= 10.0]
    tier_2 = [b for b in value_bets if 5.0 <= b["edge"] < 10.0]
    tier_3 = [b for b in value_bets if 0.0 < b["edge"] < 5.0]

    md = [
        f"# 💎 全日 Value Bets 綜合掃描報告 ({today})",
        "> 本報表由 Python 計算引擎全自動掃描全日賽事。所有選項均具備正向Expected Value (+EV)。",
        ">",
        "> *提示: `Edge` = `數學預期勝率` - `盤口隱含勝率`*",
        ""
    ]

    def add_table(tier_list, title):
        md.append(f"### {title} (共 {len(tier_list)} 個)")
        md.append("| 比賽 | 球員 | 盤口 | 賠率 | 隱含勝率 | L10 命中 | 數學預期 | Edge |")
        md.append("|:---|:---|:---|:---|:---|:---|:---|:---|")
        if not tier_list:
            md.append("| (無) | | | | | | | |")
        for b in tier_list:
            md.append(f"| {b['matchup']} | {b['player']} | {b['category']} {b['line']} | @{b['odds']} | {b['implied']}% | {b['l10_str']} | {b['expected']}% | +{b['edge']:.2f}% {b['verdict']} |")
        md.append("")

    add_table(tier_1, "🚨 Tier 1: 莊家嚴重低估 (Edge ≥ 10%)")
    add_table(tier_2, "🟢 Tier 2: 核心高價值 (Edge 5% ‑ 9.99%)")
    add_table(tier_3, "🟡 Tier 3: 邊緣正期望 (Edge 0.1% ‑ 4.99%)")

    outpath = os.path.join(target_dir, "Value_Bets_Overview.md")
    with open(outpath, 'w', encoding='utf-8') as f:
        f.write("\n".join(md))
        
    print(f"🎉 成功生成 Value Bets 總表: {outpath}")
    print(f"   總共發現: {len(value_bets)} 個 +EV 盤口！")

def main():
    parser = argparse.ArgumentParser(description="Find value bets from Data Brief JSONs")
    parser.add_argument('--dir', required=True, help="Target directory containing Data_Brief_*.json files")
    args = parser.parse_args()

    if not os.path.exists(args.dir):
        print(f"❌ Directory not found: {args.dir}")
        return

    bets = parse_data_briefs(args.dir)
    generate_markdown(bets, args.dir)

if __name__ == "__main__":
    main()
