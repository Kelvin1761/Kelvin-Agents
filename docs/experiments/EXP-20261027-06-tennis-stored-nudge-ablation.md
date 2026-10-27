# EXP-20261027-06 — Tennis：直接保存分項嘅 nudge 消融（dev-only）

- 日期：2026-10-27；睇本次消融結果之前先鎖定方法。
- 假設：現役額外 nudges 可能重複已有勝負訊號，令純 Elo 機率變差；需要逐項消融證明，而唔係憑直覺刪除。
- 舊記錄：EXP-20260826-09 §16、AUDIT_2026-08-09 已否決紅土 nudge-off；前者錯誤重建 Elo 有洩漏，後來 stored-feature 重建亦顯示移除會變差。本次只因有新增紀錄、可直接讀 **forecast 保存嘅 component／base logit** 並嚴格重現而重開量度；唔重算 history 或舊 features。
- 基線：97eaa7f9（Tennis source 063c8799）；同 EXP-20261027-05 完整資料投影、同一時間窗／一場一預測。

## 預先鎖定

- 全部已記錄、可證明賽前、結果一致及最早賽前報價可用嘅紀錄；沿用 EXP-05 eligibility，不按輸贏揀例。
- 保存嘅 `elo_base_logit` + 逐項 component 原有 weight、active flag，重現 clipped sigmoid。未移除時誤差必須 <=1e-6，否則排除並列明；不換用今天重算的 Elo。
- Baseline 與 all-off 同一 subset。若冇 active Elo backbone，排除，避免把全部刪除變成 0.5 擲毫。
- Candidate = 全部 9 個 nudges 歸零；另 9 個獨立 leave-one-out arms 作必要 ablation。冇 fit、冇掃權重／surface／閾值。
- 指標：配對 LL／Brier，4000 match bootstrap、seed 20260826、95% CI；10 個 arms 作 Holm 多重比較調整；分層只報完整 ATP／WTA／UNKNOWN，唔挑最好一層。
- 主要目標只係資訊增量診斷；paper policy 對照保持原有選擇 side、最早價、EV>0、每筆 1u，不改下注方向、價範圍或 stake。
- 此批結果已在其他審計看過，**全部係 dev，沒有 untouched holdout**。不論統計如何，本次只可 REJECT 或凍結候選等新前向證據，不能 KEEP／promotion，不能聲稱已改善盈利。

## 結果

進行中；method lock 另存 hash／UTC timestamp。

## 重建層核對／v2 addendum（v2 績效之前）

v1 嚴格忠實子集只有 326/3492：92 無 base logit、1694 無 active Elo、4 nudge sum 不符、1376 最終機率不符。v1 all-off ΔLL −0.002682，CI [−0.009639,+0.004012]；無可部署結論。

查核 mismatch 證明 `predictions.model_probability` 係 `price_match_snapshot` **經 segment-risk shrink 後**嘅機率，但 v1 只重建 raw combiner；此外 source JSON 本身保存 `selection_side`，應用該原始方向，而唔係今日 matches 排序。v1 係非折扣／碰巧可重建子集診斷，不可當全模型結論。

v2 唯一修正係完成 evaluation parity：各 arm 用原始 `selection_side`、原始 `segment_risk_discount`、原始 `no_vig_market_probability`，套用同一記錄嘅 `p = market + (raw_p-market)*(1-discount)`。缺 metadata 照拒絕，忠實誤差仍 <=1e-6。唔擬合折扣、唔用今日 level 揀折扣、唔換 base／cohort／arm／bootstrap／判決門檻。新增單元測試鎖住 full-pipeline parity，先過測試再量 v2。

呢次係明示嘅量度層修正，唔係候選成功。v1 輸出／hash保留，v2 仍係 dev-only，任何改善都不能 KEEP 或改 promotion 判決。

## v2 結果（完整已保存後處理）

3492 個固定來源中：92 缺 base logit、1694 冇 active Elo、4 nudge重建不符；其餘 **1702 場**全部重現最終保存機率至 <=1e-6。風險折扣及選擇方向取原紀錄，冇按今日賽事級別估。

| 同一1702場群體 | Baseline | All nudges off |
|---|---:|---:|
| Log loss ↓ | 0.661209 | 0.661847 |
| Brier ↓ | 0.233838 | 0.234119 |
| LL Δ | | +0.000638，95% CI [−0.001381,+0.002606] |
| Brier Δ | | +0.000281，CI [−0.000597,+0.001156] |
| EV>0 紙上平注 | 1393 單 | 1366 單 |
| P/L | −274.056u | −283.567u |
| ROI | −19.67% | −20.76% |

同群市場 LL 0.568570／Brier 0.193648。關掉nudges並無填補市場差距。

逐項 leave-one-out 全數報告（LL Δ，負數較好；10項 Holm 修正）：

| 移除項目 | LL Δ | 95% CI | Holm p（近似bootstrap尾機率） |
|---|---:|---|---:|
| serve_return_edge | +0.000372 | [-0.000106,+0.000831] | 1.000 |
| recent_form_edge | -0.000416 | [-0.000932,+0.000109] | 1.000 |
| opponent_rank_bucket_edge | -0.000171 | [-0.001051,+0.000690] | 1.000 |
| tournament_level_edge | -0.000055 | [-0.000492,+0.000357] | 1.000 |
| round_performance_edge | -0.000005 | [-0.000053,+0.000038] | 1.000 |
| big_match_edge | -0.000018 | [-0.000377,+0.000328] | 1.000 |
| pressure_edge | -0.000069 | [-0.000449,+0.000302] | 1.000 |
| head_to_head_edge | +0.000160 | [-0.000413,+0.000726] | 1.000 |
| fatigue_edge | +0.000399 | [+0.000008,+0.000786] | 0.460 |

**決定：REJECT 本次移除nudges候選。** 冇可靠精度改善，紙上ROI亦更差；單項消融無一個通過多重比較。唔取點估計最好嘅一項再試參數。此結果唔證明每個nudge有用，亦唔係新版live或untouched holdout驗證。

v1／v2全部輸出及v1原始程式SHA已保留，方法更正明示，不作成功改寫。正式模型、折扣、權重及風險／注碼參數未改。研究工具只保存研究分支，不自動合併失敗候選程式到 main。
