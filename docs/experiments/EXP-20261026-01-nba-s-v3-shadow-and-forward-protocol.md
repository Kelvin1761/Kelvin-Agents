# EXP-20261026-01 S_v3（賽前傷停名單）shadow 接線同 MS3 forward 協議（未有數據之前凍結）

- **日期**：2026-10-26（Claude Code，用戶要求先寫清楚狀態處理）
- **承接**：EXP-20261025-16（S_v3 開發：例行賽 VALID −0.0034，有洩漏上限；有價季後賽冇改善）。
- **目的**：用**賽前**傷停名單取代開發時嘅「實際冇落場」，喺 live 以 shadow（`nba_season_rate_S_v3`）記錄，攞一個冇洩漏嘅 forward 判決。
- **凍結時狀態**：ledger 入面帶 `season_rate_v3_*` 嘅腿 = 0。

## 1. 傷停狀態點處理（喺睇任何 v3 forward 數據之前定）

live 嘅來源係 ESPN 傷停名單，經 `nba_availability.classify_injury_status` 分類。實際只會出現 `Out`、`Day-To-Day` 同 `Not On Verified Roster`（10-24 樣本：43／14／1）。

| 原始狀態 | 分類 | S_v3 處理 | 原因 |
|---|---|---|---|
| Out、Doubtful、Suspended、Inactive、IR | `out` | **當缺陣，權重 1** | 同開發定義「冇落場」最接近；doubtful 實際上場率好低，`classify_injury_status` 本身已經當 out |
| Day-To-Day、Questionable、GTD | `dtd` | **當會上場，權重 0** | 開發數據冇呢個狀態，冇證據支持任何部分權重；揀 0 係保守做法，唔會誇大缺陣效應 |
| Not On Verified Roster（`roster_verified = false`） | — | **唔計** | 佢已經唔係隊友（交易或者被裁），唔係傷停；同 `compute_usage_redistribution` 一致 |
| 唔喺名單 | `ok` | 當會上場 | |

- `dtd` 嘅潛在缺陣份額**另外記錄**喺 `season_rate_v3_inputs.A_dtd`，留俾之後分析，**唔會入呢個測試嘅機率**。要用就另開新協議。
- 用嘅係報告生成嗰陣 package 入面嘅名單（`final_refresh` 會重新拉傷停名單），所以每隻腿用嘅都係嗰個快照時刻嘅賽前資訊。快照時間一定早過開賽（ledger 規則）。

## 2. 公式（同開發一致）

- **主力隊友**：喺球隊對上 10 場（截止上一個完整美國比賽日）入面出場 ≥5 場、嗰啲場次平均 ≥20 分鐘，而且係 `out` 狀態、喺 verified roster 上面。
- **預計缺陣產量**：佢最近 10 次出場（剔走季前賽、MIN > 0）嘅平均。
- **缺陣份額**：`A_s = Σ 預計缺陣產量 ÷ 球隊對上 10 場平均`，上限 0.6。
- **調整**：`μ_v3 = μ_v2 × (1 + γ_s·A/(1−A))`，γ：PTS 0.20、REB 0.05、AST 0.15、3PM 0.10（EXP-16 喺 TUNE 揀）。k 用 S_v2 未調整前嘅 μ 計，同開發一樣。
- **數據來源**：球隊對上 10 場嘅日期同平均，嚟自同一個聯盟球隊 game log（`nba_team_context`），唔使額外 API call。
- **留空**：冇球隊近況數據就報 `no_team_recent`；S_v2 留空嘅原因（例如冇對手數據）照樣傳落嚟。

## 3. MS3 forward 測試

- **係數**：`MS3: logit p = a_s + b_m·logit(1/price) + b_S·logit(S_v3)`，fit 喺同一個 19 日 dev。開發時用「冇落場」計 A，呢點係已知嘅不一致，寫低喺度。

  | Stat | 截距 | 市場 | S_v3 |
  |---|---:|---:|---:|
  | PTS | −0.1947 | 0.7387 | 0.1060 |
  | REB | −0.1352 | 0.3666 | 0.6282 |
  | AST | −0.3416 | 0.7609 | 0.1066 |
  | 3PM | −0.1598 | 0.4379 | 0.5824 |

- **工具**：`nba_ms_forward.py --model v3`，設定 `nba_ms_forward_v3.json`，SHA256 `d4ff377b554367f3e9af95c12eaa54baa38d3534e374c462f8b7be4e3cfa9c8b`（測試釘住）。
- **Live 同研究版一致**：14,400 個機率，v2（重構後）同 v3 最大差都係 0.00005，只係四捨五入。
- **規則**：樣本、150／400／800 場檢查點、97.5% 比賽日 cluster CI、五項 KEEP 條件、數據守則，全部同 EXP-20261025-12 §3–§7 一字不改。覆蓋率分母包括 `no_team_recent` 同 `no_opponent_context`，所以來源斷咗會報 `INVALID_DATA`。
- **主要問題**：MS3 係咪好過 C。描述性報告：MS3 對 MS2 同一批腿嘅分別，同埋按「有冇主力缺陣」分層。
- **多重比較**：而家有四個並行測試（EXP-12、14、15、本協議）。任何切換之前都要做 Holm 調整。
- **預期**：開發證據顯示季後賽冇改善，所以 MS3 好可能同 MS2 差唔多。例行賽傷停比季後賽多，呢個係 S_v3 唯一可能贏嘅地方。

## 4. 唔准做嘅嘢

- forward 期間唔准改 γ、狀態處理、主力定義或者係數。
- `dtd` 權重唔准因為睇完數據先調；要調就另開協議，用新數據。
- KEEP 唔等於自動上線。
