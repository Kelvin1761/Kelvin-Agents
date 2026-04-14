import os
import glob
import json
import re

target_dir = "2026-04-15_HappyValley"

def get_check_count(horse_data):
    count = 0
    matrix = horse_data.get("matrix", {})
    for key, val in matrix.items():
        if val.get("score", "") == "✅":
            count += 1
    return count

for i in range(1, 10):
    json_path = os.path.join(target_dir, f"Race_{i}_Logic.json")
    md_path = os.path.join(target_dir, f"04-15_HappyValley Race {i} Analysis.md")
    
    if not os.path.exists(json_path) or not os.path.exists(md_path):
        continue
        
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    if "verdict" not in data.get("race_analysis", {}):
        continue
        
    verdict = data["race_analysis"]["verdict"]
    horses = data.get("horses", {})
    
    with open(md_path, "r", encoding="utf-8") as f:
        md = f.read()

    # Replacements:
    # Track Scenario
    md = md.replace("- **跑道形勢:** [FILL]", f"- **跑道形勢:** {verdict.get('track_scenario', '')}")
    md = md.replace("- **信心指數:** `[極高/高/中高/中/低]`", f"- **信心指數:** `{verdict.get('confidence', '')}`")
    md = md.replace("- **關鍵變數:** [FILL]", f"- **關鍵變數:** {verdict.get('key_variables', '')}")

    # Sort TOP 4
    top4 = verdict.get("top4", [])
    # Filter and sort
    valid_top4 = []
    for t in top4:
        h_num = str(t.get("horse_num", ""))
        h_data = horses.get(h_num, {})
        rating = float(h_data.get("final_rating", 0))
        name = h_data.get("horse_name", "")
        checks = get_check_count(h_data)
        valid_top4.append({
            "num": h_num,
            "name": name,
            "rating": rating,
            "checks": checks,
            "reason": t.get("reason", ""),
            "risk": t.get("risk", "")
        })
        
    # Sort DESCENDING by final_rating
    valid_top4.sort(key=lambda x: x["rating"], reverse=True)
    
    # Fill Top 4
    places_regex = [
        r"🥇 \*\*第一選\*\*\n- \*\*馬號及馬名:\*\* \[FILL\]\n- \*\*評級與✅數量:\*\* `\[FILL\]` \| ✅ \[FILL\]\n- \*\*核心理據:\*\* \[FILL\]\n- \*\*最大風險:\*\* \[FILL\]",
        r"🥈 \*\*第二選\*\*\n- \*\*馬號及馬名:\*\* \[FILL\]\n- \*\*評級與✅數量:\*\* `\[FILL\]` \| ✅ \[FILL\]\n- \*\*核心理據:\*\* \[FILL\]\n- \*\*最大風險:\*\* \[FILL\]",
        r"🥉 \*\*第三選\*\*\n- \*\*馬號及馬名:\*\* \[FILL\]\n- \*\*評級與✅數量:\*\* `\[FILL\]` \| ✅ \[FILL\]\n- \*\*核心理據:\*\* \[FILL\]\n- \*\*最大風險:\*\* \[FILL\]",
        r"🏅 \*\*第四選\*\*\n- \*\*馬號及馬名:\*\* \[FILL\]\n- \*\*評級與✅數量:\*\* `\[FILL\]` \| ✅ \[FILL\]\n- \*\*核心理據:\*\* \[FILL\]\n- \*\*最大風險:\*\* \[FILL\]"
    ]
    
    places_names = ["🥇 **第一選**", "🥈 **第二選**", "🥉 **第三選**", "🏅 **第四選**"]
    
    for idx, p in enumerate(places_regex):
        if idx < len(valid_top4):
            t = valid_top4[idx]
            rep = (f"{places_names[idx]}\n"
                   f"- **馬號及馬名:** [{t['num']}] {t['name']}\n"
                   f"- **評級與✅數量:** `[{t['rating']}]` | ✅ {t['checks']}\n"
                   f"- **核心理據:** {t['reason']}\n"
                   f"- **最大風險:** {t['risk']}")
            md = re.sub(p, rep, md)
            
    # Top 2 Confidence
    md = md.replace("🥇 [FILL]:`[🟢極高 / 🟢高 / 🟡中 / 🔴低]` — 最大威脅:[FILL]", f"🥇 [{valid_top4[0]['num'] if len(valid_top4)>0 else ''}]:`[{verdict.get('top2_confidence_1', '')}]` — 最大威脅:[{valid_top4[1]['num'] if len(valid_top4)>1 else ''}]")
    md = md.replace("🥈 [FILL]:`[🟢極高 / 🟢高 / 🟡中 / 🔴低]` — 最大威脅:[FILL]", f"🥈 [{valid_top4[1]['num'] if len(valid_top4)>1 else ''}]:`[{verdict.get('top2_confidence_2', '')}]` — 最大威脅:[{valid_top4[0]['num'] if len(valid_top4)>0 else ''}]")
    
    # Pace Flip Insurance
    defi = verdict.get("pace_flip_insurance", {})
    faster = defi.get("if_faster", {})
    slower = defi.get("if_slower", {})
    # Only replace if placeholders exist
    md = md.replace("- 若步速比預測更快 → 最受惠: [FILL] | 最受損: [FILL]", f"- 若步速比預測更快 → 最受惠: {faster.get('benefit', '')} | 最受損: {faster.get('hurt', '')}")
    md = md.replace("- 若步速比預測更慢 → 最受惠: [FILL] | 最受損: [FILL]", f"- 若步速比預測更慢 → 最受惠: {slower.get('benefit', '')} | 最受損: {slower.get('hurt', '')}")

    # Emergency brake
    md = md.replace("**🚨 緊急煞車檢查 (Emergency Brake Protocol):**\n- [FILL]", f"**🚨 緊急煞車檢查 (Emergency Brake Protocol):**\n- {verdict.get('emergency_brake', '')}")
    
    # Blind Spots
    bz = verdict.get("blind_spots", {})
    md = md.replace("**1. 段速含金量:** [FILL]", f"**1. 段速含金量:** {bz.get('sectionals', '')}")
    md = md.replace("**2. 風險管理:** [FILL]", f"**2. 風險管理:** {bz.get('risk_management', '')}")
    md = md.replace("**3. 試閘與預期假象:** [FILL]", f"**3. 試閘與預期假象:** {bz.get('trials_illusion', '')}")
    md = md.replace("**4. 特定與老馬風險:** [FILL]", f"**4. 特定與老馬風險:** {bz.get('age_risk', '')}")
    
    # Pace collapse
    md = md.replace("**6. 🎯 步速崩潰冷門 (Pace Collapse Dark Horse) [強制檢查點]:**\n[FILL]", f"**6. 🎯 步速崩潰冷門 (Pace Collapse Dark Horse) [強制檢查點]:**\n{bz.get('pace_collapse_darkhorse', '')}")
    
    # Pace branches 5
    if "- 快步速:最利 → [FILL];最不利 → [FILL]" in md:
        md = md.replace("- 快步速:最利 → [FILL];最不利 → [FILL]", f"- 快步速:最利 → {faster.get('benefit', '')};最不利 → {faster.get('hurt', '')}")
    if "- 慢步速:最利 → [FILL];最不利 → [FILL]" in md:
        md = md.replace("- 慢步速:最利 → [FILL];最不利 → [FILL]", f"- 慢步速:最利 → {slower.get('benefit', '')};最不利 → {slower.get('hurt', '')}")

    # Underhorse signal
    underhorses = []
    for h_num, h_data in horses.items():
        if h_data.get("underhorse", {}).get("triggered") == True:
            underhorses.append(f"[{h_num}] {h_data.get('horse_name', '')}")
    uh_str = ", ".join(underhorses) if underhorses else "無觸發"
    md = md.replace("**🐴⚡ 冷門馬總計 (Underhorse Signal Summary):**\n[FILL]", f"**🐴⚡ 冷門馬總計 (Underhorse Signal Summary):**\n{uh_str}")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)

    print(f"Filled verdicts for Race {i}")

