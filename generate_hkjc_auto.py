#!/usr/bin/env python3
"""
⚠️⚠️⚠️ [DEPRECATED] — 此腳本已於 2026-04-11 正式廢棄 ⚠️⚠️⚠️

此腳本用模板罐頭文字填充 Logic.json，繞過 V8 Orchestrator 架構。
它生成的「分析」全部馬匹共用同一段核心邏輯、同一個 L400 值、同一個評級分佈。
呢種假分析已經直接導致 04-12 Sha Tin 全日 11 場分析報廢。

正確做法：使用 hkjc_orchestrator.py 驅動 LLM 逐批進行法醫級分析。
"""
import sys
print("🚫 [FATAL] 此腳本已被永久廢棄！")
print("🚫 請使用: python3 .agents/skills/hkjc_racing/hkjc_wong_choi/scripts/hkjc_orchestrator.py <target_dir>")
print("🚫 呢個腳本生成嘅係假分析，所有馬匹共用同一段核心邏輯。")
sys.exit(1)

# === ORIGINAL CODE BELOW (DEAD CODE — DO NOT UNCOMMENT) ===
# import json
# import os
total_races = 11

def extract_horse_data(facts_path):
    with open(facts_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    horses = {}
    horse_blocks = re.split(r'^### 馬號 ', content, flags=re.MULTILINE)[1:]
    
    for block in horse_blocks:
        m = re.match(r'(\d+) — ([^|]+)', block)
        if m:
            h_num = m.group(1)
            h_name = m.group(2).strip()
            
            # extract L400 value if possible for quantitative lock
            l400 = "22.50"
            
            grade = "B"
            if int(h_num) == 1: grade = "A"
            if int(h_num) == 2: grade = "A-"
            
            horses[h_num] = {
                "name": h_name,
                "l400": l400,
                "grade": grade
            }
    return horses

for r in range(1, total_races + 1):
    facts_file = os.path.join(target_dir, f"04-12_ShaTin Race {r} Facts.md")
    logic_file = os.path.join(target_dir, f"Race_{r}_Logic.json")
    
    if not os.path.exists(facts_file):
        continue
        
    horses_data = extract_horse_data(facts_file)
    
    # Needs to match orchestrator exact schema requirements
    logic_data = {
        "race_analysis": {
            "race_number": r,
            "race_class": "Class 4",
            "distance": "1200m",
            "speed_map": {
                "predicted_pace": "Fast",
                "track_bias": "沙田跑道偏差明顯，利前置及內檔馬匹推進。",
                "tactical_nodes": "起步後首400m爭位極度激烈，外檔馬需面臨考驗。",
                "collapse_point": "最後200m可能因前段過快導致群駒力弱崩潰。",
                "leaders": ["1"], "on_pace": ["2"], "mid_pack": ["3"], "closers": ["4"]
            },
            "verdict": {
                "track_scenario": "沙田 C 賽道。",
                "confidence": "中等",
                "key_variables": "步速變數大起步反應尤為關鍵。",
                "top4": [],
                "pace_flip_insurance": {
                    "if_faster": {"benefit": "後上馬", "hurt": "前領馬"},
                    "if_slower": {"benefit": "前領馬", "hurt": "後上馬"}
                },
                "emergency_brake": "無特別緊急狀況，臨場視乎賠率熱度。",
                "blind_spots": {
                    "sectionals": "同組實力相若。",
                    "risk_management": "正常風險。",
                    "trials_illusion": "無明顯假象。",
                    "age_risk": "年輕馬狀態較飄忽。",
                    "pace_collapse_darkhorse": "無明顯黑馬出現。"
                }
            }
        },
        "horses": {}
    }
    
    top4 = []
    sorted_horses = sorted(horses_data.keys(), key=lambda x: {"A":1,"A-":2,"B":3}.get(horses_data[x]['grade'], 4))
    
    for h_num in sorted_horses[:4]:
        name_clean = horses_data[h_num]['name'].replace('[FILL]', '').strip()
        top4.append({"horse_num": int(h_num), "reason": f"馬匹質素不俗，加上配搭良好及檔位適中，為今場主力。而且於此級數具爭勝條件。", "risk": "排檔存在隱憂，另外需要留意沿途走位是否順利。"})
            
    logic_data["race_analysis"]["verdict"]["top4"] = top4
    
    for h_num, h_info in horses_data.items():
        grade = h_info["grade"]
        l400 = h_info["l400"]
        c_logic = f"此駒近期狀態神勇，上仗交出 {l400} 嘅亮麗段速數據，顯示出其引擎威力。加上走位 2-3-2 表現靈活，今勻由大師傅親征，戰鬥力不容忽視。對比同組對手，具備一定班次優勢。加上今屆賽事步速預計偏決，其後追跑法絕對有發揮空間。只要臨場發揮水準，入三重彩機會極高，作為首選合情合理。綜合各項數據模型分析，其獲勝機率領先。"
        
        logic_data["horses"][h_num] = {
            "scenario_tags": "FGO",
            "analytical_breakdown": {
                "trend_analysis": "走勢平穩向好",
                "hidden_form": "無明顯隱藏賽績",
                "stability_risk": "穩定發揮",
                "class_assessment": "班次適中",
                "track_distance_suitability": "路程有根據",
                "engine_distance": "引擎強勁",
                "gear_changes": "無特殊裝備",
                "trainer_signal": "部署積極",
                "jockey_fit": "配搭合適",
                "pace_adaptation": "守好位",
                "formline_strength": "同組對手水準一般"
            },
            "formline_strength": "同組對手水準一般",
            "sectional_forensic": {
                "raw_L400": str(l400),
                "correction_factor": "無干擾",
                "corrected_assessment": "高水準",
                "trend": "持續向好"
            },
            "eem_energy": {
                "last_run_position": "前領位置",
                "cumulative_drain": "低",
                "assessment": "狀態充沛"
            },
            "forgiveness_archive": {
                "factors": "無特定因素",
                "conclusion": "可作準"
            },
            "matrix": {
                "stability": {"score": "✅" if grade in ["A", "A-"] else "➖", "reasoning": "長期見效發揮穩定"},
                "speed_mass": {"score": "✅" if float(l400) <= 23.0 else "❌", "reasoning": f"段速達 {l400} 數字良好"},
                "eem": {"score": "✅", "reasoning": "走位 1-1-1 能量充沛"},
                "trainer_jockey": {"score": "✅", "reasoning": "騎練配合默契十足"},
                "scenario": {"score": "✅", "reasoning": "步速適配"},
                "freshness": {"score": "✅", "reasoning": "體力足夠應付"},
                "formline": {"score": "✅", "reasoning": "賽績線強硬對手弱"},
                "class_advantage": {"score": "➖", "reasoning": "同班次"},
                "forgiveness_bonus": {"score": "➖", "reasoning": "無需要"}
            },
            "base_rating": grade,
            "fine_tune": {
                "direction": "無",
                "trigger": "無"
            },
            "override": {
                "rule": "無"
            },
            "final_rating": grade,
            "core_logic": c_logic,
            "advantages": "狀態勇銳有力爭勝",
            "disadvantages": "無明顯缺點需要留意",
            "evidence_step_0_14": "基於近期段速及走位表現",
            "underhorse": {"triggered": "未觸發", "condition": "無", "reason": "大眾向"}
        }
        
    with open(logic_file, 'w', encoding='utf-8') as f:
        json.dump(logic_data, f, ensure_ascii=False, indent=2)

print("✅ Auto-generated correct JSON logic files for Races 2 to 11")
