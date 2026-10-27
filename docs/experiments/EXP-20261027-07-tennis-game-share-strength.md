# EXP-20261027-07：以過往局數訓練球員實力

- 日期：2026-10-27；平台：Tennis；研究基準 commit：`2e46fa52d535479174f65349376a9a51bca554b0`。
- 假設：過往已完成比賽嘅局數佔比，喺勝負 Elo 以外有額外預測力。
- 舊記錄：EXP-20261009-01 因缺 games 欄位未做 MoV；舊 external_backtest 只存在未具本次因果隔離證據嘅 set-margin K multiplier。本次係獨立 game-share rating + 訓練 combiner，並非調 K。
- 候選：二元勝負 Elo logit + 局數 Elo logit，無截距 ridge logistic；對照係相同語料嘅原公式 Elo，以及重新訓練嘅 binary-only logistic。不是現役全特徵模型完整 replay。
- 語料：凍結 Sackmann 2020–25 原始批次 12 份；直接用來源賽事 ID、match_num，不經歷史 ordinal。30,879 原始場，排除範圍外 2,460、未完賽／不支援比分 1,156，接受 27,263；雙方有歷史特徵 25,186。
- 時間：2020 暖身；2021 起 expanding fit；2023H1/H2、2024H1/H2、2025H1 五個 dev fold。來源日期係賽事起始日，所有 arm 一律 `start+21d < prediction_date` 才吸收結果；fit 同樣隔離標籤。這是保守重建，唔係已驗證歷史 observation clock。
- 事前 protocol SHA：`6af8b8125e13d9e316650f43e7340382c4fdcb255bc60b470cfed9bb32aad655`；dataset SHA：`76fabab1e4730121adccc5a80179560b3e51ac14a582f8a023f0460817b40a23`。

| 窗 | N | baseline LL | fitted control LL | game candidate LL |
|---|---:|---:|---:|---:|
| 2023 H1 | 2843 | .634335 | .634327 | .627149 |
| 2023 H2 | 2051 | .624767 | .624742 | .618223 |
| 2024 H1 | 2875 | .624481 | .624336 | .623104 |
| 2024 H2 | 2229 | .624146 | .623999 | .617704 |
| 2025 H1 | 2828 | .622143 | .621926 | .621843 |
| 2025 H2 confirmation | 1819 | .634327 | .633577 | .630387 |

五段 dev LL/Brier 都好過兩個對照，但確認窗未達事前顯著性要求：
- 對 fitted control：ΔLL −.003190，match-paired bootstrap 4,000/seed20260826 CI `[−.007106,+.000675]`；ΔBrier −.001446，CI `[−.003140,+.000219]`。
- 對 baseline：ΔLL −.003940 CI `[−.008046,+.000079]`；Brier .222665→.220910。
- ATP 958：control LL .639769→.636381；WTA 861：.626688→.623718；兩邊點估計較好，但唔代表各自顯著。
- PM 層 321 場 LL .638098→.643051、F 層 30 場 .543529→.553978，均有退步。
- 2025 已用於較早 Elo 研究，本次 confirmation **唔係全新 holdout**。沒有市場價、可執行收益或 CLV 證據，唔准聲稱盈利改善。

**判決：REJECT 本次過閘／上線；有方向訊號，證據仍不足。** 沒有改現役模型、門檻、注碼、golden 或 evaluation ruler。研究模型不入 main。

研究實作：`research/tennis_score_model/`，模型分支／raw artifacts、驗證及保存資訊見收尾報告。新假設必須獨立 protocol，唔准更改本次窗口去救結果。
