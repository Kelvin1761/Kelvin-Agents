# EXP-20261127-32 預先登記：細場次（5–7 匹）檔位分 —— 紙上 shadow

> 呢份喺任何 forward 數據出現之前寫（2026-11-27），之後唔准改。承 [EXP-20261127-30](EXP-20261127-30-au-reeval-weights-and-draw-ladder.md)
> 嘅檔位診斷同 [EXP-20261102-08](EXP-20261102-08-au-draw-forward-protocol.md)（大場次檔位分，實驗性上線，forward 793/1,000）。
> Kelvin 2026-11-27：「go ahead」（改善空間第 2 項：細場次 arm 等大場次 forward 判完之後先開）。

## 起因

現行 `au_racing_engine/draw.py` 只對出賽馬 ≥ 8 匹（`MIN_FIELD = 8`）計檔位分。EXP-20261127-30 嘅 08-22 後新數據（4,240 場）
顯示 5–8 匹場次內檔對中檔入位差距 **+2.6pp [+0.4, +4.8]**（當時 709 場時 CI 重疊，所以排除咗細場次）。
⚠️ 呢個診斷 band 包括 8 匹（已經有檔位分）；**5–7 匹單獨嘅效應未量過**，而且細場次訊號細，可能量唔到 —— 所以先要過功效預估。

## 候選（凍結）

- **SF7**：出賽馬 5–7 匹，而且唔係直路賽（`draw.is_straight`）：`候選綜合分 = 現行綜合分 + 1.4274 × d`，
  `d = −z(場內檔位排名)`，同 Z8 一模一樣嘅公式同 β（**唔重新 fit** → `fixed_rule`，冇 in-sample 樂觀）。
  場內檔位用分析時 Logic 全部馬，同 EXP-20261102-08 一致。少過 5 匹、8 匹或以上：不變。
- 揀同一個 β 嘅原因：最簡單，而且唔使再睇歷史數據。代價係如果細場次真正效應細過大場次，候選會用過大嘅 β。呢個就係要驗嘅嘢。

## 啟動條件（三樣都要齊先開始計數）

1. **EXP-20261102-08 已經有凍結判決**（status 檔有 `evaluation`）。如果判 `primary_regression`／`ranking_metric_harm`（建議回退大場次檔位），**SF7 取消**，唔開。
2. **功效預估 PASS 率 ≥ 50%**：`power_precheck.py --platform au <base> --gap-pp <5–7 匹內檔對其他檔差距> --coverage <5–7 匹場次佔馬次>`。
   gap 同 coverage 用 2026-08-05 → 啟動前一日嘅 5–7 匹場次量（只量描述統計，唔睇候選表現）。PASS < 50% → 唔開，記錄「量唔到」。
3. 實作接好：shadow 分只寫入 prediction snapshot／`au_draw_forward` 監察（**唔入綜合分、唔上 dashboard 排名**），
   同時喺 `au_forward_tracker.py` 嘅 `FORWARD_TESTS` 登記 `draw_small_field`，並經 `forward_board.publish` 上總板。

## 監察同判決

- **窗口**：啟動後下一個賽日起，只計 5–7 匹、非直路、有完整賽果嘅場次。
- **樣本**：**600 場**（大約 2–3 個月；啟動時按實際每日場數再報預計日期，但數字唔改）。夠數之前只報場數。
- **判決**：v3 `evaluate_full_record`，`fixed_rule`，candidate = 有 SF7，baseline = 現行（5–7 匹冇檔位分），單一 arm、冇 Holm；
  ranking metric `top3_capture_at5`、`ndcg_at5`、`top5_pairwise_auc`（同 EXP-20261102-08 一樣）。
  另外報**同市場差距**（`market_ruler.py`，合約 m3）。
- **結果點用**：`PRIMARY_WIN`／`RANKING_WIN` 而且同市場差距唔變大 → 交 Kelvin 決定上唔上線。其他 → 唔上線，照記。判一次即凍結。
- **通知**：第一次夠數 Telegram primary 一次（tracker `alert_now`）。

## 唔准做

改 β、5–7 匹範圍、樣本數、窗口、指標；用 interim 數字提早判；夠數之後加 arm；用 08-05 → 11-26 嘅候選表現揀 β。
