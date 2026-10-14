# racing-analyser：可借鑑方向與信賴區間說明

日期：2026-10-14。唯讀 source review，沒有安裝／執行第三方 app，沒有改模型、部署或保存。

## 來源與範圍

Repository：https://github.com/SKStorageAU/racing-analyser

讀取 default branch master；commit SHA `b1dfffa94fe4b677529bcc2d5cfe1192f5a542b4`
（commits/master 確認；Git root tree `039096cc236a4a94e6e1147e8ced4d73ae5a955f`）。
已讀 README、config.py、app.py、analyser/scoring.py、analyser/ev_calculator.py、
scraper/tab_scraper.py、scraper/sportsbet_scraper.py、database/db.py。
讀取的 scorer / scraper blob SHA 與上述 tree 相符。完整 tree 沒有 tests、backtest 或
訓練／校準程式；有 results SQL table，但已讀 workflow 沒有結果驗證流程。
不能由此推斷作者沒有其他私人研究；只能說這份公開 source 沒有提供效果證據。

永久 source links：

- [權重](https://github.com/SKStorageAU/racing-analyser/blob/b1dfffa94fe4b677529bcc2d5cfe1192f5a542b4/config.py)
- [評分與機率](https://github.com/SKStorageAU/racing-analyser/blob/b1dfffa94fe4b677529bcc2d5cfe1192f5a542b4/analyser/scoring.py)
- [TAB parser](https://github.com/SKStorageAU/racing-analyser/blob/b1dfffa94fe4b677529bcc2d5cfe1192f5a542b4/scraper/tab_scraper.py)
- [Sportsbet enrichment](https://github.com/SKStorageAU/racing-analyser/blob/b1dfffa94fe4b677529bcc2d5cfe1192f5a542b4/scraper/sportsbet_scraper.py)
- [產品 EV](https://github.com/SKStorageAU/racing-analyser/blob/b1dfffa94fe4b677529bcc2d5cfe1192f5a542b4/analyser/ev_calculator.py)

## 實際權重與流程

| 因素 | 設定權重 | 實作觀察 |
|---|---:|---|
| recent_form | 28% | 最近五次名次，遞減權重 .35/.25/.18/.12/.10；fallback 用字元解析 form string |
| speed_rating | 20% | dfsFormRating / 全場最大值；缺 rating 用賠率排名，並非測得速度 |
| jockey | 14% | parser 設 jockey_win_pct=0，主流程沒有補 form endpoint |
| trainer | 10% | parser 設 trainer_win_pct=0；14 日狀態只存在 scorer 說明 |
| distance_affinity | 10% | parser 設 career_dist_win_pct=0 |
| track_condition | 8% | scorer 無條件返回 0.5；track condition 沒有改變此因素 |
| barrier | 6% | 三個距離組的固定表；沒有 venue／rail conditioning，field_size 參數未使用 |
| weight | 4% | 全場平均負磅減個別負磅，clip；未分解 handicap ability 與負磅效果 |

現有 app pipeline 下，34% 權重零值、8% 權重固定中性，共 42% 沒有區分馬匹。
這不等於精度會下降 42%；因素尺度、場內 z-score 與市場 prior 都會影響實際排名。
early_speed_rating / early_speed_band 有讀取及存檔，但不入上述 scorer。

機率階段將本場 1/odds 比例去水，用 logit(market_probability) + 0.25 × z(composite)，
再 sigmoid 並全場 normalize；最後按該勝率排名。
config 的 MODEL_MARKET_BLEND=0.45 不被 scorer 使用，MARKET_MARGIN=1.18 與
WIN_TO_PLACE_RATIO=2.8 亦不是現行 scorer 的算法。
所以不應稱為 55% model / 45% market 或照抄 config 即重現機率。

缺 rating 用 odds，以及機率階段再使用 odds，是兩次市場依賴。
dfsFormRating 本身的供應商定義、是否使用市場資料亦未獨立確認；不能把它當已認證
的獨立速度特徵。這次没有恢復 Kelvin 已擱置的 TAB 收集工作。

## 可獨立證明的問題

1. form string 的 `0` 進入公式 max(0, 1-(pos-1)*.175)，得到 1.175，比冠軍 1.0 高。
   主流程 last5_raw=[]，因此 fallback 特別重要；0 的來源含義要驗證，不能當第零名。
2. Top3 機率用 3p/(1+2p)，沒有其他馬的聯合次序模型。五匹等強馬，各 p_win=.2，
   它給 p_top3=.428571，總和 2.142857；在正常五匹完賽、無 dead heat 的假設下，
   對称的真正各馬 Top3 機率是 .6，總和必須 3。這是直接代入公式的數學反例，
   不是 race backtest。程式註釋稱 Harville approximation，不能據此視為已校準 Harville。
3. Insure 3rd 缺價格便用普通獨贏价 × .83；其後仍然可以產生 STRONG BET 標籤，
   沒有可持久追溯的 observed/estimated 標記。該價不是已驗證可成交報價。
4. Sportsbet browser fallback 即使未找到保險 toggle，仍會把 runner price 標為保險價；
   REST parser 以 market name 包含 insure 或 3rd 作識別，也不足以驗證完整產品條款。
5. runner DB upsert 覆寫當前 price/probability，不是 immutable pre-race snapshot；
   後續才 scratched 的舊 DB runner 沒有由這條 refresh 流程同步標記。

EV 的代數在「勝出按 reduced decimal odds 派、第二／三現金返本、其餘輸本金」假設下正確：
EV_win=p_win×O−1；EV_insurance=p_win×O' + p_2_or_3−1。
因此兩者差為 p_2_or_3−p_win×(O−O')。
本次沒有核實 Sportsbet 最新產品可用性或實際條款，不能把 repo 的假設當成現行投注規則。

## 對 Wong Choi 的借鑑判斷

| 方向 | 與我哋的重疊 | 判斷 |
|---|---|---|
| 分數轉概率、機率校準 | au_ml_program 已有 chronological calibration、Brier、log loss、calibration_table、場內 mass normalization | 不是未做過；可審計 probability 的真實含義，不能直接搬這份 heuristic |
| 市場去水及模型增量 | EXP-20260826-08；docs/plans/2026-10-14-open-source-borrowing.md 的 X0/X1/R1 已列明 | 保留市場單獨 baseline；量 model 是否超越市場，而不是只看混合比 model 好 |
| 獨贏／位置／保險回報比較 | 上述 plan R3 已提位置機率與價格一致性；本 repo 加入保險 payout 視角 | 可作往後獨立 decision research；先有校準機率、同時刻實價、精確條款、賽果，再比 OOS EV/ROI |
| 欄位與價格 provenance | 我哋已有 data_contract，TAB audit 已完成但後續暫停 | 借它的失敗例檢查假中性、零值、odds fallback、estimated quote；無需先改分數 |
| 14日 trainer /近期 people | 今日 EXP-20261014-01 測已完結三個月狀態，四候選 dev REJECT；非同一 14日定義 | 概念重疊，這份 source 的 14日欄位沒實際供值，不能當新證據重跑 |
| 複製八權重、固定 draw/低負磅 bonus | 現有 AU 特徵與歷史研究有大量重疊 | 不採用；缺 OOS validation，不見新獨立資訊 |

任何市場入模仍須明文 methodology；這次研究不更改獨立 AU scorer。
現有計劃的依賴不被這份 review 自動重啟或視為批准完成。

## 「信賴區間跨零」的正確解讀

這裏 CI 描述 candidate−baseline 的效果不確定性，並非性能 KPI 本身。
跨零表示數據與零效果、正效果及負效果仍相容；不能單靠它證明候選無效。
不跨零也不能證明無洩漏、無偏差、符合實際下注時間或能盈利。

今次 EXP-20261014-08：421 terminal races，Gold 多中 1 場 = +.2375pp；
top5_pairwise_auc +.00028777，paired 95% CI [−.00043872,+.00114106]。
少量受影響場次與小增益容易令抽樣誤差覆蓋零；跑 2000 bootstrap 不等於新增 2000 場資料。
EXP-20261014-05 的 terminal 定位标签只有 53 匹，也不足以确认 dev 的定位可靠度關係。
pace confidence / workload 直接加分在 dev 已回歸，則不是只有 CI 不夠窄的問題。

canonical 方法配對同一批場次、按場重抽 2000 次 seed=7，保住場內依赖。
場與場之間的同 meeting/day 依赖不由此處理；可能低估誤差，需要獨立 methodology audit，
不能看了 candidate outcome 才換 bootstrap 或放寬 gate。
反覆試很多候選亦不由單個 95% CI 自動校正；需要鎖 dev 選擇、保留新 terminal，並少量
預先登記假設。過去 terminal 曾被研究使用，現有重播證據屬 retrospective。

合約 §6 已要求先量部件預算及指標辨識能力；上次四方向實驗沒有完成這項前置量度，
EXP-20261014-08 已披露，不能事後用 UNRESOLVABLE 救結果。
下一次先量可辨識幅度，再定 sample budget；弱正訊號可待新資料，不能當證實無效，
也不能改尺把它叫作已證實改善。

CI 的作用是減少把抽樣偶然當成可部署升級的風險；目前沒有獨立對照證據能量出
「CI gate 令 Wong Choi 準確率提升幾多」。應並報效果大小、CI、有效樣本、時間 folds、
primary/cohort regression、資料／洩漏稽核。

統計定義參考：[NIST confidence intervals](https://www.itl.nist.gov/div898/handbook/prc/section1/prc14.htm)。
95% 指同樣方法重複抽樣產生的區間，長期約95%覆蓋真值；不是固定真值有95%概率落入
這一個已算出的區間。Bootstrap 覆蓋亦依賴抽樣及方法假設。
