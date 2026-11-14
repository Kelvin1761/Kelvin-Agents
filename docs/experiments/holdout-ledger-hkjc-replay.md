# HKJC 歷史回放 holdout 登記簿

語料切法（寫死，見 `docs/plans/2026-11-14-hkjc-history-research-programme.md` §1）：
dev 2020/21–2023/24 ｜ **holdout 2024/25–2025/26** ｜ terminal 2026/27。

規矩：每次喺 holdout 計任何數字（就算只係睇一眼）都要記一行；每個家族預先寫低最多幾多個候選會嚟 holdout（預設 ≤ 3），同一家族 Holm。

| 日期 | 家族（計劃步） | 候選 | dev 結果 | holdout 結果 | 決定 | 實驗 |
|---|---|---|---|---|---|---|
| 2026-11-14 | 第 3 步診斷性 refit | F 版（全 fit） | WF dev Good +1.89、capture +0.98、頭二 +2.81（CI>0），Gold +0.20 | Gold +1.70、Good +2.51、capture +1.98、頭二 +1.99（全 CI>0） | 回放 PASS；live 未上（Kelvin） | EXP-20261114-03 |
| 2026-11-14 | 第 3 步診斷性 refit | S 版（段速固定） | WF dev Good +1.53、capture +0.74、頭二 +2.29（CI>0），Gold +0.24 | Gold +1.93、Good +2.16、capture +1.61、頭二 +2.22（全 CI>0）；剔調參場次 Gold +2.77 | 回放新 baseline；live 交 Kelvin | EXP-20261114-03 |
| 2026-11-14 | 第 4 步段速 | FT_b50（主） | Gold +0.42 [+0.03,+0.84]、Good +0.03 | Gold +0.18、Good +0.18、capture +0.23（96% null）、頭二 +0.23，CI 全跨零 | 邊緣，唔上線；決定清單 | EXP-20261114-04 |
| 2026-11-14 | 第 4 步段速 | F_b50 | capture +0.42 [+0.06,+0.78] | 頭二 −0.47 | REJECT | EXP-20261114-04 |
| 2026-11-14 | 第 7 步直路 | 冇直路經驗 raw −1.0 | dev Gold +3.45（98% null）、Good 0 | Gold 0、Good 0、capture −0.42（輸 null） | REJECT | EXP-20261114-05 |
| 2026-11-14 | 第 8 步初出馬 | 練馬師初出率 δ=0.75 | Gold 0、Good +0.16（96% null）、capture +0.13（98%） | Gold +0.12、Good −0.06、capture +0.12、頭二 +0.23（CI>0） | 邊緣，決定清單 | EXP-20261114-06 |
| 2026-11-14 | 第 9b 步出擊 | 換上頂級騎師 δ=1.0 | Good +0.52（CI>0、100% null）、Gold +0.04 | Gold −0.88、頭二 −0.82（CI 全負） | REJECT | EXP-20261114-08 |
| 2026-11-14 | 第 10 步新訊號 | 泥地段速 FT（泥地賽事） | capture +1.44（CI>0、99% null）、Good +0.92 | Gold +0.60、Good −1.19 | REJECT | EXP-20261114-09 |
| 2026-11-15 | 19 組重建第二批（v4 尺） | 維度 × 情境互動 C=0.005（家族 5 個設定，Holm：holdout 用 99% CI） | Δlog-loss −0.00069 [−0.00119,−0.00018]、AUC +0.0022（CI>0）、Gold +0.60、Good +0.44 | Δlog-loss −0.00069 [95% −0.00136,−0.00002；99% 上界 +0.00016]、AUC +0.0009（跨零）、Gold +0.35、Good +0.53、100% null | REJECT（Holm 99% 唔過；未校正 95% 會過）；決定清單 | EXP-20261115-04 |
