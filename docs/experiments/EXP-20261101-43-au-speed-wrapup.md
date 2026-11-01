# EXP-20261101-43 速度重建收尾：切換去 speed.py、存原始 L600、修顯示、加逐仗證據（排名零變化）

- **日期**：2026-11-01；**平台**：AU；**類型**：結構／正確性／顯示（唔改排名）。
- **用戶**：「go ahead with 收尾做『code 簡化 + 修 bug + dashboard 顯示逐仗證據』（切換去 speed.py、存原始 L600 秒數、顯示逐仗證據）」。
- **前因**：EXP-39 至 42 證實現行 L600 分（近期加權）係量得到嘅最好版本；公式改動等 S2 forward（EXP-20261016-03）。

## 改咗乜

| | 之前 | 之後 |
|---|---|---|
| 計算位置 | `_pf_aggregates` 一份、`_pace_figure_score` 一份，常數兩邊各自定義 | 全部叫 `au_racing_engine/speed.py`（`run_values`／`horse_speed`／`choose`／`score`／`evidence`） |
| 聚合 | 12 個 PF 欄位計 `_avg`／`_best`，另外 tempo／rt／early pace；10 個 2026-08 起 0% 有值 | 只聚合速度分用嘅兩個（`l600_delta`、`own_l600_delta`）；`_parse_pf_token` 仲識讀舊歸檔 |
| field summary | 6 條 PF 列表 + `pf_complete_profile_field_count`（冇人讀） | 2 條 |
| 抽取 | 只存 `L600 Delta`（減咗手寫標準表），標準一改歷史就錯，查唔到標準嘅場地成條數消失 | 往績行加 `RaceL600:<秒>`；引擎 parse 做 `race_l600`（數據欄，冇分數讀） |
| 說明文字 | 計分用 own（賽事 L600 + 輸距），但寫「所在賽事 L600…唔係本駒個體 split」 | own：「本駒末段估算（近期加權）…（估算＝賽事 L600 對基準＋輸距×0.17 秒）」；race 先寫賽事數 |
| 「數據」行 | 「實測 L600（主訊號）」顯示 race-level 平均（同上面計分用嗰個數唔同）；「L600 原速」讀 Racenet 欄位，Sportsbet 年代永遠空 | 「逐仗證據」：每仗日期、場地、路程、賽事 L600 對基準、輸距、本駒估算、近期權重 |
| Dashboard 比較圖 | 近期加權上線（1c7e1794）改咗句子，`L600_RE` 對唔到，比較圖靜靜消失 | regex 接受舊、own、race 三種寫法（有測試） |
| Dashboard 逐仗 | 冇 | `renderSpeedEvidence` 表（日期／場地路程／賽事 L600／輸距／本駒估算／權重） |

## 驗證

- **全語料重評 byte-identical**：`au_dump_engine_leaves.py` 用 origin/main（`1275b287`）同新 code 各跑一次，4,049 場、
  36 MB JSON `cmp` 一模一樣。
- golden：120 匹全部一致。AU tests 1,240 passed；dashboard parser 76 passed。
- 實際渲染（2026-11-01 Albany R3，scratch 複本）同本機 dashboard：比較圖返咗，逐仗證據表正確（瀏覽器睇過）。

## 冇做

- Racenet backfill（`WC_PF_BACKFILL`、`_pf_backfill_for_race`）留低：舊歸檔重評仍然要。
- `au_ml_dataset.py` 仲讀已唔聚合嘅欄位（一直係 None），研究腳本，冇改。
- 原始 L600 只對新抽嘅頁有；歷史 Formguide 要重抽先有（唔影響排名）。
