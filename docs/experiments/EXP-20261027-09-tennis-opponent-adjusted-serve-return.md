# EXP-20261027-09：對手校正發球／接發球實力

- **日期／平台**：2026-10-27；Tennis 勝負概率研究。
- **假設**：過往發球得分、接發球實力提供 Elo／排名以外資訊；校正歷史對手實力比直接平均更有效。
- **基準 commit**：`c41a954575f1b17cfcd62632be7e5b97328155a6`。
- **搜索舊記錄**：EXP-20261027-07/08、EXP-20261026-04、`fit_hold_ml.py`、`PLAN_serve_features.md`。本次係 online service-point ability + winner head，不是已試過嘅 fresh WTA hold-rate 替換或 hold ridge refit。
- **事前 protocol SHA**：`30b737758611c1174f8d81c92757bc6fccf23270bbecfe966b02bd61c9435048`；原協議不因結果或後續報價偏好改動。

## 模型與消融

`P(server wins point)=sigmoid(mu_tour + S_server − R_returner)`。S/R 用過往雙方發球得分比例，以事前固定 decayed learning-rate 更新；所有服務對位、overall/surface 更新都讀同一 pre-match state。overall/surface 混合 .35/.65。

- mu 只用2020且 `available<2021-01-01` 嘅服務得分：ATP 142080/225376，WTA 87514/154093；logit mu .533990/.273410。
- learning-rate `120*ln(10)/400/(n+5)^.4`，無搜尋；來源只記賽事起始日，結果統一 `start+21d < forecast_date` 才用。fit label亦同樣隔離。
- 勝負 head：無截距 ridge=1 logistic；fit expanding from2021，無scaler／超參數搜尋。
- 控制：重訓 binary；binary+rank；binary+rank+**未校正**S/R。
- 候選：binary+rank+**對手校正**S/R。
- attribution：只加校正S、只加校正R。預先規定不可事後挑單項或未校正arm去救候選。
- 現役主模型沒有改。這是歷史研究 head，**不是現役全特徵／折扣／注碼 replay**。

## 語料與時間驗證

既有凍結 Sackmann raw2020–25，12批，直接 source key + winner/loser/date 對照；不經曾出錯嘅 history ordinal。接受完整比分27263場，point-count有效27131（ATP14201、WTA12930），缺／無效132。不用當場統計入自己預測；當場stats缺失亦保留該場預測，避免以賽後stats有無篩選目標。

- 服務計數須雙方 svpt、1stIn、1stWon、2ndWon 合法整數；無一方補值。
- point corpus SHA `5700413f1b5938bd7254068ff90fdac0bca20922bf5e147fd43e6739bfa9ce07`。
- 評分人口沿用binary歷史覆蓋；2023H1/H2、2024H1/H2、2025H1共12826場。五段 binary/rank losses逐項與EXP08重現至1e−12；缺point歷史用中性0，無剔走冷啟動。
- 2025已於其他研究讀過，不當新holdout。本次 **2025H2候選確認窗未開**，因dev先失敗；沒有讀2026/live holdout。

| 窗 | N | Elo+rank LL | 未校正 S/R LL | 對手校正 S/R LL | 校正對rank差 |
|---|---:|---:|---:|---:|---:|
| 2023H1 |2843|.627397|.624621|.622415|−.004981|
| 2023H2 |2051|.621277|.618894|.615862|−.005415|
| 2024H1 |2875|.616412|.615165|.614600|−.001813|
| 2024H2 |2229|.621581|.618198|.616678|−.004903|
| 2025H1 |2828|.617572|.618264|.617713|**+.000141**|

全dev：rank LL/Brier .620779/.216339，未校正 .619068/.215553，校正 .617581/.214893。校正對未校正兩項指標五段全勝；對rank Brier五段勝、LL只四段勝，**未過事前5/5要求**。

只加S全dev LL .620044、只加R .620495，合併有額外資訊；但2025H1加S相對return-only令LL變差。沒有事後改用return-only。

退步：2025H1相對rank，ATP1444場ΔLL +.001557、Clay1086場 +.002802，WTA1384場 −.001336；M405場 +.003197、PM472場 +.003565。沒有剔走呢啲層救總數。

## 固定歷史價診斷（不可代替Sportsbet驗證）

模型拒絕後仍按事前計劃報描述性市場比較：沿用EXP08既有2023/24 B365同書配對、同8240場、同EV>0/1u規則。**用戶已明確暫時只用Sportsbet；此處既有第三方歷史資料只係舊研究對照，不代表Sportsbet可執行回報，亦不會另購／假設其他莊家來源。** 沒有quote captured_at證據，不能聲稱ROI／CLV實盤驗證。

| 同8240場 | LL | Brier | 假設下注 | 假設P/L | 假設ROI |
|---|---:|---:|---:|---:|---:|
| 原binary研究對照 |.625906|.218757|6678|−806.12u|−12.07%|
| Elo+rank |.621212|.216558|6514|−936.06u|−14.37%|
| +未校正S/R |.618336|.215300|6437|−893.71u|−13.88%|
| +對手校正S/R |.616462|.214471|6385|−788.25u|−12.35%|
| 去水市場 |**.588085**|**.202366**|—|—|—|

配對bootstrap按match、4000次、seed20260826，差定義candidate−control，所有無下注場保留0：
- 對rank：ΔLL −.004749 CI[−.006386,−.003197]；每配對場P/L差 +.017938u CI[+.006826,+.028867]，總假設少蝕147.81u。
- 對未校正：ΔLL −.001874 CI[−.002593,−.001174]；每場P/L差 +.012799u CI[+.005562,+.020127]。
- **對原binary**：總假設少蝕僅17.87u；每場P/L差 +.002169u CI[−.014292,+.018140]，未證明盈利增量；ROI亦略差，不能只用較弱排名arm作有利對照。
- 對市場：ΔLL **+.028378** CI[+.024038,+.032641]；Brier差 **+.012105** CI[+.010174,+.013980]，仍明顯落後。

完整tour/surface/level/odds分層、校準bins及係數封存；odds cohort事前固定為兩邊較長報價max≤2、2–3、3–5、>5，不按勝負定義。max>5層校正後假設ROI仍−39.61%；max≤2層由rank−13.64%變−13.83%，沒有事後過濾。

## 檢查與決定

- **leakage：FLAG**。歷史publication/observation時間與quote captured_at未證實。已測21日嚴格隔離、同日凍結、當場／未來points不入特徵、mu只用暖身、player-swap對稱、tour隔離、無新資訊A/A不產生收益。
- 二十個針對測試通過；完整repo gate與保存證據見 `docs/audits/tennis-serve-model-20261027.json`。
- golden、data-contract calibration及evaluation ruler不改；生產模型、資料、下注門檻及注碼不改。
- **決定：REJECT上線；有額外預測資訊，但未過dev穩定性、仍落後市場，對原基準盈利增量不確定。** 不開新確認、不改窗口、不揀另一arm、不因歷史價少蝕而救已失敗模型。
- 研究code只保存非main分支；文件可以交付main，不會部署失敗模型。

可重跑命令、source/data/code SHA、分支與完整artifact manifest見 `docs/audits/tennis-serve-model-20261027.md`。
