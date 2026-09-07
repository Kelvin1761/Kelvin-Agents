# EXP-20260907-03 `confidence_score` 死分支清理 + 一個「條件式」常數罰分

- **日期**：2026-09-07
- **平台**：AU
- **假設**：`_has_last10_warning()` 喺 `confidence_score` 嘅 −4 係死分支
  （EXP-20260907-02 遺留）。**成立，而且唔止一個。**
- **搜索過嘅舊記錄**：EXP-20260907-02、EXP-20260907-01、
  memory `au-health-score-has-no-source`、`ab-identical-means-unwired`、
  `au-written-field-is-not-a-filled-field`
- **改到嘅檔案**：`au_racing_engine/engine_core.py`（`_confidence_score`、
  剷走 orphan `_has_last10_warning`）

## 量度方法要更正一次
我第一次用自己搭嘅 harness 跑 `_confidence_score`，得出**七個分支得三個 fire**。
**唔可信** —— harness 冇餵 speedmap 同 meeting intelligence，所以分數範圍只有
**49–79**，而真 pipeline 存檔係 **55–87**。同 EXP-20260907-02 一樣嘅陷阱
（[[ab-identical-means-invalid]] 嘅變體）：**harness 少餵嘅嘢會扮成「死分支」**。

改為量**真 pipeline 出嘅存檔實物**：836 份 Facts 嘅往績表，共 **73,452 行**。

## 逐項判決

| 項目 | 判決 | 證據 |
|---|---|---|
| `warning_line` −4 | **死** | key 由來唔存在（8,224 匹 `_data`） |
| `_latest_l600_rt_brief()` 錨點 | **死** | Facts `L600/RT` 欄 **73,452 行 0.0% 有值** |
| `_latest_l600_rt_brief()` +1 | **死** | 同上 |
| `unresolved_forgiveness` −1 | **⚠️ 每匹馬都中** | 「寬恕認定」欄 **73,452 行 100% 係 `[需判定]`** |
| `meeting_bias` 錨點 | 活 | Facts 內 bias 字眼 260 次 |
| `speedmap tactical_nodes` 錨點 | 活 | Facts 內 241 次 |

## 改咗啲咩
剷走三個死項（錨點分母 **14 → 13**）同 orphan helper `_has_last10_warning`；
source tag 去掉 `warnings`；文案唔再講 warnings。**零分數變化** ——
三個都由來冇 fire 過（golden AU 120/120 一致）。

## ⚠️ 冇動、但係壞嘅：`unresolved_forgiveness −1`
「寬恕認定」100% 都係 `[需判定]`，所以呢個**條件式**扣分其實係**常數 −1**，
零區分力。冇喺呢度剷，因為：
1. 剷走會令**每個顯示嘅信心分 +1**（用戶可見，唔再係零變化）；
2. 正確做法多數係**令「寬恕認定」真係會被判定**，唔係刪個罰分 ——
   即係 Facts 生成層有一步冇接通。

要獨立一個改動，而且要先決定係「修判定」定「刪罰分」。

## 同場掃到（未處理）
- Facts 往績表 `早段步速` 欄 **73,452 行 0.0% 有值** —— 另一條死欄位，
  唔知邊個 leaf 讀。
- `_latest_l600_rt_brief()` 仲有第三個 caller：一個叫「最新PF/RT」嘅顯示行
  （engine_core:2744）。因為同一個欄位空，嗰行永遠冇內容。helper 保留咗畀佢。

## 檢查
- **leakage-audit**：PASS（只用賽前欄位）
- **golden_scoring**：AU **120/120 一致**
- **run_tests**：15 個 suite 全綠（632 個 AU 引擎測試）
- **退步**：冇

## 結論
1. Kelvin 叫我清嘅嗰一條係死嘅，**但同一個 function 入面仲有兩條同款**，
   一次過清。錨點分母由一個達唔到嘅 14 改為 13。
2. **順帶揸到一個相反嘅缺陷**：一個「條件式」罰分實際上 100% 命中 = 常數。
   呢類嘢用「命中率係咪 0%」搵唔到，要問「命中率係咪 100%」。
3. 量度紀律：**自己搭嘅 harness 判唔到死分支** —— 少餵一個 context 欄位就會
   令活分支扮死。要用真 pipeline 嘅存檔實物。
