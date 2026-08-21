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

## 六、補 test（2026-08-21 第二輪）

第一輪四個修復只有一個有 test 保護。喺一個有多過一個 agent 同時寫嘅 repo，
冇 test 嘅修復會被靜靜移走 —— 當日已經三次見到 working tree 被其他 session 掃走。
所以補齊：

| 修復 | Test | 鎖住咩 |
|---|---|---|
| AU feature key 契約 | `test_au_expected_features_match_the_engine` | 同**引擎** `FEATURE_KEYS` 比，唔同 fixture 比 |
| 名字註解剝除 | `test_draw_annotation_in_source_names_is_not_a_mismatch` + `test_a_real_name_change_is_still_caught` | 「(檔位 N)」唔算改名，但真改名照要捉到 |
| 馬群分層輸出 | `FieldSizeReportingTests`（5 個）| 分層一定出、每場只落一個桶、`holdout_share_of_races` ≠ 日期百分比 |
| 退役工具拒絕閘 | `test_retired_weight_search_guards.py`（10 個）| exit 非零、講明退役、指去代替品、拒絕喺任何重活之前 |

`test_holdout_share_of_races_is_not_the_date_fraction` 直接砌一個「9 個疏日 +
1 個密日」嘅語料：10% 嘅**日期** → 82% 嘅**場次**。呢個就係當日實測到嗰個
「15% 日期 = 36.2% 場次」缺陷嘅單元化版本。

### 順帶發現：`au_weight_improvement_search.py` 本身已經爛

寫退役閘門嘅 opt-in test 嗰陣試過真跑：兩個工具喺 argparse 之前就載入全 archive
（一次 2 分鐘），而 `au_weight_improvement_search.py` 直接爆
`KeyError: 'race_shape'`（`scripts:157`）。所以 opt-in test 改成靜態檢查逃生門存在，
唔真跑。**呢三個工具唔止過時，其中一個已經行唔通。**

## 七、評估合約抽出成正式檔案

`docs/model-evaluation-contract.md` 之前唔存在（上一個 prompt 假設佢有）。
已建立，並且把審計第 2 節**改成指向佢**而唔係留兩份 —— 兩份唔同步係呢個 repo
最貴嘅 bug 形態。`AGENTS.md`、交接文件、`model-regression-gate` skill 都加咗指標。

## 八、`configured_scorer` 靜靜丟掉候選維度（2026-08-22 發現並修）

寫完 test 之後想量另一個 session 剷 `race_shape` 嘅效果，`au_eval --matrix-weights`
返 **全部 +0.0000**。按 memory `ab-identical-means-unwired` 嘅規矩先查 wiring —— 中。

`configured_scorer` 嘅 normalised dict 係 iterate **live `MATRIX_WEIGHTS`**：

```python
normalised = {key: weights.get(key, 0.0) / total for key in MATRIX_WEIGHTS}
```

所以任何唔喺 live 權重表嘅維度會**靜靜消失**。實測 mapper 出 **7** 個維度
（`stability, pace_perf, race_shape, jockey_trainer, class_weight, track, form_line`），
而 live `MATRIX_WEIGHTS` 得 **5** 個 → `form_line` 同 `race_shape` 兩個都被丟掉。

兩個後果：

1. **`form_line` 由來都冇得測。** 佢權重一直係 0，所以永遠喺丟掉名單。
   `au_weight_improvement_search.py` 個 docstring 明寫佢要測
   「the currently zero-weighted `form_line` dimension」—— 嗰個目標**結構上做唔到**，
   而且佢而家 opt-in 就爆 `KeyError: 'race_shape'`。
2. **`race_shape` 2026-08-22 退出排名之後，再也 A/B 唔返轉頭。**
   個 harness 會答「呢把尺分唔開」，而真相係「你個維度我無視咗」。

呢個係 repo 嘅招牌形態：**靜靜返一個錯答案，唔係報錯。**

**修法**：iterate live 權重同候選 key 嘅**聯集**，而 mapper 出唔到嘅 key 大聲死
（`ValueError`）。候選 key ⊆ live 權重表（過去所有用法）行為**完全不變** ——
`test_candidate_inside_live_weights_is_unchanged_behaviour` 鎖住。

### 修好之後量到嘅嘢（1,453 場，同一份語料）

舊權重（含 `race_shape` 0.13485）做候選 vs 現行 live（已剷）：

| | 值 |
|---|---|
| 頭5位 AUC dev | **+0.0019**（舊權重好） |
| 頭5位 AUC holdout | **−0.0041** [−0.0102, +0.0016]（新好，但區間跨 0）|
| gold / good_pos / pass / champion | +0.34 / +0.48 / +0.41 / +1.10（舊好）|
| gold_strict / winT3 | −0.14 / −0.14（新好）|

**兩個方向都過唔到閘**：舊做候選 → holdout 區間跨 0；新做候選 → dev 係負
（−0.0019，違反「dev 唔准負」）。**呢把尺喺呢份語料上分唔開兩者。**

⚠️ 即係話：剷 `race_shape` 呢個已 ship 嘅改動**唔係靠正規閘門支持**，
係靠 403 場乾淨切片嘅洩漏論證。dev 講「留住好」／holdout 講「剷咗好」嘅符號分裂
本身就係洩漏指紋（dev 71.5% 場次嘅矩陣含住自己賽果），同 EXP-06 一致。
呢個可能係合理嘅（剷走一個洩漏特徵，回測分數本來就會跌），但**同記錄嘅判決規則有偏離**，
Kelvin 應該知。

## 結果

`./檢查.sh` **全部過**，`run_tests.sh` **九個 suite 全綠**（第一次）。
新增 20 個 test（AU 18、shared 2），全部快（退役閘門 suite 0.28s）。

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
