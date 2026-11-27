# EXP-20261127-70：網球數據深入檢查 —— 最大可補缺口係身份連結（只量度）

- **日期**：2026-11-27 · **平台**：Tennis · **性質**：只量度；冇改 code、冇改模型
- **起因**：Kelvin 2026-11-27：「do another deep check to see if we are missing any data, and if we can fill any new data in to help the analysis performance」。
- **分工**：Claude 主導；Codex Terra 寫審計腳本（`deep_audit.py`、`history_gap.py`）；Gemini Hydrogen 盤點 51 個網球實驗判決；Codex Astra 評估新數據候選。結論由 Claude 核實。
- **前一份**：EXP-20261126-70（TML 斷咗一個月、低級別被標成巡迴賽，已修 2474da92；生產今朝 09:31 已補返 Challenger 到 11-16、ATP 到 11-22）。

## 1. 最大可補缺口：tennisexplorer 往績冇連到 Sportsbet 球員（已核實，未修）
- tennisexplorer 往績**一直有入庫而且新鮮**，但掛喺「姓 + 縮寫」格式嘅 player（例如「Amarilla R.」30 場、最近 11-23；「Pinho T.」最近 11-21；「Djoubri S.」最近 10-27 而且 tour 錯標 ATP），
  從來冇連到 Sportsbet 嘅全名 player（「Ramiro Amarilla」有 20131、27086 兩個紀錄，0 往績）。
- 原因：`sources/identity.py` 嘅 `plan_merges` 只將**正規化後完全同名**嘅 player 歸組（`entity_mapping.normalise_player_name` = 去空白 + 細楷），所以「amarilla r.」同「ramiro amarilla」永遠唔會合併。
- 規模（11-09…11-26 Sportsbet 場次，球員場次；姓 + 名首字母配一個近 60 日有 TE 往績嘅唯一 player）：

| 級別 | 球員場次 | 已有 TE 往績 | 唯一 TE 對應 | 多個對應 | 冇對應 | 雙打組合 |
|---|---|---|---|---|---|---|
| ITF | 1,830 | 46% | **38%** | 1% | 7% | 9% |
| UTR | 610 | 23% | **57%** | 0% | 21% | — |
| Challenger | 902 | 77% | 10% | 0% | 1% | 11% |

  連結之後上限：ITF ~84%、UTR ~80%、Challenger ~87%。`history_gap.py` 抽樣（每級 80 人）分類一致：冇往績嘅入面「名對唔上」ITF 75%、UTR 91%、Challenger 45%。
- **未核實**：姓 + 首字母配對係機械相似（「Andrew Li ↔ Li A.」呢類常見名可能錯人）。正式連結前要更強證據，例如兩邊喺同一日對同一個對手有比賽。
- **價值未知**：Elo 由 Sackmann／TML 建（`HISTORY_PROVIDERS`），TE 往績主要餵 form／fatigue／round／H2H 特徵；EXP-20261027-06 消融嗰批特徵冇貢獻；EXP-20261009-01 一類（Elo 覆蓋率 27%→79%）亦冇令模型贏市場。**要喺凍結 DB 上連結前後重定價先知**（Astra 同意係首選驗證）。

## 2. 其他數據狀況（審計 `deep_audit_out.md`）
| 項目 | 狀態 | 判斷 |
|---|---|---|
| TML 歷史 | 已修，生產補返到 11-16（Challenger）／11-22（ATP）；18 組 ID 名稱衝突、275 場擱置 | TML 似乎重編過一批 ID，另案 |
| `composite` 排名 | 10-30 起冇新行；975 名球員冇其他較新排名，當中 672 人只有 composite（多數 ITF／UTR） | 原因未證實，值得查 |
| `wta_numeric_pdf` 排名 | 11-09 起冇新行，但 `wta_ranked_players_api` 覆蓋同批 1,515/1,549 人、更新到 11-23 | 有替代，低優先 |
| WTA 發球（`wta_match_stats`） | 11-05 起停；每日 `wta_serve_profiles_stale` 警告 | **刻意**：EXP-20261026-04 REJECT，11-06 重寫刪咗抓取；警告係雜訊 |
| `prop_price_log` | 11-05 起停 | **刻意**：重寫「一本帳」，價格證據改記 `prop_tracker` |
| 雙打 | DB 有 186 場 Sportsbet 雙打（11-09 起），0 snapshot／prop／精選 | 下游已擋，只係令覆蓋率分母虛高 |
| ITF 發球數據 | 一直 0% | 冇免費來源 |
| 輪次 | ~0% | Sportsbet 冇；影響細 |
| `data_quality_score` | 一律 65 | 評分邏輯問題，另案 |

## 3. 營運（唔影響數據質素，記低跟進）
- 網球分析時間 11-21 起由 ~12 分鐘升到 ~35 分鐘（場次數冇變；11-24 18:00 得 2 場都用咗 30 分鐘）。頭 ~24 分鐘喺 `settlement_backlog`（`price_day` 第一個 stage）；今朝寫咗 966 行 `match_results`（平時每日 100–150）。今朝連 TML 補數用咗 61 分鐘。要睇 18:00 run 恆常要幾耐。

## 4. 新數據候選（Hydrogen 盤點「未試過」＋ Astra 評估）
- 未試過：傷患／退賽新聞；新球員用排名做 Elo 起點；分場地 Elo 按場數向整體收縮；ITF 發球（要爬蟲）；多莊家比價。
- Astra：首選係上面第 1 項嘅連結驗證；賺錢角度最值得驗係「落注時仍成交得到嘅跨莊／跨盤價差」；**冇一個候選已證明扣成本後贏市場**。

## 重跑
```bash
/usr/bin/python3 docs/experiments/patches/tennis_data_audit/deep_audit.py     # → deep_audit_out.md
/usr/bin/python3 docs/experiments/patches/tennis_data_audit/history_gap.py    # → history_gap_out.md
```
