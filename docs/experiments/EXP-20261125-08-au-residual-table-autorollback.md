# EXP-20261125-08 — AU 練馬師剩餘表現表：版本化＋shadow 比較＋自動回退（Tier-1 自我學習試點）

- 日期：2026-11-25 · 平台：AU · 類型：**管線／運維（唔郁模型）**
- 對象：`AU_Trainer_Residual.json`（EXP-20261122-02，每晚由 `au_trainer_residual_table.py` 重建，引擎即讀）
- Code：`au_wong_choi_auto/scripts/au_residual_versions.py`、`au_residual_shadow.py`、
  `au_racing_engine/people_overlays.py`（`default_table_path` 識讀指針）、`au_daily_schedule.step_trainer_residual_shadow`、
  `au_forward_tracker.FORWARD_TESTS["trainer_residual_autorollback"]`

## 問題

以前重建失敗就沿用舊表；重建**成功但變差**（例如語料排除咗場次、舊場次被新模型重評分、bug）冇人知。

## 設計

1. **版本化**：每次重建照舊寫 live 檔（bytes 一樣），另存
   `AU_Trainer_Residual.versions/AU_Trainer_Residual.<as_of>-<sha10>.json`，再寫指針
   `AU_Trainer_Residual.active.json`（version、file、sha256、as_of、previous、pinned、history）。
   引擎：有 `WC_AU_TRAINER_RESIDUAL_TABLE` → 照用；有效指針（sha256 驗過）→ 版本檔；冇／壞 → live 檔（同以前一樣）。
   同 sha 重跑 = 唔開新版本。保留最近 14 份；有效版、上一版、等緊 shadow 嘅版本同佢哋嘅上一版永遠唔刪。事件記入
   `AU_Trainer_Residual.events.jsonl`。
2. **只比「改寫咗舊歷史」嘅重建**：啟用時將新表截到上一版 `as_of`，同上一版比。純追加（多咗新一日）唔比 ——
   每晚加新賽果係呢個表嘅本意，而晚晚做檢定 = 一個月 30 次 2.5% 單邊測試，一定會亂咁回退。
3. **Shadow 窗口**：啟用日（悉尼日期）**之後**嘅有賽果賽日，每 7 日一個唔重疊窗口，每個改寫版本最多 3 個（21 賽日）；
   之後再有改寫或者回退 = 舊窗口停（superseded）。每個窗口夠數判一次就凍結。
4. **預先登記判法**：Δ = 每匹 Δlog-loss（新 − 舊，只計 overlay 有唔同嘅場次），賽日 bootstrap 2,000（seed 0）。
   **回退** if 最新窗口 95% CI 下界 > 0，**或者**連續 3 個已判窗口（可以跨版本；冇差異嘅窗口唔計、唔打斷）點估計 > 0。
5. **回退** = 指針指返（第一個）失敗版本嘅上一版並 `pinned`；之後重建照存但唔啟用，直到
   `au_residual_versions.py unpin --actor kelvin`。唔刪任何版本。排程 step 推 primary Telegram（`au_notify.push`）。

## 近似（為咗平，唔重跑引擎）

- 其他 leaf 凍結喺儲存值：分數 = 儲存 `ability_score` − 儲存 `trainer_residual_feature` + 該版 overlay。
- 校準 (a, α, γ) 兩邊**共用** = `au_logloss_ruler.calibrations(…, "v2")` 喺儲存 live 分數上 walk-forward（只用之前賽日），唔係每邊各自 refit。
  overlay 差異相對成個分數細（β 40），偏差對兩邊同方向。
- 場內平均只用有賽果嘅出賽馬（退出馬唔計）；live 引擎用成個 field。
- 冇未來資料：兩版都喺窗口賽日之前建好；查表只攞賽日之前嘅紀錄（`trainer_raw`），測試有覆蓋。

## 量度（現有數據，診斷用）

- **今日真實改寫**：11-25 喺 scratch 重建 vs 11-24 live 表 —— 截到 11-24 之後 1,540 個練馬師唔同（語料排除 12 個場次，races 4,276 → 4,229）。
  即係「改寫歷史」唔罕見。用之前賽日做模擬窗口（兩表都截到窗口前一日，冇前視）：11-07 起 Δ −0.00005 [−0.00033, +0.00008]、
  11-14 起 −0.00005 [−0.00018, +0.00010] → 唔會回退（正確）。
- **功效（人工壞表，10 個 7 日窗口，9 月尾至 11 月）**：
  | 壞表 | CI 下界 > 0 | 點估計 > 0 |
  |---|---|---|
  | 剩餘值正負調轉 | 4/10 | 10/10 |
  | 練馬師名洗牌 | 1/10 | 9/10 |
  | 空表 | 1/10 | 8/10 |
  | 剩餘值減半 | 0/10 | 4/10 |
  單一窗口 CI 規則保守；明顯壞嘅表主要靠「連續 3 個點估計」捉。
- **假回退風險**：中性改寫如果 3 個窗口獨立，連續 3 個點估計 > 0 ≈ 1/8。代價 = 表鎖定變舊＋Telegram，Kelvin `unpin` 就恢復。
  呢個係規則本身嘅取捨，日後如果太頻繁要開新實驗號改，唔准喺度靜靜改門檻。
- 金標：`golden_scoring --platform au` 120 匹全部一致；真表 commit 之後引擎讀到嘅 bytes、表、50 個 overlay 全部一樣。

## 已知限制

- 純追加嗰日本身寫壞（例如當日賽果錯位）唔會比到 —— 下一晚佢已經係「歷史」，同上一版一樣。呢類靠
  `data_contract`／`field_health` 喺上游捉。
- 鎖定期間表唔更新新賽日（point-in-time 照啱，只係資訊少咗）。
- 未加 dashboard 顯示；進度喺 forward 總板（`au/trainer_residual_autorollback`）同 `au-trainer-residual-shadow-status.json`。

## 決定

**上線（管線）**：唔改任何分數；有效版本內容同 live 檔逐 byte 一樣。第一晚冇指針 → 第一次重建開第一個版本（冇上一版，唔比）。
