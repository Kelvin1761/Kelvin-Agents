import sys

filename = '/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/2026-04-06 Rosehill Gardens Race 1-8/04-06 Race 1 Analysis.md'

with open(filename, 'r', encoding='utf-8') as f:
    content = f.read()

split_mark = '## [第三部分]'
if split_mark in content:
    content = content[:content.find(split_mark)]

new_tail = """## [第三部分] 🏆 全場最終決策

**Speed Map 回顧:** Moderate | 領放群: Mrs Maree (2), Compensation (7), Loera (3) | 受牽制: I Am Adonis (4)

**Top 4 位置精選**

🥇 **第一選**
- **馬號及馬名:** 3 Mrs Maree
- **評級與✅數量:** `A` | ✅ 8
- **核心理據:** 完美2檔配Nash Rawiller，形勢極佳，上仗1200m領放至最後才僅敗，縮程加上完美檔位操控大局。
- **最大風險:** 久休復出及曾有跛腳紀錄。

🥈 **第二選**
- **馬號及馬名:** 4 Alpha Zeta
- **評級與✅數量:** `A` | ✅ 8
- **核心理據:** 上仗全程4疊無遮擋造出優秀段速仍入圍，今仗排1檔徹底扭轉劣勢，賠率極具值博率。
- **最大風險:** 上仗過度消耗引發Second-up症候群。

🥉 **第三選**
- **馬號及馬名:** 7 Loera
- **評級與✅數量:** `B+` | ✅ 8
- **核心理據:** 名牌大倉初出試閘兩勝，Tim Clark配3檔前速有保證。
- **最大風險:** 初次實戰缺乏數據支持，且同場有多匹領放馬。

🏅 **第四選**
- **馬號及馬名:** 1 Compensation
- **評級與✅數量:** `B+` | ✅ 4
- **核心理據:** 初出於爛地上名，試閘兩度勝出狀態勇。
- **最大風險:** 排7檔容易被迫走三疊食風。

---

**🎯 Top 2 入三甲信心度 (Top 2 Place Confidence)**
🥇 Mrs Maree:`🟢高` — 最大威脅:久休復出狀態未達最佳
🥈 Alpha Zeta:`🟢高` — 最大威脅:受困內欄塞車

---

**[SIP-FL03] 🎰 Exotic 組合投注池建議 (Exotic Pool Box Recommendation)**
📦 **Box Trifecta(三重彩組合)建議:**
- **核心池:** 3 Mrs Maree, 4 Alpha Zeta, 7 Loera, 1 Compensation
- **擴展池(選擇性):** 無
- **建議組合:** `Top 4 Box Trifecta` = 覆蓋 Top 4 任意排列

📊 **投注邏輯:**
- 建議全 Box(無 Banker,最大覆蓋)

---

## [第四部分] 分析陷阱

- **市場預期警告:** 未見離譜大熱門。
- **🔄 步速逆轉保險 (Pace Flip Insurance):**
  - 若步速比預測更快 → Top 4 中最受惠:`Alpha Zeta` | 最受損:`Loera`
  - 若步速比預測更慢 → Top 4 中最受惠:`Mrs Maree` | 最受損:`Alpha Zeta`
- **整體潛在機會建議:** 主攻 Mrs Maree，並補 Alpha Zeta 的高賠率WP。

🐴⚡ **冷門馬總計 (Underhorse Signal Summary):**
🐴⚡ 無冷門馬訊號 — 全場馬匹評級與情勢預測高度吉合,無顯著情勢變化潛力股。

---

## [第五部分] 📊 數據庫匯出 (CSV)

```csv
1, Maiden Plate, 1100m, Nash Rawiller, Clarry Conners, 3, Mrs Maree, A
1, Maiden Plate, 1100m, Jason Collett, Jack Pilkington, 4, Alpha Zeta, A
1, Maiden Plate, 1100m, Tim Clark, Gai Waterhouse & Adrian Bott, 7, Loera, B+
1, Maiden Plate, 1100m, Rachel King, Bjorn Baker, 1, Compensation, B+
```

✅ 批次完成:Verdict / CSV 分離 | 馬匹全覆蓋 ✔️
"""

with open(filename, 'w', encoding='utf-8') as f:
    f.write(content + new_tail)

print("Correction applied successfully.")
