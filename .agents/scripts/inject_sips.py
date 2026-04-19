#!/usr/bin/env python3
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""Inject SIP-ST41, SIP-ST42, SIP-ST43, SIP-ST44 into protocol files."""
import os

BASE = "/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/.agents/skills/hkjc_racing/hkjc_horse_analyst/resources"

# ─── SIP-ST41 + SIP-ST42 → 06_rating_aggregation.md ───
fpath = os.path.join(BASE, "06_rating_aggregation.md")
with open(fpath, 'r', encoding='utf-8') as f:
    content = f.read()

INJECT_41_42 = """
**Step 14.2F: 大熱崩潰壓力測試 (Favourite Collapse Stress Test) [SIP-ST41]:**

> [!WARNING]
> **來源:** 2026-04-06 ST R4 威武年代(S, @4.7→6th)、R5 堅先生(A+, @3.0→6th)、R1 閃電小子(A-, @1.5→2nd)。短賠大熱門+風險因素組合 = 高崩潰率。

當引擎首選（Pick 1）滿足以下**全部條件**時，強制執行壓力測試：

| 條件 | 門檻 |
|:---|:---|
| 評級 | ≥ A |
| 預計獨贏賠率 | ≤ 5.0 |
| 以下任一風險 | (a) 負頂磅(≥133lb)；(b) 檔位 ≤5(1400m以上賽事)；(c) 休後復出 >60日 |

**效果：**
1. **強制寫出「崩潰情境」段落**（在 Verdict 前）：
   - **目標馬：** [馬名] | 評級：[X] | 預計賠率：[Y]
   - **崩潰誘因：** [頂磅/內檔/休後...]
   - **崩潰機率評估：** [低/中/高]
   - **若崩潰，最受惠馬：** [馬名（第二選）]
   - **資金分配調整：** 若崩潰機率 ≥ 中 → 首選注碼削減 30%，分配至第二/三選
2. **第二選最低評級門檻：** Pick 2 必須 ≥ B+ 評級。若 Pick 2 < B+，強制重新審視 T4 排列。
3. **崩潰機率判定標準：**
   - **低：** 僅 1 項風險因素 且馬匹有證明紀錄克服該因素
   - **中：** 2 項風險因素 或 1 項無克服紀錄
   - **高：** ≥3 項風險因素

**不觸發：** 首選預計賠率 > 5.0；首選評級 < A。

**Step 14.2G: 二班以上後追馬加分 (Class 2+ Deep Closer Bonus) [SIP-ST42]:**

> [!NOTE]
> **來源：** 2026-04-06 ST R10 綠族無限(@44, 走位 10→10→8→1，未入 T4)。高班 1400m 賽事中證明嘅後追馬被系統性低估。

**觸發條件：**
- 班次 ≤ 第二班
- 距離 = 1400m
- 馬匹近 5 仗中 ≥2 次走位為「後三名→入四甲」模式
- 當日賽道偏差利後追（B+2/C+3 等外偏賽道 或 A Rail）

**效果：**
- Step 14.1 情境適配維度：授予輔助 ✅ `[後追紅利 Deep Closer Bonus]`
- 若馬匹同時負輕磅（≤全場中位數）→ 額外+0.25排序加分（SIP-RR20 擴展）
- 評級不得低於 C+（保底）

**不觸發：** 班次 ≥ 第三班；距離 ≠ 1400m；近 5 仗後追成功率 <2 次。

"""

# Insert before "**Step 14.3:"
marker = "**Step 14.3:"
if marker in content:
    content = content.replace(marker, INJECT_41_42 + marker, 1)
    with open(fpath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"✅ SIP-ST41 + SIP-ST42 injected into 06_rating_aggregation.md")
else:
    print(f"❌ Marker '{marker}' not found in 06_rating_aggregation.md")

# ─── SIP-ST43 → 04_engine_corrections.md ───
fpath2 = os.path.join(BASE, "04_engine_corrections.md")
with open(fpath2, 'r', encoding='utf-8') as f:
    content2 = f.read()

SIP_ST43 = """
**[SIP-ST43] 跨場減分馬偵測 (Cross-Venue Class Dropper Detection):**

> [!NOTE]
> **來源：** 2026-04-06 ST R2 紅旺繽紛(@6.6 勝出，由谷草轉沙田作戰，底磅，兩引擎均未入 T4)。

**觸發條件：**
- 馬匹近 3 仗均於谷草（Happy Valley）出賽
- 今仗於沙田出賽
- 馬匹評分較上季高位下降 ≥ 10 分
- 負底磅（場中最輕 3 匹之一）

**效果：**
- Step 2 路程場地適性標記為 `⚠️ [跨場適性未知 (Cross-Venue Uncertainty)]`
- 若同時為底磅（場中最輕 3 匹之一）→ 情境適配從 ➖ 升為 ✅
- Step 8.2 練馬師訊號新增「跨場出擊」考量 — 練馬師刻意轉場往往有戰術目的

**不觸發：** 馬匹於近 3 仗中已有 ≥1 仗於沙田出賽；馬匹非底磅。

"""

# Insert before "### Step 7:"
marker2 = "### Step 7: 風險標記"
if marker2 in content2:
    content2 = content2.replace(marker2, SIP_ST43 + "---\n\n" + marker2, 1)
    with open(fpath2, 'w', encoding='utf-8') as f:
        f.write(content2)
    print(f"✅ SIP-ST43 injected into 04_engine_corrections.md")
else:
    print(f"❌ Marker '{marker2}' not found in 04_engine_corrections.md")

# ─── SIP-ST44 → 08_output_templates.md (underhorse signal standardization note) ───
fpath3 = os.path.join(BASE, "08_output_templates.md")
with open(fpath3, 'r', encoding='utf-8') as f:
    content3 = f.read()

SIP_ST44 = """

> [!IMPORTANT]
> **[SIP-ST44] 冷門馬訊號強制觸發標準化 (Underhorse Signal Standardized Triggers):**
> **來源：** 2026-04-06 ST 覆盤 — Heison 引擎具備冷門馬訊號系統（觸發飛來霸），Kelvin 引擎完全缺乏此安全網。
> 當馬匹符合以下 ≥2 項條件時，**強制觸發**冷門馬訊號（即使評級已定）：
> - (a) 直路賽外檔（≥9 檔）
> - (b) 全場唯一放頭馬（SIP-ST40 觸發）
> - (c) 負底磅（場中最輕 3 匹之一）
> - (d) 配備變動（初戴/除去）
> - (e) 練馬師初出馬勝出率 > 15%
> - (f) 評分已觸底（距離降班線 ≤ 3 分）
> - (g) 騎師升級（由見習生/華將升為一線外籍騎師）
> 若 ≥2 項觸發 → 強制輸出 `🐴⚡ 冷門馬訊號` 行，列明觸發條件編號及受惠情境。

"""

# Insert before "🐴⚡ 冷門馬總計"
marker3 = "**🐴⚡ 冷門馬總計 (Underhorse Signal Summary):**"
if marker3 in content3:
    content3 = content3.replace(marker3, SIP_ST44 + marker3, 1)
    with open(fpath3, 'w', encoding='utf-8') as f:
        f.write(content3)
    print(f"✅ SIP-ST44 injected into 08_output_templates.md")
else:
    print(f"❌ Marker '{marker3}' not found in 08_output_templates.md")

print("\n🏁 All SIP injections complete!")
