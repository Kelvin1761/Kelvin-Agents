import re
import os

with open('/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/.agents/scripts/fill_hkjc_verdicts.py', 'r', encoding='utf-8') as f:
    text = f.read()

# Add JSON parsing to main
# We need to change argparse to take --json
new_main = """import json
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--json", required=True)
    parser.add_argument("--safe-writer", required=True)
    args = parser.parse_args()
    
    ranked, original_text = parse_md(args.target)
    if not ranked:
        print(f"Skipping {args.target} - no horse data parsed (maybe not injected yet).")
        return
        
    labels = ['🥇 **第一選**', '🥈 **第二選**', '🥉 **第三選**', '🏅 **第四選**']
    lines = ["**🏆 Top 4 位置精選**\\n"]

    for i, r in enumerate(ranked[:4]):
        lines.append(f"{labels[i]}")
        lines.append(f"- **馬號及馬名:** {r['num']} {r['name']}")
        lines.append(f"- **評級與✅數量:** `[{r['grade']}]` | ✅ {r['total_strong']}")
        lines.append(f"- **核心理據:** {r['logic']}")
        lines.append(f"- **最大風險:** {r['risk']}")
        lines.append("")
        
    new_top4_text = '\\n'.join(lines)
    
    pattern = r'\*\*🏆 Top 4 位置精選\*\*.*?(?=\*\*🎯 Top 2)'
    if re.search(pattern, original_text, flags=re.DOTALL):
        new_text = re.sub(pattern, new_top4_text, original_text, flags=re.DOTALL)
    else:
        print(f"Warning: Top 4 section not found perfectly in {args.target}")
        new_text = original_text

    # INJECT GLOBAL METADATA
    try:
        with open(args.json, 'r', encoding='utf-8') as fj:
            d = json.load(fj)
        ra = d.get('race_analysis', {})
        sm = ra.get('speed_map', {})
        vd = ra.get('verdict', {})
        bs = vd.get('blind_spots', {})
        pfi = vd.get('pace_flip_insurance', {})

        leaders = ", ".join(sm.get('leaders', []))
        on_pace = ", ".join(sm.get('on_pace', []))
        mid_pack = ", ".join(sm.get('mid_pack', []))
        closers = ", ".join(sm.get('closers', []))

        # Speed map
        new_text = new_text.replace('- 領放群: [FILL]', f'- 領放群: {leaders}')
        new_text = new_text.replace('- 前中段: [FILL]', f'- 前中段: {on_pace}')
        new_text = new_text.replace('- 中後段: [FILL]', f'- 中後段: {mid_pack}')
        new_text = new_text.replace('- 後上群: [FILL]', f'- 後上群: {closers}')

        new_text = new_text.replace('- 領放馬: [FILL] | 搶位數量: [FILL]', f"- 領放馬: {leaders} | 搶位數量: {len(sm.get('leaders', []))}")
        new_text = new_text.replace('- 預計步速: [FILL] | 崩潰點: [FILL]', f"- 預計步速: {sm.get('predicted_pace', '-')} | 崩潰點: {sm.get('collapse_point', '-')}")
        new_text = new_text.replace('- 偏差方向: [FILL]', f"- 偏差方向: {sm.get('track_bias', '-')}")
        new_text = new_text.replace('- 受惠: [FILL] | 受損: [FILL]', f"- 戰術節點: {sm.get('tactical_nodes', '-')}") # Override because schema changed

        # Weather / Bias (if they don't map perfectly, we can leave them or replace with -)
        new_text = new_text.replace('| 天氣 / 場地 | [FILL] |', f"| 天氣 / 場地 | - |")
        new_text = new_text.replace('| 跑道偏差 | [FILL] |', f"| 跑道偏差 | {sm.get('track_bias', '-')} |")
        new_text = new_text.replace('| 步速預測 | [FILL] |', f"| 步速預測 | {sm.get('predicted_pace', '-')} |")
        new_text = new_text.replace('| 戰術節點 | [FILL] |', f"| 戰術節點 | {sm.get('tactical_nodes', '-')} |")

        # Verdict metadata
        new_text = new_text.replace('- **跑道形勢:** [FILL]', f"- **跑道形勢:** {vd.get('track_scenario','-')}")
        new_text = new_text.replace('- **信心指數:** `[極高/高/中高/中/低]`', f"- **信心指數:** `{vd.get('confidence','-')}`")
        new_text = new_text.replace('- **關鍵變數:** [FILL]', f"- **關鍵變數:** {vd.get('key_variables','-')}")

        # Top 2 Place
        # The markdown is: 🥇 [FILL]:`[🟢極高 / 🟢高 / 🟡中 / 🔴低]` — 最大威脅:[FILL]
        try:
            top_1 = ranked[0]['name'] if len(ranked) > 0 else '-'
            top_2 = ranked[1]['name'] if len(ranked) > 1 else '-'
        except:
            top_1, top_2 = '-', '-'
            
        new_text = re.sub(r'🥇 \[FILL\]:`\[.*?\]` — 最大威脅:\[FILL\]', f"🥇 {top_1}:`{vd.get('top2_confidence_1','-')}` — 最大威脅:-", new_text)
        new_text = re.sub(r'🥈 \[FILL\]:`\[.*?\]` — 最大威脅:\[FILL\]', f"🥈 {top_2}:`{vd.get('top2_confidence_2','-')}` — 最大威脅:-", new_text)

        # Pace Flip
        if_f = pfi.get('if_faster', {})
        if_s = pfi.get('if_slower', {})
        new_text = new_text.replace('- 若步速比預測更快 → 最受惠: [FILL] | 最受損: [FILL]', f"- 若步速比預測更快 → 最受惠: {if_f.get('benefit','-')} | 最受損: {if_f.get('hurt','-')}")
        new_text = new_text.replace('- 若步速比預測更慢 → 最受惠: [FILL] | 最受損: [FILL]', f"- 若步速比預測更慢 → 最受惠: {if_s.get('benefit','-')} | 最受損: {if_s.get('hurt','-')}")

        # Emergency
        new_text = new_text.replace('- [FILL]', f"- {vd.get('emergency_brake','無')}", 1) # Note: this might hit the first [FILL], so let's be careful and use regex:
        new_text = re.sub(r'\*\*🚨 緊急煞車檢查 \(Emergency Brake Protocol\):\*\*\n- \[FILL\]', f"**🚨 緊急煞車檢查 (Emergency Brake Protocol):**\\n- {vd.get('emergency_brake','無')}", new_text)

        # Blind spots
        new_text = new_text.replace('**1. 段速含金量:** [FILL]', f"**1. 段速含金量:** {bs.get('sectionals','無')}")
        new_text = new_text.replace('**2. 風險管理:** [FILL]', f"**2. 風險管理:** {bs.get('risk_management','無')}")
        new_text = new_text.replace('**3. 試閘與預期假象:** [FILL]', f"**3. 試閘與預期假象:** {bs.get('trials_illusion','無')}")
        new_text = new_text.replace('**4. 特定與老馬風險:** [FILL]', f"**4. 特定與老馬風險:** {bs.get('age_risk','無')}")
        new_text = re.sub(r'\*\*6\. 🎯 步速崩潰冷門 \(Pace Collapse Dark Horse\) \[強制檢查點\]:\*\*\n\[FILL\]', f"**6. 🎯 步速崩潰冷門 (Pace Collapse Dark Horse) [強制檢查點]:**\\n{bs.get('pace_collapse_darkhorse','無')}", new_text)

    except Exception as e:
        print(f"Error injecting global metadata: {e}")

    b64_content = base64.b64encode(new_text.encode('utf-8')).decode('utf-8')
    subprocess.run(["python3", args.safe_writer, "--target", args.target, "--mode", "overwrite", "--content", b64_content], check=True)
    print("Verdict Top 4 + Global Metadata Injection complete!")
"""

new_text = re.sub(r'def main\(\):.*', new_main, text, flags=re.DOTALL)
with open('/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/.agents/scripts/fill_hkjc_verdicts.py', 'w', encoding='utf-8') as f:
    f.write(new_text)

print("Patched fill_hkjc_verdicts.py successfully!")
