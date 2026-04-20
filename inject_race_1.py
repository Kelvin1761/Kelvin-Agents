import json
import os

target_file = "/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/2026-04-22_HappyValley (Kelvin)/Race_1_Logic.json"

data = {
    "speed_map": {
        "predicted_pace": "Fast",
        "leaders": ["4", "5", "7"],
        "on_pace": ["2", "8", "9", "12"],
        "mid_pack": ["3", "10", "11"],
        "closers": ["1", "6"],
        "track_bias": "跑馬地C道，內疊前置馬佔優",
        "tactical_nodes": "多匹馬具備前領速度，早段步速預計偏快，可能引發前領馬互相消耗。",
        "collapse_point": "最後三百米，前列馬匹群可能因為早段高耗損而力竭，後上馬有機會。"
    },
    "horses": {
        "1": {
            "matrix": {"speed_mass": "C", "eem": "B", "stamina": "C", "stability": "C", "track_fitness": "B", "jock_train": "B", "barrier_tactics": "C", "value_edge": "C"},
            "core_logic": "近仗完成時間逐漸改善，具超級反彈條件，但12檔構成障礙。",
            "advantages": ["超級反彈候選", "完成時間改善中"],
            "disadvantages": ["12檔", "走位消耗趨勢逐仗增加"]
        },
        "2": {
            "matrix": {"speed_mass": "C", "eem": "C", "stamina": "C", "stability": "B", "track_fitness": "C", "jock_train": "B", "barrier_tactics": "C", "value_edge": "C"},
            "core_logic": "完成時間相對標準穩定，走位消耗減少，但L400表現一般。",
            "advantages": ["走位消耗趨勢減少", "穩定性高"],
            "disadvantages": ["同程勝率低", "爆發力不足"]
        },
        "3": {
            "matrix": {"speed_mass": "C", "eem": "C", "stamina": "C", "stability": "C", "track_fitness": "B", "jock_train": "C", "barrier_tactics": "B", "value_edge": "C"},
            "core_logic": "最佳距離1200m，但近仗PI衰退中，走位波幅大。",
            "advantages": ["1200m路程專家"],
            "disadvantages": ["PI衰退中", "近仗名次波動"]
        },
        "4": {
            "matrix": {"speed_mass": "B", "eem": "C", "stamina": "C", "stability": "B", "track_fitness": "B", "jock_train": "A", "barrier_tactics": "A", "value_edge": "B"},
            "core_logic": "抽得1檔好位，L400及時間穩定，具備爭勝實力。",
            "advantages": ["1檔", "L400上升軌", "強配"],
            "disadvantages": ["未有頭馬紀錄"]
        },
        "5": {
            "matrix": {"speed_mass": "B", "eem": "C", "stamina": "C", "stability": "B", "track_fitness": "C", "jock_train": "B", "barrier_tactics": "C", "value_edge": "C"},
            "core_logic": "前置型跑法，近仗時間改善，但10檔增加消耗風險。",
            "advantages": ["時間改善", "前速快"],
            "disadvantages": ["10檔外檔", "走位PI衰退"]
        },
        "6": {
            "matrix": {"speed_mass": "B", "eem": "A", "stamina": "B", "stability": "C", "track_fitness": "B", "jock_train": "B", "barrier_tactics": "B", "value_edge": "B"},
            "core_logic": "上仗極高消耗，屬超級反彈候選，末段爆發力強。",
            "advantages": ["超級反彈候選", "末段爆發力強"],
            "disadvantages": ["起步偏慢", "走位消耗增加"]
        },
        "7": {
            "matrix": {"speed_mass": "C", "eem": "D", "stamina": "C", "stability": "C", "track_fitness": "C", "jock_train": "C", "barrier_tactics": "B", "value_edge": "D"},
            "core_logic": "連續3仗高消耗，實力見底風險高，不宜過分追捧。",
            "advantages": ["超級反彈條件"],
            "disadvantages": ["連續3仗高消耗", "明顯慢於標準"]
        },
        "8": {
            "matrix": {"speed_mass": "B", "eem": "C", "stamina": "B", "stability": "B", "track_fitness": "C", "jock_train": "A", "barrier_tactics": "B", "value_edge": "B"},
            "core_logic": "配潘頓強配，L400上升軌，時間穩定，具備競爭力。",
            "advantages": ["潘頓策騎", "L400上升軌", "時間穩定"],
            "disadvantages": ["高累積消耗"]
        },
        "9": {
            "matrix": {"speed_mass": "C", "eem": "C", "stamina": "C", "stability": "C", "track_fitness": "C", "jock_train": "C", "barrier_tactics": "C", "value_edge": "C"},
            "core_logic": "L400及能量雙雙下降，狀態平庸，難以言勝。",
            "advantages": ["時間改善"],
            "disadvantages": ["L400衰退", "能量下降"]
        },
        "10": {
            "matrix": {"speed_mass": "C", "eem": "C", "stamina": "C", "stability": "B", "track_fitness": "C", "jock_train": "C", "barrier_tactics": "C", "value_edge": "C"},
            "core_logic": "走位PI上升軌，但11檔外檔及起步偏慢構成負面影響。",
            "advantages": ["PI上升", "時間穩定"],
            "disadvantages": ["11檔", "起步慢"]
        },
        "11": {
            "matrix": {"speed_mass": "C", "eem": "B", "stamina": "C", "stability": "C", "track_fitness": "C", "jock_train": "C", "barrier_tactics": "B", "value_edge": "C"},
            "core_logic": "超級反彈候選，2檔內檔有利，但L400衰退中。",
            "advantages": ["超級反彈", "2檔"],
            "disadvantages": ["L400衰退", "高累積消耗"]
        },
        "12": {
            "matrix": {"speed_mass": "C", "eem": "B", "stamina": "B", "stability": "C", "track_fitness": "C", "jock_train": "C", "barrier_tactics": "C", "value_edge": "B"},
            "core_logic": "超級反彈候選，L400上升，時間改善，具備冷門潛力。",
            "advantages": ["超級反彈", "時間改善", "L400上升"],
            "disadvantages": ["8檔", "近期大敗"]
        }
    }
}

if os.path.exists(target_file):
    with open(target_file, "r", encoding="utf-8") as f:
        existing_data = json.load(f)
else:
    existing_data = {}

existing_data["speed_map"] = data["speed_map"]
existing_data["horses"] = data["horses"]

with open(target_file, "w", encoding="utf-8") as f:
    json.dump(existing_data, f, ensure_ascii=False, indent=2)

print("Injected Race 1 Logic!")
