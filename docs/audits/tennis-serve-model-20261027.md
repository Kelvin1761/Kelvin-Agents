# Tennis 發球／接發球模型研究（2026-10-27）

已實際訓練「對手強度校正後嘅發球／接發球實力」勝負模型，並完成未校正版本、只加發球、只加接發球等消融。**新資訊令歷史預測較準，但今次未達穩定性與盈利要求，不升級現役模型。**

完整配置、數字及退步：[EXP-20261027-09](../experiments/EXP-20261027-09-tennis-opponent-adjusted-serve-return.md)。

- 27,263場接受歷史中，27,131場有完整合法服務得分計數。無需要靠補值製造資訊。
- 五個驗證段共12,826場：校正後五段都好過未校正版本，但對Elo+rank只有四段LL較好；2025H1由 .617572→.617713，未過事前5/5閘。候選2025H2確認窗保持關閉。
- 兩個分量都有全dev邊際貢獻；最近段ATP／Clay仍有退步，沒有事後剔走或改揀單項。
- 相同8,240場固定歷史價：rank／raw／adjusted LL為 .621212／.618336／.616462，市場仍 .588085。
- 校正候選假設P/L −788.25u，比上輪rank少蝕147.81u；但原binary對照係−806.12u，差僅17.87u且配對CI跨零，ROI亦由−12.07%變−12.35%。**不能將相對一個較弱候選嘅改善，當成已改善原基準盈利。**

用戶實際只用 **Sportsbet**。上述報價係沿用已固定嘅B365歷史研究對照，無可靠capture時刻，**不是Sportsbet實盤回報或可執行ROI／CLV驗證**。後續實際報價／盈利驗證以Sportsbet為準；沒有假設Pinnacle、Betfair接入。

研究以既有凍結原始來源直接key/ID/date對照，21日延遲重建歷史，fit labels亦做時間隔離；尚未證實publication/observation clock，leakage保持FLAG。2025亦屬重複研究資料，不冒充全新holdout；沒有讀2026/live holdout。

基準 `c41a954575f1b17cfcd62632be7e5b97328155a6`。研究程式於非main分支 `codex-tennis-serve-model-20261027`，完整來源SHA見伴隨JSON。現役完整模型未重放，此為來源隔離研究head，不可當現役實績。

## 重跑

研究程式隨分支／artifact保存，`serve_protocol.json`係今次唯一候選協議；`protocol.json`等EXP07/08 helper原樣保留作基準及市場重用。

```bash
P=/Users/imac/Antigravity-repo/tennis-wong-choi/.venv/bin/python
R=/Volumes/Kelvin\ Hardisk\ 1/WongChoi-Archive/scratch/tennis-serve-model-20261027
export PYTHONDONTWRITEBYTECODE=1
$P research/tennis_serve_model/serve_model.py run --data "$R/tennis-serve-corpus-20261027.json" --out /private/tmp/tennis-serve-replay
# dev已失敗，唔開 --confirmation
$P research/tennis_serve_model/serve_market.py --predictions /private/tmp/tennis-serve-replay/dev_predictions.json --corpus "$R/tennis-serve-corpus-20261027.json" --cache /Users/imac/Antigravity-repo/tennis-wong-choi/src/data/external --out /private/tmp/tennis-serve-market-replay
$P -m pytest research/tennis_serve_model -q
```

原始frozen DB係 `.../scratch/tennis-bugs-20261026/bug_research_baseline.db`，SHA `2e13a17a63871cbd5e108a4c258ec1c7193d1c032752ed74025f8f02249284ac`；新語料SHA `5700413f1b5938bd7254068ff90fdac0bca20922bf5e147fd43e6739bfa9ce07`；協議SHA `30b737758611c1174f8d81c92757bc6fccf23270bbecfe966b02bd61c9435048`。

保存內容包括全部source/protocol/tests、逐場預測、係數、校準bins、同8240場市場對照及分層、corpus audit、gate log、immutable manifest；具體hash及驗證狀態見伴隨JSON。

驗證：20個研究測試、`./檢查.sh --quick`、完整`./檢查.sh`全綠；16組suite通過。Artifact manifest SHA `dc90e287c8f7d81fa88b1db33ddb6eced71c2fdaefd86502a1396cd430351d00`。
