<!-- ============================================================ -->
<!-- EEM Energy & Pace Cascade (Steps 7-10) -->
<!-- Split from 02d_eem_pace.md on 2026-04-05 -->
<!-- Dependencies: 02a_pre_analysis.md, 02c_track_and_gear.md -->
<!-- Referenced by: 02e_jockey_trainer.md, 02f_synthesis.md -->
<!-- ============================================================ -->

### Step 7: EEM 能量消耗 (Energy Expenditure & Pace Buffer)
- 1-wide基準 | 2-wide +3-5m | 3-wide no cover +8-12m | 4-wide +14-18m(每1m ≈ 0.06-0.08s)

- **[SIP-2] 場地調節係數 (Track Condition EEM Multiplier):** 所有外疊 (2-wide 以上) 的能量消耗懲罰必須按照當日實際掛牌場地乘以以下係數調整:

  | 場地等級 | 外疊懲罰係數 | 說明 |
  |:---|:---|:---|
  | Heavy 10 | ×1.6 | 極端泥濘,體能消耗呈指數上升 |
  | Heavy 8-9 | ×1.5 | 嚴重泥濘,外疊致命 |
  | Heavy 7 | ×1.3 | 中度偏重,外疊顯著不利 |
  | Soft 6-7 | ×1.0 | 標準懲罰,維持基準計算 |
  | Soft 5 | ×0.9 | 外疊輕微不利,稍作折扣 |
  | Good 3-4 | ×0.7 | 外疊懲罰大減,馬匹移動流暢 |
  | Firm 1-2 | ×0.6 | 場地快捷,外疊幾乎無損耗 |

  **使用方法:** 先計算原始 EEM 外疊消耗(如 3-wide no cover = +10m)→ 乘以對應係數(如 Soft 5 = ×0.9 → 實際 +9m)→ 代入最終判斷。若調整後仍超過 +10m,維持 `[高消耗]`;若低於 +6m,降格為 `[中等消耗]`。

  **⚠️ 重要:** 若場地掛牌為 Soft 或更佳,「致命死檔」(Fatal Draw) 的判斷門檻必須同步提高——外檔 (10+) 喺 Heavy 8 地屬「致命」,但喺 Soft 地只屬「中等不利」,**嚴禁在 Soft 場地使用「致命死檔」描述**。

- **[SIP-3] 後追馬場地懲罰調節 (Closer Penalty Track Adjustment):** 後追跑法 (Settled Runner / Type B) 喺 EEM 維度的自動 ❌ Weak 判定,必須按場地條件調整:

- **[SIP-RR11] 急彎短途大場外檔處罰 (Tight-Turn Sprint Wide Draw Penalty):**
  - **觸發條件:** 急彎跑道(Rosehill / Canterbury / Morphettville 等起步後 ≤400m 入彎的場地)+ 距離 ≤1200m + ≥14 匹參賽馬 + 後追型馬匹(Settled/Closer/Type B/C)+ 檔位 ≥10。
  - **效果:** EEM 維度**自動 ❌ Weak**(即使其他 EEM 因素正面)。相當於額外 -0.5 級懲罰。
  - **原因:** 急彎短途大場中,外檔後追型必須在入彎前覆蓋更多距離尋找好位,消耗倍增。前領型外檔可以搶前省力,但後追型外檔 = 雙重劣勢(追不到好位 + 彎道走外疊)。
  - **前領型豁免:** 若馬匹為確認的前領型(生涯 ≥50% 領放/箱位),此 SIP 不適用(前領型可從外檔搶前控制步速)。
  - **邏輯基礎:** 2026-03-21 Rosehill R8 覆盤中,Warwoven(後追型,14 檔,A-)跑第 6,從 9th settled 追到 6th 但始終無法進入前列。急彎 1200m + 16 匹 + 外檔 = 結構性劣勢無法靠實力彌補。

- **[SIP-RR13] Caulfield Good 地後追馬偏差降級 (Caulfield Good Rail-True Closer Penalty):**
  - **觸發條件(全部同時成立):** (1) 馬場 = Caulfield;(2) 場地 = Good 3 或 Good 4;(3) 跑道欄位 = Rail True(或 Rail Out ≤ 3m);(4) 馬匹跑法 = 後追型 / 極後追型 (Type B Settled Runner),近 5 仗平均 in-run 位置 ≥ 6th(中距離賽)或 ≥ 5th(短途賽)。
  - **觸發效果 — 分級降級:**
    - 極後追 (近 5 仗平均 ≥ 8th settled):EEM **❌ Weak**(強制,取代任何原有判定)+ 微調可降一級
    - 後追 (近 5 仗平均 6th-7th settled):EEM **❌ Weak**(強制)+ 微調可降半級
    - 前中段偏後 (近 5 仗平均 4th-5th settled):EEM **➖ Neutral**(維持現判)+ 無額外降級
  - **慢閘加重:** 若後追馬同時有慢閘頑疾(近 5 仗 ≥ 2 次 Stewards 記錄 slow begin/slow away),上述降級效果**加半級**。
  - **豁免條件(滿足其一即可減半降級效果):** 觸發 SIP-8 頂級後追豁免;Tier 1 騎師 + 評分 ≥ 90;步速預測 Genuine-to-Suicidal;**雙頂級騎練組合**(騎師 LY WR ≥19% + 練馬師 LY WR ≥19% 同時成立)— 此組合代表高 class 後追馬有足夠能力克服 Caulfield 直路限制。
  - **與 SIP-8 互動:** SIP-8 豁免可將 ❌ 緩和至 ➖,但微調降級仍維持半級(Caulfield 367m 直路係硬性物理限制,不可完全豁免)。
  - **不適用場景:** Caulfield Soft 5+ → 退回 SIP-3。Caulfield 1000m → 退回 SIP-CH18-4。
  - **雙軌模式明確邊界 (SIP-RR01 Interaction):** 當 SIP-RR01 雙軌觸發（Good 4 / Soft 5 並行）時:
    - 📗 **Good 4 版本:** SIP-RR13 完整適用（後追馬 EEM 強制 ❌）
    - 📙 **Soft 5 版本:** SIP-RR13 不適用，退回 SIP-3（後追馬 EEM 最差 ➖）
    - 此條件差異必須反映在雙軌評級差異理據中。
  - **邏輯基礎:** 2026-03-21 Caulfield 覆盤中,4 匹 S/A+/A- 級後追馬(King Zephyr A+ → 6th、Jimmysstar S → 7th、Planet Red S- → 6th、Damask Rose A- → 7th)全部大敗。同日前領/前中段馬 4 場全贏。Good + Rail True + 367m 直路 = 後追馬結構性劣勢。


  | 場地等級 | 後追馬 EEM 判定 | 原因 |
  |:---|:---|:---|
  | Heavy 8+ | ❌ Weak(維持原判定) | 極端重地,後追幾乎無法追上 |
  | Heavy 7 | ❌ Weak(需有明確遮擋位置才豁免) | 重地後追極端不利 |
  | Soft 6-7 | ➖ Neutral(除非明確顯示塞車風險) | 後追馬有能力追擊,不自動懲罰 |
  | Soft 5 及更佳 | ➖ Neutral 至 ✅ Strong(若步速配合) | 後追馬具充分反擊空間 |

  **配套修改:** `EEM與形勢` 半核心維度的 ❌ Weak 觸發條件(在 Step 14.E 評級矩陣)亦同步適用上述調節——喺 Soft 5 或更佳場地,後追跑法 + 外檔/不理想位置的聯合 ❌ 需考慮場地係數調節,**嚴禁因跑法被動而在 Soft 地自動判定 ❌**。

- **[SIP-8 進階版] 頂級後追豁免 (Elite Closer Override):** 
  - **觸發條件:** 若馬匹擁有「全場最快 / 極佳」的末段衝刺力 (Type B),**且**賽跑距離為 ≥1200m(容許足夠直路追趕),**且**預期步速為 `Moderate` 或更快(非 Crawl)。
  - **豁免效果:** 系統**不可**單純因為「外檔後追」或「內檔塞車風險」而在 Step 14.E 的 `EEM與形勢` 維度強制判定 ❌ Weak,亦不應在微調因素中因「被動跑法」而降級。
  - **核心邏輯:** 此類馬匹具備頂級爆發力豁免權 (Elite Late Speed Exemption)。只要預期步速不至極度緩慢 (Crawl),其進攻潛力可直接覆蓋場地偏差或外檔帶來的物理距離消耗。若步速為 `Crawl`,則此豁免**不生效**,因為即使有頂級變速力,在慢步速賽事中落後太遠依然無法反先。

- **[SIP-R14-2] 頂級騎師檔位豁免 (Elite Jockey Draw Override):**
  - **觸發條件:** 馬匹由 Tier 1 頂級騎師策騎(完整名單見 `07_jockey_profiles.md`:**James McDonald (J-Mac)、Tommy Berry、Nash Rawiller、Craig Williams、Damian Lane、Mark Zahra、Tom Marquand**),**且**馬匹評分 ≥ 85,**且**馬匹狀態非 Deep Prep (≥6仗)。
  - **豁免效果:** 外檔懲罰(7-12 檔)**最多降半級**(即原本降一級改為降半級)。
  - **J-Mac 特殊條款:** 若 J-Mac 策騎 **且** 馬匹評分 ≥ 90,檔位懲罰可進一步鬆綁至**僅加入 ⚠️ 風險標記而不觸發降級**。J-Mac 的走位能力在數據上已證明可完全克服外檔劣勢。
  - **核心邏輯:** 2026-03-14 Rosehill 覆盤中,J-Mac 連續 3 場從外檔勝出(R3 Pembrey 7檔、R7 Sixties 10檔、R8 Lazzura 8檔),Tommy Berry 亦從外檔表現穩定。傳統「外檔必降」邏輯對頂級騎師不適用。
  - **互斥:** 若馬匹同時觸發「致命死檔 (Fatal Draw)」微調降級(Step 14.E),此豁免可將其覆蓋為「⚠️ 風險標記」但不完全消除。在 Moonee Valley 等極端急彎場地,即使頂級騎師亦難克服 12+ 檔,此時豁免降至「降半級」而非「不降」。

- **[SIP-R14-3] 內檔被困擁堵風險 (Inner Draw Congestion Trap):**
  - **觸發條件:** 馬匹排 **1-2 檔**,**且**跑法為**非領放型**(跟前/居中/後上/被動型),**且**出賽馬匹數 ≥ **10 匹**。
  - **風險效果:** 在風險標記中加入 `[內檔被困風險 (Inner Draw Congestion)]`,並在 Step 14.E 的 「EEM與形勢」維度判斷中視為 **-0.5 級微調降級因素**。
  - **加重條件:** 若前方有 ≥3 匹領放/跟前型馬匹佔據內欄(即該馬極可能被前方多匹馬堵死),風險計為 **1 項完整風險標記**(可觸發複合風險升級)。
  - **核心邏輯:** 2026-03-14 覆盤中,排 1 檔的 Militarize (A級「神級膽材」) 及 Jambalaya (A-級) 均未入前三。1-2 檔的非領放馬在大場次中易被前方馬群封死,特別在 Rosehill 等急彎場地。
  - **豁免:** 若馬匹為**已確認的領放型**(近 5 仗 ≥3 次領放),此規則不適用。若步速預測為 `Genuine-to-Fast` 或以上(馬群拉散,被困機率極低),此規則亦不適用。

- **[幾何豁免 — 直線衝刺覆寫]:** *(詳見 `resources/02b_straight_sprint_engine.md`)* 當 Step 0.1 = `[STRAIGHT SPRINT]` 時,外疊 EEM 處罰**完全關閉**,切換至風向能量模型 (Wind Energy Model)。
  > **[條件載入]** 完整風向能量模型邏輯僅在 `[RACE_TYPE: STRAIGHT_SPRINT]` 時從 `resources/02b_straight_sprint_engine.md` 載入。
- **[Pace Buffer 步速緩衝]:** 若賽事步速為 `Crawl (龜速)`,3-wide 無遮擋 **不可** 視為高消耗,反而有利避險積聚動能。只有在正常或快步速下,3-wide 才是致命消耗。
- 兩仗真高消耗 ×1.3 | 三仗真高消耗 ×1.6
- 潛在機會:近三仗 EEM 高消耗但輸近 + 今仗好檔 = 超級潛在機會

**EEM 命名觸發條件(矩陣判斷基準):**
- **✅ Strong (四大觸發條件):**
  1. `[逆境破格 The Monster]`:近仗經歷幾何「真高消耗」(三/四疊望空)卻依然勝出或上名 → 證明其級數遠超物理限制。
  2. `[超級反彈 The Rebounder]`:近仗經歷幾何「真高消耗」僅敗或輸近,且今仗客觀形勢大幅改善(如檔位 14→1,或步速逆轉) → 釋放隱藏實力。
  3. `[隱形消耗反彈 The Rhythm Rebound]`:近仗看似幾何「低消耗」(1-2疊),但遭遇嚴重的**隱形消耗**(如:嚴重𢳂頭人馬角力 > 400m,或中段窒步勒避需重新蹓躂),導致大敗。今仗有條件改善 → 實際體力未見底,被市場嚴重低估。
  4. `[姿態破格 The Dominator]`:近仗雖受惠於低消耗/靚位(1-2疊),但贏馬姿態呈統治級(輕鬆大勝/大把在手),證明其實力深不見底,不應因走位舒服而受罰。
- **❌ Weak:**
  - `[實力見底 Exposed Illusion]`:近仗經歷「真低消耗」(慢步速配合+內欄黃金包廂/輕鬆單騎),且走勢順暢無隱形消耗,毫無物理蝕位卻依然大敗 → 證明其實力不足。
- **➖ Neutral:** 正常消耗對應正常賽果,或高消耗導致大敗(合乎物理常理)。

**EEM 步速紅利 (Pace Bonuses):**
- **[慢步速檔位紅利 (Slow Pace Positional Bias)]:** 當步速預期為 `中等偏慢 (Moderate-to-Slow)` 或 `龜速 (Crawl)` 時,排 1-4 檔的**前領型/跟前型**馬匹自動獲得「位置保證紅利」。在急彎場地(Rosehill / Moonee Valley / Caulfield / Canterbury)此紅利極度放大,即使馬匹級數稍遜(如 C 級),也必須在對比外檔馬時給予情境加分。
  - **[SIP-C14-6] C 欄大場慢步速紅利折扣:** 若觸發「步速互燒警報」(Pace Meltdown Alert,見 Step 10),原本的「慢步速檔位紅利」**不再適用**(因為慢步速前提已被推翻,實際步速可能更快)。所有基於「慢步速」設定的前領馬紅利必須重新評估。
- **[慢步速內檔受困風險 (Slow Pace Inner Draw Trap)]:** ⚠️ 上述紅利**僅限前領型/跟前型馬匹**。若排 1-2 檔的馬匹為**後上型/被動型 (Settled Runner)**,在慢步速下馬群極度壓縮 (Bunched),內欄馬匹極易被前方集團封死無位出 (Held up)。此時 1-2 檔從「紅利」反轉為「受困風險」,在急彎窄場 (Canterbury / Moonee Valley / Rosehill 1200m) 尤為致命。此類馬匹須在風險儀表板中加入 `[慢步速內檔受困]` 標記。
  - **[SIP-R14-3 增強] 大場次內檔被困風險擴展:** 即使步速並非慢步速,若出賽馬匹 **≥10 匹**、排 1-2 檔、且跑法為非領放型,仍須加入 `[內檔被困風險 (Inner Draw Congestion)]` 標記(見 Step 7 SIP-R14-3)。此標記在急彎場地的嚴重程度翻倍。
- **[快步速輕磅紅利 (Fast Pace Light Weight Bonus)]:** 當步速預期為 `快 (Genuine-to-Fast)` 或 `自殺式 (Suicidal)` 時,負磅 ≤53kg 的後追/中疊馬獲得額外「能量補償紅利」。前方重磅馬 (≥59kg) 在快步速下崩潰機率極高,輕磅馬的體力優勢在末段會被成倍放大。
- **[慢步速互斥條件]:** 若一匹馬已因「慢步速檔位紅利」(前置好位)獲得情境加分,不可同時因「慢步速但末段追近 = 隱藏強馬」再獲額外加分。兩者描述不同受惠機制(前者利前置,後者利後追),同一匹馬只能觸發其中一個。
- **[SIP-C14-1] C 欄出馬匹數分級懲罰 (Rail-Out Field Size Scaling):** 當跑道欄位為「C 欄 (Rail Out ≥6m)」或任何外移欄時,外檔 (≥8 檔) 及後追馬的 EEM 懲罰按出馬匹數分級調整:

  | 出馬匹數 | 外檔/後追 EEM 懲罰係數 | 說明 |
  |:---|:---|:---|
  | ≤8 匹 | ×1.0 (維持原判) | 小場馬群短,外檔確實無路可走 |
  | 9-12 匹 | ×0.6 (懲罰減四成) | 中場馬群有一定縱深,後追馬可選擇路線 |
  | ≥13 匹 | ×0.4 (懲罰降至四成) | 大場馬群縱深足夠,後追馬有多條追擊路線 |

  **使用方法:** 計算 C 欄外檔/後追的原始 EEM 懲罰後,乘以上述係數。若調整後 EEM 從 `[高消耗]` 降至 `[中等消耗]`,`EEM與形勢` 維度判定同步由 ❌ 調至 ➖。

### Step 8: 段速真偽 (Sectional Illusion)
- Class Par 比對(→ `<class_par_reference>`)+ 段速基準對比(→ `<sectional_benchmarks>`)
- 慢步速 = 段速不可靠 | 快步速前領仍堅持 = 超強
- 衰退率:`(2×L200 - L400) / (L400 - L200)`,>15% = 體力問題,<5% = 有餘力
  > 公式與 `03e_class_standards.md` 一致:前 200m split = L400 - L200,後 200m split = L200,衰退率 = (後半段 - 前半段) / 前半段。
- 末200m全場前3 → 體能充足
- **[長途韌力權重提升 (Stamina Reliability Boost)]:** 喺 2400m 或以上賽事,若馬匹嘅「末 200m 全場前三」伴隨「距離已證明 (≥ 2200m 有好表現)」,其「段速與引擎」維度權重應提升至與核心維度相等。長途賽事中,「真正的長途氣量」與「末段前三的段速穩定性」係最高優先級。
- **⚠️ 保守修正原則:** 段速修正結論係「實際能力優於/弱於時間所示」,屬**定性方向判斷**,不等於「大幅升級」。特別係「三疊望空」同時出現於段速修正 (Step 8) 同 EEM (Step 7) 時,段速修正應保守處理 — 僅確認「能力不弱於所示」,避免同 EEM 維度雙重膨脹。

**[BAKED-急彎後追封頂] EEM 維度自動 ❌ 條件（原 02g_override_chain.md 急彎封頂規則）:**
- **急彎起步即入彎** (Rosehill 1200m / Moonee Valley 1200m / Caulfield 1400m) + **純後追馬** (Type B / Settled Runner) → EEM **自動 ❌**
  - **豁免:** 超班降班 ≥2 級；出馬 ≥13 匹 + 末段前 3（完全取消）；出馬 ≥13 匹（放寬至 ➖）
- **[BAKED-Rosehill 1200m 塞車] Rosehill 1200m** + 後追型 + 受困往績（近 5 仗 ≥2 次 Stewards 記錄 held up/checked） → EEM **自動 ❌** + **計 2 項風險標記**（從一般 1 項加倍）
  - **邏輯基礎:** Rosehill 1200m 起步即入彎,後方馬群極易喺彎位擠成一團,物理上幾乎唔容許缺乏前速嘅馬失機第二次。

### Step 8.2: 走位-段速複合分析 (Position-Sectional Composite) [SIP-AU-P2b]

從 Facts.md 提取走位消耗等級（Step 7 EEM 判定），同段速 Δ 尾段偏差值（Step 8）進行交叉分析：

| 走位消耗等級 | 段速 Δ 尾段 | 複合判讀 | 段速質量修正 |
|:---|:---|:---|:---|
| 高消耗 (3-wide+) | 末段前 3 | 「逆境段速」→ 可觸發 SYN-AU1 | ✅✅ |
| 高消耗 (3-wide+) | 末段中等 | 「消耗抵消」→ 實際能力優於字面 | 至少 ➖ |
| 低消耗 (1-wide) | 末段前 3 | 「舒服快跑」→ 段速打折 | ✅ 但降權 |
| 低消耗 (1-wide) | 末段差 | 「實力見底」→ 可觸發 CON-AU1 | ❌ |

**走位來源:** Racenet Sectionals + In-Run Position（Facts.md 已預注入）
**輸出:** 複合判讀結果傳入綜合合成的 `EEM與形勢` 半核心維度，作為 SYN-AU1/CON-AU1 觸發依據。

### Step 8.3: 賽事短評交叉驗證 (Stewards Commentary Cross-Validation) [SIP-AU-P3c]

Analyst 必須引用 Racenet Race Comments / Stewards Reports 進行交叉驗證：

1. **Engine Type 驗證:** 若 Stewards 連續描述「settled last / dropped out」但 Engine = Type A (前領) → 標記 `[引擎矛盾 ⚠️]`，回溯 Step 2 重新審視
2. **受阻模式識別:** 近 3 場含「held up / checked / steadied / bumped」→ 觸發寬恕加分考量（Step 6）
3. **走位消耗確認:** Comments 含「three deep / four deep / uncovered / wide throughout」→ 確認高消耗，強化 Step 8.2 判讀
4. **隱藏表現發掘:** Comments 含「closing late / strong finish / only beaten X lengths / not knocked about」→ 段速質量需重審

**數據來源:** `claw_racenet_scraper.py` Race Comments 欄位
**限制:** 若 Race Comments 缺失，此步驟標記 `[N/A — Comments 不可用]` 並跳過。

### Step 8.4: 完成時間偏差分析 (Finish Time Deviation) [SIP-AU-P2c]

比較馬匹完成時間與 Class Par（參照 `au_class_par_reference.json` 或 `03e_class_standards.md`）：

| 偏差 | 判讀 | 影響 |
|:---|:---|:---|
| 快於 Par ≥0.5s | ✅ 有餘力（需確認場地條件） | 狀態/段速維度加強 |
| 介乎 Par ±0.5s | ➖ 正常 | 無影響 |
| 慢於 Par ≥1.0s | ⚠️ 可能體力不足 | 需交叉驗證 EEM/場地 |

**場地修正:** 每升一級場地（Good→Soft→Heavy）約 +1.5-3.0s，必須扣除場地影響後再比較。
**趨勢分析:** 連續 3 場偏差收窄 = 上升趨勢 ✅，傳入 Step 1 狀態維度作為上升證據。
**限制:** 若缺乏準確完成時間數據，此步驟標記 `[N/A]` 並跳過。

### Step 9: 賽績交叉驗證 (Collateral Form)
- 正向:上仗贏馬隨後高班勝 → +1.5-2分。前五有 ≥3匹隨後入位 = High-Quality Form
- 反向:贏過的對手隨後慘敗 → -20-30%。深度連鎖追溯兩層
- 1馬位 ≈ 0.16-0.18s(短途) / 0.15-0.17s(中距離)
- **[久休馬賽績延伸追溯 (Long Spell Collateral Extension)]:** 若馬匹休息期 ≥ 14 週(久休),其最近一仗嘅賽績參考價值較低(時效衰減)。此時交叉驗證必須追溯對手**後續 3 仗**表現(而非標準的 2 層),以獲取更充分嘅數據支持。若 3 仗追溯中 ≥2 匹對手在同班或更高班次勝出/入前三 = 久休馬嘅早期賽績仍具高含金量。若 3 仗追溯中對手普遍走勢低迷 = 早期賽績含金量存疑,賽績線維度降至 ❌。

### Step 10: 步速瀑布與陣型 (Pace Cascade & Race Shape)

**速度地圖建構:**
- Compulsory Leader:近5仗領放 ≥3次 | Likely Leader:領放 2次+內檔(1-4)
- Presser:前三位置 ≥3次+有早段速度 | 首戴眼罩 → 可能前移
- Settled Runner:後半段 ≥4次 | 騎師為已知後上型
- 近5仗從未領放+無早段速度 = 絕非前領

**步速分級:**
≥3匹搶 → Genuine-to-Suicidal → 利後段 | 1匹無挑戰 → Crawl → 偷襲+40%
Suicidal(快>2s) 崩潰>85% | Genuine(快0.5-2s) | Moderate(接近Par) | Crawl(慢>1.5s) 偷襲>60%
崩潰點 800m-600m。距離差 >5身位 = Risk High

**[Engine-Pace Matching Matrix (引擎-步速適配矩陣)]:**
> [!IMPORTANT]
> Step 10 完成步速預測後,必須對每匹馬嘅引擎類型 (Step 2) 進行步速匹配判定。匹配結果直接傳入 Step 14.1 情境適配維度及 Step 14.2B 微調因素。

| 引擎類型 | 龜速 (Crawl) | 中等偏慢 | 中等 (Moderate) | 快 (Genuine) | 自殺式 (Suicidal) |
|:---|:---|:---|:---|:---|:---|
| **Type A (前領均速)** | ✅ 極度受惠 | ✅ 受惠 | ➖ 中性 | ⚠️ 體力風險 | ❌ 嚴重消耗 |
| **Type B (末段爆發)** | ❌ 嚴重受損 | ⚠️ 受損 | ➖ 中性 | ✅ 受惠 | ✅ 極度受惠 |
| **Type C (持續衝刺)** | ➖ 中性 | ✅ 受惠 | ✅ 受惠 | ➖ 中性 | ⚠️ 體力風險 |

**匹配結果傳導:**
- ✅ 極度受惠/受惠 → 情境適配維度加分信號
- ❌ 嚴重受損/消耗 → 情境適配維度扣分信號 + 微調因素偏差逆轉觸發

**賽事形態:**
Bunched(慢步速→密集→後上受困×1.5→前領偷襲)| Strung-out(快步速→拉散→後上找出路但需更強追勁)
→ 預判形態 + 標注對每匹馬影響

**[直線衝刺專用] 直線步速模型覆寫 (Straight Sprint Pace Override):**
> **[條件載入]** 以下直線步速模型僅在 `[RACE_TYPE: STRAIGHT_SPRINT]` 時適用。完整邏輯見 `resources/02b_straight_sprint_engine.md`。
當 Step 0.1 = `[STRAIGHT SPRINT]` 時,以下邏輯**取代**標準步速瀑布:無搶位動態、前領崩潰率極高 (60-70%)、分組競速 (Split-Field Racing)、速度地圖替換為推進組/跟進組/後追組。

**[SIP-C14-6] 步速互燒警報 (Pace Meltdown Alert):**
當跑道欄位為 C 欄/外移欄 **且** 出馬 ≥12 匹 時,強制執行以下步速額外評估:
- **偵測條件:** 場內有 ≥3 匹被識別為 `Compulsory Leader` / `Likely Leader` / `Presser`(即前置速度引擎)。
- **觸發效果:** 步速分級自動上調一級(如 `Moderate` → `Genuine`;`Genuine` → `Genuine-to-Suicidal`)。
- **下游影響:** 所有前領/跟前馬的 `EEM與形勢` 維度判斷必須考慮「被逼消耗」——即使該馬本身想控速,周圍 ≥2 匹競速者迫使步速加快,EEM 自動從 ➖ 調至 ❌ 或從 ✅ 調至 ➖。
- **豁免:** 若前領馬為 `DOMINANCE_GAP = 明確 (Clear)` 的唯一主導領放者(無人挑戰其權威),此警報不觸發(該馬可自控步速)。

**[SIP-FL06] 濕地專家前領崩潰懲罰軟化 (Wet Specialist Front-Runner Override):**
- **觸發條件:** 場地為 Heavy 7+ **且**馬匹被識別為前領型 (Type A / Compulsory Leader / Likely Leader)。
- **標準處理(無此 SIP 時):** Heavy 場前領型馬自動被標記為「Heavy 場前領崩潰風險」,步速形勢配合從升級因素降為降級因素,EEM 維度可能從 ➖ 降至 ❌。
- **SIP-FL06 軟化規則:** 若前領馬同時擁有 **濕地(Soft/Heavy)勝出紀錄 ≥ 1 場**,上述「Heavy 場前領崩潰」懲罰**減半**:
  - EEM 維度不因「Heavy 前領崩潰」單獨降至 ❌,最差維持 ➖
  - 「步速形勢逆轉」微調降級不觸發(濕地專家已證明有能力在爛地維持前速)
  - 但風險標記 `[Heavy 前領消耗 ⚠️]` 仍保留(警示而非懲罰)
- **進階觸發:** 若前領馬濕地紀錄為 **≥ 3 場且 WR ≥ 33%**(即 Soft/Heavy 場專家),「Heavy 場前領崩潰」懲罰**完全取消**。此類馬已充分證明濕地前領能力。
- **安全閥:** 若前領馬為全場最重磅(≥ 60kg)**且**步速預測為 Genuine-to-Suicidal,SIP-FL06 軟化不生效(重磅 + 快步速 + 重地 = 三重物理極限,濕地經驗無法覆蓋)。
- **邏輯基礎:** 2026-03-28 Flemington R10 覆盤中,Taken(1600m 三戰全勝 + 濕地 2 勝)被降至 B+ 因為「18 號最外死檔 + 前領型 + Heavy 8 崩潰陷阱」。但 Taken 跑第二。引擎對濕地專家嘅前領崩潰預設過於嚴格——有濕地勝績嘅前領馬已經證明可以喺爛地維持步速。

**[新增] 領放主導階梯 (Leader Dominance Hierarchy):**
恰好 2 匹潛在領放馬時,**不可**自動默認為搶位快步速。必須執行以下主導評估:
- **因素 A — 路程專家 (Route Specialist):** 該馬是否在同場同程 ≥2 次領放勝出/上名?
- **因素 B — 近態強弱 (Current Form):** 近績是否在贏馬/穩定上名 vs 對方近績差/場地轉換/升班/首出?
- **因素 C — 騎師權威 (Jockey Authority):** 騎師是否為當季 Top-5 且慣性控制步速 vs 對方騎師為被動型/見習?
- **裁決:** 若一方在 ≥2/3 因素中明確佔優 → `DOMINANCE_GAP = 明確 (Clear)` → 預測 **Soft Lead / Crawl**(弱方高機率退讓)
- **裁決:** 若雙方勢均力敵或各佔一項 → `DOMINANCE_GAP = 不明確 (Unclear)` → 維持 **Contested / Genuine** 預測

**[SIP-R14-4] Good 場地 Group 級別前領偏差下調 (Good Track Group-Level Pace Bias Suppression):**
- **觸發條件:** 場地掛牌為 **Good 3 或 Good 4**,**且**賽事級別為 **Group 1 / Group 2 / Group 3 / Listed**。
- **調整效果:** 所有「Good 4 利前領/內欄偏差加成」在 Group/Listed 級別賽事中**下調 50%**。
  - 即 Good 4 的「前領步速配合紅利」由「極佳/盡享偏差」降級至「佳/受惠偏差」
  - 前領馬在 Group 賽事中的「步速形勢配合」微調升級因素,需附加條件:前領馬必須具備 ✅「段速與引擎」核心維度(證明其速度硬實力足以在高級別步速下堅持)
- **核心邏輯:** 2026-03-14 覆盤中,Good 4 場地下多匹被評為 A 級的前領馬在 Group 級別均敗陣(R7 Shangri La Boy、R8 Arctic Glamour 均未入前三)。Group 級別賽事步速顯著更快,前領馬直路受壓程度遠高於一般 Benchmark 讓賽。Good 4 的偏差紅利在高級別賽事中被「更快的實際步速」中和。
- **豁免:** 若前領馬為**唯一領放馬** (Compulsory Leader) 且 `DOMINANCE_GAP = 明確`(即無競爭者挑戰),此下調**減半**(即下調 25% 而非 50%),因為獨領放馬的戰術控制權依然極大。
- **不適用場景:** Good 1-2 (Firm) 場地不受此規則影響。Soft/Heavy 場地亦不適用(有獨立規則處理)。

**[SIP-SL02] Good 場地前領馬生存率重新校準 (Good Track Leader Survival Recalibration):**
- **觸發條件:** 場地掛牌為 **Good 3 或 Good 4**,**且**距離 ≤ **1400m**,**且**馬匹為前領型 (Compulsory Leader / Likely Leader / Presser — 近 5 仗 ≥2 次領放或跟前)。
- **校準效果 — EEM 消耗減免:**
  - Good 場地前領馬嘅 EEM 步速消耗係數**下調 15%**。即原本計算為「中等消耗」嘅前領馬,喺 Good 場地下可降格為「輕微消耗」。
  - 前領馬 EEM 維度判定**禁止**單純因為「前領型=高消耗」而自動降至 ❌ Weak。Good 場地摩擦力低,前領馬嘅體力損耗遠少於 Soft/Heavy 場地,引擎必須反映呢個物理現實。
  - **步速形勢配合**微調升級因素對前領馬嘅效力**上調 50%**:若前領馬為獨領放或僅有 1 匹競爭者,配合 Good 場地 → EEM 維度自動 ✅ Strong(而非 ➖)。
- **額外加成 — 輕磅前領組合:**
  - 若前領馬同時負磅 ≤ 55kg → 在 Good 場地嘅 EEM 消耗進一步下調至原本嘅 **60%**。輕磅 + Good 地 + 前領 = 三重體力保護。
  - 若前領馬同時由見習騎師策騎(減磅 ≥ 2kg)→ 額外記錄為 `[Good 地前領輕磅優勢]` 微調升級候選。
- **安全閥(不適用場景):**
  - 若步速預測為 **Genuine-to-Suicidal** 且場內有 ≥3 匹前置引擎(步速互燒) → SIP-SL02 嘅消耗減免**不生效**(快步速+多馬搶位 = Good 地紅利被抵銷)。
  - 若場地為 Good **但**使用 C 欄/外移欄 + ≥14 匹 → 消耗減免**減半**(大場馬群壓縮削弱前領馬位置控制權)。
- **邏輯基礎:** 2026-04-06 Sandown Lakeside 覆盤中,Good 4 場地下前領型馬匹勝出/上名率超過 60%:R1 Blind Raise (前列→冠軍)、R2 Jewel Of Heaven (全程領放→季軍)、R3 Wings Of Carmen (前領通殺→冠軍 $41)、R5 Nation State (前列→冠軍 $9)。引擎嘅步速模型假設「快步速=前領馬必然崩潰」,但 Good 場地嘅低摩擦力令前領馬嘅體力損耗大幅降低,呢個物理因素之前被引擎忽略。

**[新增] 同門馬房戰術部署 (Same-Stable Deployment):**
當同一練馬師有 2+ 匹馬在同一場賽事中,評估是否存在「犧牲領放」動態(一匹王牌領放為同門後追馬設定步速)。若同門領放馬之間不會互爬,步速應從 Genuine 降低至 Soft Lead / Moderate。此效應會放大前領馬(包含同門跟前馬)的優勢。

**[新增] 小場覆寫協議 (Small Field Override Protocol):**
當賽前出現大規模退出 (Scratchings) 導致參賽馬少於 **6 匹**時,必須自動執行以下調整:
1. **級數降權:** 「級數與負重」維度權重自動降一級(✅→➤),因為小場競賽中級數壓制 (Class Pressure) 大幅削弱。
2. **位置升權:** 檔位/守位嘅重要性顯著上升。戰術走位往往能蓋過 5-8 分的評分差距。
3. **步速重建:** 若核心領放馬已退出 → **必須重新執行 Step 10 步速瀑布**,重新評估均速型馬 (Grinder) 在慢節奏下嘅生存率。
4. **小場與位置:** 為全場最低級數的馬匹重新審視:若其走位提升(因減少競爭),其實力可能超水平發揮。

