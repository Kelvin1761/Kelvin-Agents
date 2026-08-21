# EXP-20260821-05 審計後續修復：三個閘門一直係壞嘅

- **日期**：2026-08-21
- **平台**：AU + HKJC（共用工具）
- **類型**：閘門／測試修復（**冇改任何 model code、權重、feature 或評估方法**）
- **起因**：`docs/audits/2026-08-21-repo-model-audit.md`
- **搜索過嘅舊記錄**：EXP-01/02/03/04，同 `MEMORY.md` 85 條
- **⚠️ 編號**：我原本寫成 `-04`，同另一個 session 嘅 `EXP-20260821-04-au-draw-field-size-scaling` 撞名。嗰個被 EXP-03 內文引用（「候選見 EXP-04」），所以編號歸佢，我改做 `-05`。

## 一、`racing_data_health.py` 嘅 AU 分支由頭到尾係壞嘅

`EXPECTED_FEATURES["au"] = {"speed","form","class","pace","weight","draw"}` ——
**六個名一個都唔存在**。AU Logic 檔真實 key 係 `form_score` / `pace_map_score` 等 18 個。
所以 `MISSING_FEATURES` 對**每匹馬**都觸發。

另外 `FACTS_NAME_MISMATCH` / `SOURCE_NAME_MISMATCH` 亦係每匹都中：Facts / Racecard
寫「Family Of League (檔位 11)」，Logic 只存純馬名，比較時冇剝走註解括號。

實測（2026-08-21 Beaudesert，8 場）：

| code | 修之前 | 修之後 |
|---|---|---|
| FACTS_NAME_MISMATCH | 77 | **0** |
| SOURCE_NAME_MISMATCH | 77 | **0** |
| MISSING_FEATURES | 77 | **0** |
| SOURCE_LOGIC_MISMATCH | 8 | 8（真訊號，見下） |

三個場次合計清走 **207 個假警報**。**HKJC 完全冇變**（1 + 1 前後一樣）——
呢個係修改前特意錄落嚟做對照嘅。

### 點解冇人發現

只有 `hkjc_orchestrator` 會叫呢個掃描；**AU 主流程從來冇接**。
而審計原本嘅建議係「幫 AU 接上去」—— 如果照做，會即刻 block **100%** AU deploy
（`deploy_allowed` 恆為 False）。**所以 AU 冇接嘅真正原因係接落去會爆。**

### test 自己鎖死咗個 bug

`test_racing_automation_common.py` 個 `_meeting()` fixture 用**同一批假名**
餵 `feature_scores`，所以 test 一直綠。呢個正係 `data_contract.py` docstring 講嘅
形態：一個自己餵 input 嘅 test，睇唔到常數同現實脫節。

已加 `test_au_expected_features_match_the_engine` —— 佢**唔同 fixture 比，同引擎比**
（`FEATURE_KEYS`），所以下次有人寫個唔存在嘅 key 就會紅。

## 二、`SOURCE_LOGIC_MISMATCH` 係真訊號，但嚴重程度分類錯

Racecard 列**全部報名**，Logic 只留**出賽**。所以 mismatch 係退出馬造成，正常。

核實（400 個有賽果嘅場次，Logic 匹數 vs 賽果 CSV 實際出賽匹數）：

| | 場數 | 佔比 |
|---|---|---|
| Logic == 賽果 | 362 | **90.5%** |
| Logic < 賽果 | 20 | 5.0% |
| Logic > 賽果 | 18 | 4.5% |

**我冇改佢個 severity。** 由 error 降做 warning 就係「改檢查令佢過」——
要改就要改成同**出賽名單**比而唔係同報名名單比，嗰個係設計決定，留俾 Kelvin。

⚠️ 剩下 9.5% 係真差異，值得跟：最極端係
`2025-09-13 Flemington R4` Logic 9 vs 賽果 18（少一半）。

## 三、`au_eval.py` 加咗馬群分層（附加輸出，判決規則冇改）

場數指標（Gold / Good位 / Pass）冇按馬群大細正規化。dev 901 場實測
（時間因素已隔離）：

| 馬群 | 場數 | Gold |
|---|---|---|
| ≤8 | 211 | **31.58%** |
| 9-10 | 260 | 15.38% |
| 11-12 | 228 | 9.21% |
| 13+ | 202 | 8.91% |

3.5 倍差距。而 dev 平均馬群 10.51、holdout 9.08，**≤8 匹嘅場次由 dev 佔 23%
變成 holdout 佔 44%** —— 表面「holdout Gold 20.70% 好過 dev 16.13%」主要就係咁嚟。

同桶比較之後差異細而且**方向混雜**（≤8: 31.58→33.63、9-10: 15.38→13.33、
11-12: 9.21→9.65、13+: 8.91→5.00）。所以正確講法係
**「pooled 嗰 +4.6pp 係組成造成」**，唔係「holdout 一律差過 dev」——
我審計第一版寫錯咗後者，已更正。

`au_eval.py` 而家一定會印：真實 holdout **場次**佔比（15% 日期 = **36.2%** 場次）、
兩邊平均馬群（差 >0.5 就出警號）、同逐桶 Gold / Good位 / Pass。

## 四、三個已退役嘅權重搜索工具加咗拒絕閘

`au_matrix_weight_search.py`、`au_clean_7d_weight_search.py`、
`au_weight_improvement_search.py` —— argmax / coordinate descent，
實測 dev good_pos +3.80 / holdout −5.61。而家直接 exit 2 並指去 `au_matrix_refit.py`。
歷史對照要 `WC_ALLOW_RETIRED_WEIGHT_SEARCH=1`。

## 五、長期紅嘅 test

`test_hkjc_high_quality_features.py` 兩個 test 由 2026-08-03 起紅。核實：
`rating_series` 只存在於 `scratch/hkjc_high_quality_dimension_gate.py`，
而 `parse_normalized_sectionals` **成個 repo 都唔存在**（`AGENTS.md` 原本寫「兩個都
只存在於 scratch」，只對一半）。改為 `unittest.expectedFailure` + 寫明原因。

## 結果

`./檢查.sh` **全部過**，`run_tests.sh` **九個 suite 全綠**（第一次）。

## Baseline（順帶記錄）

**AU**（`b51793d7`，1,413 場 / 14,121 匹）
頭5位 AUC：all 0.6793 · dev 0.6871 · holdout 0.6631
gold 17.79% · good_positional 23.53% · pass 46.99% · champion 25.73%

**HKJC**（264 場，`hkjc_no_regression_gate.py`）
Gold 19（7.20%）· Good 68（25.76%）· Pass 124（46.97%）· Champion 73（27.65%）
MRR 0.4656 · Order Issue 101 · Avg Top4 Hits 2.083 · Passing candidates: none

⚠️ **AU 同 HKJC 嘅 Gold 唔可以直接比。** HKJC 個 7.20% 接近 AU 嘅
`gold_strict` 6.24%，唔係 AU 個 `gold` 17.79%。

**決定**：KEEP（全部係閘門／測試修復，冇 model 改動，golden 兩平台各 120 匹一致）
**commit**：未 commit

## 重跑

```bash
export PYTHONDONTWRITEBYTECODE=1
./檢查.sh
PYTHONPATH=. python3 .agents/skills/shared_racing/scripts/racing_data_health.py \
    --platform au --meeting-dir "<AU meeting>"
cd .agents/skills/au_racing/au_wong_choi_auto/scripts
python3 au_dump_engine_leaves.py --out /tmp/leaves.json
python3 au_eval.py --data /tmp/leaves.json
python3 .agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_no_regression_gate.py
```
