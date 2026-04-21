import json

file_path = '/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/2026-04-22_HappyValley/Race_1_Logic.json'

with open(file_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

data["horses"]["2"] = {
  "_locked": True,
  "_validation_nonce": "DONE_2",
  "_validated": True,
  "horse_name": "跑得好快",
  "jockey": "布文",
  "trainer": "黎昭昇",
  "weight": 134,
  "barrier": 9,
  "last_6_finishes": "9-7-14-12-11-3",
  "days_since_last": 21,
  "season_stats": "季內 (0-0-1-6) | 同程 (0-0-1-4) | 同場同程 (0-0-1-3)",
  "scenario_tags": "[\"強配布文\", \"降班\", \"狀態回勇\"]",
  "analytical_breakdown": {
    "stability_risk": "季內7戰雖僅得1位，但頭馬距離近期呈收窄趨勢（14-3/4→8→2-1/4→4），狀態正蘊釀反彈。",
    "class_assessment": "評分由50分大幅降至41分，已具備班次優勢。",
    "track_distance_suitability": "1200米為其最佳路程（0-1-4）。",
    "engine_distance": "上仗L400造23.57秒呈漸進加速，末段表現穩定。",
    "weight_trend": "體重穩定，但今仗需負134重磅，對體能有一定要求。",
    "gear_changes": "近期配備變動頻繁，上仗除下部分配備後走勢不過不失。",
    "draw_verdict": "排9檔屬中性（勝率8.0%），需視乎布文發揮。",
    "trainer_signal": "強配布文，出擊意圖明顯。",
    "jockey_fit": "布文接手，對提升戰鬥力有直接幫助。",
    "pace_adaptation": "預計中等步速，其混合型引擎能適應。",
    "sectional_profile_summary": "近3仗中有兩仗呈漸進加速，末段能量維持穩定（83-85）。",
    "margin_trend": "輸距離收窄中，表現逐漸改善。",
    "position_sectional_composite": "上仗(1W1W2W)採取低消耗跑法，有助今仗保留體力。",
    "finish_time_deviation": "完成時間偏差穩定，雖略慢於標準但波幅不大。",
    "eem_analysis": "走位消耗逐仗減少，上仗低消耗，今仗若形勢配合有力一戰。",
    "hidden_form": "無",
    "competition_events": "無",
    "trend_analysis": "狀態及走勢呈微升軌跡。",
    "formline_strength": "✅ 強 (強組比例: 10/14)"
  },
  "sectional_forensic": {
    "raw_L400": "23.57",
    "correction_factor": "無",
    "corrected_assessment": "末段追勢平穩",
    "trend": "23.57→23.51→24.37→24.81→24.72→22.95 → 趨勢: 波動"
  },
  "eem_energy": {
    "last_run_position": "11-10-9",
    "cumulative_drain": "中低",
    "assessment": "走位消耗逐仗減少，體力充沛"
  },
  "race_forgiveness": [],
  "matrix": {
    "stability": {
      "score": "➖",
      "reasoning": "近績不算好，但頭馬距離收窄中且評分大幅下調"
    },
    "speed_mass": {
      "score": "✅",
      "reasoning": "上仗L400=23.57漸進加速，能量83維持穩定"
    },
    "eem": {
      "score": "➖",
      "reasoning": "9檔中性，上仗低消耗省力"
    },
    "trainer_jockey": {
      "score": "✅✅",
      "reasoning": "強配布文接手，出擊意圖極為強烈"
    },
    "scenario": {
      "score": "➖",
      "reasoning": "9檔勝率8.0%屬中性，需布文克服外檔及重磅"
    },
    "freshness": {
      "score": "➖",
      "reasoning": "休賽21日正常，1200米為最佳路程"
    },
    "formline": {
      "score": "✅",
      "reasoning": "賽績線指標達10/14屬強組"
    },
    "class_advantage": {
      "score": "➖",
      "reasoning": "降班具優勢，但需負134重磅"
    },
    "forgiveness_bonus": {
      "score": "➖",
      "reasoning": "不適用，未有競賽事件寬恕紀錄"
    }
  },
  "interaction_matrix": {
    "SYN": "強配布文 + 降班優勢",
    "CON": "降班 vs 134重磅",
    "CONTRA": "無"
  },
  "base_rating": "[AUTO]",
  "fine_tune": {
    "direction": "+",
    "trigger": "強配布文",
    "channel_a": "騎師加乘",
    "channel_b": "無"
  },
  "override": {
    "rule": "無"
  },
  "final_rating": "[AUTO]",
  "core_logic": "跑得好快季內7戰僅得1位，雖然表面賽績一般，但目前評分已降至41分，配合頭馬距離近期有收窄跡象（上仗輸4馬位），狀態正蘊釀反彈。今仗配上冠軍級騎師布文，出擊意圖明顯。上仗(1W1W2W)採取低消耗跑法，L400造23.57秒呈漸進加速，末段有一定追勢。排9檔屬中性（勝率8.0%），若布文能克服134磅頂磅阻力並順利切入找尋遮擋，在強組賽績線（10/14）支持下，具備突擊入冷位置條件。",
  "advantages": [
    "強配布文，配合評分大幅下調（50→41分），出擊意圖強烈。",
    "賽績線頗強（10/14屬強組），且上仗低消耗跑法保留體力。",
    "頭馬距離呈收窄趨勢，狀態逐漸回勇。"
  ],
  "disadvantages": [
    "排9檔稍嫌偏外，且要負134磅重磅。",
    "季內7戰僅得1上名，整體勝出率依然偏低。"
  ],
  "evidence_step_0_14": "已完成"
}

data["horses"]["3"] = {
  "_locked": True,
  "_validation_nonce": "DONE_3",
  "horse_name": "歷險大將",
  "jockey": "布浩榮",
  "trainer": "徐雨石",
  "weight": 131,
  "barrier": 5,
  "last_6_finishes": "8-7-7-2-1-9",
  "days_since_last": 35,
  "season_stats": "季內 (1-1-0-5) | 同程 (1-1-0-3) | 同場同程 (1-1-0-2)",
  "scenario_tags": "[\"升班\", \"有利檔位\", \"最佳路程\"]",
  "analytical_breakdown": {
    "stability_risk": "季初取得1冠1亞後，近三仗表現回落（7-7-8），狀態轉趨飄忽。",
    "class_assessment": "今仗回升第四班作賽，面對強手考驗較大。",
    "track_distance_suitability": "1200米為其最佳路程，累積1冠1亞。",
    "engine_distance": "上仗L400造23.61秒呈漸進加速，末段仍有餘力。",
    "weight_trend": "體重微跌，今仗需負131磅，升班兼負重磅有一定阻力。",
    "gear_changes": "上仗佩戴B2/TT，今仗無進一步配備數據。",
    "draw_verdict": "排5檔屬有利位置（勝率15.0%），有助慳位跟前。",
    "trainer_signal": "布浩榮配徐雨石，未見特別強烈出擊訊號。",
    "jockey_fit": "騎師無明顯幫助。",
    "pace_adaptation": "預計中等步速，排5檔容易進佔好位。",
    "sectional_profile_summary": "近3仗中有兩仗呈漸進加速，能量水平穩定（84-86）。",
    "margin_trend": "近仗輸距離介乎2-1/4至4馬位，表現未算大敗。",
    "position_sectional_composite": "上仗(1W1W2W)走位屬低消耗，今仗體力充沛。",
    "finish_time_deviation": "完成時間偏差穩定，接近標準時間。",
    "eem_analysis": "走位消耗逐仗減少，配合5好檔，形勢大好。",
    "hidden_form": "無",
    "competition_events": "上仗受阻及起步不利，有寬恕空間。",
    "trend_analysis": "狀態稍稍回落，但走位消耗在減低。",
    "formline_strength": "❌ 弱 (強組比例: 1/11)"
  },
  "sectional_forensic": {
    "raw_L400": "23.61",
    "correction_factor": "無",
    "corrected_assessment": "末段追勢穩定",
    "trend": "23.61→23.25→22.57→23.54→22.91→24.34 → 趨勢: 波動"
  },
  "eem_energy": {
    "last_run_position": "3-2-8",
    "cumulative_drain": "中等",
    "assessment": "走位消耗逐仗減少，上仗低消耗有利今仗發揮"
  },
  "race_forgiveness": [
    "上仗受阻及起步不利"
  ],
  "matrix": {
    "stability": {
      "score": "➖",
      "reasoning": "季初曾勝出，但近三仗走勢回落"
    },
    "speed_mass": {
      "score": "✅",
      "reasoning": "L400漸進加速，能量86穩定"
    },
    "eem": {
      "score": "✅",
      "reasoning": "5檔有利，上仗走位低消耗"
    },
    "trainer_jockey": {
      "score": "➖",
      "reasoning": "配搭一般，欠缺強烈出擊訊號"
    },
    "scenario": {
      "score": "✅",
      "reasoning": "5檔勝率達15%，形勢大好"
    },
    "freshness": {
      "score": "✅",
      "reasoning": "1200米為最佳路程，曾獲1冠1亞"
    },
    "formline": {
      "score": "❌",
      "reasoning": "賽績線指標僅1/11屬弱組"
    },
    "class_advantage": {
      "score": "❌",
      "reasoning": "升班作賽兼需負131磅，處於劣勢"
    },
    "forgiveness_bonus": {
      "score": "✅",
      "reasoning": "上仗見競賽事件受阻，有寬恕空間"
    }
  },
  "interaction_matrix": {
    "SYN": "有利檔位 + 最佳路程",
    "CON": "升班 vs 重磅",
    "CONTRA": "無"
  },
  "base_rating": "[AUTO]",
  "fine_tune": {
    "direction": "無",
    "trigger": "無",
    "channel_a": "無",
    "channel_b": "無"
  },
  "override": {
    "rule": "無"
  },
  "final_rating": "[AUTO]",
  "core_logic": "歷險大將季初於第五班同程取得1冠1亞，但近三仗表現回落（7-7-8）。今仗回升第四班作賽兼需負131磅，對抗力成疑。不過，其同程1200米累積1冠1亞屬最佳路程，今仗抽排有利的5檔（勝率15%），上仗(1W1W2W)走位屬低消耗，體力回復充沛。上仗L400造出23.61秒呈漸進加速，反映末段仍有餘力。雖然賽績線極弱（1/11屬強組），但在C+3跑道利前置及檔位優勢下，若布浩榮能咬緊步速，仍有冷位憧憬。",
  "advantages": [
    "抽排5檔屬統計有利位置（勝率15%），配合上仗低消耗走位，形勢大好。",
    "1200米為最佳路程（1冠1亞），場地適性高。",
    "段速呈漸進加速，末段仍具備一定追勢。"
  ],
  "disadvantages": [
    "今仗升班作賽兼需負131磅，級數及負磅均面臨考驗。",
    "賽績線極弱（僅1/11屬強組），對手賽績水準偏低。"
  ],
  "evidence_step_0_14": "已完成"
}

with open(file_path, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("Horse 2 and 3 successfully restored.")
