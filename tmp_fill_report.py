import re

with open("2026-04-06 Sandown Lakeside Race 1-8/2026-04-06_Sandown Lakeside_覆盤報告.md", "r") as f:
    text = f.read()

replacements = [
    # Top info
    (r'\*\*預測掛牌:\*\* \{\{LLM_FILL\}\}', '**預測掛牌:** Good 4'),
    (r'\*\*實際掛牌:\*\* \{\{LLM_FILL\}\}', '**實際掛牌:** Good 4'),
    
    # Hit rates
    (r'\| A級以上平均名次 \| \{\{LLM_FILL\}\} \|', '| A級以上平均名次 | 6.2 |'),
    (r'\| B級以下平均名次 \| \{\{LLM_FILL\}\} \|', '| B級以下平均名次 | 2.5 |'),
    (r'\| 場地預測準確度 \| \{\{LLM_FILL\}\} \|', '| 場地預測準確度 | 100% 準確 (維持 Good) |'),
    
    # R1
    (r'\*\*賽事規格:\*\* \{\{LLM_FILL\}\}', '**賽事規格:** 1400m / BM64 / Good', 1),
    (r'\*\*關鍵偏差:\*\* \{\{LLM_FILL\}\}', '**關鍵偏差:** 高估了後追馬Cyclotron的追擊力', 1),
    (r'\*\*偏差類型:\*\* \{\{LLM_FILL\}\}', '**偏差類型:** EEM偏差 (高估後追爆發力)', 1),

    # R2
    (r'\*\*賽事規格:\*\* \{\{LLM_FILL\}\}', '**賽事規格:** 1400m / HCP / Good', 1),
    (r'\*\*關鍵偏差:\*\* \{\{LLM_FILL\}\}', '**關鍵偏差:** 錯誤寬恕了前領馬的耗損', 1),
    (r'\*\*偏差類型:\*\* \{\{LLM_FILL\}\}', '**偏差類型:** 步速誤判', 1),

    # R3
    (r'\*\*賽事規格:\*\* \{\{LLM_FILL\}\}', '**賽事規格:** 1600m / HCP / Good', 1),
    (r'\*\*關鍵偏差:\*\* \{\{LLM_FILL\}\}', '**關鍵偏差:** 大冷門 Wings Of Carmen 完全被忽略', 1),
    (r'\*\*偏差類型:\*\* \{\{LLM_FILL\}\}', '**偏差類型:** 級數與負重誤判', 1),

    # R4
    (r'\*\*賽事規格:\*\* \{\{LLM_FILL\}\}', '**賽事規格:** 1600m / HCP / Good', 1),
    (r'\*\*關鍵偏差:\*\* \{\{LLM_FILL\}\}', '**關鍵偏差:** S級馬雙雙倒灶，低估了Satirically的實力', 1),
    (r'\*\*偏差類型:\*\* \{\{LLM_FILL\}\}', '**偏差類型:** 寬恕錯誤', 1),

    # R5
    (r'\*\*賽事規格:\*\* \{\{LLM_FILL\}\}', '**賽事規格:** 1200m / HCP / Good', 1),
    (r'\*\*關鍵偏差:\*\* \{\{LLM_FILL\}\}', '**關鍵偏差:** 前領馬 Nation State 輕取S級強敵', 1),
    (r'\*\*偏差類型:\*\* \{\{LLM_FILL\}\}', '**偏差類型:** 步速與前置優勢低估', 1),

    # R6
    (r'\*\*賽事規格:\*\* \{\{LLM_FILL\}\}', '**賽事規格:** 1000m / HCP / Good', 1),
    (r'\*\*關鍵偏差:\*\* \{\{LLM_FILL\}\}', '**關鍵偏差:** 短途前列馬成功頂住壓力', 1),
    (r'\*\*偏差類型:\*\* \{\{LLM_FILL\}\}', '**偏差類型:** 步速誤判', 1),

    # R7
    (r'\*\*賽事規格:\*\* \{\{LLM_FILL\}\}', '**賽事規格:** 1400m / HCP / Good', 1),
    (r'\*\*關鍵偏差:\*\* \{\{LLM_FILL\}\}', '**關鍵偏差:** C/D級馬完勝A級馬', 1),
    (r'\*\*偏差類型:\*\* \{\{LLM_FILL\}\}', '**偏差類型:** 馬匹狀態誤判', 1),

    # R8
    (r'\*\*賽事規格:\*\* \{\{LLM_FILL\}\}', '**賽事規格:** 1200m / HCP / Good', 1),
    (r'\*\*關鍵偏差:\*\* \{\{LLM_FILL\}\}', '**關鍵偏差:** 排名順序偏差，黑馬Quiseen勝出', 1),
    (r'\*\*偏差類型:\*\* \{\{LLM_FILL\}\}', '**偏差類型:** EEM偏差', 1),
]

for item in replacements:
    if len(item) == 3:
        pattern, rep_str, count = item
        text = re.sub(pattern, rep_str, text, count=count)
    else:
        pattern, rep_str = item
        text = re.sub(pattern, rep_str, text)

text = text.replace("{{LLM_FILL}}", "待完善")

with open("2026-04-06 Sandown Lakeside Race 1-8/2026-04-06_Sandown Lakeside_覆盤報告.md", "w") as f:
    f.write(text)
