# EXP-20261016-76 結果：`timing_trial_600m_avg_speed` 點解從來冇值 —— 改動**唔上線**（照登記停）

- **預先登記**：[protocol](EXP-20261016-76-au-trial-speed-field-dead-protocol.md)（`20413fca`，rebase 後喺 `b4b90dfb` 之上）。

## 點解冇值（審計）

- 寫入者：`_build_timing_summary` 由每場往績嘅 `l600_split_seconds` 計 600m 速度；解析只認 Racenet 格式
  `(600m / 00:34.123)`（`_parse_formguide_entries`）。
- Sportsbet Formguide 冇逐駒 600m 分段：乾淨窗 68,287 條試閘行，場級 L600 差 41.9%、頭馬時間 65.1%，**逐駒 600m 0%**。
- 結果：乾淨窗 28,974 匹 `timing_trial_600m_avg_speed` 同正式賽 `timing_600m_avg_speed` **都係 0% 有值**。
- 試閘速度資訊冇浪費：場級 L600 + 輸距（個體 L600）已經經 `pace_figure_score` 入分（少過 6 場嘅馬，試閘 PF 行保留）。

讀呢套欄嘅地方：`_form_score`（新馬試閘時間 +5／+3，會影響排名）、`_trial_score`（+4／+2，試閘分已退出排名）、
`_sectional_breakdown`（段速分，權重 0）、`_l600_speed_brief`（報告文字）。

## 驗證（判決）

剷走 `_form_score` 同 `_trial_score` 兩段，改動前後 production dump（`au_dump_engine_leaves.py`，全語料 32,448 匹）：

- **乾淨窗（08-05 起）：0 匹改變。**
- **全語料：199 匹改變、15 場排名改變** —— 全部喺 2025-12（29）、2026-01（7）、2026-04（92）、2026-05（50）、2026-06（21），
  即係 Racenet 時代存檔（嗰陣仲有逐駒 600m 時間，條規則真係觸發過）。改變嘅 feature：trial_score 165、form_score 149、form_quality_score 149。

登記寫明「全語料逐位元相同，有任何一匹唔同 → 停，唔上線」，所以**今次唔發佈**。改動同測試留喺分支 `claude-au-trial-speed-dead-20261016`。

## 跟住點做（要用戶決定）

live（全部 Sportsbet）同乾淨窗都唔受影響；受影響嘅只係 Racenet 時代嘅舊存檔回放。如果要上線，要當一個新嘅 §7 決定
（「數據源已經唔存在嘅規則」）重新登記，並寫明舊存檔回放會有 15 場排名改變。
