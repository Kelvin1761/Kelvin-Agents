#!/usr/bin/env python3
import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import re

def verify_file(filepath):
    if not os.path.exists(filepath):
        print(f"❌ 錯誤: 檔案 {filepath} 不存在")
        sys.exit(1)
        
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    required_blocks = [
        ("🗺️ 戰場全景", "第一部分戰場全景"),
        ("🛡️ 戰馬矩陣剖析", "戰馬矩陣剖析"),
        ("🏆 Top 4 位置精選", "Top 4 位置精選"),
        ("🥇 **第一選**", "Top 4 第一選標籤"),
        ("🥈 **第二選**", "Top 4 第二選標籤"),
        ("🥉 **第三選**", "Top 4 第三選標籤"),
        ("🏅 **第四選**", "Top 4 第四選標籤"),
        ("分析盲區", "分析盲區"),
    ]
    
    missing = []
    for keyword, desc in required_blocks:
        if keyword not in content:
            missing.append(desc)
            
    num_horses = len(re.findall(r'### 【No\.', content))
    
    # If there are horses, ensure EVERY mandatory field appears `num_horses` times.
    if num_horses > 0:
        mandatory_horse_fields = [
            "#### 🧠 核心分析",
            "#### 📊 7D 評分矩陣",
            "#### ✅ 優勢",
            "#### ⚠️ 風險",
            "#### 🔢 15 項分數",
        ]
        
        for field in mandatory_horse_fields:
            field_count = content.count(field)
            if field_count < num_horses:
                missing.append(f"馬匹分析區塊不完整 ({field} 僅有 {field_count}/{num_horses} 匹馬包含此區塊。不允許對跑位差/評級低嘅馬匹進行精簡。)")

    top4_labels = [
        ("🥇 **第一選**", "第一選"),
        ("🥈 **第二選**", "第二選"),
        ("🥉 **第三選**", "第三選"),
        ("🏅 **第四選**", "第四選"),
    ]
    top4_required_bullets = ["馬號及馬名", "核心理據", "最大風險"]

    for label_keyword, label_name in top4_labels:
        if label_keyword in content:
            # Extract the block after this label until the next 🥇🥈🥉🏅 or ### header
            label_pos = content.index(label_keyword)
            # Find the end of this selection's block
            next_boundary = len(content)
            for boundary_marker in ["🥇 **", "🥈 **", "🥉 **", "🏅 **", "### ["]:
                next_pos = content.find(boundary_marker, label_pos + len(label_keyword))
                if next_pos != -1 and next_pos < next_boundary:
                    next_boundary = next_pos
            block = content[label_pos:next_boundary]
            for bullet in top4_required_bullets:
                if bullet not in block:
                    missing.append(f"Top 4 {label_name} 缺少必要子彈點欄位: {bullet}")

    if "[FILL]" in content or "PLACEHOLDER" in content or "分析中" in content:
        missing.append("報告仍殘留 placeholder / 未完成內容")

    if missing:
        print(f"❌ 驗證失敗 ({filepath})! 缺少以下必備區塊或區塊不完整:")
        for m in missing:
            print(f"   - {m}")
        print("\n👉 請 Agent 立即修復遺漏的區塊，每匹馬必須有完全一致的法醫流程，然後再向用戶匯報。")
        sys.exit(1)
    else:
        print(f"✅ 驗證成功 ({filepath})! AU Auto 報告結構完整，{num_horses} 匹馬內容已齊備。")
        sys.exit(0)

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 verify_analysis_au.py <filepath>")
        sys.exit(1)
    verify_file(sys.argv[1])
