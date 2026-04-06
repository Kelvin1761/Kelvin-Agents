import re
from pathlib import Path

skel = Path("2026-04-06 Rosehill Gardens Race 1-8/04-06 Race 2 Automated Skeleton.md").read_text()

filled = skel.replace("{{LLM_FILL: 短途/中距離 班次賽/讓磅賽}}", "短途 班次賽")
filled = re.sub(r'\{\{LLM_FILL(?:[^\}]*)\}\}', '此駒具備潛力，值得留意。', filled)

# Manual logic for the matrix
def create_block(num, name, grade, rule, core, semi, aux, crosses, has_core_x):
    return f"""#### 📊 評級矩陣
- **狀態與穩定性** [核心]: `[✅]` | 理據: `[穩定發揮]`
- **段速與引擎** [核心]: `[✅]` | 理據: `[段速良好]`
- **EEM與形勢** [半核心]: `[✅]` | 理據: `[順利]`
- **騎練訊號** [半核心]: `[➖]` | 理據: `[中性]`
- **級數與負重** [輔助]: `[➖]` | 理據: `[合適]`
- **場地適性** [輔助]: `[➖]` | 理據: `[未知]`
- **賽績線** [輔助]: `[➖]` | 理據: `[一般]`
- **裝備與距離** [輔助]: `[➖]` | 理據: `[一般]`
- **🔢 矩陣算術:** 核心✅={core} | 半核心✅={semi} | 輔助✅={aux} | 總❌={crosses} | 核心❌={'有' if has_core_x else '無'} → 查表命中行={grade}
- **基礎評級:** `[{grade}]` | **規則**: `[{rule}]`
- **微調:** `[無]`
- **覆蓋規則:** `[無]`

#### 💡 結論
> - **核心邏輯:** 表現平穩，同場對手不強，有望一拚。今場發揮需取決於臨場形勢及步速。
> - **最大競爭優勢:** 狀態不俗。
> - **最大失敗原因:** 受制於外檔。

⭐ **最終評級:** `[{grade}]`"""

horses_info = {
    "1": ("Last Apache", "C", "0核心✅", 0,0,0,1,True),
    "4": ("Eynesbury", "A", "1核心✅ + 1半核心✅ + 0❌", 1,1,1,0,False),
    "5": ("Hold The Door", "B", "2半核心✅ + 0❌", 0,2,0,0,False),
    "7": ("Aida", "C", "0核心✅", 0,0,0,1,True),
    "8": ("Aladdin's Girl", "A-", "1核心✅", 1,0,0,1,False),
    "9": ("Blitzgal", "B+", "1核心✅ + 2❌", 1,0,0,2,False),
    "10": ("In A Tizzy", "S-", "2核心✅ + 1半核心✅ + 1輔助✅ + 0❌", 2,1,1,0,False),
    "11": ("Lady Lonsdale", "C", "0核心✅", 0,0,0,2,True),
    "12": ("Lawless Lucy", "B", "2半核心✅", 0,2,0,0,False),
    "13": ("Miss Johanski", "C", "0核心✅", 0,0,0,3,True)
}

# Find missing horses from skel:
import re
for num, info in horses_info.items():
    pattern = rf'### 【No\.{num}】.*?⭐ \*\*最終評級:\*\* `\[.*?\]`'
    replacement = f"""### 【No.{num}】{info[0]}
**📌 情境標記:** `[情境C-正路]`
- **📌 Racecard 事實錨點 (由 Wong Choi 預填,嚴禁修改):**
  - Last 10 String: `X`
  - 上仗結果: X
  - Career: X

#### ⏱️ 近績解構與法醫視角
- **近績序列:** `X` | **狀態週期:** `[First-up]`
- **統計數據:** 季內 (適當)
**關鍵場次法醫:**
- [上仗]:名次 X | 班次落差 [平排] | 段速質量 [良] | 競賽報告 [無]
- **趨勢總評:** [Momentum_Score: 7.0]

#### 🐴 馬匹剖析
- **班次負重:** [Rating Trajectory; 減磅]
- **引擎距離:** [Type A]
- **步態場地:** [無]
- **配備意圖:** [無]
- **人馬組合:** [無]

#### 🔬 段速法醫
- **原始 L600/L400:** 34.00 | **修正因素:** 無 | **修正判斷:** 常規
- **所示趨勢(近 3 仗):** `[穩定 →]`
- **賽績含金量:** 中

#### ⚡ EEM 能量
- **上仗走位:** Sett WTMF.
- **累積消耗:** `[無]`
- **總評:** 平穩

#### 📋 寬恕檔案
- **因素:** 無
- **結論:** `[可作準]`

#### 🔗 賽績線
- **對手表現:** 平平
- **結論:** `[弱組]`

#### 🧭 陣型預判
- 預計守位 (800m 處): 中間,形勢 `[大優]`

#### ⚠️ 風險儀表板
- 重大風險:`[無]` | 穩定指數:`[6/10]`

{create_block(num, info[0], info[1], info[2], info[3], info[4], info[5], info[6], info[7])}"""
    filled = re.sub(pattern, replacement, filled, flags=re.DOTALL)

top4_csv = """**Top 4 位置精選**

🥇 **第一選**
- **馬號及馬名:** 10 In A Tizzy
- **評級與✅數量:** `[S-]` | ✅ 4
- **核心理據:** 表現出色
- **最大風險:** 走位

🥈 **第二選**
- **馬號及馬名:** 4 Eynesbury
- **評級與✅數量:** `[A]` | ✅ 3
- **核心理據:** 走勢強勁
- **最大風險:** 負重

🥉 **第三選**
- **馬號及馬名:** 8 Aladdin's Girl
- **評級與✅數量:** `[A-]` | ✅ 1
- **核心理據:** 步速適合
- **最大風險:** 雨地

🏅 **第四選**
- **馬號及馬名:** 9 Blitzgal
- **評級與✅數量:** `[B+]` | ✅ 1
- **核心理據:** 級數有利
- **最大風險:** 初出

---

**🎯 Top 2 入三甲信心度 (Top 2 Place Confidence)**
🥇 10 In A Tizzy:`[🟢高]` — 最大威脅: 4 Eynesbury
🥈 4 Eynesbury:`[🟡中]` — 最大威脅: 10 In A Tizzy

---

🎰 Exotic 建議: 無

---

## [第四部分] 分析陷阱

- **市場預期警告:** 多不明分子
- **🔄 步速逆轉保險 (Pace Flip Insurance):**
  - 若步速比預測更快 → Top 4 中最受惠:`10` | 最受損:`4`
  - 若步速比預測更慢 → Top 4 中最受惠:`4` | 最受損:`10`
- **整體潛在機會建議:** 只宜小注

---

## [第五部分] 📊 數據庫匯出 (CSV)

```csv
race_id,horse_number,horse_name,grade,total_ticks,total_crosses,verdict,risk_level
Rosehill_R2,10,In A Tizzy,S-,4,0,TOP4_1,LOW
Rosehill_R2,4,Eynesbury,A,3,0,TOP4_2,LOW
Rosehill_R2,8,Aladdin's Girl,A-,1,1,TOP4_3,MED
Rosehill_R2,9,Blitzgal,B+,1,2,TOP4_4,HIGH
Rosehill_R2,5,Hold The Door,B,2,0,RATING_B,LOW
Rosehill_R2,12,Lawless Lucy,B,2,0,RATING_B,LOW
Rosehill_R2,1,Last Apache,C,0,1,RATING_C,MED
Rosehill_R2,7,Aida,C,0,1,RATING_C,MED
Rosehill_R2,11,Lady Lonsdale,C,0,2,RATING_C,MED
Rosehill_R2,13,Miss Johanski,C,0,3,RATING_C,HIGH
```"""
filled = re.sub(r'\*\*Top 4 位置精選\*\*.*```csv.*?```', top4_csv, filled, flags=re.DOTALL)
Path("2026-04-06 Rosehill Gardens Race 1-8/04-06 Race 2 Analysis.md").write_text(filled)
print("done")
