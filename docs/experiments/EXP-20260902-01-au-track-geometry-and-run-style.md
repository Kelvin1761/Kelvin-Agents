# EXP-20260902-01 賽道幾何修好之後，跑法 × 幾何 有冇獨立資訊

- **日期**：2026-09-02
- **平台**：AU
- **假設**：短直路利前置、長直路利後上 —— 呢個交互作用喺模型評完分之後仲有獨立資訊，
  可以由 Sportsbet 跑法標籤 × 賽道幾何 落到排名。
- **搜索過嘅舊記錄**：`docs/experiments/` 全掃冇「跑法 × 幾何」記錄。相關舊結論：
  memory `au-run-style-mostly-unpredictable`（跑法**單獨**喺 top-4 之內 AUC 0.5175
  [0.5000, 0.5348]，冇 ship）、[EXP-20260821-04](EXP-20260821-04-au-draw-field-size-scaling.md)
  （檔位按馬匹數縮放 REJECT）、[EXP-20260831-13](EXP-20260831-13-au-barrier-is-prescratching-draw.md)。
  **呢次係新測試**，因為之前根本冇正確嘅直路長度可以做交互項。
- **改到嘅檔案／組件**：
  - `au_racing_engine/engine_core.py`（幾何來源、venue section 切法）
  - `.agents/scripts/inject_fact_anchors.py`（Facts 層同一個 bug）
  - 新增 `au_wong_choi_auto/scripts/fetch_au_track_geometry.py` + `resources/au_track_geometry.json`
  - 新增 `tests/test_track_profile_venue_scoping.py`

## 前置：幾何數據本身係壞嘅

呢個實驗做唔做得成，前提係先有正確幾何。實測 2026-09-02：

| 症狀 | 影響 |
|---|---|
| `_track_venue_section()` 開咗 `re.S`，標題行 `.*` 跨行 | **14,727 行報告、85 個場地**印住合集檔第一節（Canterbury）嘅 `1570m / 280m` |
| 都會檔個表喺 `#` 一級標題之下、第一個 `##` 之上 | Randwick / Flemington / Caulfield / Doomben / Rosehill **6,227 行冇尺寸** |
| Facts 層逐行掃成份合集檔再覆蓋 | Belmont / Sandown 攞到 **Ascot 尺寸 + Canterbury 特性**，一個唔存在嘅賽場 |
| 手寫檔本身有錯 | Morphettville 寫 2000/350（真值 2339/334）、Ascot 寫 1860/350（真值 2022/294）、Canterbury 直路 280（真值 308） |

修法：幾何改為由 `fetch_au_track_geometry.py` 生成，兩個來源
（racinglife.com.au、justhorseracing.com.au）逐場地交叉核對，分歧記入 `conflict`
但採用 racinglife（實測 justhorseracing 有過期條目：Pakenham 仲係搬去 Tynong 之前
嘅 1400m 舊場、Rockhampton 1600m）。markdown 淨係保留文字特性。
覆蓋：語料庫 96 個場地 **85 個有齊周長＋直路**；餘下 11 個（Broome、Carnarvon、
Katherine、Mt Isa、Roma、Tuncurry、Emerald、Gympie、Narrandera、Caulfield Heath、
Pakenham Synthetic）兩個來源加人手都查唔到，一律留白。

## 數據
- **語料**：`AU_Racing` 兩個 root（含 `Archive/`），只取 **2026-08-05 起**嘅乾淨
  point-in-time 場次（之前嗰批係賽後重新評分，跑法標籤本身會食到賽果）。
- **樣本**：8,908 個 runner / 928 場 / 72 個場地 / 18,380 對場內比較。
- **跑法來源**：`_data.running_style_line`（Sportsbet），四個值 ——
  前領 3.8%、跟前 7.4%、守中 68.7%、後上 20.1%。守中大部分係**證據不足嘅預設值**。
- **指標**：場內 AUC（同場上名 vs 落榜兩兩比較）；cohort 用「超額 = 上名率 − 3/出馬數」
  做場內公平份額校正（唔校正就會把細場當成好跑法）。

## 結果

### 交互作用：加幾何令個訊號**變差**，三個切法一致

| 特徵 | 全場 AUC | top-4 之內 | 只計有走位證據 |
|---|---|---|---|
| 跑法（單獨） | 0.5149 [0.5050, 0.5246] | 0.5128 [0.4984, 0.5289] | **0.5489 [0.5241, 0.5781]** |
| 跑法 × 直路長度 | 0.5140 [0.5052, 0.5222] | 0.5037 [0.4887, 0.5169] | 0.5423 [0.5193, 0.5653] |
| 檔位（單獨） | 0.5106 [0.4949, 0.5239] | 0.5079 [0.4831, 0.5284] | — |
| 檔位 × 賽道緊度 | 0.5106 [0.4974, 0.5265] | 0.5079 [0.4840, 0.5302] | — |
| 檔位 × 直路佔比 | 0.4854 [0.4708, 0.4980] | — | — |

### 分層：cohort 方向啱，但唔夠 power

| 直路 | 前置族 n | 後上 n | 前置 − 後上 超額 | 95% CI |
|---|---|---|---|---|
| <300m | 99 | 174 | +1.08pp | [−9.58, +12.93] |
| 300–379m | 508 | 844 | +10.32pp | [+5.46, +15.40] ✅ |
| 380–429m | 249 | 440 | +1.00pp | [−5.69, +7.79] |
| ≥430m | 83 | 144 | +2.61pp | [−10.01, +15.70] |

**唔單調** —— 假設預測最短直路差距最大，實測最短嗰桶差距最細。唯一顯著嗰格
（300–379m）就係 70% 樣本所在，即係全局「前置 > 後上」喺有 power 嗰度現形，
唔係幾何交互作用。逐場地連續相關 r(直路長度, 前置優勢) = **−0.530**，方向啱，
但只有 9 個場地夠 n，而且 Ballarat Synthetic（375m，+25.28pp）同 Ipswich
（300m，+29.35pp）就佔咗大部分擺動。

檔位 × 周長同樣：細場 +3.67pp / 中場 +0.75pp / 大場 −0.70pp，**單調而且方向啱**，
但三格 CI 全部跨零。

### 順帶量到嘅：跑法本身係正交嘅

| 相關 | 值 |
|---|---|
| ρ(跑法, 模型分)（場內 z-score） | **+0.079** |
| ρ(跑法 × 直路, 模型分) | +0.048 |
| ρ(跑法, 跑法 × 直路) | +0.545 |

`race_shape` 2026-08-22 退出排名之後，跑法喺排名層**權重係零**，所以呢個 +0.079
係真嘅未用資訊。對比：`pace_figure` 係現時唯一講得上正交嘅 leaf（ρ ≤ 0.13）。

## 檢查
- **leakage-audit**：PASS — 只用 2026-08-05 起嘅 point-in-time 場次；跑法標籤同幾何
  都係賽前拎得到；賽果只做 label。⚠️ 舊語料唔可以用，因為賽後重新評分會令跑法標籤
  食到當日賽果（見 `au-sportsbet-postrace-leakage`）。
- **golden_scoring**：冇郁（AU / HKJC 各 120 匹馬全部一致）—— 幾何修正純顯示。
- **data_contract**：PASS（引擎指紋變咗，已重新 `--calibrate --since 2026-08-05`）。
- **退步**：冇。`./檢查.sh` 五項全綠。

## 結論

**幾何交互作用唔存在，唔係「太細」係「加咗更差」。** 三個獨立切法（全場、top-4、
只計有證據）加上直路長度之後 AUC 全部低過跑法單獨用，檔位 × 緊度更加係一模一樣
（0.5106 → 0.5106）。cohort 層面方向啱但唔單調，而唯一顯著嗰格就係樣本最多嗰格 ——
即係全局跑法效應，唔係幾何。9 個可量度場地嘅 r = −0.530 睇落吸引，但兩個異常點
（Ballarat Synthetic、Ipswich）就撐起咗大半，n = 9 冇 power。

**幾何嘅價值喺報告層，唔喺排名層。** 修好之後 85 個場地印返自己嘅周長／直路／方向，
Sandown 由「極窄小場 / 直路 280m / 短直路令後追 timing 更緊」變返 2087m / 491m ——
呢個係真嘅修復，只不過唔會郁排名。

**真正值得追嘅係跑法本身，唔係幾何。** 剔走「證據不足預設守中」之後，跑法場內 AUC
0.5489 [0.5241, 0.5781]，CI 清楚離開 0.50，而且對模型 ρ 只有 +0.079。之前 memory
記住嘅 0.5175 [0.5000, 0.5348] 係**溝埋預設守中**量出嚟 —— 同 `au-neutral-point-is-per-leaf`
同 `au-only-half-the-leaves-score` 一樣嘅形狀：覆蓋率溝淡咗判別力。呢個要行足
`model-regression-gate`（baseline → dev → 時間 fold → holdout）先講得上 ship。

**決定**：
- 賽道幾何做排名特徵 → **REJECT**
- 賽道幾何做資料修正／報告層 → **KEEP**（已上線）
- 跑法（限有走位證據）做排名特徵 → **NEEDS MORE TESTING**（未跑過閘，未 ship）

**commit**：未 commit

## 重跑
```bash
python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/fetch_au_track_geometry.py
python3 -m pytest .agents/skills/au_racing/au_wong_choi_auto/tests/test_track_profile_venue_scoping.py -q
./檢查.sh
```
