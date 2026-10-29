# EXP-20261030-01 NBA：stats.nba.com 封鎖時嘅 ESPN／快照後備

- **日期**：2026-10-30
- **平台**：NBA
- **假設**：stats.nba.com 封 IP 時，用 ESPN 嘅球員賽績同陣容、加上一日內嘅聯盟數據快照，可以重現 nba_api 嘅 L10 輸入（逐場一樣），令排程唔使成日落空；冇快照就要 fail closed，唔准用空白聯盟數據出分析。
- **搜索過嘅舊記錄**：EXP-20261025-07（NBA 機會量接線，唔相關）；冇其他 ESPN 後備記錄。
- **改到嘅檔案／組件**：`.agents/skills/nba/nba_espn_stats.py`（新）、`nba_league_snapshot.py`（新）、`nba_api_breaker.py`（加 `failure_count`）、`nba_data_extractor/scripts/nba_extractor.py`、`nba_daily_auto/tests/test_nba_nbacom_outage_fallback.py`、兩個 `tests/conftest.py`

## 背景
2026-10-29 21:00 起 stats.nba.com（Akamai）對本機完全唔回應，到 10-30 09:15 仍然封住（12 小時以上）。
10-30 嘅三場（CLE@ATL、MEM@POR、SAC@NOP）喺 21:00／21:45／06:30／08:30 全部 `orchestrator_exit_1:all`，冇分析、冇注。
10-29 已上線嘅 circuit breaker 只係令佢快啲失敗。

## 配置
- **baseline**：`3aad151d`（nba.com 唔通 = 全場失敗）
- **candidate**：nba.com 有回應時**完全唔變**。唔通時：
  - 陣容 → ESPN team roster，用上次 nba.com 陣容快照／nba_api 離線球員表對返 NBA id，對唔到嘅剔走並列名，唔估。
  - 球員賽績（L10、h2h）→ ESPN gamelog，轉成 PlayerGameLog 一模一樣嘅欄位，`fetch_player_gamelog` 嘅截止日、去重、L10 邏輯原封不動。
  - 聯盟數據（team_stats、player_advanced、key_defenders、team_dvp）同球員 splits → 最近一次成功抓取嘅快照，**最多舊一日**，而且快照嘅日期窗口一定 ≤ 今次窗口（冇前視）。
  - 冇快照 → `league_tables_unavailable`，exit 1（同以前一樣失敗）。
  - 每個 package 寫 `meta.nbacom_fallback`（幾多球員用 ESPN 賽績、邊幾張表用快照）。

## 數據（parity）
- **語料**：`/Users/imac/wongchoi-scheduler/2026-10-29 NBA Analysis/nba_game_data_*.json`（12 場，nba_api 喺 10-28 抽嘅正式輸入）
- **方法**：用 extractor **自己嘅** `fetch_player_gamelog`，只將 `PlayerGameLog` 換成 ESPN，同一個 `as_of`／`include_previous`，逐個球員比較 L10 日期、對手、13 項數據。
- **樣本**：378 名球員（另 3 名 ESPN 陣容搵唔到）

## 結果
| 項目 | 第一次 | 修 Play-In 後 |
|---|---|---|
| L10 完全一樣 | 310 / 378（82.0%） | **358 / 378（94.7%）** |
| 日期不同 | 60 | 10 |
| 數據不同 | 8 | 10 |

第一次嘅 50 個日期差異全部係 Play-In：ESPN 將佢叫做「2025-26 Play In Regular Season」，結尾都係「Regular Season」，被當成常規賽；nba_api 嘅 Regular Season／Playoffs 都唔包 Play-In。已修並加測試。

餘下 20 個差異：
- **MIN 差 1 分鐘**（8 人，各一場）：兩邊秒數捨入唔同。對 L10 平均影響 ≤0.1 分鐘。
- **AST 差 1**（2 人，各一場）：似係數據更正，ESPN 同 nba.com 其中一邊未跟。
- **L10 尾段上季季後賽唔同**（10 人，多數係轉會球員）：其中一邊多／少一場舊季後賽。
- `games_played`（總歷史場數）54 人唔同，但下游冇任何地方讀。
- ESPN 冇 PLUS_MINUS（寫 0），下游冇讀。

## 端到端
nba.com 真係封住嘅情況下（10-30 09:40）跑 `nba_extractor.py --date 20261030 --game CLE_ATL`：陣容同 L10 全部經 ESPN 抽到（CLE 10 人、ATL 13 人，9 名新球員對唔到 NBA id 被剔走並列名）；冇快照，聯盟數據四張表全空 → 加入 fail-closed 閘之前會照出 package，**呢個係加閘嘅原因**。

## 檢查
- **leakage-audit**：PASS —— ESPN 賽績用美東日期 + nba_api 同一個 `date_to` 窗口；快照只可以用窗口 ≤ 今次嘅（測試釘死）。
- **golden_scoring**：唔適用（NBA，冇改評分）
- **data_contract**：唔適用
- **退步**：nba.com 正常時零改變。後備時 ~5% 球員 L10 有 1 分鐘／1 助攻級差異。

## 結論
後備路徑重現 nba_api 輸入 94.7% 逐場一樣，其餘係捨入或來源更正級別差異；呢個唔係模型改動，亦唔聲稱改善任何預測，只係令 nba.com 封鎖時排程仍然有 L10 可用。聯盟數據冇自己嘅替代來源，只靠一日內快照；冇快照就照舊失敗，唔會出盲分析。

**決定**：KEEP（數據來源後備，非模型改動）
**commit**：見發佈 manifest

## 重跑
```bash
cd docs/experiments/evidence   # 只讀；需要 scheduler 嘅 <日期> NBA Analysis/nba_game_data_*.json
PYTHONDONTWRITEBYTECODE=1 python3 EXP-20261030-01-nba-espn-parity.py 2026-10-29
```
