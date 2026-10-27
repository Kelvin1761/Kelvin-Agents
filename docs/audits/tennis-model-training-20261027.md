# Tennis 模型訓練：預測改善與盈利分開驗證（2026-10-27）

今次實際訓練兩個模型方向，唔係只改投注篩選器。**直接排名先驗降低歷史預測誤差，但固定價假設損益更差；沒有可交付現役嘅盈利改善。** 因此沒有改現役模型、投注門檻或注碼。

## 兩個已完成嘅模型實驗

1. [EXP07：過往局數實力](../experiments/EXP-20261027-07-tennis-game-share-strength.md)。訓練 binary Elo + game-share Elo combiner，並用 fitted binary-only 對照隔離「重新校準」收益。五段 dev 都較準；1819場確認 ΔLL −.003190，95% CI 跨零，未過預先規定要求。
2. [EXP08：直接排名先驗](../experiments/EXP-20261027-08-tennis-continuous-rank-prior.md)。訓練 binary Elo + log-rank-ratio；同時測試 games+rank，按五段 dev 拒絕不穩定合併，沒有看確認結果反選。

研究對照係來源隔離、延遲21日嘅歷史 Elo，不是現役全特徵模型及實際下注 replay；不能把下列數字當現役模型 ROI。

| 確認窗2025H2（1819場） | fitted binary control | binary+rank |
|---|---:|---:|
| log loss（低較好） | .633577 | .627834 |
| Brier（低較好） | .222356 | .219687 |

相對 control，ΔLL −.005743，95% match-paired CI [−.010584,−.000982]；ΔBrier −.002669，CI [−.004818,−.000533]。ATP/WTA 點估計都較好，WTA 優勢很細，PM/F 層仍有退步。呢啲係歷史研究改善證據，唔係盈利證據。

## 盈利檢查阻止咗一個錯誤升級

事前固定同書配對 B365 報價、1u、EV>0、無參數搜尋。2023/24 ATP/WTA XLSX 同來源身份、日期窗、surface、雙方局數唯一配對，餘8240場。

| 相同8240場 | fitted binary control | binary+rank | 去水價格 |
|---|---:|---:|---:|
| log loss | .625906 | .621212 | **.588085** |
| Brier | .218757 | .216558 | **.202366** |
| 假設下注 | 6678 | 6514 | — |
| 假設損益 | −806.12u | −936.06u | — |
| 假設 ROI | −12.07% | **−14.37%** | — |

候選仍明顯輸市場。相對 fitted control，每配對場假設損益差 −.015769u，CI [−.030932,−.001028]；沒有下注場保留0計配對差。**XLSX 沒有可靠報價擷取時間，以上不是可執行 ROI、CLV 或開盤策略回報。** 佢足以反對「預測較準所以一定更賺錢」，不足以證明實盤回報。

## 證據限制與已做防線

- 原始資料 frozen Sackmann 2020–25 12批；無2026/live holdout參與本次訓練或選擇。所有接受比分逐一驗完成狀態；raw source key、winner、loser、date 對照，不依賴曾出錯嘅 history ordinal。
- 30,879原始場→27,263接受；25,186有雙方歷史。2020暖身；2021起expanding fit；2023H1至2025H1五段驗證；fit標籤亦做21日隔離。
- 同一賽事賽後資訊唔入自己預測。來源只記起始日，統一延遲21日；原始 publication/observation clock 未證實，**leakage狀態仍為FLAG，不能 promotion**。
- 2025曾在其他研究讀過；今次確認亦不是全新holdout。未宣稱跨實驗多重比較或實盤power過閘。
- 初版EXP08把未入選combined確認描述數字一併輸出，已完整保留`rank-v1/`，修正輸出範圍並加測試；候選選擇、係數及rank數值沒有改。沒有用該數字救已淘汰combined。
- 沒有覆寫現役模型／資料、沒有調threshold或借用holdout調參。golden、data-contract calibration、model evaluation ruler均不改。

## 可重現與保存

研究基準：`2e46fa52d535479174f65349376a9a51bca554b0`。研究程式只保存於非main分支 `codex-tennis-score-model-20261027`，來源 commit 見伴隨 JSON。

封存：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-score-model-20261027/`（約37MB）。內有`source/`全部protocol、實作、測試及凍結係數、兩份語料、三組逐場輸出、初版記錄及`artifact_manifest.json`。

- 原始 frozen DB：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-bugs-20261026/bug_research_baseline.db`；SHA256 `2e13a17a63871cbd5e108a4c258ec1c7193d1c032752ed74025f8f02249284ac`；唯讀，無複製大DB。
- score corpus SHA `76fabab1e4730121adccc5a80179560b3e51ac14a582f8a023f0460817b40a23`；rank corpus SHA `d231ff94d2162f54e21da13aa10ebbb04120339fa4d7ba88dfe9ac8630b3f000`。
- manifest SHA `db207b53905b6c7a1beb91a587737aeabcb0542031edaef55cb23e4510c07e33`。
- Corpus audit：active SQLite及4份catalog snapshot均`ok`；沒有用runtime snapshot替代歷史catalog。

由已保存研究分支：

```bash
P=/Users/imac/Antigravity-repo/tennis-wong-choi/.venv/bin/python
R=/Volumes/Kelvin\ Hardisk\ 1/WongChoi-Archive/scratch/tennis-score-model-20261027
export PYTHONDONTWRITEBYTECODE=1
$P research/tennis_score_model/score_model.py run --data "$R/tennis-score-corpus-20261027.json" --out /private/tmp/tennis-score-replay --confirmation
$P research/tennis_score_model/rank_prior.py run --data "$R/tennis-rank-corpus-20261027.json" --out /private/tmp/tennis-rank-replay --confirmation
$P research/tennis_score_model/market_diagnostic.py --predictions /private/tmp/tennis-rank-replay/dev_predictions.json --corpus "$R/tennis-rank-corpus-20261027.json" --cache /Users/imac/Antigravity-repo/tennis-wong-choi/src/data/external --out /private/tmp/tennis-market-replay
$P -m pytest research/tennis_score_model -q
```

驗證：30個研究測試通過；`./檢查.sh --quick`通過；完整 `./檢查.sh` 正常權限重跑通過，16組suite全綠（含NBA642測試、Tennis858測試）。第一次sandbox跑嘅4個NBA失敗均因`ps`禁止，兩份log都封存，沒有改測試或跳過suite。

下一輪模型方向應優先提供 Elo／排名以外嘅獨立資訊，例如**對手強度校正後嘅發球及接發球實力**，沿用固定時間fold、單項消融同市場對照；先驗證相對市場嘅增量，再考慮新forward快照。不能只加大已有訊號權重，亦不能因ROI負就掃新threshold。
