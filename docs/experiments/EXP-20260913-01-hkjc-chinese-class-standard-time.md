# EXP-20260913-01 — HKJC 中文班次標準時間正規化

- **日期**：2026-09-13
- **平台**：HKJC
- **假設**：Facts 近績使用中文班次時，`get_standard_time()` 應命中同班 C1–C5，唔應靜靜借用 C4。
- **搜索過嘅舊記錄**：`EXP-20260912-01` 首次發現並刻意延後；本實驗獨立處理，冇再改官方時間表。
- **改到嘅組件**：`.agents/scripts/inject_hkjc_fact_anchors.py`、對應 regression tests；
  release policy 加精確 HKJC root-runtime allow-list，避免批准後 activation `targets=[]`。

## 缺陷（可獨立證明，唔靠績效數字）

標準時間 JSON 用 `C1`–`C5` 做 key，但存檔 Facts 近績大量使用 `第一班`–`第五班`。
`get_reference_sections()` 本身識正規化，`get_standard_time()` 卻直接拼 raw label；exact key
搵唔到之後按 `C4 → C3 → C5 → C2 → C1 → G` 借值。

跑馬地 1200 米 baseline 實測：

| 輸入 | 舊結果 | 正確同班標準 | 判定 |
|---|---:|---:|---|
| 第一班 | 69.70 | 68.95 | 錯 |
| 第二班 | 69.70 | 69.10 | 錯 |
| 第三班 | 69.70 | 69.50 | 錯 |
| 第四班 | 69.70 | 69.70 | 碰巧正確 |
| 第五班 | 69.70 | 69.85 | 錯 |

即係除第四班之外，中文班次全部靜靜變成 C4。修正與績效方向無關；即使回測數字相反，
仍然應修，符合模型評估合約 §7 嘅 correctness 條件。

## 修復

新增單一 `_normalise_race_class_key()`，由標準時間同參考段速 lookup 共用：

- `第一班`–`第五班`、`第 1 班`–`第 5 班`、`C1`–`C5`、`Class 1`–`Class 5` → C1–C5
- 一／二／三級賽、Group／Grade／G1–G3 → G
- 新馬／Griffin → GR
- 未知 label 原樣保留；兩個 caller 原有嘅 missing/fallback policy 不變，唔捏造新映射

同時修正部署 routing：`inject_hkjc_fact_anchors.py` 同兩份 HKJC 標準時間資料位於歷史性
repo-level `.agents/scripts/`，舊 activation policy 只識 domain package，會將呢啲 release
判成 `production_sync_domains=[]`。新增三個檔案嘅 exact allow-list；未知 root script 仍然唔猜 domain。

## 配對 replay

- **baseline code**：`84d20f25acaec8c0e7915511c11581dc34e9bff6`
- **candidate**：只加班次正規化；時間值本身不變
- **標準時間表**：固定由 commit `cf98f9580d58e841cc509c46ba5ce5a1f2146171` 取
  `2025-08-26` 官方表；早過全部 2026 評估場次，避免用 2026-08-25 新表倒灌歷史
- **語料**：21 meeting／200 場；同場同馬；evaluation sample hash
  `655b59043c6c9ecddddfaea6468400d267c4671e38873845d60231a45c80827f`
- **影響範圍**：1,437 匹馬 finish-time block 有變，涉及 194 場；14/200 場 Top-5 次序／邊界有變
- **dev**：162 場；**terminal**：38 場（2026-07-08、07-12、09-06、09-09）

| 指標 | baseline all | candidate all | dev Δ / 95% CI | terminal Δ / 95% CI |
|---|---:|---:|---:|---:|
| Gold | 13.000% | 12.500% | −0.617pp [−1.852, 0.000] | 0.000pp [0, 0] |
| Good positional | 22.500% | 22.000% | −0.617pp [−1.852, 0.000] | 0.000pp [0, 0] |
| Top-3 capture@5 | 62.167% | 62.167% | 0.000pp | 0.000pp |
| NDCG@5 | 52.595% | 52.697% | +0.126pp | 0.000pp |
| Competitive recall@5 | 57.775% | 57.875% | +0.123pp | 0.000pp |

Stage 4 表現候選判決係 **`REJECT / primary_regression`**：兩個 primary 嘅 dev 點估計各跌
1 場，所以唔准當成表現改善。

### §7 guardrail

- dev 兩個 primary 嘅 paired bootstrap CI 上界都係 `0.000`，**唔係全負**。
- terminal 兩個 primary 逐場零差。
- 預先聲明 cohort：field-size `≤8 / 9–10 / 11–12 / 13+`，baseline 首選 SP
  `≤3 / 3–5 / 5–10 / 10–20 / >20`；兩個 primary 合共 18 格，**冇一格 CI 全負**。
- leakage audit PASS：候選只讀賽前已知嘅歷史班次；固定表生效日早過評估 meeting；
  賽果／SP 只作 label 同 cohort，冇入評分。

## 驗證

- 中文 C1–C5 lookup：5/5 同 compact key 完全一致；另覆蓋帶括號文字及 `第 3 班`。
- HKJC high-quality regression：8 tests OK（2 個 repo 已知 expected failure）。
- HKJC Auto：119 tests OK。
- `py_compile`：PASS（cache 指去 `/private/tmp`）。
- `./檢查.sh --quick`：PASS；AU/HKJC golden 都係 120/120。
- HKJC data contract：最近 172 場／2,181 匹全部欄位合格。
- Release policy regression：三個 HKJC root-runtime 檔全部 route 到 `hkjc`；未知 root script 保持空 target。
- Golden `--record`、data-contract `--calibrate`、模型說明生成器已實跑；生成差異只係今日新增語料／
  生成時間，並非本修正造成，故冇混入 release。現有 scoring fixture 仍 120/120 一致。

## 結論

呢個候選**冇通過表現閘，唔係一個已證實嘅預測改善**。但舊 code 將明確第一／二／三／
五班當第四班係可獨立證明嘅錯誤，而 primary／cohort 冇顯著退步；因此按合約 §7：

**決定：KEEP（正確性修正）／表現候選 REJECT。**

## 重跑

```bash
PYTHONDONTWRITEBYTECODE=1 python3 .agents/scripts/tests/test_hkjc_high_quality_features.py
PYTHONDONTWRITEBYTECODE=1 WC_DISABLE_HKJC_PROFILE_ENRICH=1 \
  python3 /private/tmp/hkjc_class_normalization_gate.py
```
