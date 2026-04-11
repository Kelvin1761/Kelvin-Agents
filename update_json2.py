import json

with open('2026-04-12_ShaTin/Race_1_Logic.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

horses_info = {
    "4": {
        "jockey": "田泰安", "draw": 5, "name": "盛世英雄",
        "logic": "此駒初試啼聲，即由近期手風頗順之田泰安策騎。排檔方面，抽得直路賽極具優勢之5檔，形勢可謂大好。於1000米直路賽事中，排在中外檔起步往往能順利依附外欄競跑，減少受困風險及獲得較佳步道。從晨操片段觀察，此駒步頭硬朗，前速銳利，配合田泰安硬悍之騎功，預期起步後能迅速上前佔取主動位置。只要賽前備戰工夫達標，憑藉檔位之利及騎師硬功，絕對有條件於這場新馬混戰中突圍而出，屬三甲要角。"
    },
    "5": {
        "jockey": "班德禮", "draw": 6, "name": "雙劍合璧",
        "logic": "作為全場唯一抽得最外檔(6檔)之新駒，此駒於這場直路賽中佔盡「黃金通道」之地理優勢。歷來沙田1000米直路賽，貼近外欄競跑之馬匹往往具備顯著優勢，尤其對缺乏經驗之新馬而言更是一大助力。配上鬥志鮮明之班德禮，戰意毋庸置疑。雖然試閘表現未算極度亮眼，但考量到新馬進度可以一日千里，加上檔位形勢之絕對優勢，足以彌補部分經驗或進度上之不足。若起步順利並成功貼欄領放或跟守好位，絕對是一路不可忽視之奇兵，具備爆冷潛力。"
    },
    "6": {
        "jockey": "楊明綸", "draw": 1, "name": "精英奪冠",
        "logic": "此駒首度上陣即面對嚴峻考驗，抽得直路賽被視為「死亡內檔」之1檔起步。過往數據顯示，沙田1000米排1檔之馬匹往往需要克服極大困難，尤其新馬在內疊容易受壓或於馬群中不知所措。加上配搭楊明綸，相較同組對手未算最頂級配搭。晨操觀感亦只屬初起階段，走規仍有待改善。礙於客觀形勢極度不利，預計今仗旨在熟習競賽環境及步速，除非具備超級質素，否則難有作為。理應作為觀察名單之一員，待轉場或增程再作打算。"
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
            "trainer_jockey": {"score": "✅" if info["jockey"] == "田泰安" else "➖", "reasoning": f"由{info['jockey']}策騎"},
            "scenario": {"score": "✅" if info["draw"] >= 5 else "❌", "reasoning": f"沙田直路1000米，排{info['draw']}檔"},
            "freshness": {"score": "✅", "reasoning": "初出馬，充滿新鮮感。"},
            "formline": {"score": "➖", "reasoning": "無賽績線可作比較。"},
            "class_advantage": {"score": "➖", "reasoning": "同為新馬，無班次優勢。"},
            "forgiveness_bonus": {"score": "➖", "reasoning": "無須寬恕。"}
        },
        "base_rating": "A" if info["draw"] >= 5 else "C",
        "fine_tune": {
            "direction": "無",
            "trigger": "無"
        },
        "override": {
            "rule": "無"
        },
        "final_rating": "A" if info["draw"] >= 5 else "C",
        "core_logic": info["logic"],
        "advantages": "檔位特佳" if info["draw"] >= 5 else "體力滿滿的新馬",
        "disadvantages": "初出欠經驗" if info["draw"] >= 5 else f"排{info['draw']}檔極不利",
        "evidence_step_0_14": "綜合試閘觀感及檔位形勢推斷",
        "underhorse": {"triggered": "未觸發", "condition": "無", "reason": "非步速受害者"}
    }

with open('2026-04-12_ShaTin/Race_1_Logic.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
