# EXP-20261027-08：直接排名先驗，預測較準但盈利診斷不過關

- 日期：2026-10-27；平台：Tennis；基準 `2e46fa52d535479174f65349376a9a51bca554b0`。
- 假設：賽前排名比例可以喺勝負 Elo 以外補充實力資訊。
- 舊記錄：EXP-20261009-01 未做排名播種；EXP-20261027-07 局數候選未通過確認顯著性。現役 probability_model 用 current rank 選 opponent-rank bucket，唔係直接連續排名先驗。本次不覆寫或「救」EXP07。
- 模型：`sigmoid(beta_elo * Elo_logit + beta_rank * log(rank_B/rank_A))`，A/B 由來源 ID 決定，與勝方無關；無截距、ridge=1、無搜尋超參數。排名須雙方正整數 ≤10,000，缺一方先驗設 0。
- 消融：baseline 原公式、重訓 binary-only、binary+games、binary+rank、binary+games+rank。所有 arm 同語料、同歷史可用時間、同測試人口。
- **基準係來源隔離嘅歷史 Elo 研究模型，不是現役全特徵／風險折扣／實際注碼 replay。** 研究係量新訊號，不可把下文 ROI 當現役實績。

## 語料、事前鎖及切分

同 EXP07：凍結來源 2020–25，27,263 場接受；25,186 場雙方有歷史。直接 source key 驗 winner/loser/date，避開歷史 ordinal 問題。排名有值 ATP 14,235、缺 38；WTA 有值 12,917、缺 73。

- `rank_protocol.json` SHA `dc79629698ed26fd8124c0be6f82c85b39fd880e65070402063ce6d2c89b2cc7`
- rank dataset SHA `d231ff94d2162f54e21da13aa10ebbb04120339fa4d7ba88dfe9ac8630b3f000`
- 2020 暖身，2021 起 expanding fit。來源 tourney_date +21 日 **嚴格早於**預測／fit cutoff 才用結果。所有 arm 相同延遲。
- 2023H1/H2、2024H1/H2、2025H1 五段 dev；確認 2025H2。2025 已於 EXP07 同更早研究讀過，因此不是 untouched holdout；本次只有事前固定候選嘅研究確認。

## 消融結果

| 窗 | N | fitted binary LL | +games LL | +rank LL | +games+rank LL |
|---|---:|---:|---:|---:|---:|
| 2023H1 | 2843 | .634327 | .627149 | .627397 | .621582 |
| 2023H2 | 2051 | .624742 | .618223 | .621277 | .615861 |
| 2024H1 | 2875 | .624336 | .623104 | .616412 | .615543 |
| 2024H2 | 2229 | .623999 | .617704 | .621581 | .615684 |
| 2025H1 | 2828 | .621926 | .621843 | .617572 | .618190 |

+rank LL/Brier 五段都勝 fitted binary。合併 games+rank 喺最後 dev LL/Brier 均輸 rank-only，按事前規則淘汰，**唔因舊確認窗合併數字較靚而反選佢**。

確認窗（1819；排名雙方有值1812），只入選 rank：

| 指標 | binary control | rank | 差（candidate−control） | 95% 配對 CI |
|---|---:|---:|---:|---|
| log loss | .633577 | .627834 | −.005743 | [−.010584, −.000982] |
| Brier | .222356 | .219687 | −.002669 | [−.004818, −.000533] |

- 配對單位 match，4,000 重抽，seed20260826；未聲稱跨實驗多重比較過閘。
- 確認用 fit N=21464、最新可用 training label 2025-06-30；係數 Elo=.6188494987243924、rank=.26609369068683864；無確認窗重新 fit。
- ATP 958：LL .639769→.629392；WTA 861：.626688→.626100，後者優勢很細。
- 退步：PM 321 場 LL .638098→.650523；F 30 場 .543529→.554483。沒有事後剔走佢哋救模型。

## 固定市場／盈利診斷

模型選定後，**先寫** `market_protocol.json`（SHA `5aff40c800dc0d439276a0e704e419631e24fb096132fa62b1430ca5c99dc3d5`）再讀價格：既有2023/24 ATP/WTA XLSX，只用同列配對 B365W/B365L；無 Pinnacle fallback。姓名→ID 有歧義拒絕；tour/surface、21日賽事窗、雙方完整局數一致，雙向唯一、不重用配對。

10,387 原列，排除未完成385、姓名缺／歧義1079、無唯一配對644、價格／列無效37、重用2；餘 **8240 場**。配對減少本身係限制，不當全體實績。

| arm | LL | Brier | 假設下注數 | 假設損益（1u） | 假設 ROI |
|---|---:|---:|---:|---:|---:|
| 原公式 research baseline | .625964 | .218794 | 6666 | −818.09 | −12.27% |
| fitted binary control | .625906 | .218757 | 6678 | −806.12 | −12.07% |
| fitted binary+rank | .621212 | .216558 | 6514 | −936.06 | **−14.37%** |
| 去水價格概率 | **.588085** | **.202366** | — | — | — |

下注規則事前固定為兩邊 `p*odds−1` 最大值 >0 才 1u，無其他門檻／止蝕／擇日；各模型可自行選邊。概率模型原始 sigmoid 用於假設決策，LL/Brier 所有 arm 用相同 .02/.98 機率 clamp。無任何收益參數搜尋。

- rank 對 fitted binary：ΔLL −.004694 CI [−.007421,−.001898]；但每配對場假設損益差 **−.015769u** CI [−.030932,−.001028]（無落注場保留0，逐場配對）。
- rank 對去水市場：ΔLL **+.033127** CI [+.028467,+.037667]；ΔBrier **+.014192** CI [+.012139,+.016230]，仍明顯輸。
- **XLSX 冇可驗證 captured_at，唔係可執行 ROI／CLV／開盤優勢證據。** 以上只係固定價描述性模擬。不能由較低 loss 推論更賺錢。

## 檢查與判決

- leakage：**FLAG**。只用過往比分更新，canonical orientation、同日/21日隔離、fit label embargo 皆有測試；但原始2020–25 publication/observation clocks、排名確切發佈時間及歷史報價時刻未證實。不能聲稱 PIT promotion PASS。
- 初版 harness 曾把未入選 combined arm 嘅確認描述數字一併輸出；初版完整封存 `rank-v1/`。輸出範圍已修正並加 regression test，入選規則／係數／rank 結果不變，未用 combined 確認數字重新選模型。
- 現役評分、注碼、evaluation ruler、golden、資料庫完全不改。
- **預測研究：有改善證據；盈利／上線判決：REJECT。** 對市場仍輸、固定價假設損益更差、沒有全新 forward holdout，不部署本候選。研究 code 只保存非 main 分支。

重跑、完整 artifacts、hash 及驗證見 `docs/audits/tennis-model-training-20261027.md`。
