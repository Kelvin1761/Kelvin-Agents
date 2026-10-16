# EXP-20261016-77 上線決定：試閘速度搬去試閘備戰（用戶決定，唔係實驗 WIN）

- **決定**：Kelvin 2026-10-16「將試閘速度搬去試閘備戰，冇顯著變差 good, so go ahead and make sure we update wong choi dashboard as well」。
- **依據**：[EXP-77 結果](EXP-20261016-77-au-trial-speed-to-preparation-results.md) —— §8 `both_arms_reject`（冇改善），但排名指標冇顯著跌
  （唔似 EXP-01 F6c 剷走試閘行嗰陣三個排名指標 CI 全負）。上線理由係**可解釋性**：所有試閘證據集中喺試閘備戰，
  速度分只反映正式賽（見 memory「Kelvin 試閘維度設計方向」）。
- **已知代價（照寫）**：v3 全紀錄 Gold −0.04pp、Good +0.16pp（CI 跨零）；分層 11–12 匹 Good CI 全負；§8 fixed OOS Gold −0.27pp。

## 改動

- `performance_pf_metrics`：L600 環境分一律唔計試閘 PF 行（以前少過 6 場嘅馬會計）。
- 新 leaf `trial_speed_score`（試閘 L600 分）：試閘 PF 行個體 L600 平均，場內 z（≥ 3 匹有值），60 − 20z；只限正式賽少過 6 場嘅馬。
- 試閘備戰 = 0.5 × 試閘密度（`preparation_score`）+ 0.5 × 試閘 L600 分；係數 0.2524 不變。
- `_build_field_summary` 加 `trial_speed_field_count/mean/stdev`；引擎輸出 `trial_speed_detail`。
- 報告／dashboard：renderer 以前**冇試閘備戰維度嘅細項分支**，而家兩個組件都有細項；dashboard 前端照讀「評分構成」，backend 132 個測試過。
- 覆盤報告：新 leaf 歸「段速／試閘／速度訊號」主題。

## 驗證

- 上線引擎同評估過嘅研究候選（`ts_split` 變體）乾淨窗 23,949 匹 ability 同試閘 L600 分**逐匹差 0**。
- golden 重錄（fixture 冇試閘 L600 分 → 60，試閘備戰向中性收一半，例如 63.38 → 61.69，係預期）；data contract 重新 calibrate；模型說明重生；`./檢查.sh` 全綠。
- 一場真賽事（2026-10-14 Caulfield R2，scratchpad 副本）重新出報告，試閘備戰兩個組件同細項正常顯示，dashboard parser 讀到六個維度。

今日改動嘅 forward 確認（EXP-74）凍結喺 `2d7ec14c`，**唔包括**呢個改動。
