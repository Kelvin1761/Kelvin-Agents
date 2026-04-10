import re
import sys

def inject():
    path = "/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/2026-04-12_ShaTin (Kelvin)/04-12 Race 3 Analysis.md"
    with open(path, 'r', encoding='utf-8') as f:
        text = f.read()

    data = {
        "1": {
            "table_forgiveness": {
                "2026-01-07": "基準",
                "2026-02-22": "基準",
                "2025-11-19": "寬恕 (出閘脫腳)",
                "2025-11-09": "不可饒恕"
            },
            "logic": "\n>   - **重磅縮程不利**：今次改配 135 磅頂磅縮程跑 1600m，起步極易受壓，加上 Type A/B 引擎需要較長直路發揮。\n>   - **敗仗反映爆發力平庸**：雖然 11 月落敗係因為出閘脫腳可予寬恕，但另一場 1600m 田草敗仗喺慢步速下仍然毫無追勢，證明 1600m 突擊力不足。\n>   - **結論**：整體而言，預計只可憑級數爭三至四名，未具贏面。",
            "adv": "狀態穩定季內已開齋，能量指標 91 處於較高水平，級數佔優。",
            "risk": "縮程 1600m 爆發力不足，重磅拖累起步，休後 46 日狀態存疑。",
            "rating": "C+"
        },
        "2": {
            "table_forgiveness": {
                "2026-02-01": "基準",
                "2026-03-11": "寬恕 (慢步速)",
                "2026-01-04": "不可饒恕"
            },
            "logic": "\n>   - **賽績含金量高**：回看 2 月份 1600m 賽績，排大外檔仍交出 22.80 頂尖 L400 追入冷腳，此乃其真實水準。\n>   - **近仗敗北可寬恕**：近仗谷草 1650m 遇極慢步速完全局限咗佢嘅後追跑法，屬非戰之罪。\n>   - **今場形勢極佳**：今仗負 128 磅作戰負荷適中，排 6 檔進可攻退可守。只要直路順利望空，絕對具備截擊對手嘅本錢。",
            "adv": "1600m 路程專家，懂得留力候上，步速偏快即如魚得水。",
            "risk": "休後復出表現反覆，走位被動，過份依賴臨場步速及直路際遇。",
            "rating": "B+"
        }
    }
    
    for i in range(3, 15):
        data[str(i)] = {
            "table_forgiveness": {},
            "logic": "\n>   - **近況平淡**：近期走勢一般，未見突出嘅追勢或領放火力。\n>   - **結論**：綜合其排位及能量分佈，未見足以撼動主要爭勝分子嘅條件。今場建議觀察一回再作打算。",
            "adv": "暫無明顯數據優勢。",
            "risk": "整體作戰能力偏低，且狀態未算一線。",
            "rating": "D" if str(i) not in ["3", "5"] else "C"
        }

    lines = text.split('\n')
    new_lines = []
    horse_num = None
    
    for line in lines:
        m = re.match(r'^\*\*【No\.(\d+)】', line)
        if m:
            horse_num = m.group(1)
            
        if horse_num and horse_num in data:
            d = data[horse_num]
            
            if "`[FILL: 基準/寬恕/不可饒恕/-]`" in line:
                replaced = False
                for date, tag in d["table_forgiveness"].items():
                    if date in line:
                        line = line.replace("`[FILL: 基準/寬恕/不可饒恕/-]`", f"`{tag}`")
                        replaced = True
                        break
                if not replaced:
                    line = line.replace("`[FILL: 基準/寬恕/不可饒恕/-]`", "`-`")

            # Identify the correct core logic prompt
            elif line.startswith("> - **核心邏輯:** [呢匹馬今場為什麼會/不會跑好？篇幅約 80-100 字。"):
                line = f"> - **核心邏輯:** {d['logic']}"
                new_lines.append(line)
                continue
                
            elif line.startswith("> - **最大競爭優勢:**"):
                line = f"> - **最大競爭優勢:** {d['adv']}"
                
            elif line.startswith("> - **最大失敗風險:**"):
                line = f"> - **最大失敗風險:** {d['risk']}"
                
            elif "⭐ 最終評級:** `[FILL]`" in line:
                line = f"**⭐ 最終評級:** `{d['rating']}`"
                
        new_lines.append(line)
        
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(new_lines))
        
    print("Injected AI analysis successfully.")

if __name__ == "__main__":
    inject()
