# EXP-20261016-07 結果：eq2_N6 + S2 一齊，同 eq2_N6 上線實作

- **預先登記**：[protocol](EXP-20261016-07-au-eq2n6-plus-s2-protocol.md)
- **性質**：用戶要求上線、接受研究證據（來源 FLAG，**唔係正式 v3 WIN**）。兩個 forward shadow 照跑做上線後確認。

## 一齊測（研究診斷，1,482 場／41 日 OOS）

| 比較 | fixed arm | refit arm | 判決 |
|---|---|---|---|
| C（eq2_N6 + S2）vs base | Gold **+1.96pp [+0.49, +3.69]** | Gold **+1.62pp [+0.21, +3.05]** | PRIMARY_WIN |
| C vs eq2_N6（S2 嘅邊際） | Gold +0.34、Good −0.41pp | Gold −0.27、Good −0.34pp | **REJECT（both_arms_reject）** |

**依登記規則 1：只推 eq2_N6；S2 繼續等 forward（EXP-20261016-03）。**
S2 喺 eq2_N6 之上冇邊際 —— 兩個改善好可能捉緊同一樣嘢（場內相對嘅往績質素）。

## eq2_N6 引擎實作

- `engine_core`：`FORM_QUALITY_*` 凍結常數、`_form_quality_digest`（重用 PQ digest 揀選規則，
  上限 6 場）、`refresh_form_quality`（由 Formguide 重算，live 同重播同一條路）、
  `_merged_form_quality`（場內 z；冇值就用舊 0.6／0.4 組合）。
- `au_auto_orchestrator`：場內摘要之前叫 `refresh_form_quality`；摘要加 `form_quality_field_*`。
- `dimensions`：新 leaf `form_quality_score`（入排名、**唔算證據**）；`stability = 近績質素分 × 1.0`，
  **係數 0.371 不變**（§8：fixed arm WIN → 用現行權重上線）。近績分同表現質素分保留做報告組件同
  安全欄證據 —— 安全欄觸發同之前一樣。
- `matrix_mapper.with_form_quality`：舊 feature 向量冇新 leaf 時，用佢自己嘅 fallback（舊組合）補上，
  所以存檔 Logic、golden、未更新嘅研究工具結果同上線前一模一樣，唔會靜靜變 60。
- `au_dump_engine_leaves`：評分前叫 `refresh_form_quality`（缺咗會喺輸出前失敗，同其他 enrichment 一樣）。
- 覆盤報告：新 leaf 歸入「近況／穩定性」改善主題。

### 引擎版重新量（真正上線嘅算術）

研究版場內標準化只用有賽果嘅馬；引擎同表現質素分一樣用全場報名馬。11% 匹馬嘅 leaf 因此唔同，
所以用引擎 dump 重跑 §8：

| arm | Gold | Good | Top5 AUC |
|---|---|---|---|
| fixed | **+1.82pp [+0.26, +3.49]** | +1.01pp [−0.68, +2.87] | +0.0055 [−0.0001, +0.0115] |
| refit | **+2.02pp [+0.72, +3.39]** | +1.75pp [0.00, +3.68] | **+0.0080 [+0.0028, +0.0133]** |

研究診斷 `PRIMARY_WIN / fixed_arm_win`，arm Holm p fixed 0.025、refit 0.006。live guard PRIMARY_WIN。
（一匹馬 ability 因 `proven_class` 4 位捨入差 0.0001，同之前 arm 一樣用 production 算術重算。）

## 檢查

- 單元測試 1,796 過；registry 快照只郁 FEATURE_KEYS／ABILITY_FEATURE_KEYS／MATRIX_FORMULAS／
  FEATURE_LABELS（安全欄證據清單、維度權重不變）。
- golden：存檔 feature 經兼容補值 → 120 匹全部一致。**golden 未覆蓋新 leaf**，要等存檔用新引擎重評。
- data contract：重新 calibrate（指紋 `132355ae4442`）；用新引擎重評 2026-10-16 Gatton 8 場，
  發佈閘 exit 0，`form_quality_score` 係 `new-field` 警告 —— 上線後有新數據要再 calibrate。
- 模型說明重新生成；`./檢查.sh` 全過。

## 發佈前提

`./保存.sh` 會同步四條線 production 並自動 merge，要用戶確認。前面仲有 §8 把尺（EXP-20261015-20）、
試閘分退出（EXP-20261016-01）、班次 parser（EXP-20261016-05）未發佈；release 係串行。
