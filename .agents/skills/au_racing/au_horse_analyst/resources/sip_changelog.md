# SIP Changelog (AU)
> 合規 Agent 每次掃描時讀取此文件，特別檢查最近 2 次更新嘅 SIP 是否被正確套用。

## Latest Updates

<!-- Newest entries at top. Keep last 5 updates only. Archive older entries to 00_sip_index.md. -->

### 2026-03-31 — SIP-RH01~RH06: Rosehill 2026-03-28 Reflector 覆盤批量 SIP（6 項）
- **Changed:** 新增 6 項 SIP，源自 Rosehill 全日 Soft 場覆盤（R1/R9/R10 省賽升班馬三場贏馬被踢出、SIP-R14-5 門檻過窄、JMcD×Waller 大熱 0/2、🐴⚡ 偵測到但未執行、NZ 馬光環失控、上仗贏單因子信任過高）：
  - **SIP-RH01** 省賽升班市場錨定保護（場地專家+輕磅+好檔+升騎 ≥3/4 → Class Jump Penalty 取消。SP≤$5 → 禁止評級低於 B+）→ `02` Step 3
  - **SIP-RH02** Soft 場超輕磅爆發器（SIP-R14-5 擴闊：Soft 5+ ≤56kg+≤8 檔 → +0.5 級；場地專家同時成立 → +1.0 級）→ `02` Step 3
  - **SIP-RH03** JMcD×Waller Brand Trap（SIP-RR05 修訂：T1×T1+SP≤$3+後追+≥10匹 → 品牌溢價歸零+BRAND TRAP 標記）→ `02` Step 11
  - **SIP-RH04** 🐴⚡ 冷門馬強制升位協議（SIP-RR16 強化：🐴⚡+≥3 正面條件 → 強制升位 B+ + 替換 Top 4 末位）→ `02` Step 14.F
  - **SIP-RH05** NZ 遠征馬光環折扣（SIP-RR06 修訂：NZ G1 加分封頂 +0.5 級。首次 AU → +0.25。AU ≥2場+入位 → 取消折扣）→ `02` Step 13
  - **SIP-RH06** 上仗勝出單因子修正（「上仗贏」需同場/同距/同場地 ≥2/3 項。不滿足 → ➖。G2+ 低班勝出 → +0.25 折扣）→ `02` Step 12
- **Target Files:** `02_algorithmic_engine.md` (Step 3, 11, 12, 13, 14.F), `00_sip_index.md`
- **Impact:** 解決 Rosehill 覆盤六大系統性缺陷。核心發現：引擎偵察力一流但執行力不足（「識咗但唔信」），修正後應將偵察成果轉化為實際命中。
- **Regression Check:** 若省賽升班+場地專家+輕磅+好檔馬匹仍因 Class Jump 降級至 B/B- = 回歸。若 Soft 5+ 場地 55.5kg+2 檔馬匹未觸發 SIP-RH02 = 回歸。若 T1×T1+SP≤$3+後追+≥10匹仍獲騎練 ✅ = 回歸。若 🐴⚡+≥3 正面條件馬匹仍僅作備註 = 回歸。

### 2026-03-31 — SIP-FL01~FL06: Flemington 2026-03-28 覆盤批量 SIP（6 項）
- **Changed:** 新增 6 項 SIP，源自 Flemington 全日覆盤（10 場中 S- 勝率僅 14%、排序倒掛率 83%、2YO 框架失效、練馬師主打猜測干擾、Heavy 前領過度懲罰）：
  - **SIP-FL01** 內檔輕磅半核心乘數（Barrier 1-3 + ≥3kg 輕磅差 → EEM +半級 + 微調升半級，T1 騎師可升一級）→ `02` Step 3
  - **SIP-FL02** S- 超配組合稅（T1 練馬師 + T1 騎師 + 大熱門三重疊加 → 步速圖審查，陷入 Traffic 封頂 A-）→ `02` Step 14.E
  - **SIP-FL03** Exotic 組合投注池建議（Top 4 評級密集無明確 S- 統治者 → Box Trifecta/First 4 組合建議）→ `06` Part 3
  - **SIP-FL04** 2YO/初出馬配備懲罰軟化（Hoof Filler/Lugging Bit/Nose Roll 懲罰減半，精英馬房完全取消）→ `02` Step 0.5
  - **SIP-FL05** 禁止練馬師主打猜測（嚴禁推測同門馬「主打/副打」，每匹馬獨立評級）→ `02` Step 12
  - **SIP-FL06** 濕地專家前領崩潰懲罰軟化（Soft/Heavy 勝績≥1 場：懲罰減半；≥3 場+WR≥33%：完全取消）→ `02` Step 10
- **Target Files:** `02_algorithmic_engine.md`, `06_output_templates.md`
- **Impact:** 解決 Flemington 全日覆盤識別嘅五大系統性缺陷：(1) 內檔+輕磅被降為備註而非算分乘數導致 83% 排序倒掛；(2) S- 精英組合過度膨脹導致 14% 勝率投注陷阱；(3) 候選池準確但排序失敗導致獨贏投注價值低；(4) 2YO 初出馬配備懲罰過重導致 D 級馬贏出；(5) 練馬師主打猜測干擾客觀評級。
- **Regression Check:** 若讓磅賽中 Barrier 1-3 + ≥3kg 輕磅差馬匹仍僅在備註中標記而 EEM 未受影響 = 回歸。若 T1+T1+大熱門三重疊加且步速圖顯示 Traffic 嘅馬匹仍獲 S- = 回歸。若 2YO 初出馬因單一 Hoof Filler 即判裝備 ❌ = 回歸。若引擎輸出中出現「Maher 主打可能係 X」等推測性描述 = 回歸。若有 Soft/Heavy 勝績嘅前領馬仍因「Heavy 前領崩潰」被 EEM 判 ❌ = 回歸。

### 2026-03-29 — SIP-RF01~RF02: Soft 雙軌篩選與濕地封頂 (Soft Place Rate & Wet Track Cap)
- **Changed:** 新增 2 項 SIP，修改 SIP-RR08 Tier 定義 + SIP-RR09 協同條件，並新增覆蓋規則。源自 Rosehill 2026-03-28 全日 Soft 場覆盤（10 場中多場無 Soft 經驗馬被引擎高估，而穩定入位馬被低估，主因為「未體驗」➖不扣分漏洞與單一 WR% 指標）：
  - **SIP-RF01** Soft 入位率雙軌篩選（Soft WR<20% 但 PR≥60%+樣本≥3 → Tier 2.5 + 場地❌保護 + SIP-RR09 豁免 + 冷門馬訊號）→ `02` Step 4
  - **SIP-RF02** 濕地未知風險封頂（Soft 5+ 場地下：Tier 4 封頂 A-，Tier 5 封頂 B+。賦予場地維度強制否決權）→ `02` Step 14.E
  - **SIP-RR08 修正** 新增 Tier 2.5（Soft 入位穩定）+ Tier 5 收緊門檻（需 PR<50%）
  - **SIP-RR09 修正** 新增 SIP-RF01 協同豁免條件（Soft PR≥60% 馬匹不觸發 Place Rate 折扣）
- **Target File:** `02_algorithmic_engine.md` Step 4 & Step 14.E
- **Impact:** Soft 場地分析大幅精準化。「穩定入位但未能轉勝」嘅馬不再被錯判為場地風險，獲提升至配腳地位。同時徹底堵塞「無場地經驗馬」因 ➖ 不扣分而斬獲 A/A+ 評級嘅系統漏洞。
- **Regression Check:** 若 Soft 5+ 場地下 Soft PR≥60%+樣本≥3 嘅馬匹仍被歸入 Tier 4/5 或場地適性判❌，即為回歸。若 Soft 5+ 場地下 Tier 4（未知）馬匹仍獲 A/A+ 評級，或 Tier 5（風險）馬匹仍獲 A-/A 評級，即為回歸。

### 2026-03-22 — SIP-RR13 微調: 雙頂級騎練豁免
- **Changed:**
  - **SIP-RR13** 新增第 4 項豁免條件：**雙頂級騎練組合**（騎師 LY WR ≥19% + 練馬師 LY WR ≥19% 同時成立）→ 降級效果減半
  - 源自 R5 驗證：Meridius (Zahra 19.4% + Kennewell 20.1%) 雖為後追但以實力克服 Caulfield 偏差贏馬 → 原 SIP-RR13 過度懲罰高 class 後追馬
- **Target File:** `02_algorithmic_engine.md` Step 7 SIP-RR13
- **Impact:** 防止雙頂級騎練組合嘅高 class 後追馬被過度降級
- **Regression Check:** 若 Caulfield Good Rail-True 下極後追馬 + 非頂級騎練仍獲豁免 = 回歸

### 2026-03-22 — SIP-RR12~RR16: Caulfield 2026-03-21 覆盤批量 SIP（5 項）
- **Changed:** 新增 5 項 SIP，源自 Caulfield 全日 Good 地覆盤（後追馬系統性大敗 + 歷史率過度信任 + 場地勝率封頂缺失 + 距離專精低估 + 冷門馬輸出斷裂）：
  - **SIP-RR12** 超高歷史衰減（Place Rate≥85% + First-up≥90天 → 穩定指數✅降➖ + 保底降一檔）→ `02` Step 1
  - **SIP-RR13** Caulfield Good 後追馬偏差降級（Caulfield+Good+Rail True+後追 → EEM❌ + 分級降級）→ `02` Step 7
  - **SIP-RR14** Good 地勝率封頂（Good 3-4+樣本≥8場+勝率≤15% → 硬性封頂 B）→ `02` Step 14.E
  - **SIP-RR15** 距離全勝專精（特定距離100%W+≥3場 → 裝備與距離✅ + 升半級）→ `02` Step 2
  - **SIP-RR16** 冷門馬偏差自動升位（前領偏差冷門馬+Good+Rail True → 替換Top4第4選）→ `02` Step 14.F
- **Target File:** `02_algorithmic_engine.md`
- **Impact:** 後追馬在 Caulfield Good Rail-True 日嘅過度評級被系統性修正；First-up 超高歷史率馬匹獲合理衰減；Good 地勝率極低馬匹獲硬性封頂；距離全勝紀錄獲獨立識別；冷門馬訊號可轉化為 Top 4 行動
- **Regression Check:** 若 Caulfield Good Rail-True 下極後追馬仍獲 S/A+ 且 EEM 非❌ = 回歸。若 Place Rate≥85% First-up≥90天馬匹穩定指數仍自動✅ = 回歸。若 Good 勝率≤15%+樣本≥8場馬匹仍獲 A-/A = 回歸

### 2026-03-22 — SIP-RR11 + RR06 修正: R8 盲測微調
- **Changed:**
  - **SIP-RR11** 急彎短途大場外檔處罰（後追型+檔≥10+≤1200m+≥14匹→EEM❌）→ `02` Step 7
  - **SIP-RR06 修正** 增加差距門檻 ≤2L + 條件匹配 ≥1 項，防止 G1 季軍盲目保底
- **Target File:** `02_algorithmic_engine.md`
- **Impact:** 修正後追型外檔在急彎短途大場被高估的問題；防止 G1 Pipeline 過度推廣不匹配的馬匹

### 2026-03-22 — SIP-RR08~RR10: Rosehill R3 盲測衍生批量 SIP（3 項）
- **Changed:** 新增 3 項 SIP，源自 R3 盲測中首兩選未入前三的診斷：
  - **SIP-RR08** Soft 場地分級排序（Specialist>Immune>Risk 強制排序）→ `02` Step 4
  - **SIP-RR09** Place Rate Soft 場折扣（Soft 0% + Place≥80% → 保底降至 B）→ `02` Step 4
  - **SIP-RR10** 精英練馬師跨州突襲訊號（T1 遠征意圖+前領型重磅豁免）→ `02` Step 13
- **Target File:** `02_algorithmic_engine.md`
- **Impact:** 修正「Soft 免疫 ≠ Soft 受惠」排序錯誤；限制高 Place Rate 在 Soft 場的保底上限；識別精英練馬師遠征意圖訊號
- **Regression Check:** 若 Soft 確認場地下 Tier 3 免疫馬排在 Tier 1/2 前 = 回歸。若 Soft 0% + 92% Place 仍保底 B+ = 回歸

### 2026-03-22 — SIP-RR01~RR07: Rosehill Gardens 2026-03-21 覆盤批量 SIP（7 項）
- **Changed:** 新增 7 項 SIP，源自 Rosehill 全日 Soft 場地覆盤：
  - **SIP-RR01** 雙軌場地評級制度（Good 4 / Soft 5 並行雙評級+雙 Top 4）→ `02` Step 4 + `06` Part 3
  - **SIP-RR02** Soft 場地專家雷達（Soft WR≥40% 自動標籤+B+保底+場地維度升半核心）→ `02` Step 4
  - **SIP-RR03** 大規模退出應急協議（Top 4 中≥2匹退出→迷你重排）→ `06` Part 4
  - **SIP-RR04** Soft 場地輕磅優勢加成（≤54kg +0.5級 / ≥58kg -0.5級 / ≥59kg -1.0級）→ `04d` Rule 4
  - **SIP-RR05** 頂級騎練聲望溢價交叉檢查（JMcD/Waller Soft WR<30%→加成減半）→ `02` Step 11
  - **SIP-RR06** G1 亞季軍自動保底（G1 Top 3 + Place≥75% → 最低 A-）→ `02` Step 13
  - **SIP-RR07** 爆冷潛力賽事預警（爆冷指數≥6→降信心+擴大掃描）→ `06` Part 4
- **Target Files:** `02_algorithmic_engine.md`, `04d_wet_track.md`, `06_output_templates.md`
- **Impact:** Soft 場地分析精確度大幅提升；場地不穩定時用戶可自選 Good/Soft Top 4；輕磅+Soft 專家獲合理加成；大規模退出有自動重排機制
- **Regression Check:** 若 Soft 場地下 Soft WR≥40% 的馬匹仍獲 B 或以下評級且無保底觸發，即為回歸。若場地 UNSTABLE 但僅輸出一組 Top 4，即為回歸

### 2026-03-18 — SIP-CH18-4: 1000m 標準彎道短途模組 (1000m Standard Bend Sprint Module)
- **Changed:** 新增 Step 0.2 — 1000m 彎道賽專用覆蓋規則。4 條規則：(A) Slow starter/closer 強制降級、(B) On-pace 加成、(C) 負重放大效應、(D) 見習騎師 1000m 風險。
- **Target File:** `02_algorithmic_engine.md` Step 0.2
- **Impact:** 所有 1000m 標準彎道賽（非直線衝刺）嘅 closer/slow starter 將被額外降級，on-pace 馬匹獲加成。見習騎師+closer+外檔觸發騎練❌。
- **Regression Check:** 若 1000m 彎道賽中 closer/slow beginner 馬匹仍獲 A 級評級且 EEM 維度非❌，即為回歸

### 2026-03-18 — SIP-CH18-1: 負重交叉核實協議 (Weight Cross-Verification Protocol)
- **Changed:** 新增見習騎師 claim 雙源核實規則。基礎負重 vs 實際負重差距 ≥2kg 觸發紅旗警告。
- **Target File:** `02_algorithmic_engine.md` Step 3
- **Impact:** 所有含見習騎師嘅賽事分析必須獨立確認 claim 是否適用，避免負重數據錯誤導致評級失準
- **Regression Check:** 若分析中見習騎師馬匹嘅負重直接以 "Base - Claim" 計算而無核實，即為回歸

### 2026-03-18 — SIP-CH18-2: 場地勝率門檻降級 (Track Condition Win Rate Threshold)
- **Changed:** 新增場地勝率 ≤15% (≥5場樣本) 強制 ❌ + 微調降半級規則。前領型加重至可降一級。
- **Target File:** `02_algorithmic_engine.md` Step 4
- **Impact:** 場地適性弱嘅馬匹評級將更精確反映實際風險，避免「已識別❌但評級未受影響」嘅問題
- **Regression Check:** 若場地勝率極低(≤15%)嘅馬匹仍獲 A-/A 評級且無微調降級，即為回歸

### 2026-03-18 — SIP-CH18-3: 退出馬名單最終核實 (Scratching Verification Protocol)
- **Changed:** 新增分析前強制鎖定出賽名單嘅規則。若使用早期數據須標注警告。出賽數變動須重做 Speed Map。
- **Target File:** `06a_data_retrieval.md`
- **Impact:** 防止因退出名單錯誤導致整場分析基於錯誤嘅出賽馬匹數
- **Regression Check:** 若分析中嘅出賽馬匹數與最終結果不符（如多計或少計退出馬），即為回歸
