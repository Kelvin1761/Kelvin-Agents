# 模型評估合約（AU / HKJC Wong Choi）

## 市場尺 m2 = AU／HKJC 模型 KEEP 條件（2026-11-25，Kelvin「ok 用市場尺做 KEEP 條件」）

> **由 2026-11-25 起登記嘅 AU／HKJC 模型候選**（評分、排名、權重、leaf、校準）用呢條判 KEEP。之前判咗嘅唔追溯；
> 跑緊嘅 forward 照用登記時嘅尺。計法同下面 m1 一樣（`market_ruler.py` VERSION `m2`）。

### KEEP 要三樣都過
1. **市場尺 B PASS**（下面 m1「判法 B」）：
   - AU：`--price sp` PASS，**而且** `--price bsp` 獨贏 ΔΔ 點估計 ≥ 0（BSP 覆蓋少啲，唔要求 CI，但唔准方向相反）。
   - HKJC：`--platform hkjc --window dev` PASS；過咗先開 `--window holdout` 確認（獨贏 ΔΔ 點估計 ≥ 0）。holdout 唔准用嚟揀候選或者調參。
2. **排名唔准顯著變差**：排名尺（AU log-loss v2／HKJC 回放 v5.2）嘅 Δlog-loss（候選 − baseline，正 = 差咗）95% CI **下界 ≤ 0**
   （即係唔准「顯著差咗」；排名改善唔係必要），
   而且排名尺嘅護欄（AU：場內 AUC Δ 下界 > −0.0015、Gold／Good 點估計 > −1pp；HKJC：v5.2 護欄 2 同 4）要過。
3. 照舊：leakage audit、§6 功效預估、多樣嘢一齊郁要 ablation、可退回 baseline。

### 唔使過市場尺嘅（照舊用排名尺）
- §7 正確性修正、數據管線修正、純顯示改動（排名唔變）。
- Kelvin 明確話「分析用途上線」嘅改動：可以單憑排名尺 KEEP，但實驗記錄要寫明「分析改善、市場尺 FAIL」，同埋唔准用嚟支持任何落注規則。

### 點解（Kelvin 2026-11-25 決定；代價已講明）
現行 AU／HKJC 模型都冇市場以外資訊（EXP-20261124-90／-92、EXP-20261125-01）；KEEP 咗咁多排名改善 ROI 冇郁。
改咗之後研究只會留「市場唔知嘅資訊」。**代價**：大部分純排名改善會 REJECT，dashboard 排名會難啲再進步（除非 Kelvin 逐個用「分析用途上線」放行）。

## 市場尺 m1（2026-11-24，Kelvin「做第 1 項：對市場嘅尺」；EXP-20261124-90）

> 判決器：`.agents/skills/shared_racing/scripts/market_ruler.py --platform au BASE.json [CAND.json]`。
> **唔取代**排名尺（AU log-loss v2、HKJC 回放 v5）—— 兩把尺答唔同嘅問題，兩個判決一齊報。

### 點解要
排名尺問「排名準唔準」；市場尺問「準得過收市價嗎」。過去三個月 AU 排名尺 KEEP 咗好多改動，但係
位注 2,379 注 −22.3%（EXP-20261124-23）、BSP 規則全部 CI 下界 < 0、模型對 BSP 冇額外資訊（EXP-20261124-60）。
即係排名改善嘅資訊，市場早已經有。冇把尺量呢樣嘢，研究就會一直優化一個唔賺錢嘅目標。

### 方法（m1）
- 市場機率 p_m = (1/收市價) 場內正規化。AU 有兩個價（`--price`）：`sp` = dump 每匹嘅賽果 SP（預設，任何 dump 都有）；
  `bsp` = Betfair BSP（`au_bsp.py`，記錄器＋公開 CSV；EXP-20261124-92）。BSP 較 sharp（每場獨贏 nll 低 0.018，約 8 SE），
  配唔齊 BSP 嘅場剔走並報配對數。`early` = 賽日 10:30 前早更 Sportsbet 價（落注嗰刻；`au_early_prices.py`，EXP-20261125-05）。
  z = 場內標準化 ability。
- **獨贏（主）**：條件 logit 頭馬 s = α·log p_m + β·z，對淨市場 s = α·log p_m。
- **入頭三（輔）**：logit P = c + α·logit q_m + β·z，q_m = Harville 由 p_m 推。
- walk-forward：每 7 個賽日重 fit，只用之前賽日；頭 20 個賽日唔計分；AU 只用 2026-08-05 起乾淨語料。
- 每場 Δll = ll(市場＋模型) − ll(淨市場)，正 = 模型有市場冇嘅資訊。賽日 bootstrap 2,000（ratio of sums）。
- 收市價只係**評估基準**：唔入模型、唔揀注。所以唔觸犯「賠率唔准做隱藏 proxy」。

### 判法
- **A. 單一模型（有冇市場以外資訊）**：嗰個市場嘅 Δll 95% CI 下界 > 0。
- **B. 候選對 baseline（市場尺 PASS）**：獨贏 ΔΔ（候選 − baseline）CI 下界 > 0、入頭三 ΔΔ 點估計 ≥ 0、
  三個時間塊至少兩個 ΔΔ > 0，而且計分賽日 ≥ 30、三個時間塊都有場。
- 配對只用兩邊 key（日期、場次）一樣**兼**馬名、名次、價都一樣嘅場；唔一樣嘅數出嚟（`mismatched_races`），唔配。
- 入頭三唔計 ≤ 3 匹嘅場（個個入三甲，冇資訊）。fit 未收斂會印警號。
- ability 一定要係賽前凍結嘅分（dump 本身係 point-in-time）；fit 類候選照 v3 規矩交 walk-forward 預測，
  唔准用含 SP 或者賽果嘅 fit 出嚟嘅分（Sol 覆核 2026-11-24）。

### 用途（m1 起生效；KEEP 部分 2026-11-25 起由上面 m2 取代）
1. **AU 模型候選一律照報市場尺**（A 同 B，`sp` 同 `bsp` 兩個價都報），寫入實驗記錄。（m1：KEEP 由排名尺判 —— 已由 m2 取代。）
   排名尺 KEEP 但市場尺 B FAIL = 「分析改善」，唔可以講「投注改善」。
2. **任何真錢落注規則**（新開或者由紙上轉真錢）：用嗰個規則嘅模型版本，喺佢落注嘅市場要過 A
   （喺 Betfair 落就用 `bsp`；喺 Sportsbet 落就用 `sp`，而且 `bsp` 都要過 —— 打唔贏最 sharp 嘅價，就係靠價差唔係靠模型）；
   過咗 A 都只係必要條件，仲要過嗰個規則自己預先登記嘅 ROI forward（扣抽水）。
3. ~~用市場尺 PASS 做 KEEP 條件 = 留畀 Kelvin~~ → Kelvin 2026-11-25 決定做，見上面「市場尺 m2」。

### 驗證（EXP-20261124-90）
- 正對照（頭馬 ability 加 0.1 SD）：PASS，ΔΔ +0.0076 [+0.0037, +0.0115]；負對照（場內洗牌）：FAIL。
- 現行 live（`au-debut-trainer-20261124/BASE.json`）：獨贏 Δll −0.00043 [−0.00159, +0.00078]，
  入頭三 −0.00044 [−0.00126, +0.00042] → 冇市場以外資訊，同 EXP-20261124-60（BSP）一致。
- 舊 KEEP 候選 F1（近績 SD 下限）：獨贏 ΔΔ −0.00002 [−0.00019, +0.00015] → FAIL；SPG 亦 FAIL。
- 配對 ΔΔ CI 半寬約 0.0002–0.0004，即係細過呢個嘅市場資訊增量量唔到。

### 未做
- （已做）HKJC：EXP-20261125-01 接駁（`--platform hkjc BASE.jsonl [CAND.jsonl]`，賽果庫最終獨贏賠率按 (日期, 場次, 名次) 配）。
  現行 live 回放（`base_live_20261122.jsonl`，5,679 場）：獨贏 Δll −0.00029 [−0.00066, +0.00005] → 冇市場以外資訊。
  HKJC 候選照 AU 一樣：一律照報市場尺（A 同 B）。
- （已做）BSP 版：記錄器 BSP 11-06 → 11-23 全 null，EXP-20261124-91 修好兼補返；EXP-20261124-92 接駁做 `--price bsp`。
  現行 live 喺 BSP：獨贏 Δll −0.00037 [−0.00133, +0.00058] → 都係冇市場以外資訊。
- NBA／網球：二元盤，形狀唔同；佢哋已經有去水 log-loss／CLV 研究（EXP-20261124-70／-71）。

## HKJC 歷史回放尺 v5（2026-11-22，Kelvin 同意；取代 v4 做新候選判決器）

> 判決器：`hkjc_reflector/scripts/hkjc_replay_compare_v5.py`。**同 v4 只差一樣**：校準加馬匹數。窗、判法 1–5、護欄、null、Holm 全部照 v4（下面）。
> 之前用 v4 判咗嘅唔追溯改判。實驗：EXP-20261122-24。

- **改咗咩**：v4 p = σ(a + α·(raw − 場均))；v5 p = σ(a + α·(raw − 場均) + γ·logit(3/N))，N = 有名次嘅出賽馬數，(a, α, γ) 由訓練段 fit。
- **點解**：一場 N 匹只有 3 個位（6 匹場基準 50%、14 匹場 21%）。v4 唔知 N → 細場系統性估低、大場估高，log-loss 同殘差診斷都帶住場次大細雜訊；
  EXP-20261122-22／23「殘差顯著但入分唔過」部分係呢個。
- **驗證**：
  - 校準：baseline（base_venue_age）絕對 log-loss dev 0.50703 → 0.50150、holdout 0.49403 → 0.49024；fit 出 γ ≈ 1.17（理論 ≈1）。
  - 一致性：7 個舊候選（D1、D2、V2、A2、N1、N3、C0）v4／v5 dev 判決**全部一樣**，Δlog-loss 最多差 0.00002 —— 新尺唔係放水亦唔係收緊，只係校準準啲。
- **殘差診斷**：之後用殘差表揀方向，要用 v5 嘅校準 p（計埋馬匹數），唔好再用冇 N 嘅版本估幅度。

### v5.2 頭二護欄（2026-11-23，Kelvin「先整頭二尺」；EXP-20261123-03）
- **加咗咩**：護欄 4 —— **爭勝馬頭二 Plackett–Luce 損失**唔准顯著變差（Δ 95% CI 下界 > 0 → REJECT）。每次判決都印出嚟。
  爭勝馬 = baseline 同候選各自頭四名嘅聯集；喺呢班馬入面量「邊兩匹跑頭二」：P(第一) = softmax(β·raw)，P(第二 | 第一已走) 同一個 softmax；
  損失 = −log P(第一) − log P(第二 | 第一)；β baseline 同候選各自由訓練段 fit（同 log-loss 一樣 walk-forward）。
- **點解**：Kelvin 最睇重頭二。舊「頭二選有中」／「頭二入面入頭三匹數」冇功效：剷走 25% 或者 50% 騎練訊號、加同幅度雜訊，z 全部 < 2（量唔到）。
  爭勝馬頭二 PL：剷騎練 25% z +3.4、50% z +5.1、剷檔位 50% z +2.2、同幅度雜訊三次 z +2.4～+3.3（全部捉到）；A/A = 0。
- **一致性**：舊 PASS（D1、V2、A2、J3）v5.2 全部照 PASS；V2 −0.0013、A2 −0.0016、J3 −0.0065（頭二排得準啲，CI 唔過零），D1 打和。
- **每次照印「頭二入面入頭三總匹數差」同「首選贏差」（dev／holdout，連 CI）** —— Kelvin 2026-11-23：現階段頭二入位最重要；
  PL 護欄只擋「顯著變差」，唔證明改善；上唔上線 Kelvin 睇埋呢兩個實際數字決定（例：J3 dev 頭二入頭三 −18 匹 [−51,+16]、首選贏 −5 → 唔上）。
- 唔追溯舊判決。

### v5.1 護欄（2026-11-22，Kelvin 同意；EXP-20261122-33）
- **改咗咩**：判法 2（護欄）由「Gold、Good 各自 95% CI 下界 > −1.0pp」改為
  **「場內 AUC Δ 95% CI 下界 > −0.0015，而且 Gold、Good 點估計 > −1.0pp」**。判法 1（log-loss）、3（null）、窗、Holm 唔變。
- **點解**（dev 窗量度，`patches/hkjc_guard_v51/`）：
  - 靈敏度：剷走成個「狀態與穩定性」維度，Good +0.56、Gold 下界 −1.21（擦邊）；剷一半捉唔到。Gold／Good 只睇頭幾匹，CI 闊到分唔出「剷走核心維度」同「冇嘢發生」。
  - 同幅度雜訊（J1 大小嘅 raw Δ 場內洗牌）：Good 護欄只捉到 14/30；AUC 下界 ≤ −0.0015 捉到 28/30。
  - 真 J1 Δ（套落現 base）：AUC +0.066×10⁻² [−0.071, +0.202]×10⁻² —— 排名冇變差，但舊護欄喺 holdout 判死（Good 下界 −1.28）。
  - 剷走 25% 騎練訊號 AUC 下界 −0.0024、剷走 50% 檔位走位 −0.0029 → 新護欄捉到。
  - A/A（base 對自己）：REJECT ✅。
- **唔追溯**：之前用舊護欄判嘅（包括 J1）唔改判；新家族要重新 fit、重新跑 dev／holdout。
- 判決器：`hkjc_replay_compare_v5.py`（印 v5.1 判決，同時印舊護欄做對照）。

## HKJC 歷史回放尺（v4，2026-11-15，Kelvin 決定）

> 適用：**HKJC 候選喺歷史回放語料**（6,047 場，`docs/plans/2026-11-13-hkjc-historic-engine-replay.md`）判。live 389 場語料
> 係舊權重調參場次（EXP-20261113-05、EXP-20261114-03），唔再做主判決語料。v3（下面）保留畀 AU 同舊記錄；之前判咗嘅唔追溯改判。
> 判決器：`hkjc_reflector/scripts/hkjc_replay_compare_v4.py`。

### 點解換
EXP-20261114-05／-08／-11、EXP-20261115-01：好多訊號喺模型之上真（似然度、跨窗穩定），但 Gold／Good 只郁 ±0.3pp；
「點估計唔准負」喺細幅真改善下面大約一半機會判死（Gold／Good 只睇頭幾個選擇，係粗指標）。Kelvin 2026-11-15 揀：主指標改機率 log-loss。

### 窗（寫死）
dev 2020/21–2023/24｜holdout 2024/25–2025/26｜terminal 2026/27（2019/20 係 burn-in）。holdout 每個候選家族只睇一次，記入
`docs/experiments/holdout-ledger-hkjc-replay.md`；同一家族 Holm。

### 判法
1. **主指標**：入頭三 log-loss（逐匹）。機率 p = σ(a + α·(raw − 場均))；(a, α) baseline 同候選**各自**由訓練段 fit
   （dev 窗逐季 walk-forward；holdout／terminal 用全 dev）。Δlog-loss 95% CI 上界 < 0（按**賽日** bootstrap 2,000）。
2. **護欄**：Gold、Good 各自 95% CI 下界 > −1.0pp（唔可以明顯變差）。
3. **null**：Δlog-loss 要好過 95% 場內洗牌 null（候選對 baseline 嘅 raw Δ 喺場內隨機排列，同幅度、冇資訊）。
4. 另報場內 AUC Δ、capture@5、頭二選有中（唔係閘）。
5. fit 類候選一定要交 walk-forward 預測（同 v3）；walk-forward 檔冇訓練季時，候選校準可以用全季版本（只影響 a、α 兩個純量），要喺記錄寫明。

### 驗證把尺
- A/A（候選 = baseline）：REJECT ✅（2026-11-15）。
- 第一次應用：場地類型適性（EXP-20261115-02）Δlog-loss −0.00020 [−0.00063,+0.00021] → REJECT —— 新尺唔係「放水」：細到 CI 跨零嘅照樣唔過。

### 其他照舊
leakage audit、§6 功效前置、§7 正確性修正、多重比較、Kelvin 決定上線嘅改動要登記 forward 退回監察。

## AU log-loss 尺（2026-11-21，Kelvin 決定）

> 適用：**2026-11-21 之後新嘅 AU 候選**。判決器：`au_wong_choi_auto/scripts/au_logloss_ruler.py`。
> 跑緊嘅 forward（登記喺 11-21 之前，同 EXP-20261121-31／-32 以前登記嗰批）照用登記時嘅尺；之前判咗嘅唔追溯改判。
> v3（下面，Gold／Good＋ranking metric）照計照報，做第二意見。

### 點解換
同 HKJC v4 同一個原因：Gold／Good 只睇頭幾個選擇，細而真嘅改善大約一半機會判死。EXP-20261121-35 同一批測試：
人工真改善 v3 2–14/30、log-loss 20/20；純噪音誤判 log-loss 0/40；13 個舊候選冇一個翻案。

### 點解唔係歷史回放
AU 賽前輸入重砌唔到（往績頁封頂 10 仗兼賽後抓、騎練率單一快照、官方評分只回溯一星期）。用 2026-08-05 起乾淨
point-in-time 語料；每日 +60–80 場，語料自己變長。

### 判法（v2，2026-11-23，EXP-20261123-01；`evaluate()` 預設）
1. **主指標**：入頭三 log-loss（逐匹）。p = σ(a + α·(raw − 場均) + γ·logit(3/N))（N = 場內匹數；標籤係入頭三，
   所以係 3/N，唔係派位數）；(a, α, γ) baseline 同候選**各自** walk-forward fit（每 7 個賽日重 fit，只用之前賽日；
   頭 20 個賽日只訓練唔計分）。Δlog-loss 95% CI 上界 < 0（賽日 bootstrap 2,000）。
2. **護欄**：場內 AUC Δ 95% CI 下界 > −0.0015，**而且** Gold、Good 點估計 > −1.0pp。
3. **null**：好過 95% 場內洗牌 null（候選對 baseline 嘅 raw Δ 喺場內隨機排列）。
4. 另報 Gold、Good（連 CI 下界）、場內 AUC、capture@5、頭二選有中、同 v3 判決（唔係閘）。

**點解換（v1 → v2）**：同 HKJC EXP-20261122-33／-24 同一個問題，用 AU 數據重新量（門檻唔係照抄）：
- 舊 Gold／Good CI 護欄對「同幅度、冇資訊」嘅改動只捉到 8/30（F1 幅度洗牌）；場內 AUC 下界 ≤ −0.0015 捉到 29/30，
  真 F1（AUC 下界 −0.0011）唔會誤殺。剷走維度 18 個設定：舊護欄捉 7 個、AUC 捉 11 個。
- 校準唔計馬匹數：baseline 絕對 log-loss 0.5693 → 0.5533（AU 馬匹數 5–20，變化大過 HKJC）；舊判決 Δ 幾乎唔變。

**v1（2026-11-21）**：校準冇 γ；護欄 = Gold、Good 各自 95% CI 下界 > −1.0pp。`evaluate(..., version="v1")` 重現；
v1 判咗嘅唔追溯改判；11-23 之前登記嘅 forward（PR1 shadow、馬齡／up-nil）照用 v1。
`calibrations()`／`_nll()` 預設仲係 v1，因為 live 嘅練馬師剩餘表現表（`au_trainer_residual_table.py`）用緊 (a, α)。

### 其他
- fit 類候選照舊要交 walk-forward 預測（v3 規矩）；leakage audit、§6 功效前置、§7 正確性修正、Holm 照舊。
- **PASS ≠ 改善好多**：0.25% 馬加 0.3 分都過到（EXP-20261121-35）。上線仍然要睇幅度、護欄同 Kelvin 決定，並登記 forward 退回監察。
- （v1 時代）log-loss 好咗但 Gold／Good 踩護欄（例：EXP-20261111 F1，Δ −0.00107、Good 下界 −1.00）= REJECT。
  v2 下 F1 喺舊 dump 會 PASS —— 舊判決唔追溯；要翻案就喺現行 live 上重建、當新候選重新跑（Kelvin 2026-11-23 要求全部重跑）。
- **Kelvin 取捨（2026-11-22）**：「如果明顯改善 Good 同埋 1 hit 都可以諗」—— Gold 跌可以考慮接受，**前提係 Good 同頭二選有中
  兩個嘅 95% CI 下界都 > 0**。呢個唔係自動 PASS 路線：符合嘅候選要交 Kelvin 決定，而且要用新賽事 forward 確認
  （睇完結果先換判法 = 事後選擇）。第一個用呢條嘅係 EXP-20261122-05 PR1 shadow。

## Stage 4 判決順序（v3，2026-10-10）—— 全紀錄判決

> v2（下面）保留做歷史；**2026-10-10 之後嘅新候選一律用 v3**。之前用 v2 判咗嘅記錄
> 唔追溯改判決。判決器：`model_evaluation_decision.evaluate_full_record`。

### 點解換

v2 用最後 15% 日期做 terminal（HKJC 約 50–60 場）：85% 證據唔參與判決、terminal
被重複開過好多次、時間尾段又啱啱係新季（條件切分）。實測：HKJC 騎練季節加權候選喺
v2 terminal「實際前三平均名次改善，CI 唔跨零」，喺 v3 全紀錄變成 Δ −0.0000
CI [−0.0085, +0.0078] —— 嗰個 terminal「改善」係 50 場嘅噪音。

### 兩類候選，兩種模式（`mode` 必須聲明）

| mode | 適用 | 點解冇偏差 |
|---|---|---|
| `fixed_rule` | 冇由數據學嘢：正確性修正、預先登記嘅固定值、還原寫明嘅設計 | 冇調參 → 冇 in-sample 樂觀；**全部紀錄都用** |
| `walk_forward_oos` | 由數據 fit 數值（權重、門檻、gain、幅度） | 製造者要交 walk-forward 預測：每個賽日只用之前嘅賽日 fit。全部歷史每場都係 out-of-sample |

**fit 咗但冇 walk-forward 預測 → 直接 REJECT**（`fitted_candidate_needs_walk_forward_predictions`）。

### 判決次序

1. 安全：同場數、leakage audit PASS、ranking metric 已登記。
2. **Primary**（Gold、Good 位置）：全紀錄點估計 < 0，或者 K=6 個連續時間塊入面
   少過 ⌈K×2/3⌉ 塊 ≥ 0 → `REJECT / primary_regression`。
3. **PRIMARY_WIN**：任一 primary 嘅 95% CI 下界 > 0（同埋第 2 步已過）。
4. Ranking metric 任何一個 CI 上界 < 0 → `REJECT / ranking_metric_harm`。
5. **RANKING_WIN**：≥ 2 個 ranking metric 點估計 > 0 而且時間塊達標，其中 ≥ 1 個
   CI 下界 > 0。
6. 否則 `REJECT / ranking_evidence_too_weak`。

**推論**：bootstrap 以**賽日**做單位（同日賽事共用場地、偏差、同一次排程 run，
逐場 bootstrap 會高估信心），2000 次。

### Ranking metric 登記（HKJC）

`hkjc_eval_harness.RANKING_METRICS`：top3 capture@5、NDCG@5、competitive recall@5、頭三平均模型名次，
同 **`top2_any_hit`（頭二選最少一隻上名，2026-11-12 Kelvin 加）**。

- 點解加：Kelvin 嘅落注用法睇頭二選；「頭二選 0 中變 1 中」係實際改善，但 Gold（前三全部入頭四）同 Good（頭二選兩隻都上名）
  都唔會記錄到。佢只喺 Gold、Good 都冇跌（第 2 步過咗）先有作用，同其他 ranking metric 一樣要時間塊達標兼 CI 支持。
- 性質（2026-11-12 量）：baseline 449 場 71.5%；EXP-20261112 系列候選郁 0–17 場、CI 半闊約 1–2pp。
- 驗證把尺：A/A REJECT；EXP-20261112-02／-04／-05／-08／-09／-12 九個 arm 重判，判決同原本一樣（冇一個因為加咗佢而變）。
- 加多一個 ranking metric 會令 RANKING_WIN 稍為易過（多重比較）；**之前判咗嘅候選唔追溯改判**。
- AU 冇加（AU harness 自己嘅 ranking metric 列表唔郁）。→ **2026-11-21 改：AU 都加咗，見下面。**

### Ranking metric 登記（AU，2026-11-21 Kelvin 加，EXP-20261121-32）

唯一一份：`au_eval.RANKING_METRICS`（AU 所有判決器 import 佢，唔准自己抄一串）：
top3 capture@5、NDCG@5、top5 pairwise AUC，加 **`top2_any_hit`（頭二選最少一隻上名）**、
**`top2_place_rate`（頭二選上名數 ÷ 2）**、**`top3_place_rate`（頭三選上名數 ÷ 3）**。

- 點解加：Kelvin 2026-11-21「Gold、Good 以外，好似 HKJC 咁，頭 1、2 排序好咗、0 中改善、頭 5／頭 3 位置好咗都應該考慮」。
  頭 5 位置 = capture@5（已有）；頭 3 = `top3_place_rate`；頭 1、2 = `top2_place_rate`；0 中 = `top2_any_hit`。
- 判決次序唔變：Gold、Good 有一項點估計 < 0 照樣 `primary_regression`；新指標只喺 Gold／Good 冇跌先有份判，
  任何一個 CI 上界 < 0 = `ranking_metric_harm`。
- 驗證把尺（3,736 場，08-05 起）：A/A REJECT ✅；純噪音候選（σ 0.5／2.0 各 40 個）誤判 WIN 0/80（舊尺 0/80）；
  人工真改善敏感度同舊尺相若（例：排第 3–5 嘅上名馬 0.5% 加 1 分，14/30 vs 13/30）；
  舊 fixed_rule 候選 13 個重判：冇一個變 WIN；3 個（EXP-20261113-21 FINAL／WA／WB）由 `ranking_evidence_too_weak`
  改判 `ranking_metric_harm`（頭三上名率 −0.17 至 −0.21pp，CI 唔跨零）—— 結論一樣係 REJECT。
- **2026-11-21 之前已預先登記嘅 forward 測試凍結用舊尺**（`au_eval.RANKING_METRICS_PRE_20261121`：檔位、初出、H2、
  L600 近期、Lpos、海外代理）—— 中途換尺 = 改咗佢哋登記咗嘅判決規則。之前判咗嘅候選唔追溯改判。

### 其他規則

- **多重比較**：同一候選家族（同一假設嘅唔同 arm）要登記，用 `holm_adjust` 調整 p 值；
  只有調整後仍然顯著先可以報 WIN。
- **Forward holdout**：v3 判 WIN 之後，最終確認用之後未睇過嘅賽日（HKJC 由 2026-10-11 起），
  一個候選家族只開一次。
- **§6 功效前置**、**§7 正確性修正**、**leakage audit** 照舊適用。
- **語料**：HKJC 用 `hkjc_eval_harness.py`（真 production 計分路徑 + PIT priors，
  自動剔走欄位死咗嘅賽日）；AU 用自己語料，**fit 類候選只可以用 2026-08-05 之後
  乾淨 point-in-time 段做 walk-forward**（之前存檔係賽後重評，有前視）。
- **驗證把尺**：A/A（候選 = baseline）必須 REJECT；已知結果嘅舊候選重判要判得啱。

### 8. 兩邊都 refit（2026-10-15 加）—— 管會改變 leaf 資訊量嘅候選

> 呢次係**獨立改把尺**，冇包含任何候選 model／feature／weight 改動。
> 實驗記錄：`EXP-20261015-20`。判決器：`model_evaluation_decision.evaluate_with_refit_arms`。

**問題**：之前一個候選只會放入**現行權重**度比較。但現行權重係喺舊 leaf 之下 fit 出嚟：
修好之前個 leaf 嘈，權重就會偏細；其他維度亦會頂替佢攞走一部分權重。
所以「凍結權重下過唔到」唔等於「呢個修正冇用」，有可能只係「舊權重聽唔到佢」
（實例：試閘分 AUC 0.5587、覆蓋 98.6%，但每分只傳導 0.007 綜合分）。

**適用**：所有會改變 leaf／維度資訊量嘅候選，即係修正 leaf、加或者剷 leaf、改覆蓋率。
純權重候選（本身已經係 fit）同純顯示改動唔適用。

**四個 arm**：

| | 現行權重 | walk-forward refit |
|---|---|---|
| baseline leaf | A0 | B0 |
| candidate leaf | A1 | B1 |

| 比較 | 模式 | 答咩問題 |
|---|---|---|
| **fixed arm** A1 vs A0 | `fixed_rule` | 唔郁權重，直接上線得唔得？ |
| **refit arm** B1 vs B0 | `walk_forward_oos` | 兩邊都有自己嘅權重，特徵本身係咪真係好咗？ |
| **live guard** B1 vs A0 | `walk_forward_oos` | 連新權重一齊上線，會唔會差過而家 live？ |
| **stale** B0 vs A0 | 只報告 | 現行權重係咪已經過時？ |

**判決**（以下次序）：

1. B0 同 B1 一定要用**同一個預先登記嘅 refit 程序**：同一套窗口、warmup、draw 數、
   seed、目標函數、fallback 規則同維度集。程序要喺睇任何 arm 結果之前鎖定，
   以 hash 證明兩邊一樣，唔一樣就直接拒絕（`refit_procedure_not_symmetric`）。
   refit 只可以用 v3 准許嘅乾淨窗口（AU：2026-08-05 起）。
2. fixed arm 同 refit arm 係同一個候選嘅兩次機會，所以當一個 family 做 **Holm**
   調整（以每個 arm WIN 所依靠嘅指標中最細嘅 p）。調整後 p < 0.05 先算數。
3. fixed arm WIN → **用現行權重上線**（`candidate_with_live_weights`）。
4. 否則 refit arm WIN，**而且** live guard 唔係 `primary_regression`／`ranking_metric_harm`
   → **候選 leaf 連同佢嘅 refit 權重一齊上線**（`candidate_with_refit_weights`），
   當一個改動。上線用嘅權重係用同一程序、喺上線日之前全部乾淨數據 fit 出嚟嘅共識。
5. 其他情況一律 REJECT（`refit_package_regresses_live`／`arm_multiplicity_not_significant`／
   `both_arms_reject`）。

**唔准做嘅嘢**：

- **唔可以將 B1 vs A0 當成候選嘅功勞。** 如果 B0 本身已經贏 A0，嗰份增益屬於 refit，
  唔屬於候選。候選嘅功勞只係 B1 − B0。B0 贏 A0 嘅話，`baseline_weights_stale` 會舉旗，
  要另外以純權重候選（`walk_forward_oos`）身份過閘，唔可以夾帶上線。
- **「全部權重設中性／相等」唔係判決 arm**，只可以做診斷。EXP-20261010-06：
  HKJC 中性權重 Good −6.99pp [−11.5, −2.6]，明顯差過現行權重；喺一個差好多嘅模型上面
  加分，唔代表喺 live 模型上面加分。
- **唔追溯。** 呢條規則之前已經 REJECT 嘅候選唔會自動改判。要用 §8 重測舊候選，
  就當一個新實驗：揀一張短名單，預先登記成一個 family，入面再做 Holm。
  唔准將全部舊 REJECT 逐個用 B arm 再試一次。
- **§6 功效前置照舊適用。** refit 會加變異，refit arm「CI 跨零」好多時只係量唔到。

**工具現況**（2026-10-15）：判決器已有，有測試（`test_refit_both_arms.py`，A/A 必須 REJECT）。
AU 嘅 walk-forward refit 預測產生器未整理成可重用工具；
EXP-20261015-02 嘅研究程式（分支 `codex-au-trial-cutoff-20261015`）係起點。
HKJC 可以用 `hkjc_weight_study.py` 嘅 `wf_refit` arm。

## Stage 4 判決順序（v2，2026-08-26）

呢次係**獨立改把尺**，冇包含任何候選 model／feature／weight 改動。舊 AU AUC-only
同 HKJC all-archive no-regression 判決保留喺下面做 v1 歷史記錄；由 v2 開始，正式
promotion 統一跟以下次序，但 AU 同 HKJC 仍然各自跑自己嘅 engine 同語料：

1. **安全／樣本閘**：baseline 同 candidate 必須同 sample hash、同場數、同一個已鎖
   dev／terminal split；leakage audit 通過；唔准用 holdout 調參或改尺救候選。
2. **Primary KPI**：兩邊都用 canonical `gold`（實際前三全部喺 model Top 4）同
   `good_positional`（model 第 1、2 揀都上名）。任何一項喺 dev 或 terminal 點估計
   回歸即 REJECT。
3. **`PRIMARY_WIN`**：Gold 或 Good 至少一項 dev、terminal 都改善，而且 terminal
   paired race bootstrap 95% CI 下界 > 0；另一項保持無回歸。
4. **`RANKING_WIN`**：Gold／Good 保持無回歸時，容許純排序改善。只可喺預先登記嘅
   `top3_capture_at5`、`mean_top3_model_rank`（越低越好）、
   `competitive_recall_at5`、`ndcg_at5`、`top5_pairwise_auc` 入面判斷；至少兩項 dev
   同 terminal 都改善，至少一項 terminal paired CI 下界 > 0，而且冇 ranking metric
   嘅 terminal CI 全負。
5. **Cohort guardrail**：field-size／venue／going 等預先聲明 cohort 有實質 regression
   一律 REJECT。多個 feature／weight 一齊郁仍然要 ablation。

Machine-readable 判決器：
`.agents/skills/shared_racing/model_evaluation_decision.py`。佢只接受已計好、已配對嘅
evidence，唔會讀 holdout 幫候選揀參數，亦唔會改任何 domain score。

> v2 嘅意思唔係「細數字都當真」。我哋接受 ranking-only 方向，但仍要同一語料、
> out-of-sample、paired CI 同 primary 無回歸。證據未夠就係 REJECT／繼續 shadow，
> 唔會因為進入 squeezing stage 就將 noise 叫做 improvement。

**呢份係「一個候選好唔好」嘅唯一裁判規則。** 建立於 2026-08-21，由 code 反推
（之前冇呢份文件，所以同一個候選喺唔同 harness 之下可以得出相反結論）。

每一項都標明**來源**：`code` = 由現行 code 讀出，`推斷` = 我推斷，`實測` = 當日跑出嚟。
**唔准喺呢度填估出嚟嘅值。** 改咗 code 就要改呢度。

> ⚠️ 改動呢份文件 = 改動判決規則。`model-regression-gate` 明文禁止「換指標／換窗／
> 換 top-K 去救一個候選」。要改把尺就當一個**獨立**改動，先單獨論證，唔可以同
> 候選一齊改。

### 6. 功效前置條件（2026-08-31 加）—— 管排名證據層

> **2026-11-25 加：開實驗之前先跑功效預估**（`shared_racing/scripts/power_precheck.py --platform au|hkjc BASE --gap-pp G --coverage C`，
> EXP-20261125-02）。佢喺真語料砌一個同模型完全無關、組別差 G、覆蓋 C 嘅理想訊號，用真把尺判 5 次。
> PASS 率 < 50% = **預設唔開**（理想訊號都量唔到，真訊號通常更難；真要開就喺實驗記錄寫明理由）；
> 50–80% = 邊緣，要寫明點解仲做；≥ 80% 照常。呢個係近似上限，唔係判決 —— 判決仍然由把尺做。
> 結果寫入實驗記錄嘅「功效預估」一行。例：1.4pp × 9%（EXP-20261122-32 嗰種）= 1/3 PASS → 唔應該開。

> 判決之前一定要先問：**呢把尺分唔分得到？**

「CI 跨零」有**兩個**成因，意思完全相反：(a) 候選真係冇用；
(b) **閘門根本量唔到呢個部件** —— 呢個係尺嘅問題，唔係候選嘅問題。

2026-08-31 實測（1,782 場，逐個 leaf 設中性 60，量 `top5_pairwise_auc` 嘅
holdout 影響）—— 即係嗰個 leaf 嘅「總身家」：

| leaf | 完全剷走佢 | 閘門睇唔睇到 |
|---|---:|---|
| performance_quality | −0.0180 | ✅ |
| jockey | −0.0178 | ✅ |
| trainer | −0.0093 | ✅ |
| form | −0.0017 | ❌ |
| track | −0.0032 | ❌ |
| jockey_horse_fit | −0.0025 | ❌ |
| pace_figure | +0.0004 | ❌ |
| rating | +0.0001 | ❌ |
| trial | +0.0010 | ❌ |
| sectional / pace_map / health / consistency / class | +0.0000 | 冇入排名 |

holdout 268 場嘅 95% 門檻係 **±0.0058**。**14 個 leaf 入面 11 個，連「完全剷走
佢」都細過呢個門檻。**

**所以 `top5_pairwise_auc` 唔可以單獨做判決** —— 呢個正好係 v2 唔用 AUC-only
嘅理由。實例（2026-08-31，同一個候選）：

| | AUC-only（v1） | Stage 4 v2 |
|---|---|---|
| 個體化 `pace_figure` | holdout +0.0010 [−0.0049, +0.0066] → **證明唔到** | `gold` holdout **+2.99pp** [+1.00, +5.19] → **PRIMARY_WIN** |

**兩把尺對同一個改動得出相反判決**，而 v2 嗰邊係量到嘅（`gold` 動 3pp）。

#### 規則

判 `RANKING_WIN` 之前，對每個要用嘅 ranking metric 量兩個數：
- **閘門 MDE**：該 metric 喺 terminal 嘅 paired bootstrap CI 半寬
- **部件預算**：將候選掂到嘅部件設中性，量同一個 metric 嘅 |Δ|

**若 部件預算 < 閘門 MDE → 嗰個 metric 對呢個候選係非資訊性**，唔可以用佢做
`RANKING_WIN` 嘅兩個訊號之一，亦唔可以用佢嘅「CI 跨零」當反面證據。
如果五個 ranking metric 全部非資訊性，判決記 `UNRESOLVABLE` 而唔係 `REJECT`。

⚠️ 呢條規則**唔可以事後套落一個已經 REJECT 咗嘅候選**。要喺量度**之前**先計，
寫落實驗記錄。

### 7. 正確性修正（2026-08-31 加）—— 唔走候選流程

有一類改動**唔係為咗變好**，而係**修一個可以獨立證明係錯嘅嘢**：

- 一個常數嘅註釋聲稱佢係實測值，但實測係另一個數
  （例：`WET_FORM_PRIOR = 0.5  # ~0.496 measured`，四種計法都係 0.35–0.40）
- 一個 regex 靜靜掉走一整類數據
  （例：`RE_WINNING_TIME` 漏走所有跑少過一分鐘嘅賽事，28.2%）
- 一個閘門睇唔到自己要守嘅嘢（例：overlay 唔喺 `data_contract`）

呢類改動**唔需要證明 primary KPI 升**，但要全部滿足：

1. **錯處可以獨立證明** —— 唔靠績效數字，而係「code 自己聲稱嘅嘢同事實唔符」
2. **零顯著退步** —— primary（`gold`／`good_positional`）唔可以有顯著負；
   預先聲明嘅 cohort（馬群大細 ×4、首選 SP ×5）冇一個 CI 全負
3. **leakage audit PASS**
4. **實驗記錄要明文寫「呢個冇通過表現閘，唔係一個已證實嘅改善」**

⚠️ **呢個類別最容易被濫用。** 判斷標準係「**如果績效數字係相反方向，你仍然
會改佢嗎？**」—— 答唔到「會」就唔屬呢類，要走候選流程。

實例（2026-08-31）：濕地 `WET_FORM_PRIOR` 0.5 → 0.3758 喺 Stage 4 v2 之下係
**REJECT**（`primary_regression`：`good_positional` dev −0.16pp / holdout
−0.20pp），但作為正確性修正上線 —— 因為舊 prior 令「跑到群體平均率嘅馬」
被罰，而且罰則隨濕地經驗遞增（0 場 0.00 → 40 場 −1.68），呢個係可以獨立
證明嘅錯，同績效數字無關。記錄：`EXP-20260831-08`。

---

## AU（v1 歷史記錄）

### 判決規則（PRIMARY）

> **頭 K=5 位配對嘅場內 AUC，holdout 上 95% 配對 bootstrap 區間唔過 0。
> dev 點估計唔准係負。就係咁多。**

來源：`au_eval.py` docstring 寫死。

**點解唔用場數指標做主裁判**：2026-08-04 校準過 —— 對 leaf 加 ±0.3 **確定中性**
嘅隨機擾動跑 40 次，dev 5-fold + walk-forward + holdout 三道閘全過嘅係 **0/40**。
假陽性 0 好，但同時代表真 +1pp 嘅改動大機會過唔到。場數指標照要報，但係**次要**。

### 規格

| 項 | 值 | 來源 |
|---|---|---|
| 基準命令 | `au_dump_engine_leaves.py --out X` → `au_eval.py --data X` | code |
| 前置 | `au_matrix_refit.py verify --data X`（replica 一致性，未 verify 過唔好信搜索結果） | code |
| 主指標 | 頭 K=5 位配對場內 AUC | code |
| bootstrap | 2000 次，**按場**重抽（同場配對唔獨立，按對重抽會低估區間）；`seed=7` 已固定 | `BOOT=2000`, `_boot_ci` |
| 次要指標 | gold, gold_strict, good_positional, pass, champion, winner_in_top3/5, t3prec, mrr, ndcg5, blowout | `eval_metrics.py` |
| **搜索目標（判決）** | **`place` = (gold, good_pos, pass, t3prec)** —— 2026-08-23 由 `balanced` 改。本 project KPI 係上名捕捉，`balanced` 會令搜索用 `champ`/`winT3`/`mrr` 買走 `pass`/`t3prec`。歷史紀錄（08-01/08-03/08-08 三次重 fit）係 `balanced` 出嘅，要對比要明確傳 `--obj balanced` | `au_matrix_refit.OBJ_PRESETS` |
| **分層指標** | 場數指標按馬群大細分四桶（≤8 / 9-10 / 11-12 / 13+）—— **必報** | `au_eval.FIELD_BUCKETS` |
| dev/holdout | 按**唯一日期**切，尾 15% 日期入 holdout；唔切開同一日 | `date_partitions()` |
| fold | dev 內部 5 個時間 fold | `au_feature_ab` / `au_matrix_refit` |
| 訓練期 | **不適用** —— 冇訓練步驟，六維權重手工擬合 | 推斷 |
| 隨機種子 | `golden_scoring.SAMPLE_SEED=20260821`；bootstrap `seed=7` | code |
| 必需數據 | `AU_Racing/**/Race_*_Logic.json`（用 `corpus_paths`，要包 `Archive/`）+ `AU_Historical_Raw_Race_Results.csv` | code |
| 排除記錄 | 前三不足 3 匹、冇頭馬嘅場次（`_counts` 直接 `continue`） | code |
| 樣本 | 1,413 場 / 14,121 匹 | 實測 2026-08-21 |

### 現行 baseline（commit `b51793d7`，喺 `99d81e64` 一樣成立）

| 指標 | all | dev (901) | holdout (512) |
|---|---|---|---|
| **頭5位 AUC** | 0.6793 | 0.6871 | 0.6631 |
| 全場 AUC | 0.6655 | 0.6725 | 0.6503 |
| gold | 17.79% | 16.13% | 20.70% |

> ⚠️ **`gold` 嘅定義好易讀錯。** 佢係「**實際前三全部落喺模型頭四揀之內**」
> （捕捉率 —— 三隻上名馬有冇一隻走漏），**唔係**「頭馬喺模型頭四揀之內」。
> 2026-08-23 有一次分析全程用錯後者並叫佢 `gold@4`，令幾個候選睇落有「gold 升」
> 嘅好處，用正確定義重測之後嗰個好處**完全消失**（pace_perf 減權 Good位 −2.43 ❌、
> 剷濕地 overlay Gold −0.17、PF×PI 降權 Good位 −1.08 ❌）。舊定義叫 `gold_strict`
> （模型頭三揀全部上名）。三個數字唔可以混住講。
| gold_strict | 6.24% | 6.01% | 6.64% |
| good_positional | 23.53% | 21.47% | 27.15% |
| pass | 46.99% | 43.72% | 52.73% |
| champion | 25.73% | 24.81% | 27.34% |
| winner_in_top3 | 56.13% | 54.62% | 58.79% |
| t3prec | 47.51% | 46.13% | 49.93% |

分層（Gold，dev / holdout）：≤8 匹 31.58% / 33.63% ｜ 9-10 15.38% / 13.33% ｜
11-12 9.21% / 9.65% ｜ 13+ 8.91% / 5.00%

---

## HKJC（v1 歷史記錄）

**用完全另一套閘門**，同 AU 嘅 AUC 判決規則**唔通用**。

| 項 | 值 | 來源 |
|---|---|---|
| 命令 | `hkjc_no_regression_gate.py`（冇 `--baseline` 模式，設計上比較候選） | code |
| maximize keys | gold, good, min_threshold, champion, top3_has_champion, mrr, avg_top4_hits | code |
| 樣本 | 264 場 | 實測 |

### 現行 baseline

Gold 19（**7.20%**）· Good 68（25.76%）· Pass 124（46.97%）· Champion 73（27.65%）
· MRR 0.4656 · Order Issue 101 · Avg Top4 Hits 2.083 · Passing candidates: none

> ⚠️ **AU 同 HKJC 嘅 Gold 唔可以直接比。** HKJC 個 7.20% 接近 AU 嘅
> `gold_strict` 6.24%，**唔係** AU 個 `gold` 17.79%。冇任何文件講兩套指標點對應 ——
> 呢個係已知缺口。

---

## 已知缺陷（記錄，未修）

1. **「85/15」呢句話係錯嘅。** `date_partitions` 切嘅係**日期**。新語料每日場次密度
   高好多，所以 15% 日期 = **36.2% 場次**（512 / 1,413）。
   `au_eval.py` 而家一定印 `holdout_share_of_races`，但 repo 內仍有 docstring 寫「85/15」。
2. **dev / holdout 係 regime 切分，唔止時間切分。**
   dev 只有 11.0% 係乾淨 point-in-time、平均馬群 10.51；
   holdout 100% 乾淨、平均馬群 9.08。`au_eval.py` 差距 >0.5 會出警號。
3. **場數指標唔按馬群正規化。** dev 內 Gold 由 ≤8 匹 31.58% 跌到 13+ 匹 8.91%（3.5×）。
   pooled 比較會被組成變化冒充成模型變化 —— 所以分層係**必報**，唔係可選。
4. **2026-08-05 之前嘅檔位相關 A/B 唔可信。** `au_draw_bias_matrix.json` 由完整賽果
   重建，回測舊場次時矩陣含住嗰場自己嘅賽果。live 冇問題（評分嗰刻未來未存在）。
   詳見 [EXP-06](experiments/EXP-20260821-06-au-race-shape-contribution.md)。
5. **HKJC 嚴重缺實驗** —— 絕大部分實驗都係 AU。

---

## 相關

- 完整審計：[`audits/2026-08-21-repo-model-audit.md`](audits/2026-08-21-repo-model-audit.md)
- Codex 交接：[`handoff/2026-08-21-codex-handoff.md`](handoff/2026-08-21-codex-handoff.md)
- 實驗記錄：[`experiments/INDEX.md`](experiments/INDEX.md)
- 紀律規則：`AGENTS.md` 嘅「改模型嘅規矩」；`.claude/skills/model-regression-gate/`
