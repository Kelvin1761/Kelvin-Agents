# EXP-20261104-01 Dashboard 顯示修正：試閘備戰判讀、leaf 標籤、直路賽劇本（分數零差）

- **日期**：2026-11-04；**平台**：AU；**baseline**：`274d0277`。
- **用戶**：「please also make sure our dashboard are reflecting and displaying the new structure」。

## 搵到嘅三個顯示問題（全部舊有，唔係拆檔引起）

1. **試閘備戰冇判讀、冇證據**：`_describe_matrix`／`_matrix_anchor_lines` 冇 `preparation`，dashboard 只見
   「試閘備戰 暫時只算中性參考」同空白證據欄 —— 但 `preparation_detail` 明明有「往績表試閘 2 課、2 課跑入前列 +3.38」。
2. **leaf 標籤手抄**：`_feature_label` 漏咗 `form_quality_score`、`preparation_score`、`trial_speed_score`，dashboard 組件印原始英文 key。
3. **直路賽戰術劇本寫「首彎前」**：劇本喺數據準備階段砌好，唔知係直路賽（Flemington ≤1200m 冇彎）。

## 改動

- 新 `_describe_preparation_matrix`（試閘密度加分項 + 試閘 L600 狀態）同 `preparation` anchors（試閘交代、試閘密度加分、試閘 L600、狀態週期）。
- `_feature_label` 改由 `dimensions.LEAF_SPECS` 推導（唯一真源）。順帶 `health_score` 由手抄「健康分」變 registry 嘅「備戰完整度分」。
- `_tactical_scenario_text`：`_straight_course()` 時「首彎前」→「早段」、「入直路前」→「末段」。

## 核對

- 全語料 dump：4,210 場、41,283 匹，分數 0 匹有差。
- 報告文字（10-20..10-26，2,607 匹）：只有預期三處變 —— 試閘備戰 2,607、狀態與穩定性組件標籤 2,607、直路賽劇本 25。
- Dashboard：`generate_static._collect_meeting` 讀 2026-11-03 Flemington（scratch 副本重評）：試閘備戰 verdict
  「試閘密度：試閘交代密度足夠（+3.4）；試閘 L600 數據唔夠…」、證據兩行；R4 直路賽劇本「盡量喺早段切入前列」。
