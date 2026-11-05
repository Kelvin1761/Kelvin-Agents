# EXP-20261105-08 正確性修正：重播用咗過期 `career_race_starts`（2026-08-05～09，23 個場次）

- **日期**：2026-11-05；**平台**：AU；**類型**：§7 正確性修正（重播／判決數據，唔郁 live）。
- **發現**：EXP-20261105-07 初出馬診斷 —— dump 入面 `career_starts == 0` 但有往績嘅馬 1,695 匹，全部喺 08-05～09。

## 成因

嗰批 Logic 由舊 parser 寫：Facts 寫 `生涯: 7`（冇冒號），舊 parser 要冒號 → 存咗 `career_race_starts = 0`、`career_tag = DEBUT`。
`data_prep._extract_career_starts` 早已修好，live 每次經 `enrich_logic_from_facts` 由 Facts 重抽，所以 live 冇事。
但 `au_dump_engine_leaves.py`（au_eval、walk-forward、§8、matrix refit 嘅唯一數據來源）直接讀 Logic，冇 enrich →
重播將有往績嘅馬當初出：`trial_performance_applies` 回 True，試閘分／試閘 L600 照計；`preparation_cycle` 亦食錯場數。

全語料掃描（47,884 匹）：存值同 `facts_section` 重抽唔一致 **2,086 匹，全部「0 → n」，全部喺 08-05～09**；冇一匹缺 `facts_section`。

## 修正

- `data_prep.refresh_career_starts(logic)`：由已存 `_data.facts_section` 重抽 `career_race_starts`／`career_tag`（同 live enrich 一樣嘅 parser）。
- `au_dump_engine_leaves.py` 喺 `refresh_form_quality` 之前叫佢。Live 路徑唔變（golden 唔受影響）。
- 測試：`tests/test_refresh_career_starts.py`（真實形狀 `生涯: 7` + 存值 0 → 7／ESTABLISHED）。

## 判決（v3 fixed_rule，3,433 場，baseline = main dump `heavy-c2/BASE.json`）

`scratch/au_track_simplify_judge_20261103.py`：改咗 **119 場**（只喺 08-05 23、08-06 15、08-07 24、08-08 54、08-09 3），34 場頭兩選有變。

| 指標 | Δ | 95% CI |
|---|---|---|
| Gold | −0.087pp | [−0.240, 0.000] |
| Good | +0.029pp | [0.000, +0.096] |
| top3@5 | 0.000 | [−0.063, +0.060] |
| AUC | +0.004 | [−0.014, +0.025] |

冇 primary 顯著負、冇分層 CI 全負 → **§7 PASS，上線**（正確性修正，唔聲稱改善）。

- 修正後仍有 3 匹 `career_starts == 0` 但 `prep_stage` 唔係 debut（2026-06-10），Facts 本身寫 0，唔屬今次範圍。
- 影響：之後所有用 dump 嘅判決（包括 v3／§8 基線）喺 08-05～09 會同之前嘅數字有細微分別；舊實驗記錄唔重算。
- Dump：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/career-starts/`。
