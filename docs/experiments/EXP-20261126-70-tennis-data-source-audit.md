# EXP-20261126-70：網球數據源審計 —— TML 歷史斷咗一個月、低級別賽事被標成巡迴賽

- **日期**：2026-11-26 · **平台**：Tennis · **性質**：數據管線修正（唔改定價 code、唔改模型）
- **起因**：Kelvin 2026-11-26：「fix the data sources for tennis… could be one of the reason why tennis has been struggling recently… fill as much data as possible」。
- **相關舊記錄**：EXP-20261113-50（Challenger 場地回填 94% → ΔLL +0.0182，REJECT）；memory「Elo 覆蓋率修好咗，模型照樣輸」。**補數據唔等於贏**，所以今次只修「壞咗」嘅，唔加新特徵。

## 審計（定價母體 = Sportsbet 場次，2026-08…11，按月 × 級別；`coverage.py`）
| 級別 | 佔定價 | 缺口 |
|---|---|---|
| ITF | ~55–60% | 場地 0%、保發率 0%、破發點 ~20%、≥10 場往績 ~50% —— **一直冇來源**（結構性） |
| Challenger | ~25% | 場地 13–18%（回填已 REJECT）；其他 ≥78% |
| 未分類 | ~15% | 多數係 UTR；排名 28%、Elo 39% |
| 巡迴賽 11 月 | 細 | 排名 17%、Elo 27% —— 因為「巡迴賽」入面混咗 UTR／Challenger（見發現 2） |
所有級別：輪次 ~0% 已知；`data_quality_score` 冇一場 >65（警告扣分上限 35 → 一律 65 = 剛好過 0.65 門檻，等於冇篩）。

精選 ROI（11-05 起）：Challenger 11-05…14 71 注 −9.0%；11-15… 100 注 **−33.0%**；UTR／雙打／其他合共 ~12 注。

## 發現 1：TML 歷史由 2026-10-28 起每日中止（已修）
- `history_lowtier`（TML Challenger → ATP 資格賽 → ATP 正賽季度 CSV；Challenger／ATP 唯一有發球數據嘅歷史源，Sackmann 06-02 已凍結）
  102 次 run 全部 `PlayerIdentityConflict: tennismylife_history/KE64: 'Toby Samuel' -> 'Stefan Kozlov'`，**成個檔中止**，後面兩個檔都冇跑。log 只寫 WARNING。
- DB：TML Challenger 最新 10-19、ATP 10-26；上游 CSV 有到 11-16（10-19 後 894 場有發球數據）。
- 修正：`_ingest_rows` 逐行，衝突就擱置嗰場、其餘照入（同 `ingest_rankings` 嘅 identity hold 一樣）；擱置數經 `errors` 變 degraded 警告，唔會靜靜消失。
- 副本試跑（外置碟 DB 副本）：入 10,776 場，Challenger 去到 **11-16**（10-20 後 +1,402）、ATP 去到 **11-22**（含 ATP Finals）；擱置 332 場（3%）。
- **未解**：擱置嘅 ID 唔止 KE64（K0DB、E0AC、G0AO…），而且 KE64 同 K0DB 喺我哋 DB 都係「Toby Samuel」—— TML 似乎重新編過一批 ID，或者舊對應本身有錯。要另外查。

## 發現 2：低級別／雙打賽事被 tennis-data 索引用城市名配成巡迴賽（已修）
- 「UTR Men Miami USA」→ ATP_1000、「UTR Women Miami USA」→ WTA_1000、「ATP Challenger 75 Sydney」→ ATP_250、「ATP 250 Stockholm Doubles」→ Stockholm 單打。
- 兩個讀者都揀中錯行：`feature_builder` 優先有場地嘅行（索引有、名稱 heuristic 冇），`props._match_meta` 揀最新嘅行；`tier_of` 先睇 level → 定價當 TOUR。
- 10 月起約 413 場受影響。
- 修正：`tennisdata_competition_meta` 遇到名有低級別或雙打標記（`has_circuit_marker`，重用 `_NAME_LEVEL_RULES`／`is_doubles_competition`；團體賽唔擋）就唔配；每日 backfill 跑 `purge_mismatched_tennisdata_levels` 清走舊錯行（冪等；副本清 71 行，再跑 0）。

## 影響（預先講明，唔聲稱改善）
- 兩樣都係修返**設計本身想要**嘅行為（每日入 TML；名稱有標記就唔估），唔係新特徵；定價 code 冇改，重播（凍結 DB）唔受影響。
- 修正後 Challenger／ATP 發球、Elo、往績會追返到 11 月尾；低級別唔再當巡迴賽定價。**對 ROI 嘅效果冇量度**，要睇之後嘅精選 forward。
- 唔做：ITF 發球數據（冇免費來源；Sofascore／Flashscore 涉及爬蟲同條款，要 Kelvin 決定）；Challenger 場地（EXP-20261113-50 已 REJECT）；`data_quality_score` 門檻（評分邏輯，另案）。

## 監察
「Wong Choi 系統升級方案」session 喺 `field_health_sports.py` 加「來源新鮮度」（每個 `source_provider` 最新 `match_date` 落後，同自己 14 日正常比，拉闊就 Telegram primary）—— 會捉到同類問題。

## 重跑
`docs/experiments/patches/tennis_data_audit/coverage.py`（唯讀，讀主 checkout DB）。

## 覆核（Sol，兩次）
- TML：一場被擱置時可能已寫咗賽事同勝方（真資料，接受）；KE64 仍被拒（冇靜靜合併）；擱置數經 errors 變 degraded（已核 run.py）。
- 級別：「125」誤殺擔心唔成立（真數據所有 125 都係 WTA 125／Challenger 125，例如「WTA 125 Rome」被標成 WTA_1000）；purge 加保險：同 tournament／tour 有其他行先刪（生產 DB 現時 0 個會被刪空）。WTA 125 喺 `tier_of` 當 TOUR 係原有行為，另案。
