# EXP-20261026-03 — Tennis 現況審計及既有 frozen shadow 前向檢查

- 日期／平台：2026-10-26／Tennis。
- 問題：現有資料及量度可唔可信；已登記 Elo shadow 有冇相對現役同市場嘅前向增量。
- 舊記錄：`EXP-20260826-09`、`EXP-20261009-01`、`EXP-20261015-05`。
- Baseline：`36101baa8d4638f7c7a62f876ec105f3eee8e2d4`；live DB 唯讀，冇覆蓋原模型。
- 呢次係既有 frozen shadow 嘅監測／資料品質審計，**冇新候選、冇 fit 或調參，唔另開新 holdout 家族**。

## 語料及規則

`/Users/imac/Antigravity-repo/tennis-wong-choi/tennis_wc.db`；active SQLite 同四份 catalog snapshots
quick-check／row-watermark 通過。完整 snapshot counts、欄位風險同重跑命令見
[全面審計](../audits/tennis-model-review-20261026.md)。

Shadow 用原 `EXP-20261009-01` 既定起點 2026-10-10、版本
`elo-v2-start-of-day.surface-0.35`、同一筆保存嘅 production／shadow forecast；
paired bootstrap by match，4,000 次、seed 20260826。冇改 frozen ruler。
原 harness 370 場包含 winner 衝突同退賽等不合資格賽果；按獨立資料規則排除 21 場，
剩 349 場敏感度診斷。呢個清理唔會將原來不合格嘅資料變成可 promotion 嘅證據。

## 結果

| 群體 | N | Production LL | Shadow LL | 市場 LL | Δ shadow−production（95% CI） |
|---|---:|---:|---:|---:|---|
| 全部 | 349 | 0.68794 | 0.68002 | 0.60636 | −0.00792 [−0.01506, −0.00129] |
| Tour／Challenger allowlist 群體 | 214 | 0.67295 | 0.66303 | 0.63058 | −0.00993 [−0.01832, −0.00095] |

全部 Brier 0.24658 → 0.24305，Δ −0.00353 [−0.00672, −0.00052]；市場 0.20963。
UNKNOWN 層 n=20 點估計略差，CI 跨零；Tour／ITF 層嘅 LL CI 亦跨零，唔隱藏。

現有 PIT research paper book：973 個 value bets，ROI −15.93%；
9,576 個 canonical scorecard rows，raw Brier 0.2082 對市場 0.1921。
正式 family gate `RESEARCH_ONLY`，prop live ledger 0 注。
呢批 row 唔係獨立比賽樣本；native result conflicts 同歷史盤口錯標亦要先處理。

## 正確性修正及判斷

離線審計／回測工具有四類修正：首筆同時 odds pair 及保存骨幹、賽前 forecast／label knowledge cutoff
同多來源去重、SQL error fail-closed、日期範圍 ledger／settled-only ROI denominator。
修正 code 同測試留喺獨立審閱分支；production weights／pricing／thresholds／registry 冇改。

**決定：NEEDS MORE TESTING，繼續 SHADOW；唔 promotion。**
有初步相對現役增量，仍然輸市場，未有足夠 power／calibration／CLV／ROI gate 證據。
**離線工具正確性修正冇通過模型表現閘，唔係已證實嘅預測改善。**

## 重跑

先用修正分支 `codex-tennis-model-audit-20261026`：

```bash
export PYTHONDONTWRITEBYTECODE=1
PY=/Users/imac/Antigravity-repo/tennis-wong-choi/.venv/bin/python
DB=/Users/imac/Antigravity-repo/tennis-wong-choi/tennis_wc.db
"$PY" docs/audits/tennis-model-review-20261026-shadow.py --db "$DB"
cd tennis-wong-choi
PYTHONPATH=src "$PY" scripts/audit_model_data.py --db "$DB" --with-roi
```
