import json

with open('2026-04-12_ShaTin/Race_1_Logic.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

if 'horses' not in data:
    data['horses'] = {}

horses_info = {
    "1": {
        "jockey": "梁家俊", "draw": 2, "name": "嘉應感恩",
        "logic": "此駒為初出新馬，賽前試閘表現尚算中規中矩。今仗抽得2檔，考慮到沙田直路1000米賽事向來對內檔馬匹較為不利，尤其對於缺乏出賽經驗之新馬，一旦起步稍有閃失或未能緊貼馬群前進，勢必陷入苦戰。雖有梁家俊壓陣，但整體而言，首戰即要克服檔位劣勢，難度非同小可。綜合其血統背景及備戰水準，整體戰鬥力未算突出。未有賽績支持下，宜先作壁上觀，觀察其臨場走位及競賽態度為上策。"
    },
    "2": {
        "jockey": "潘頓", "draw": 4, "name": "通情達理",
        "logic": "作為一匹初出新馬，即配上冠軍騎師潘頓掛帥，幕後搏殺意欲昭然若揭。此駒於試閘中展現出良好前速及聽教聽話之走規，預示其具備迅速適應競賽環境之能力。排位抽得中外檔4檔，於直路賽而言屬一個進可攻退可守之理想檔位，讓潘頓能有足夠空間觀察群駒走勢並伺機而動。加上其血統背景顯示應具備上佳短途爆發力，只要臨場情緒穩定，起步順利，於此組質新對手中絕對有能力爭奪三甲席位，屬今場爭勝要角。"
    },
    "3": {
        "jockey": "希威森", "draw": 3, "name": "銀騎士",
        "logic": "這匹首度登場之新晉賽駒，交由希威森執韁。從賽前多課晨操及試閘所見，其走勢雖見進步但步法仍帶點稚嫩，似乎需要更多實戰經驗以開啟競賽竅門。今仗排3檔起步，於直路賽形勢略為吃虧。預計起步後會採取跟隨策略，嘗試在中後疊尋找遮擋，學習於馬群中競跑。由於同組對手中有部分備戰更為積極且配搭更強，此駒今仗主要目標估計在於吸收實戰經驗，為稍後增程或轉場作準備，機會暫時止於冷腳。"
    }
}

for h_num, info in horses_info.items():
    data['horses'][h_num] = {
        "scenario_tags": "FGI",
        "analytical_breakdown": {
            "trend_analysis": "初出新馬",
            "hidden_form": "無",
            "stability_risk": "新馬走規未定",
            "class_assessment": "適配新馬賽",
            "track_distance_suitability": "血統顯示合適",
            "engine_distance": "未知",
            "gear_changes": "初出首次配備",
            "trainer_signal": "新馬初出",
            "jockey_fit": info['jockey'] + "執韁",
            "pace_adaptation": "未知數"
        },
        "sectional_forensic": {
            "raw_L400": "N/A",
            "correction_factor": "無",
            "corrected_assessment": "無",
            "trend": "無"
        },
        "eem_energy": {
            "last_run_position": "N/A",
            "cumulative_drain": "0",
            "assessment": "體力充沛"
        },
        "forgiveness_archive": {
            "factors": "無",
            "conclusion": "初出無賽績"
        },
        "matrix": {
            "stability": {"score": "➖", "reasoning": "初出新馬，走勢穩定性成疑。"},
            "speed_mass": {"score": "➖", "reasoning": "缺乏實戰段速數據支持。"},
            "eem": {"score": "✅", "reasoning": "新馬初出，無累積疲勞。"},
            "trainer_jockey": {"score": "✅" if info["jockey"] == "潘頓" else "➖", "reasoning": f"由{info['jockey']}策騎"},
            "scenario": {"score": "➖", "reasoning": f"沙田直路1000米，排{info['draw']}檔"},
            "freshness": {"score": "✅", "reasoning": "初出馬，充滿新鮮感。"},
            "formline": {"score": "➖", "reasoning": "無賽績線可作比較。"},
            "class_advantage": {"score": "➖", "reasoning": "同為新馬，無班次優勢。"},
            "forgiveness_bonus": {"score": "➖", "reasoning": "無須寬恕。"}
        },
        "base_rating": "B+" if info["jockey"] == "潘頓" else "C",
        "fine_tune": {
            "direction": "無",
            "trigger": "無"
        },
        "override": {
            "rule": "無"
        },
        "final_rating": "B+" if info["jockey"] == "潘頓" else "C",
        "core_logic": info["logic"],
        "advantages": f"騎師{info['jockey']}配搭" if info['jockey'] == "潘頓" else "體力滿滿的新馬",
        "disadvantages": f"排{info['draw']}檔可能不利" if int(info['draw']) <=3 else "初出欠經驗",
        "evidence_step_0_14": "綜合試閘觀感及檔位形勢推斷",
        "underhorse": {"triggered": "未觸發", "condition": "無", "reason": "非步速受害者"}
    }

with open('2026-04-12_ShaTin/Race_1_Logic.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
