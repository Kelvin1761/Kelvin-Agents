# EXP-20261102-08 預先登記：大場次檔位分 —— 用戶接受嘅實驗性上線 + forward 監察

> 呢個 forward 開始前寫（2026-11-02），之後唔准改。承 [EXP-20261102-07](EXP-20261102-07-au-draw-big-field-results.md)
>（四個 arm 全正，Holm 後 0.068 REJECT）。用戶：「ok 開 i think 檔位 is something our model really need」。

- **候選（凍結）**：Z8 —— 出賽馬 ≥ 8 匹：`候選綜合分 = 現行綜合分 + 1.4274 × d`，`d = −z(場內檔位排名)`（0 = 最內，
  退出後檔位）；少過 8 匹不變。β = EXP-07 walk-forward 最後一日（用 2026-08-05 → 10-31 全部賽果）。
  揀 Z8 唔揀 ZD8：最簡單、ZD8 三段 β 差唔多（1.32／1.52／1.48），分路程冇帶嚟額外嘢。
- **2026-11-02 改為 USER-ACCEPTED EXPERIMENTAL LIVE**（任何 forward 數據出現之前；用戶：「i want to have something live and
  keep monitoring if we can already see signal」）：檔位分由 `au_racing_engine/draw.py` 直接入綜合分（overlay `draw_feature`），
  `WC_AU_DRAW_LIVE=0` 即時回退。**呢個唔係已證實改善**（EXP-07 Holm 後 p 0.068）。
  場內檔位用分析時 Logic 全部馬（賽前已知；退出馬未剔走嘅場次會同 harness 用嘅「實際出賽馬」唔同，語料約 18% 場次）。
- **監察**：`au_draw_forward.py` 由儲存 Logic 重算：上線版（連 `draw_feature`）vs 同一份但檔位分 = 0。
  未夠數每晚寫 `interim`（累計 Gold／Good／前三場數，描述用，唔係判決）。
- **窗口**：2026-11-02 起（EXP-07 語料最後一日係 11-01），只計 ≥ 8 匹兼有完整賽果嘅場次。
- **樣本**：1,000 場（約 24 個賽日、11 月尾）。夠數之前只報場數，唔出結果指標。
- **判決**：v3 `evaluate_full_record`，`fixed_rule`（β 凍結），candidate = 有檔位、baseline = 冇檔位，單一 arm、冇 Holm；
  ranking metric `top3_capture_at5`、`ndcg_at5`、`top5_pairwise_auc`。`primary_regression`／`ranking_metric_harm` →
  建議回退（Kelvin 決定）；PRIMARY_WIN／RANKING_WIN → 由實驗性轉正式；其他 → 維持實驗性，交 Kelvin。
  判一次即凍結（status 檔有 `evaluation` 就唔再重算）。
- **通知**：`au_forward_tracker.py` `draw_big_field`；scheduler `step_draw_forward` 每晚更新，夠數 Telegram 一次。

## 唔准做

改 β、門檻、樣本數、窗口；用 interim 數字提早判（佢只係描述）；夠數之後再加 arm 或者換指標。
