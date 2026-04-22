# SIP Changelog (HKJC)
> 合規 Agent 每次掃描時讀取此文件,特別檢查最近 2 次更新嘅 SIP 是否被正確套用。

## Latest Updates

<!-- Newest entries at top. Keep last 5 updates only. Archive older entries to 00_sip_index.md. -->
<!-- Template for new entries:
### [DATE] — [SIP-ID]: [Title]
- **Changed:** [What was modified]
- **Target File:** [Which resource file]
- **Impact:** [What should change in Analyst output]
- **Regression Check:** [What to look for if Analyst reverts to old behavior]
-->
### 2026-04-06 — SIP-ST44: 冷門馬訊號標準化 (Underhorse Signal Standardized Triggers)
- **Changed:** 冷門馬訊號新增 7 項標準化觸發條件(≥2 項觸發即強制輸出），統一 Kelvin/Heison 引擎標準
- **Target File:** `08_templates_rules.md`
- **Impact:** 所有 B+ 或以下馬匹均需按標準條件掃描冷門訊號
- **Regression Check:** 若全場唯一放頭馬+底磅+配備變動仍無冷門訊號觸發 → SIP 未生效

### 2026-04-06 — SIP-ST43: 跨場減分馬偵測 (Cross-Venue Class Dropper Detection)
- **Changed:** Step 6 新增跨場標記 — 近3仗全谷草+轉沙田+降分≥10+底磅 → 情境升級
- **Target File:** `04_engine_corrections.md`
- **Impact:** 谷草轉沙田底磅馬不再被系統性忽略
- **Data Points:** R2 紅旺繽紛(@6.6, 谷草→沙田底磅, 兩引擎均未入T4→冠軍)
- **Regression Check:** 若近3仗全谷草+底磅馬轉沙田仍被忽略 → SIP 未生效

### 2026-04-06 — SIP-ST42: 二班以上後追馬加分 (Class 2+ Deep Closer Bonus)
- **Changed:** Step 14.2G 新增 — ≤二班+1400m+後追成功≥2次+賽道利後追 → 情境輔助✅
- **Target File:** `06_rating_aggregation.md`
- **Impact:** 高班 1400m 後追馬獲得結構性加分
- **Data Points:** R10 綠族無限(@44, 走位10→10→8→1, 未入T4→冠軍)
- **Regression Check:** 若二班1400m+後追成功紀錄馬仍無情境✅ → SIP 未生效

### 2026-04-06 — SIP-ST41: 大熱崩潰壓力測試 (Favourite Collapse Stress Test)
- **Changed:** Step 14.2F 新增 — 首選≥A+賠率≤5.0+風險因素 → 強制崩潰情境分析+Pick2≥B+
- **Target File:** `06_rating_aggregation.md`
- **Impact:** 短賠大熱門不再被盲目追捧，強制考慮崩潰可能
- **Data Points:** R4 威武年代(S→6th @4.7)、R5 堅先生(A+→6th @3.0)
- **Regression Check:** 若首選A級+賠率≤3.0+頂磅仍無崩潰壓力測試 → SIP 未生效

### 2026-04-06 — SIP-ST40: 直路賽放頭壟斷覆蓋 (Straight Course Front-Runner Monopoly Override)
- **Changed:** `10a_track_sha_tin_turf.md` 新增 — 1000m直路+唯一放頭馬+初出馬>40% → 評級下限B-
- **Target File:** `10a_track_sha_tin_turf.md`
- **Impact:** 直路賽壟斷放頭馬不再被 L400 歷史段速壓至 D 級
- **Data Points:** R1 飛來霸(D級→23倍冠軍, 全場唯一放頭馬, 7匹初出)
- **Regression Check:** 若1000m直路唯一放頭馬+初出馬>40%仍被評D級 → SIP 未生效

### 2026-04-01 — SIP-ST33: AWT 排序風險加強修正 (AWT Ranking Risk Enhancement)
- **Changed:** SIP-RR20 排名風險折扣新增 4 項 AWT 專用修正因子:後追外檔(-0.5)、連勝加磅(-0.5)、見習首配(-0.5)、醫療風險(-0.25)
- **Target File:** `10c_track_awt.md`
- **Impact:** AWT 賽事 Pick 1/2 排序更準確,減少 Pick 3/4 超越率
- **Regression Check:** 若 AWT 後追型+非1-3檔馬仍穩居 Pick 1 → SIP 未生效

### 2026-04-01 — SIP-ST32: AWT 老馬輕磅回師冷門升級 (AWT Veteran Light Weight Return)
- **Changed:** Step 14.5 冷門冠軍安全網新增 AWT 老馬輕磅觸發因子: ≥6歲+AWT紀錄+最輕磅+久休≥35日→升B/B+
- **Target File:** `10c_track_awt.md`
- **Impact:** AWT 老馬+輕磅+經驗組合被正確識別為冷門潛力馬
- **Data Points:** R1 #12 爆熱 (B-, 7歲, 118lb最輕, AWT經驗→1st)
- **Regression Check:** 若 AWT ≥6歲+最輕磅+AWT入前四紀錄仍維持 D/C 級 → SIP 未生效

### 2026-04-01 — SIP-ST31: AWT S-/A+ 品質閘門加強 (AWT Elite Rating Quality Gate)
- **Changed:** SIP-HV15 S-品質閘門新增 AWT 專用第 4 項閘門: 需≥1 AWT勝或≥3 AWT入前四才可維持S-/A+
- **Target File:** `10c_track_awt.md`
- **Impact:** AWT 賽事 S-/A+ 評級更可靠,防止僅有 1-2 次 AWT 入位即獲最高評級
- **Data Points:** R1 #3 銳一 (S-, 僅1次AWT亞軍→不入前四)
- **Regression Check:** 若 AWT 僅1-2次入位馬仍獲 S- → SIP 未生效

### 2026-04-01 — SIP-ST30: AWT 呼吸道風險升級 (AWT Respiratory Risk Escalation)
- **Changed:** Step 7 風險標記新增 AWT 呼吸道修正: 喘鳴近4仗≥1次→計2個風險標記; ≥2次→封頂B+
- **Target File:** `10c_track_awt.md`
- **Impact:** 有喘鳴/氣管有血歷史的馬匹在 AWT 被正確限制評級
- **Data Points:** R1 #5 魅力星 (A+, 近2仗喘鳴, AWT→僅3rd)
- **Regression Check:** 若有喘鳴紀錄馬匹在 AWT 仍獲 A+ → SIP 未生效

### 2026-03-29 — SIP-RR22: 5-6歲突然贏馬回落 (Mid-Age Surprise Win Fallback)
- **Changed:** Step 14.2B 新增降級因素 — 5-6歲 + 上仗勝出 + 近10仗入三甲≤2次(含勝出) → Top 4 排序降半級
- **Target File:** `06_rating_aggregation.md`
- **Impact:** 5-6歲 inconsistent 馬匹突然贏馬後下仗被正確壓低;長期上名(≥4次入三甲)豁免
- **Regression Check:** 若5歲馬近10仗僅1次入三甲(含該勝)但下仗仍維持原評級 → SIP 未生效
- **Design:** 與「贏馬回落風險」(≥7歲)互補。≤4歲受 Rising Star 保護,5-6歲用此規則,≥7歲用現有規則

### 2026-03-22 — OBS-004: B-級冷門掃描 (B-Grade Longshot Scan) [🟡觀察中]
- **Changed:** Step 14.2D 新增 — B-評級+最輕磅+好檔(≤4)+Top騎師+≥1400m → 標記🏂B-冷門觀察
- **Target File:** `06_rating_aggregation.md`
- **Impact:** B-冷門馬在冷門馬訊號中被列出(暫不自動升級)
- **Data Points:** R8 #13 紫荊拼搏 (B-, 班德禮+檔2+116lb最輕→1st 15x)
- **Status:** 🟡 觀察中 — 需 ≥3 案例確認

### 2026-03-19 — SIP-HV1: 沉睡專家回師豁免 (Dormant Expert Revival Exemption)
- **Changed:** Step 5 新增 5.6 — 近4仗差但近10仗有同場地同路程入三甲 → 穩定性覆蓋為 ⚠️➖
- **Target File:** `04_engine_corrections.md`
- **Impact:** D級場地路程專家回師時應升至 C-/C+ 而非維持 D
- **Regression Check:** 若場地路程專家回師仍被判 D 級 → SIP 未生效

### 2026-03-19 — SIP-HV2: 大幅配備變動升級 (Major Gear Change Upgrade)
- **Changed:** Step 6 新增 ≥2項配備變動+Tier1/2騎師 → 練馬師訊號觸發半核心✅
- **Target File:** `04_engine_corrections.md`
- **Impact:** 大幅除/加配備的馬匹不再被低估
- **Regression Check:** 若 ≥2項配備變動+一線騎師仍未觸發練馬師訊號 → SIP 未生效

### 2026-03-19 — SIP-HV3: 臨門一腳缺失 (Closing Kick Deficit) [強化版]
- **Changed:** Step 14.2B 分兩級:(A) 全前5有三甲但0勝→降半級 (B) 全前5但0三甲→穩定性強制➖+降半級
- **Target File:** `06_rating_aggregation.md`
- **Impact:** 「穩定地平庸(4th/5th常客)」唔再獲穩定性✅
- **Regression Check:** 若近4仗全4th/5th嘅馬匹仍獲穩定性✅ → SIP 未生效

### 2026-03-19 — SIP-HV4: 晨操/試閘/從化輔助維度 (Trackwork/BT/Conghua Auxiliary)
- **Changed:** 新增 Step 6.5 — 近績差+正面訓練訊號 → 配合SIP-HV1可升半級
- **Target File:** `04_engine_corrections.md`
- **Impact:** 近績差但狀態回勇的馬匹獲得「解鎖」機會
- **Regression Check:** 若近績差馬匹有正面試閘/晨操仍被完全忽略 → SIP 未生效

### 2026-03-19 — SIP-HV5: 潘頓溢價穩定性收緊 (Purton Premium Stability Tightening)
- **Changed:** Step 4 新增旗標+穩定性❌+段速非前三 → 封頂B+
- **Target File:** `04_engine_corrections.md`
- **Impact:** 穩定性差的潘頓座騎不再獲 A 級以上評級
- **Regression Check:** 若穩定性❌的潘頓座騎仍被評 A 級 → SIP 未生效

### 2026-03-19 — SIP-HV6: 醫療事故自動作廢 (Medical Incident Auto-Void)
- **Changed:** Step 12 新增醫療事故(流鼻血/跛行)單一因素自動觸發「上仗不可作準」+ 穩定性排除
- **Target File:** `05_forensic_eem.md`
- **Impact:** 流鼻血/跛行場次結果從穩定性計算中完全排除,避免虛假❌
- **Regression Check:** 若有流鼻血紀錄的馬匹穩定性仍將該仗計入 → SIP 未生效

### 2026-03-19 — SIP-HV7: HV 1650m 外疊風險擴展 (HV 1650m Outer Draw Risk Extension)
- **Changed:** HV 專家矩陣新增 1650m 檔 8-9 非前領型 → Top 4 排序降半級
- **Target File:** `04_engine_corrections.md`
- **Impact:** HV 1650m 檔 8-9 的中群/後追型馬匹在 Top 4 排序中降半級
- **Regression Check:** 若 HV 1650m 檔 8-9 中群型馬仍為 Top 1 精選 → SIP 未生效

### 2026-03-19 — SIP-HV8: 極密出練馬師信心訊號 (Rapid Turnaround Confidence Signal)
- **Changed:** Step 6 新增 ≤14日密出+穩定性❌ → 練馬師訊號半核心✅ + 封頂放寬至A-
- **Target File:** `04_engine_corrections.md`
- **Impact:** 穩定性差但被練馬師極密出嘅馬匹獲得信心加分
- **Regression Check:** 若 ≤14日密出+穩定性❌嘅馬匹仍被封頂B+ → SIP 未生效

### 2026-03-19 — SIP-HV9: 巔峰久休豁免 (Peak Form Break Exemption)
- **Changed:** Step 6 新增 35-56日久休+休息前≥2勝/≥3三甲 → 路程❌降為⚠️➖
- **Target File:** `04_engine_corrections.md`
- **Impact:** 巔峰狀態馬匹中度久休不再被一律判❌
- **Regression Check:** 若休前2/1/1巔峰馬匹久休仍被判❌ → SIP 未生效

### 2026-03-19 — SIP-HV10: HV長途外檔放寬 (HV Long Distance Outer Draw Relaxation)
- **Changed:** HV 專家矩陣新增 1800m/2200m 致命死檔門檻從 ≥10 放寬至 ≥12
- **Target File:** `04_engine_corrections.md`
- **Impact:** HV 1800m/2200m 檔10-11 不再被一律判致命死檔
- **Regression Check:** 若 HV 1800m 檔11 馬匹仍被致命死檔降級 → SIP 未生效

### 2026-03-19 — SIP-HV11: 入位常客降級 (Bracket Runner Downgrade)
- **Changed:** Step 14.2B 新增降級因素:近4仗≥3仗前6但0三甲 → 穩定性⚠️➖+排序降半級
- **Target File:** `06_rating_aggregation.md`
- **Impact:** 「永遠差少少」型馬匹被正確壓低評級
- **Regression Check:** 若近4仗4/5/4/6但0三甲嘅馬匹仍獲穩定性✅ → SIP 未生效

### 2026-03-19 — SIP-HV12: 下行軌跡懲罰 (Downward Trajectory Penalty)
- **Changed:** Step 14.2B 新增降級因素:近≥3仗連續下滑 → 穩定性降一級
- **Target File:** `06_rating_aggregation.md`
- **Impact:** 狀態正在惡化嘅馬匹被正確壓低評級
- **Regression Check:** 若近績3→4→5→10下行軌跡嘅馬匹穩定性維持不變 → SIP 未生效

### 2026-03-19 — SIP-HV13: 全場最輕磅中長途冷門 (Lightest Weight Mid-Long Distance Longshot)
- **Changed:** Step 14.2C 冷門掃描新增觸發訊號:≥1650m + 全場最輕磅(或差≤2lb) + 近績差
- **Target File:** `06_rating_aggregation.md`
- **Impact:** 中長途賽全場最輕磅馬匹即使近績差亦會被冷門掃描捕捉
- **Data Points:** R9 爆得美麗(117lb→1st 7.1x) + R6 竣誠駒(116lb→2nd 15x)
- **Regression Check:** 若≥1650m全場最輕磅D/C級馬匹未被冷門掃描標記 → SIP 未生效
