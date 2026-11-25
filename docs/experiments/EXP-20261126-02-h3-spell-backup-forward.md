# EXP-20261126-02 H3 休後狀態曲線：預先登記 forward（shadow）測試（AU）

- 日期：2026-11-26（Kelvin：「做 1-3」）
- 來源：EXP-20261125-06 —— 休 ≥90 日 −2.5pp、覆蓋 13.9%；功效預估 2/3 PASS「邊緣」
- 引擎：`au_hypothesis_forward.py`（通用假設 forward，自學循環 P0，docs/plans/2026-11-26-self-learning-loop.md）；同 H1（EXP-20261125-11）同一套做法

## 假設
H3 休後狀態曲線：資料已經喺 live leaf／欄位度，市場定價正確，模型份量／形狀唔啱。即使 PASS 都只係**追近市場**（追市場軌），唔係贏市場。

## 候選（2026-11-26 凍結，之後唔再 fit）
- 候選 ability = live ability + Σ w·term；term = ind(days_since_last ≥ 90)、ind(0 < days_since_last ≤ 14)；冇值 = 0
- w = spell90 −1.7226、backup14 +1.1544（ability 分）
- fit：`docs/experiments/patches/au_hyp_forward/fit_frozen.py --arm EXP-20261126-02`，BASE（`au-debut-trainer-20261124/BASE.json`，sha 86c01ecb…）2026-08-05 → 11-25，4,260 場／110 日。
  形狀同 H1：logit P(top3) = a + α·(ability−場均) + γ·logit(3/N) + Σ β·(term − 場均)，w = β/α。
- in-sample log-loss 0.5518931 → 0.5514715（−0.00042／匹） —— 只供參考，唔係證據（H1 係 −0.0015）。
- frozen.json sha256 登記喺 `ARMS`，載入時核對。

## 防洩漏
日期欄位，賽前已知；BASE 同 live 用同一個欄位 python_auto.preparation_cycle.days_since_last_run（au_dump_engine_leaves.py:180）；live 11-20→24 組別比例 13.8%／31.2% vs fit 13.9%／33.3%。SP 只做市場尺基準，唔入候選。

## 開始日、樣本量（預先登記）
- START = **2026-11-27**（11-26 嘅快照喺登記之前已發佈）。
- 目標：第一次**同時**夠 **60 個賽日同 2,000 場**嗰日做 cutoff（H1 嘅兩倍：功效預估只係邊緣，in-sample 改善細過 H1）。
  之前嘅快照場次只做 walk-forward 校準。**唔准因為結果邊緣而延長**（換窗 = REJECT）。

## 判決規則（合約 m3 追市場軌，判一次就凍結）
同 EXP-20261125-11：排名尺 v2 PASS（只計 forward 賽日）**而且** windowed gap_change 點估計 ≤ 0。另報市場尺 A／B。
判決鎖 `<資料根>/WongChoiControl/forward_verdicts/EXP-20261126-02.json`。PASS = Kelvin 決定上唔上線；FAIL = 記錄，唔准同一批數據重試。

## 接駁
- 排程 `au_daily_schedule.step_hyp_forward`（evening，`step_h1_forward` 之後）：`au_hypothesis_forward.py nightly`；失敗唔 runlog.warn。
- 狀態檔 `<WORK_DIR>/au-hyp-forward-EXP-20261126-02.json`（盲）；`au_forward_tracker.FORWARD_TESTS` 已登記（ready_from_status），夠數推 Telegram＋forward 總板。

## 狀態
- 2026-11-26：凍結、登記；forward 0 場。live 排名冇郁（golden 不變）。
