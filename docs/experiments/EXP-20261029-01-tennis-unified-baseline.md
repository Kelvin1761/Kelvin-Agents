# EXP-20261029-01：統一研究語料及保存預測 baseline

- 日期：2026-10-28開始、29日完成基準量度（Sydney）；平台：Tennis。
- 假設／目的：新候選之前，量清楚保存預測有幾多可以忠實重現；同一群體比較模型與市場。沒有候選或調參。
- 搜尋：EXP-20261027-05/06/07/08/09、EXP-20261026-04/05、外部項目筆記及 frozen tennis-v1。舊REJECT不重開。
- Baseline：runtime `1f46514bf9f7ab3386e9054363da93baf9ad3d83`，歷史保存預測含多版本；registered model仍為8b149c85 shadow，兩者分開記錄。
- 實作：`research/tennis_unified/warehouse.py`／`baseline.py`／`protocol_f00.json`；方法／source lock先於baseline量度。原frozen source及hash保留在外置證據。

## 語料、資格及結果

完整live DB以一個pinned read transaction做SQLite backup，40張表所有rows/indexes，source/destination counts一致，integrity_check通過；1,939,058,688 bytes，SHA256 `67e62704fc83299ee1cb2172eed9a747aa9d46415bd24715c7fde6969aa02f58`。Central同時核對4份已登記archive、active DB及watermarks全過，冇用archive代替live DB。

15,851行預測 → 3,845個有首份賽前forecast及一致完成結果嘅fixture → 排除280冇首價、3報價未喺forecast前完成觀察／入庫、15inactive → 3,547場。時鐘須aware，首價MIN(id)不合格時不轉用後價。

Saved Elo base＋active components、nudge cap、原selection side、原segment-risk shrink完整重現；排除66 metadata不足、1,734無active Elo、4 nudge sum不符，餘1,743場誤差≤1e−6。呢個係忠實歷史subset，唔係今日完整模型重跑。

| 同一1,743場 | 保存模型 | 去水市場 | market−model gain／95% match CI |
|---|---:|---:|---|
| LL | .662752 | .572953 | −.089799 [−.105992,−.073217] |
| Brier | .234516 | .195363 | −.039153 [−.046255,−.031930] |

4,000 match bootstrap、seed20260826、95% CI；沒有候選有效性檢定／選擇。混合tour/level及多個歷史版本，唔當main-tour今日表現。有frozen fixture兼parity只有7場，LL gain .022041／Brier gain −.007905，兩項CI都跨零，未達600／power；完整raw-source資格亦未證實。

全量warehouse audit另外有critical：83個爭議／無效winner fixture、1個winner不屬於該場、3,087/13,243個Aug27後props係post-start或無法定時。保留／隔離原觀察，唔以刪除或倒填證據修數字。詳細row-flow、全部排除及paired rows外置保存。

## 決定及後續

**NEEDS_MORE_TESTING／DATA_QUALIFICATION_REQUIRED**。Baseline量度完成；不是model KEEP或promotion。全部SEEN_DEV，沒有untouched holdout；沒有實盤下注。Raw-source/label隔離、目前daily board缺口及完整feature provenance要先處理，再開候選。正式模型／注碼／ruler未改。

Leakage：FLAG，legacy fixture及feature/raw-source原始資格不足。Golden/data-contract：無模型評分參數更改；repo完整gate通過。不能把市場在legacy群體領先，當成今日model已被完整驗證。

## 重現

Repo研究分支 `codex-tennis-unified-research-20261028`；baseline實作SHA256 `396a86c3e117fa4305f85a6402ce9d904382396e8841868dc79418ced666de58`，Python3.9.6／NumPy2.0.2。

```bash
P=/Users/imac/Antigravity-repo/tennis-wong-choi/.venv/bin/python
R='/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-unified-20261028'
PYTHONDONTWRITEBYTECODE=1 "$P" -m research.tennis_unified.baseline --db "$R/warehouse.db" --output "$R/baseline-new-replay"
```

原結果：`$R/baseline/`、`run_manifest.json`、`preflight_lock.json`、`warehouse_inventory.json`、`runtime/`。完整進度及其他限制見[進度報告](../audits/tennis-unified-research-progress-20261028.md)。
