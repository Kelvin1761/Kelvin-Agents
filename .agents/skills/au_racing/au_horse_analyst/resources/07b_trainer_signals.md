# 練馬師出擊訊號 (AU Trainer Signals)

> **條件式讀取：** 只需關注 Wong Choi 提供嘅 `[ACTIVE_TRAINERS]` 中列出嘅練馬師。其餘練馬師嘅訊號可以跳過。

當你在執行 `Step 12` 時，請對照以下訊號判定馬匹是否觸發了特定嘅強勢部署。

---

## 12.A 練馬師分級 (Trainer Tiers)

> **基線參考（2025-26 季截至 2026 年 3 月）：** 以下分級為基線參考。若 Wong Choi 數據包或搜索結果顯示某練馬師嘅當季表現明顯偏離其列出嘅分級（如 Tier 2 練馬師跨州 Group 級別頻繁勝出），應動態升/降級。**不在任何列表 = 無訊號 (➖ Neutral)**，不可自動給予 ❌。

| 級別 | 練馬師 | 2025-26 季參考 |
|:---|:---|:---|
| **Tier 1 (精英)** | Chris Waller, Ciaron Maher & David Eustace, James Cummings (Godolphin), Peter & Paul Snowden, Annabel Neasham, Anthony & Sam Freedman, Gai Waterhouse & Adrian Bott | Waller 228W(全澳#1)、Maher 195W(全澳#2)。Group 1 常客。首出馬成功率顯著高於平均 |
| **Tier 2 (主力)** | Bjorn Baker, Chris Munce, Mark Newnham, Kris Lees, Gerald Ryan & Sterling Alexiou, John O'Shea, Hawkes Racing, Mick Price & Michael Kent Jr, David Payne, Danny O'Brien, Wendy Roche, Joe Pride | Baker 76W(NSW#3)。穩定都會出馬量。有特定州際/場地/距離強項 |
| **Tier 3 (標準)** | 其他練馬師 | 季內中後段。出馬量較少或勝率偏低 |

---

## 12.B 練馬師州際/場地偏好 (Trainer State & Track Preference)

> **原理：** 澳洲幅員遼闊，練馬師往往有明確嘅州際/場地強項。當馬匹配搭「場地專家」練馬師+適合場地 = 正面訊號加成。

### NSW 練馬師

| 練馬師 | 偏好場地 | 偏好距離 | 備註 |
|:---|:---|:---|:---|
| Chris Waller | **Randwick ✅✅**, Rosehill ✅ | 全距離 | 全澳最強馬房。每場地皆穩定但 Randwick 贏馬最多。跨州(VIC)亦有穩定部署 |
| Peter & Paul Snowden | **Randwick ✅✅** | 1000-1400m | **2YO/3YO 短途專家**。初出馬成功率極高。Randwick 為主場 |
| Gai Waterhouse & A. Bott | Randwick ✅, Rosehill ✅ | 1000-1600m | **前領型部署專家**。初出馬以前領搶放著稱 |
| James Cummings (Godolphin) | Randwick ✅, Rosehill ✅ | 1200-2000m | **Autumn Carnival 鋪路專家**。進口馬首戰質素高。全距離皆有部署 |
| Annabel Neasham | Randwick ✅ | 1400-2400m | **首出勝率極高**。中長距離為主。跨州(VIC)亦有穩定部署 |
| Bjorn Baker | **Rosehill ✅✅** | 1200-1600m | **Rosehill 專家**。省賽降都會班次減磅內檔強項 |
| Mark Newnham | Randwick ✅ | 1200-1600m | 穩定都會練馬師。偶有 Group 級別突出表現 |
| Gerald Ryan & S. Alexiou | Rosehill ✅ | 1000-1400m | 短途穩定 |
| John O'Shea | Rosehill ✅, Randwick ✅ | 1200-1800m | 均衡型。穩定出馬量 |

### VIC 練馬師

| 練馬師 | 偏好場地 | 偏好距離 | 備註 |
|:---|:---|:---|:---|
| Ciaron Maher & David Eustace | **Caulfield ✅✅**, Flemington ✅ | 全距離 | **全澳規模最大馬房之一**。跨州(NSW/QLD)極頻繁。Quick Backup 蓄意部署著稱 |
| Anthony & Sam Freedman | **Flemington ✅✅**, Caulfield ✅ | 1600-2500m | **長途馬季中增程專家**。Melbourne Cup 系列賽常客 |
| Mick Price & Michael Kent Jr | Caulfield ✅, Moonee Valley ✅ | 1200-1600m | 穩定 VIC 主力。短中距離為主 |
| Michael & Wayne & John Hawkes | Flemington ✅ | 1200-1600m | 資深家族練馬師。穩定中段 |
| Wendy Roche | **Moonee Valley ✅✅** | 1200-1600m | Moonee Valley 專家。急彎場地強項 |

### QLD 練馬師

| 練馬師 | 偏好場地 | 偏好距離 | 備註 |
|:---|:---|:---|:---|
| Chris Munce | **Eagle Farm ✅✅**, Doomben ✅ | 1200-1600m | **QLD 冠軍練馬師**。Eagle Farm 勝率極高。Brisbane Winter Carnival 常客 |

**場地偏好使用規則：**
- 馬匹今仗場地 = 練馬師偏好場地 ✅✅ → 在 `馬匹分析 > 風險與練馬師意圖` 中標記 `[場地專家]`
- **場地專家標記不改變評級矩陣嘅 ✅/❌，但可作為 Step 14.E 微調嘅正面因素**
- **此表為輔助參考**。若數據包有 `Trainer-Track Specialisation Search` 搜索結果（Step 12 規定），以搜索結果為準

---

## 12.C 練馬師部署模式偵測 (Trainer Pattern Detection)

> **原理：** 除咗固定嘅條件表之外，以下通用模式可適用於所有練馬師，偵測到時標記為正面/負面訊號。

### 正面模式 (觸發 ✅ 或 ➖→✅)

| 模式 | 條件 | 標記 | 說明 |
|:---|:---|:---|:---|
| **騎師升級** | 上仗騎師排名低於今仗騎師（對比最近 12 個月勝率排名）| `[騎師升級 ✅]` | 練馬師刻意配更好騎師 = 有信心出擊 |
| **轉廄即勝跟進** | 轉廄首仗勝出 + 今仗同練馬師第二仗 | `[轉廄跟進 ✅]` | 新練馬師調教見效 = 信心正面 |
| **蓄意放草部署** | 休息 ≥28 天 + 上仗跑入前五 | `[蓄意部署 ✅]` | 有走勢馬刻意放草恢復 = 目標明確 |
| **關鍵配備升級** | 首次戴眼罩/首去眼罩/首次戴面箍 + Tier 1 練馬師 | `[配備升級 ✅]` | 精英馬房配備調整通常有針對性（見 Step 5 精英馬房裝備升權） |
| **跨州遠征** | 跨州出賽 + Tier 1 練馬師 + 配一線騎師 | `[精英遠征 ✅]` | 精英馬房跨州遠征 = 有信心（運費+旅程成本高） |
| **連勝加碼** | 上仗勝出 + 今仗同場同距離 + 同騎師 | `[連勝鎖定 ✅]` | 全因素重複 = 練馬師認定配方有效 |
| **3rd-Up 大考** | Third-up + 距離增程 + Tier 1/2 練馬師 | `[大考部署 ✅]` | 蓄兵三仗後增程 = 蓄意部署大考 |
| **省賽轉都會精英** | 省賽勝出 + 轉都會 + Tier 1 練馬師 + 騎師升級 | `[都會升級 ✅]` | 精英馬房認為馬匹已準備好面對都會級別 |

### 負面模式 (觸發 ❌ 或 ➖→❌)

| 模式 | 條件 | 標記 | 說明 |
|:---|:---|:---|:---|
| **騎師下降** | 上仗騎師排名高於今仗（特別是 Tier 1 → Tier 3+）| `[騎師下降 ⚠️]` | 無法留住好騎師 = 信心存疑 |
| **頻繁換騎** | 近四仗配 4 位不同騎師 | `[找答案 ⚠️]` | 對此馬缺乏信心 |
| **升班無升級** | 升班 + 無騎師升級 + 無配備變動 | `[升班裸出 ⚠️]` | 無準備嘅升班 = 可能只為賺獎金或填場 |
| **連續差仗同部署** | 近三仗同騎師+同走法+全差(≥6th) | `[策略疲勞 ⚠️]` | 練馬師無新方案 |
| **都會轉省賽** | 都會連續差仗 + 退回省賽 + Tier 3 練馬師 | `[信心崩潰 ⚠️]` | 練馬師放棄都會競爭 |

---

## 12.D 練馬師特定出擊訊號（觸發時標記）

> **以下為高信心度嘅特定練馬師模式。觸發時直接在評級矩陣「騎練訊號」維度標記 ✅。**
> **這些訊號已在 `02_algorithmic_engine.md` Step 12 同 Step 13 有對應規則。此處集中列出以便對照。**

| 練馬師 | 模式 | 條件 | 標記 |
|:---|:---|:---|:---|
| Chris Waller | A | 3rd-Up 大考（蓄兵三仗） | `Waller 3rd-Up` |
| Chris Waller | B | 濕地專家出擊：座騎有濕地贏績+今場 Soft/Heavy | `Waller Wet Track` |
| Chris Waller | C | Maiden/BM58 騎，備資 ≤7 天 + 減磅 ≥2kg | `Waller Quick Backup` |
| Chris Waller | D | 都會初出馬 + ≥2 項裝備（舌帶/鉞剣口詞鐵/閘前除耳塞） | `Waller Metro Debut` |
| Waterhouse/Bott | A | 初出馬 + 試閘走勢凌厲 + 內檔 (1-4) + 前領騎師 (如 Tim Clark) | `Waterhouse/Bott Debut` |
| Waterhouse/Bott | B | 馬匹初戴眼罩+轉快放 | `Waterhouse/Bott Pace` |
| Ciaron Maher | A | 跨州遠征配一線騎師 | `Maher Far Raid` |
| Ciaron Maher | B | 短間距 ≤14 天再出（蓄意部署） | `Maher Quick Backup` |
| James Cummings | A | 秋季嘉年華鋪路，2nd-up/3rd-up 增程 | `Cummings Autumn Trail` |
| James Cummings | B | 海外進口馬首戰/次戰澳洲，配一線騎師 | `Cummings Import Strike` |
| Peter & Paul Snowden | A | 2YO/3YO 短途初出或 Second-up 配好檔 | `Snowden Sprint` |
| Annabel Neasham | A | 首出勝率極高，休後復出+試閘佳 | `Neasham First-Up` |
| Anthony & Sam Freedman | A | 長途馬季中增程至 2000m+（蓄兵大考） | `Freedman Stayer` |
| Bjorn Baker | A | 省賽降都會班次+減磅+內檔 | `Baker Metro Drop` |
| Chris Munce | A | Eagle Farm + 內檔(1-5) + 1200-1400m | `Munce Eagle Farm` |
| Chris Munce | B | Brisbane Winter Carnival + 配頂級遠征騎師 | `Munce Carnival Strike` |
| Mark Newnham | A | 上仗受困(Held up) + 檔位大幅改善 + 同騎師 | `Newnham Rebound` |
| Mick Price & Kent Jr | A | Moonee Valley/Caulfield + 前速馬 + 內檔(1-4) | `Price MV Control` |
| Joe Pride | A | Canterbury + 前速 + 內檔(1-4) | `Pride Canterbury Boss` |

---

## 12.E Step 12 練馬師訊號綜合判定流程

每匹馬嘅練馬師訊號判定必須按以下流程：

1. **確認練馬師分級** (Tier 1/2/3)
2. **檢查場地偏好** — 今仗場地是否匹配（若有搜索結果以搜索為準）
3. **掃描特定出擊訊號表** (12.D) — 是否觸發任何已知模式
4. **掃描通用模式偵測** (12.C) — 是否觸發正面/負面通用模式（騎師升級/下降、轉廄跟進、蓄意部署等）
5. **綜合判定：**
   - 觸發 ≥1 個特定訊號 OR ≥2 個正面通用模式 → `✅`
   - 觸發 1 個正面通用模式 + Tier 1 練馬師 → `✅`
   - 觸發 1 個正面通用模式 + Tier 2/3 → `➖` (中性偏正面)
   - 無任何觸發 → `➖`
   - 觸發 ≥1 個負面模式 → `❌`（除非同時觸發正面特定訊號可對沖）

6. **輸出格式：** 在分析中，`Step 12 風險與練馬師意圖` 需列明：
   - 練馬師分級 (Tier X)
   - 場地偏好匹配 (✅/❌/均衡)
   - 觸發嘅訊號 (標記名稱)
   - 騎師升級/下降判定
   - 最終訊號結論 (✅/➖/❌)

---

## 12.F 與 Step 13 互動規則（首出馬/質新馬）

| 練馬師分級 | 首出馬封頂 | 條件 |
|:---|:---|:---|
| **Tier 1** | B+ 基礎（可觸發覆寫至 A-/A+） | 需配合 Waller Metro Debut / Waterhouse/Bott Debut 等特定訊號 |
| **Tier 2** | B 基礎 | 配合試閘佳+一線騎師可微升至 B+ |
| **Tier 3** | B- 基礎 | 試閘+血統皆極佳可微升至 B |

> **注：** Step 13 嘅封頂規則（單純試閘最高 B / 試閘+血統+練馬師最高 B+）仍為硬性規則。只有 `Waller Metro Debut` 同 `Waterhouse/Bott Debut` 等特定訊號可覆寫封頂。
