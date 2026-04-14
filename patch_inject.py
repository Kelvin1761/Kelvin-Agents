import re
import os

with open('/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/.agents/scripts/inject_hkjc_batch.py', 'r', encoding='utf-8') as f:
    text = f.read()

new_inject_func = """def inject_horse_data(horse_chunk, data):
    ab = data.get('analytical_breakdown', {})
    
    cores = [data.get('matrix', {}).get('stability', {}).get('score', '➖'), data.get('matrix', {}).get('speed_mass', {}).get('score', '➖')]
    semis = [data.get('matrix', {}).get('eem', {}).get('score', '➖'), data.get('matrix', {}).get('trainer_jockey', {}).get('score', '➖')]
    auxs = [data.get('matrix', {}).get('scenario', {}).get('score', '➖'), 
            data.get('matrix', {}).get('freshness', {}).get('score', '➖'), 
            data.get('matrix', {}).get('formline', {}).get('score', '➖'), 
            data.get('matrix', {}).get('class_advantage', {}).get('score', '➖'), 
            data.get('matrix', {}).get('forgiveness_bonus', {}).get('score', '➖')]
            
    core_pass = sum(1 for c in cores if '✅' in c)
    semi_pass = sum(1 for c in semis if '✅' in c)
    aux_pass = sum(1 for c in auxs if '✅' in c)
    core_fail = sum(1 for c in cores if '❌' in c)
    total_fail = core_fail + sum(1 for c in semis if '❌' in c) + sum(1 for c in auxs if '❌' in c)

    uh_trig = "觸發" if data.get('underhorse', {}).get('triggered', False) else "未觸發"
    uh_cond = data.get('underhorse', {}).get('condition', '')
    uh_reason = data.get('underhorse', {}).get('reason', '')
    
    replacements = [
        (r'- \*\*走勢趨勢 \(Step 10\.3\+\):\*\* \[FILL\]', f"- **走勢趨勢 (Step 10.3+):** {ab.get('trend_analysis', '')}"),
        (r'- \*\*隱藏賽績 \(Step 6\+12\):\*\* \[FILL\]', f"- **隱藏賽績 (Step 6+12):** {ab.get('hidden_form', '')}"),
        (r'- \*\*贏馬回落風險 / 穩定性 \(Step 5\):\*\* \[FILL\]', f"- **贏馬回落風險 / 穩定性 (Step 5):** {ab.get('stability_risk', '')}"),
        (r'- \*\*級數評估 \(Step 8\.1\):\*\* \[FILL\]', f"- **級數評估 (Step 8.1):** {ab.get('class_assessment', '')}"),
        (r'- \*\*路程場地適性 \(Step 2\):\*\* \[FILL\]', f"- **路程場地適性 (Step 2):** {ab.get('track_distance_suitability', '')}"),
        (r'- \*\*引擎距離 \(Step 2\.6\):\*\* \[FILL\]', f"- **引擎距離 (Step 2.6):** {ab.get('engine_distance', '')}"),
        (r'- \*\*配備變動 \(Step 6\):\*\* \[FILL\]', f"- **配備變動 (Step 6):** {ab.get('gear_changes', '')}"),
        (r'- \*\*部署與練馬師訊號 \(Step 8\.2\):\*\* \[FILL\]', f"- **部署與練馬師訊號 (Step 8.2):** {ab.get('trainer_signal', '')}"),
        (r'- \*\*人馬/騎練配搭 \(Step 2\.5\):\*\* \[FILL\]', f"- **人馬/騎練配搭 (Step 2.5):** {ab.get('jockey_fit', '')}"),
        (r'- \*\*步速段速 \(Step 0\+10\):\*\* \[FILL\]', f"- **步速段速 (Step 0+10):** {ab.get('pace_adaptation', '')}"),
        (r'- \*\*競賽事件 / 馬匹特性:\*\* \[FILL\]', f"- **競賽事件 / 馬匹特性:** {data.get('forgiveness_archive', {}).get('factors', '無')}"),
        (r'- \*\*綜合結論:\*\* `\[FILL\]`', f"- **綜合結論:** `{data.get('evidence_step_0_14', '')}`"),
        
        (r'- \*\*逐場寬恕判定:\*\* `\[JSON Array.*?\]`', f"- **逐場寬恕判定:** `['見因素分析']`"),
        
        (r'- 穩定性 \[核心\]: `\[FILL\]` \| 理據: `\[FILL\]`', f"- 穩定性 [核心]: `{cores[0]}` | 理據: `{data.get('matrix', {}).get('stability', {}).get('reasoning', '')}`"),
        (r'- 段速質量 \[核心\]: `\[FILL\]` \| 理據: `\[FILL\]`', f"- 段速質量 [核心]: `{cores[1]}` | 理據: `{data.get('matrix', {}).get('speed_mass', {}).get('reasoning', '')}`"),
        (r'- EEM 潛力 \[半核心\]: `\[FILL\]` \| 理據: `\[FILL\]`', f"- EEM 潛力 [半核心]: `{semis[0]}` | 理據: `{data.get('matrix', {}).get('eem', {}).get('reasoning', '')}`"),
        (r'- 練馬師訊號 \[半核心\]: `\[FILL\]` \| 理據: `\[FILL\]`', f"- 練馬師訊號 [半核心]: `{semis[1]}` | 理據: `{data.get('matrix', {}).get('trainer_jockey', {}).get('reasoning', '')}`"),
        (r'- 情境適配 \[輔助\]: `\[FILL\]` \| 理據: `\[FILL\]`', f"- 情境適配 [輔助]: `{auxs[0]}` | 理據: `{data.get('matrix', {}).get('scenario', {}).get('reasoning', '')}`"),
        (r'- 路程/新鮮度 \[輔助\]: `\[FILL\]` \| 理據: `\[FILL\]`', f"- 路程/新鮮度 [輔助]: `{auxs[1]}` | 理據: `{data.get('matrix', {}).get('freshness', {}).get('reasoning', '')}`"),
        (r'- 賽績線 \[輔助\]: `\[FILL\]` \| 理據: `\[FILL\]`', f"- 賽績線 [輔助]: `{auxs[2]}` | 理據: `{data.get('matrix', {}).get('formline', {}).get('reasoning', '')}`"),
        (r'- 級數優勢 \[輔助\]: `\[FILL\]` \| 理據: `\[FILL\]`', f"- 級數優勢 [輔助]: `{auxs[3]}` | 理據: `{data.get('matrix', {}).get('class_advantage', {}).get('reasoning', '')}`"),
        (r'- 寬恕加分: `\[FILL\].*?` \| 理據: `\[FILL\]`', f"- 寬恕加分: `{auxs[4]}` | 理據: `{data.get('matrix', {}).get('forgiveness_bonus', {}).get('reasoning', '')}`"),
        
        (r'\*\*🔢 矩陣算術:\*\* 核心✅=\[FILL\] \| 半核心✅=\[FILL\] \| 輔助✅=\[FILL\] \(含寬恕加分\) \| 總❌=\[FILL\] \| 核心❌=\[FILL\] → 查表命中行=\[FILL\]', 
         f"**🔢 矩陣算術:** 核心✅={core_pass} | 半核心✅={semi_pass} | 輔助✅={aux_pass} (含寬恕加分) | 總❌={total_fail} | 核心❌={core_fail} → 查表命中行=-"),
        
        (r'\*\*14\.2 基礎評級:\*\* `\[FILL\]` \| `\[FILL\]`', f"**14.2 基礎評級:** `{data.get('base_rating', '-')}` | `-`"),
        (r'\*\*14\.2B 微調:\*\* `\[FILL\]` \| `\[FILL\]`', f"**14.2B 微調:** `{data.get('fine_tune', {}).get('direction', '-')}` | `{data.get('fine_tune', {}).get('trigger', '-')}`"),
        (r'\*\*14\.3 覆蓋:\*\* `\[FILL\]`', f"**14.3 覆蓋:** `{data.get('override', {}).get('rule', '-')}`"),
        
        (r'> - \*\*核心邏輯:\*\* \[呢匹馬.*?\]', f"> - **核心邏輯:** {data.get('core_logic', '')}"),
        (r'> - \*\*最大競爭優勢:\*\* \[明確列出\]', f"> - **最大競爭優勢:** {data.get('advantages', '')}"),
        (r'> - \*\*最大失敗風險:\*\* \[若為A-或以上必須寫,否則明確寫「無」\]', f"> - **最大失敗風險:** {data.get('disadvantages', '')}"),
        
        (r'\*\*⭐ 最終評級:\*\* `\[FILL\]`', f"**⭐ 最終評級:** `{data.get('final_rating', '-')}`"),
        
        (r'🐴⚡ \*\*冷門馬訊號 \(Underhorse Signal\):\*\* `\[觸發 / 未觸發\]`\\n(?:若觸發,必須列明:\\n- \*\*受惠條件:\*\* `\[.*?\]`\\n- \*\*理由:\*\* \[.*?\])?', 
         f"🐴⚡ **冷門馬訊號 (Underhorse Signal):** `{uh_trig}`" + (f"\\n若觸發,必須列明:\\n- **受惠條件:** `{uh_cond}`\\n- **理由:** {uh_reason}" if uh_trig == '觸發' else ""))
    ]
    
    for pattern, repl in replacements:
        # replace any literal backslashes if needed, though raw strings handle some
        horse_chunk = re.sub(pattern, repl.replace('\\\\', '\\\\\\\\'), horse_chunk, count=1, flags=re.DOTALL)
        
    return horse_chunk
"""

# Replace the old inject_horse_data in the script using regex cleanly
# find the def inject_horse_data block and replace it until def main():
new_text = re.sub(r'def inject_horse_data\(horse_chunk, data\):.*?def main\(\):', new_inject_func + '\ndef main():', text, flags=re.DOTALL)

with open('/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/.agents/scripts/inject_hkjc_batch.py', 'w', encoding='utf-8') as f:
    f.write(new_text)

print("Patched inject_hkjc_batch.py!")
