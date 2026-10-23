# EXP-20261023-04 NBA 開季數據：逐隊／逐球員由上季補缺（正確性修正，唔係模型改善）

- **日期**：2026-10-23
- **平台**：NBA
- **假設**：新季回退（EXP-20261021-01 嘅 Issue 1）只喺整個聯盟 feed 少於 25 行先觸發；feed「夠行數但有隊缺席」時會靜靜冇數據。**可證偽**：用真實 API 數有幾隊缺，同重抽後缺口有冇補到。
- **搜索過嘅舊記錄**：EXP-20261021-01（新季 fallback）。冇其他相關記錄。
- **改到嘅檔案**：`nba_extractor.py`（`fetch_with_season_fallback` 加 `fill_below`；team_stats／team_dvp／player_advanced／key_defenders 四個 feed 啟用）、`test_nba_season_fallback.py`。
- **唔係**：冇改機率、權重、揀腿規則。**冇聲稱改善。**

## 事故（2026-10-23）
- `LeagueDashTeamStats` 用今季查詢，只回傳**今季已打過波**嘅球隊：2026-10-23 係 28 隊（用 2025-26 係 30 隊）。DEN、CLE 要當晚先打首戰，所以冇列。
- 28 ≥ `MIN_TEAM_ROWS`(25) → 整個今季 feed 被信任；DEN／CLE 嘅 `team_stats` 同全部球員 `advanced` 都係空。
- 報告印「對手球隊數據為空」，gate 搵唔到合格腿 → CLE_PHI、DEN_OKC **兩場零組合**。舊引擎（legacy）跑同一份數據一樣零組合，所以唔係校準層 C 嘅問題。
- 開季頭一兩星期每日都會有未打首戰嘅球隊，所以呢個係會重複發生嘅缺陷，唔係偶發。
- 重抽冇用：用同一份規則重抽，結果一模一樣（DEN team_stats 0、advanced 0）。

## 修正
- 今季有嘅 row 照用；今季冇嘅 key（球隊／球員）逐個由上季補。截止日期 `as_of` 照舊套用上季，唔會讀到當日或之後賽事。
- team_stats／team_dvp：已有 30 隊就唔再多一個請求。player_advanced／key_defenders：冇固定完整行數，永遠補。
- `info` 記錄 `fallback_partial`、`filled_from`、`filled_count`、`filled_keys`（最多 40 個），並維持 `fallback_used=True`，令報告繼續顯示「用咗上季數據」。

## 真實 API 驗證（2026-10-23 重抽 DEN_OKC，scratchpad，未入生產）
| feed | 舊（只用今季） | 新 |
|---|---|---|
| team_stats DEN | 空 | 6 項（上季） |
| DEN 球員有 advanced | 0／14 | 14／14 |
| team_stats 行數 | 28 | 30（補 2） |
| player_advanced 行數 | — | 618（補 296） |
| key_defenders 行數 | — | 611（補 307） |

## 限制
- 補上嘅係**上季**數字（同整隊用上季一樣），轉隊／陣容大變嘅球員會偏差；EXP-20261022（穩膽方案）Phase 3 先處理。
- 報告嘅「Pace／防守用上季」提示唔區分「全部」同「只補咗兩隊」。
- 冇驗證補缺對組合結果嘅影響（今日該兩場已開賽）；只驗證咗「資料有冇到」。
- 同一日另一個修正（快取要求每隊都完整）係獨立 release。
