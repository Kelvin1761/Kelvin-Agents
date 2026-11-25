# EXP-20261126-01 H2 騎師＋練馬師分加重：預先登記 forward（shadow）測試（AU）

- 日期：2026-11-26（Kelvin：「做 1-3」）
- 來源：EXP-20261125-06 —— 騎師 z≥1 模型殘差 +3.5pp、覆蓋 17.4%（EXP-06 表）；功效預估 2/3 PASS「邊緣」
- 引擎：`au_hypothesis_forward.py`（通用假設 forward，自學循環 P0，docs/plans/2026-11-26-self-learning-loop.md）；同 H1（EXP-20261125-11）同一套做法

## 假設
H2 騎師＋練馬師分加重：資料已經喺 live leaf／欄位度，市場定價正確，模型份量／形狀唔啱。即使 PASS 都只係**追近市場**（追市場軌），唔係贏市場。

## 候選（2026-11-26 凍結，之後唔再 fit）
- 候選 ability = live ability + Σ w·term；term = z(jockey_score)、z(trainer_score)
- w = jockey_score 0.9898、trainer_score 0.8460（ability 分每場內 SD）
- fit：`docs/experiments/patches/au_hyp_forward/fit_frozen.py --arm EXP-20261126-01`，BASE（`au-debut-trainer-20261124/BASE.json`，sha 86c01ecb…）2026-08-05 → 11-25，4,260 場／110 日。
  形狀同 H1：logit P(top3) = a + α·(ability−場均) + γ·logit(3/N) + Σ β·(term − 場均)，w = β/α。
- in-sample log-loss 0.5518931 → 0.5510766（−0.00082／匹） —— 只供參考，唔係證據（H1 係 −0.0015）。
- frozen.json sha256 登記喺 `ARMS`，載入時核對。

## 防洩漏
騎師名單賽前公佈；jockey／trainer leaf 嘅 LY 統計 D<今日（EXP-20261015-04 已修）；冇新欄位，只係 live 已用緊嘅 leaf。SP 只做市場尺基準，唔入候選。

## 開始日、樣本量（預先登記）
- START = **2026-11-27**（11-26 嘅快照喺登記之前已發佈）。
- 目標：第一次**同時**夠 **60 個賽日同 2,000 場**嗰日做 cutoff（H1 嘅兩倍：功效預估只係邊緣，in-sample 改善細過 H1）。
  之前嘅快照場次只做 walk-forward 校準。**唔准因為結果邊緣而延長**（換窗 = REJECT）。

## 判決規則（合約 m3 追市場軌，判一次就凍結）
同 EXP-20261125-11：排名尺 v2 PASS（只計 forward 賽日）**而且** windowed gap_change 點估計 ≤ 0。另報市場尺 A／B。
判決鎖 `<資料根>/WongChoiControl/forward_verdicts/EXP-20261126-01.json`。PASS = Kelvin 決定上唔上線；FAIL = 記錄，唔准同一批數據重試。

## 接駁
- 排程 `au_daily_schedule.step_hyp_forward`（evening，`step_h1_forward` 之後）：`au_hypothesis_forward.py nightly`；失敗唔 runlog.warn。
- 狀態檔 `<WORK_DIR>/au-hyp-forward-EXP-20261126-01.json`（盲）；`au_forward_tracker.FORWARD_TESTS` 已登記（ready_from_status），夠數推 Telegram＋forward 總板。

## 狀態
- 2026-11-26：凍結、登記；forward 0 場。live 排名冇郁（golden 不變）。
