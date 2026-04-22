<!-- ============================================================ -->
<!-- Track, Gear & Forgive File (Steps 4-6) -->
<!-- Split from 02c_track_and_gear.md on 2026-04-05 -->
<!-- Dependencies: 02a_pre_analysis.md, 02b_form_analysis.md -->
<!-- Referenced by: 02d_eem_pace.md -->
<!-- ============================================================ -->

### Step 4: 步態與場地 (Stride & Track)
- 大步幅 = 長直路佳/急彎損 | 高步頻 = 小場佳
- 濕地:大步幅 = 黏腳 | 高步頻+輕磅 = 最優
- 該場贏馬紀錄 → +15%。首次轉向+急彎 = Risk High
- 州際:首次跨州 -5%,東部→西澳 -10%
- **[州際轉場強化扣分 (Enhanced Interstate Transfer Penalty)]:** 維省 (VIC) 馬匹首次轉戰急彎場地(Rosehill / Moonee Valley / Caulfield),風險權重升至 **-15%**(取代通用 -5%)。Flemington 嘅寬闊彎道幾何結構與 Rosehill/MV 嘅急彎南轅北轍,馬匹需要完全唔同嘅轉彎技術。**降回 -5% 嘅條件:** 馬匹有該目標場地嘅試閘數據且顯示轉彎順暢;或馬匹已在其他急彎場地(如 Sandown)有好表現。東岸→西澳 維持 -10% 不變。

- **[SIP-1] 場地預測容錯機制 (Surface Forecast Tolerance):** 若賽前預測場地為 Heavy 或天氣高度不穩定(如預報降雨概率 ≥60% 且跨越場地等級邊界),必須執行**雙軌敏感度分析**:同時評估「預測場地」及「場地上/下一級」兩種情境對每匹馬的影響。若某匹馬在兩種情境下評級差異 ≥1 級(如 Good 下 A- 但 Soft 下 B),須在該馬分析中標注 `[場地敏感 — 評級受場地變動影響]`,並在第四部分緊急煞車中提醒用戶賽日覆核場地狀態。此機制確保場地預測誤差不會導致推薦失準。

- **[SIP-4] 場地敏感度標籤 (Track Condition Sensitivity Label):** 為每匹馬完成 Step 4 分析後,必須輸出以下標籤之一,顯示馬匹優勢對場地條件的依賴程度:
  - `[場地極敏感 — 僅 Heavy 有優勢]`:馬匹過往重地贏績為主要優勢,而無 Soft 地好表現,且預測場地為 Heavy。**關鍵:** 若實際場地掛牌為 Soft 或更佳,此類馬匹的場地適性維度需由 ✅ 降為 ➖,且任何「Swamp Beast」描述必須被移除或降格。
  - `[場地敏感 — Soft/Heavy 均有表現]`:馬匹在 Soft 及 Heavy 場地均有入位紀錄。場地估算小幅偏差不影響評級。
  - `[場地中性]`:馬匹在 Good 至 Heavy 範圍均有良好表現,場地適性不敏感。
  - `[場地限制 — 僅 Good 地有優勢]`:馬匹缺乏濕地實績,若場地為 Soft 6+ 需加入 ⚠️ 風險標記。

- **[SIP-CH18-2] 場地勝率門檻降級 (Track Condition Win Rate Threshold):** 在 Step 4 場地適性判斷中,若馬匹在今場場地條件下嘅**勝率 ≤ 15%**(且樣本 **≥ 5 場**),場地適性強制判 **❌ Weak**,**且**在微調因素中觸發「場地盲門」降級(可降半級)。此規則確保「場地弱點已識別但未反映於評級」嘅情況不再發生。
  - **前領型加重:** 若馬匹為前領/跟前型且場地勝率 ≤ 15%,「場地盲門」降級加倍至可降一級(前領型極度依賴場地速度,場地不合 = 前速減弱 = 更嚴重)
  - **[SIP-GF02] Good 地泥地馬降班/騎師護體 (Good Track Wet-Specialist Guard):** 若今場為 Good 地但馬匹因勝率 ≤15% 觸發降級,且馬匹具備「降班 ≥1 級」或「配 Tier 1-2 騎師 (相比前仗有明確升級)」,微調降級效果**減半**(降 0.25 級而非 0.5 級)。場地 ❌ 判定維持。若同時具備上述兩項條件,減免效果**不疊加**(仍為降 0.25 級)。若微調後評級仍跌至 D,自動提升至 **C-**。
    - **安全閥:** 若 Good 地歷史樣本 ≥ 10 場且入位率 (PR) ≤ 20%,此護體失效。
    - **邏輯基礎:** 2026-04-02 Gosford R6 覆盤中,Speedy Henry 因判定為泥地馬而在 Good 地判 D,但憑藉降班優勢及 Tyler Schiller 的走位以後追姿態跑獲亞軍。系統低估了「軟地專家」降班及好騎師在好地帶來的補償能力。
  - **邏輯基礎 (CH18-2):** 2026-03-18 Caulfield Heath R8 覆盤中,Viasain (Good 9:1-1-2 = Win% 11%) 嘅場地適性已被標記為 ❌,但評級 A- 未受足夠影響。最終跑第 4 (2L),in-run 始終居第 5 位,完全未能發揮前領優勢。

- **[SIP-RR01] 雙軌場地評級制度 (Dual Track Rating System — Good 4 / Soft 5 並行輸出):**
  - **觸發條件:** 場地預報處於 Good 4 和 Soft 5 之間(即兩者皆有可能),例如:「Good 4,可能升至 Soft 5」、「Good 4 to Soft 5 UNSTABLE」;或當日降雨預報 ≥ 30%;或場地被標記為 UNSTABLE。
  - **執行規則:**
    1. 為每匹馬在最終裁決中輸出**兩個獨立評級**:一個基於 Good 4 場地、一個基於 Soft 5 場地。
    2. 差異說明:若兩個評級差 ≥ 1 級,必須附帶差異說明(如「Soft WR% 數據不足」或「Soft 場專家,輕磅加成」)。
    3. 在 `[第三部分]` 最終決策中,輸出**兩組完整 Top 4**:📗 Good 4 場地 Top 4 和 📙 Soft 5 場地 Top 4。
  - **用戶使用方式:** 賽前根據最終公佈場地條件,選擇對應的 Top 4 版本。引擎不自動判斷場地,決策權留在用戶手中。
  - **邏輯基礎:** 2026-03-21 Rosehill 覆盤中,預測 Good 4 但實際 Soft。Pinito(Good A / Soft B-)第 9 名、Campaldino(Good A+ / Soft B)第 7 名、Chayan(Good A / Soft C+)第 8 名。若用戶在賽前收到 Soft 版本 Top 4,可避免以上所有失誤。

- **[SIP-RR02] Soft 場地專家雷達 (Soft Track Specialist Radar):**
  - **觸發條件:** 賽事場地為 Soft 5 或以上。
  - **自動標籤:** 若馬匹 Soft WR% ≥ 40%(且樣本 ≥ 3 場),在分析中自動添加 🌧️`[Soft 場地專家]` 標籤。
  - **評級保底:** 帶有 Soft 場地專家標籤的馬匹,最低評級不得低於 **B+**(與「鐵腳保底」同等級別)。
  - **維度權重動態調整:** 場地為 Soft 5+ 時,「場地適性」維度從「輔助」升級為「半核心」,相應調整評級計算。
  - **反向篩選:** Soft WR% = 0%(且樣本 ≥ 2 場)的 Good-only 馬匹,在 Soft 場地上自動降一級並標記 ⚠️`[場地風險 — 無 Soft 勝績]`。
  - **冷門掃描強化:** Soft 專家即使賠率偏冷(≥$15),仍應在冷門馬訊號中獲得「⚡ 強力冷門」評級。
  - **邏輯基礎:** 2026-03-21 Rosehill 覆盤中,Marhoona(Soft WR 高)冠軍、Guest House(100% Place)冠軍、Catch The Glory(Soft 50%)冠軍——均因引擎低估 Soft 場地適性而被排在 Top 4 之外或過低。

- **[SIP-RR08] Soft 場地分級排序 (Soft Track Hierarchy — Specialist > Immune > Risk):**
  - **觸發條件:** 場地確認為 Soft 5+。
  - **強制排序規則:** 在 Top 4 最終排名中,嚴禁將「Soft 免疫」馬排在「Soft 受惠/專家」馬之上。分級如下:
    - **Tier 1 — Soft 專家 (WR ≥40%, 樣本≥3)**:最優先。獲 SIP-RR02 標籤。**⚠️ 小樣本限制:Soft 樣本 ≤2 場的馬匹禁止列入 Tier 1,最高 Tier 2。**
    - **Tier 2 — Soft 受惠 (WR 20-39%)**:第二優先。場地正面因素。
    - **Tier 2.5 — Soft 入位穩定 [SIP-RF01] (WR <20%, 但 PR ≥60%, 樣本≥3)**:介乎受惠與免疫之間。此類馬喺 Soft 場唔常贏但穩定入位 = 場地唔構成風險。排序高於 Tier 3 但低於 Tier 2。**⚠️ 呢類馬適合作為三重彩/四重彩嘅安全腳,但非首選贏馬候選。**
    - **Tier 3 — Soft 免疫 (場地全能,Good/Soft/Heavy WR 差距 <10%)**:第三。場地「不受影響」但不代表「有優勢」。
    - **Tier 4 — Soft 未知 (Soft 樣本 = 0)**:第四。數據不足,風險中性偏負。
    - **Tier 5 — Soft 風險 (WR = 0%, 樣本≥2, 且 PR <50%)**:最低。獲 SIP-RR02 反向標籤。**[SIP-RF01 修正]** 若 Soft WR = 0% 但 Soft PR ≥ 60%(樣本≥3),此馬**不得列入 Tier 5**,強制提升至 **Tier 2.5**(入位穩定)。此類馬證明了場地適應能力但未能轉化為勝場。
  - **排序覆蓋:** 若兩匹馬評級相同(如都是 B+),Tier 較高的馬自動排在前面。若 Tier 1 馬評級比 Tier 3 馬低半級(如 B+ vs A-),Tier 1 馬仍應排在 Tier 3 馬之上(場地是確定因素,權重更高)。
  - **例外:** 若 Tier 3(免疫)馬的評級比 Tier 1/2 馬高 ≥1.5 級(如 A+ vs B),則免疫馬可排在前面(實力差距壓倒場地因素)。
  - **邏輯基礎:** 2026-03-21 Rosehill R3 覆盤中,Starphistocated(Soft 25% = Tier 3 免疫)被排為第一選但跑第 5,而 Polymnia(場地中性 + 63% Place = Tier 4 但位置更穩)跑第 2。「免疫」≠「受惠」,在 Soft 場地上場地專家和受惠者應排在免疫者前面。

- **[SIP-RR09] Place Rate Soft 場折扣 (Place Rate Soft Discount):**
  - **觸發條件:** 馬匹 Soft WR% = 0%(且 Soft 樣本 ≥ 1 場)**且** Place Rate ≥ 80%。
  - **效果:** Place Rate 作為「鐵腳保底」的上限從 **B+** 降至 **B**。即 Place Rate 仍作為保底依據,但在 Soft 場地下不可因高 Place Rate 單獨維持 B+ 或以上。
  - **原因:** Place Rate 建立在歷史場地條件上(通常以 Good 場為主)。當場地轉為 Soft 而馬匹 Soft 0% 時,歷史 Place Rate 不可直接遷移。
  - **SIP-RR05 協同:** 若同時觸發 SIP-RR05(JMcD/Waller 場地限制),Place Rate 保底進一步降至 **B-**。
  - **[SIP-RF01 協同]:** 若馬匹 Soft WR = 0% 但 **Soft PR ≥ 60%**(樣本≥3),SIP-RR09 嘅「保底上限從 B+ 降至 B」**不觸發**。此類馬已通過 SIP-RF01 證明 Soft 場入位能力,歷史 Place Rate 仍具參考價值。保底維持 **B+**。
  - **邏輯基礎:** 2026-03-21 Rosehill R3 覆盤中,Pinito(92% Place Rate + Soft 0%)被保底在 B+ 第二選,但實際跑第 9 名。92% Place Rate 全在 Good 場建立,Soft 場下完全不可遷移。

- **[SIP-RF01] Soft 入位率雙軌篩選 (Soft Place Rate Dual-Track Screening):**
  - **觸發條件:** 賽事場地為 Soft 5+,**且**馬匹 Soft WR% < 20%(勝率偏低),**但** Soft PR%(入位率 = 前三名完成率)≥ 60%(入位率高),**且**樣本 ≥ 3 場。
  - **核心邏輯:** 現有系統以 Soft WR%(勝率)作為場地適性主要判斷標準。但勝率同入位率係兩個獨立維度:
    - **Soft WR% 高**(≥40%)= 喺 Soft 場能贏 = 場地「專家」
    - **Soft PR% 高**(≥60%)但 WR% 低 = 喺 Soft 場跑得穩但贏唔到 = 場地「適應者」
    - **兩者都低** = 場地真正風險
    純粹用 WR% 會將「穩定入位但未能轉勝」嘅馬錯判為場地風險馬(Tier 4/5),導致呢類馬喺 Top 4 篩選中被過度懲罰。
  - **效果:**
    1. **Tier 提升:** 觸發 SIP-RF01 嘅馬匹喺 SIP-RR08 排序中自動歸入 **Tier 2.5**(Soft 入位穩定),排序高於 Tier 3(免疫)、Tier 4(未知)同 Tier 5(風險)。
    2. **場地適性維度保護:** 場地適性維度**不得判為 ❌ Weak**,最低維持 **➖ Neutral**。若 Soft PR% ≥ 80%(樣本≥3),可判為 **✅ Strong**(近乎場地專家水平嘅穩定性)。
    3. **保底保護:** SIP-RR09 嘅 Place Rate Soft 折扣對此類馬**不生效**(見 SIP-RR09 協同)。
    4. **冷門馬訊號:** 觸發 SIP-RF01 + 賠率 ≥ $10 嘅馬匹,自動列入冷門馬掃描為 🐴`[Soft 入位型冷門]`(穩定入位 = 適合三重彩/四重彩腳)。
  - **安全閥:**
    - 若 Soft PR% ≥ 60% 但近 3 仗 Soft 場表現**全部**跑第 4 名或更差(即入位率只係歷史數據,近態已衰退),SIP-RF01 **不生效**,維持原 Tier 判定。
    - 若馬匹 Soft 樣本全部來自**省賽 (Provincial/Country)**,且今仗為都會 (Metro),Tier 2.5 **降至 Tier 3**(省賽入位率不可直接遷移至都會)。
  - **輸出標記:** 觸發時喺馬匹分析中標注 🌧️📊`[Soft 入位穩定 — PR X% / WR Y% / N 場]`。
  - **邏輯基礎:** 2026-03-28 Rosehill 覆盤中,多匹馬 Soft WR% 偏低但實際 Soft 場穩定入位或贏出(如 Welwal R9 $11 贏馬,分析僅評 B-)。純粹以 Soft WR% 篩選導致引擎低估「場地適應者」嘅穩定性。入位率係場地適應能力嘅第二維驗證——一匹喺 Soft 場穩定跑入前三嘅馬,其場地風險遠低於從未喺 Soft 場入位嘅馬。

- **[SIP-4] 「Swamp Beast」場地觸發門檻 (Swamp Beast Activation Threshold):**
  - 「Swamp Beast (Swamp Beast)」或任何「Heavy 地專家」稱謂,**僅當實際賽事掛牌為 Heavy 7 或以上時才可觸發**相關評級加分。
  - 若場地掛牌為 Soft(無論 Soft 5、Soft 6 或 Soft 7),「Swamp Beast」稱謂不發揮加分效用,僅保留作一般「良好濕地適應良好」的參考,限「場地適性」維度保持 ➖ Neutral(如僅有 Soft 地贏績支持)或 ✅ Strong(若在 Soft 及 Heavy 共 ≥3 戰入位)。
  - 喺 Soft 場地分析中使用「Swamp Beast」標籤即視為評級失真。

### Step 5: 裝備解碼 (Gear Changes)
Blinkers 1st = 求變/搶放 | Blinkers Off = 轉後上 | Tongue Tie/Ear Muffs首戴 = 改善末段 | Nose Band/Lugging Bit = 矯正閃 | Bar Plates首戴 = 蹄傷修復
- **[裝備+騎師協同 (Gear-Jockey Synergy)]:** 當一匹有搶口/外閃紀錄嘅馬「除眼罩 (Blinkers Off)」配「頂級騎師」,呈個往往係馬房成功解決心理問題嘅訊號。Step 5 與 Step 11 嘅協同作用應更敏感:頂級騎師 + 修正裝備 = 狀態反彈訊號 (+1 微調升級因素)。
- **[精英馬房裝備升權 (Elite Stable Gear Premium)]:** 精英馬房(Waller / Snowden / Freedman / Hawkes / Maher / Neasham)嘅首次裝備變動(尤其 Blinkers 1st 或 Tongue Tie 1st)成功率顯著高於平均水平。若精英馬房首戴裝備 + 配合強試閘表現,裝備與距離維度自動從 ➖ 升至 ✅(代表裝備變動非探索用途,而係針對性修正)。非精英馬房首次裝備變動維持標準處理(未驗證 = ➖ 最高)。**互斥:** 若精英馬房裝備升權已令「裝備與距離」維度升至 ✅,且同一裝備變動亦觸發練馬師出擊訊號(如 `Waller Metro Debut` 嘅裝備組合),「騎練訊號」維度嘅 ✅ 不可因同一裝備事件重複計分。騎練訊號維度必須以騎練合作數據或其他獨立訊號(如 Quick Backup 間距部署)嚟判斷,不可引用裝備。

### Step 6: 競賽報告法醫 & 寬恕檔案 (Steward Reports & Forgive File)
- "Lame"/"Bleeder"+試閘轉好 = 反彈。"Checked"/"Hampered" >2馬位 → -0.3s
- "Held up" → -0.5s至-0.8s。查 "Slow out"/"Raced wide"/"Bumped on jumping"
- **[寬恕檔案 Forgive Run]:** 若上仗具備 ≥2項不可控致命阻礙(如嚴重勒避 + 3-wide 無遮擋,或賽後發現心律不正/流鼻血),判定「上仗不可作準 (Forgive Run)」,評級直接回溯參考前仗數據。
- **[嚴重受困自動作廢 (Severe Blockage Auto-Void)]:** 若馬匹上仗名次 ≥10th,且競賽報告明確出現 「Held up」/「Checked severely」/「Unable to obtain clear running」/「Hampered」 等受困描述,則該仗段速數據**完全失真**,此單一因素即足以觸發「上仗不可作準 (Forgive Run)」,無需第二個寬恕因素。必須強制回溯至最近一仗「望空」嘅賽事重新錪定段速與 形勢。
- **[寬恕班次過濾器 (Forgive Run Class Filter)]:** 當觸發 Forgive Run 並考慮評級升級時,必須驗證馬匹的**生涯最佳 Rating 與今仗 BM 級別之差距**。若馬匹生涯最佳 Rating 落後今仗 BM 級別 >5 分(例如生涯最佳 62 但今仗為 BM70),則寬恕 (Forgive Run) 仍然成立(忽略該劣質賽事),但**嚴禁因寬恕而升級評級**。邏輯基礎:寬恕代表「嗰仗唔作準」,但唔代表馬匹級數足以在更高班次勝出。級數天花板係硬性物理限制,寬恕無法覆蓋。
- **[V 型反彈觸發條件 (V-Rebound Prerequisites)]:** 若 Step 6 結論為「上仗不可作準」,**且**觸發回溯後的可作準賽事顯示馬匹在「同場 + 同程」具備勝出/上名紀錄,**且**今仗回歸該首本場地/路程。⚠️ **強制能力證明:** 馬匹必須在過往賽績中**已經證明過具備「V 型反彈」的實力**(例如過往曾於大敗或嚴重受困後的一仗重新交出極佳表現或勝出)。若無此「反彈往績」,純屬主觀期望,一律僅視為普通寬恕 (Forgive Run)。滿足所有條件 → 此情境方能視為**正面反彈訊號**,強制將 Step 0.5 情境標籤升級為 `[情境A-升級]`。**澳洲擴展:** 若馬匹從跨州失趗回到家鄉主場 (Home State Track),同樣觸發 V 型反彈。
- **⚠️ 反三重計算 (Anti-Triple-Count):** 若 V 型反彈已將情境標籤升級為 `[情境A-升級]`,則 Step 14.E 嘅寬恕輔助加分 (+1 ✅) **不再生效**。V 型反彈本身已包含數據重置 + 正面情境升級,屬最強等級寬恕受益,不可再疊加額外 ✅。擇一原則:V 型反彈 OR 輔助 ✅,不可兼得。

