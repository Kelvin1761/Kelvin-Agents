# EXP-20261101-01 NBA：ESPN play-by-play 還原場上陣容 → 球員 OFF/DEF rating、在場 PACE

- **日期**：2026-11-01
- **平台**：NBA
- **假設**：ESPN `summary?event=` 嘅 play-by-play（換人紀錄）可以還原每個回合場上 10 個人，計出嘅球員 OFF/DEF_RATING、在場 PACE 貼近 nba.com，足以填返 `nba_espn_league.player_advanced` 而家係 `null` 嘅欄位。
- **搜索過嘅舊記錄**：EXP-20261031-01（box score 計球隊／球員表；球員 OFF/DEF、PACE 留 `null`，因為要在場回合）、EXP-20261030-01、盤點文件 `docs/plans/2026-11-01-nba-espn-as-primary-source.md` 第四節。
- **改到嘅檔案**：`.agents/skills/nba/nba_espn_lineups.py`（新）、`nba_espn_league.py`（`fill_on_court_ratings`；`_game` 同 lineups 共用一次 summary 請求）、`nba_extractor.py`（`espn_league_fallback` 填 on-court 欄位）、`nba_espn_http.py`（`WC_NBA_ESPN_HTTP_RESPONSES_DIR`）、測試 `test_nba_espn_lineups.py`、`test_nba_espn_league.py`。

## 做法
- 第 1 節正選＝box score `starter`；之後跟 `Substitution`（participants＝[入場, 離場]）推進。
- 第 2 節起，節與節之間冇換人紀錄：該節入面有動作、或者未入場就被換出嘅球員＝開節喺場；全節冇碰過紀錄嘅人由上一節收節五人補。技術犯規／暫停等唔計。解析唔到啱啱好五人嘅一節**唔用**（記入 `quality.bad_periods`），唔估。
- 回合結束：入波（有 and-one 就等罰球）、一輪罰球最後一球入、防守籃板、失誤、節完 —— nba.com 定義。得分同回合記畀當刻場上 10 人。
- 所有 summary 經 `nba_espn_http.get_json`（限速＋熔斷），完場賽事 `fresh_after`＝該美東日 06:00 翌日，即係**一場賽事一世只抓一次**；box score 同陣容由同一份 raw 解析（`nba_espn_league._game` 改用 `nba_espn_lineups.fetch_summary`）。

## 一、自我檢查（同一場 box score，2026-27 共 81 場）
| 項目 | 結果 |
|---|---|
| 解析唔到嘅節 | **0 / 979**（窗口加總） |
| 球員在場分鐘 vs box `MIN`（整數） | 中位差 0.27、p90 0.46、最大 4.0 |
| 點出嘅回合 / box 估算 `FGA+0.44FTA−OREB+TOV` | 中位 **0.977**（p10 0.948、p90 1.008）—— 同 nba.com 比 box 低約 2%（EXP-20261031-01 嘅 0.98）吻合 |
| 換人對唔上（離場者唔喺場） | 36 / 17,100 |

## 二、球隊層面 vs nba.com（排程 `nba_game_data_*.json`，2026-27 nba_api 表，n=80）
| | 中位 \|Δ\| | 偏差 |
|---|---|---|
| OFF_RATING | **0.79** | +0.33 |
| DEF_RATING | **0.72** | +0.28 |
| PACE | **0.50** | −0.32 |
| 得分 | 0.0 | 0.0 |

比 box score 估算（OFF 1.10／DEF 0.85／PACE 0.65）仲貼。

## 三、球員層面 vs nba.com（同一批快照，2026-27 本季值；`filled_keys` 嘅 2025-26 補值排除）
未修正有系統性偏差：OFF +1.66、DEF +2.13、PACE −1.72 —— 即係 nba.com 每個球員記多約 1.6% 回合，而球隊總數一樣。試過兩個「有原則」嘅解釋，都唔係：

| 試法 | dev DEF 偏差 | 結論 |
|---|---|---|
| 回合結束時嘅 10 人（採用） | +2.13 | 偏高 |
| 回合期間曾經上過場嘅人全部記一個 | −2.02 | 矯枉過正 |
| 罰球記畀犯規嗰刻嘅陣容 | +2.13（無變） | 唔係成因 |
| 同一窗口錯開一日（試 nba.com 延遲） | 中位差 2.10 vs 1.80 | 唔係延遲 |

所以用一個常數 `PLAYER_POSSESSION_SCALE`，**dev 窗口（history_date_to 10-21..10-24）定、test 窗口（10-25..10-27）驗**，同 EXP-20261031-01 一樣做法：

| 尺度（dev） | OFF 偏差 | DEF 偏差 | PACE 偏差 |
|---|---|---|---|
| 1.000 | +1.66 | +2.13 | −1.72 |
| 1.012 | +0.35 | +0.82 | −0.49 |
| **1.016** | **−0.08** | **+0.39** | **−0.08** |
| 1.020 | −0.50 | −0.03 | +0.33 |

**Test 窗口（1.016，n=583）**：

| | 中位 \|Δ\| | p90 | 偏差 | Pearson r | nba.com 跨球員 SD |
|---|---|---|---|---|---|
| OFF_RATING | **1.5** | 4.2 | −0.25 | 0.986 | 19.3 |
| DEF_RATING | **1.5** | 3.7 | −0.04 | 0.977 | 17.2 |
| PACE | **1.11** | 3.5 | +0.18 | 0.884 | 5.5 |
| NET_RATING | 1.6 | 4.8 | −0.21 | 0.990 | 27.4 |

按在場分鐘分層（DEF_RATING，test）：<30 分鐘 中位 2.2（p90 9.8）；30–100 分鐘 1.4（p90 3.1）；**≥100 分鐘 0.9**（p90 2.5）。差異隨樣本收窄，即係主要係細樣本噪音，唔係定義錯。

**對唔上嘅 436 行**：全部係 nba.com 快照入面嘅 2025-26 補值（`filled_keys` 只列頭 40 個，所以過濾唔晒；呢啲球員本季未出場，ESPN 自然冇）同埋 nba_api 離線名單未有嘅 2026 新秀（Aday Mara、Kingston Flemings…）。後者喺生產一樣對唔到 NBA id，所以會留 `None`，同 USG／TS 一樣。

2025-26 全季 parity（155 名訓練語料球員，nba.com 常規賽終值 vs ESPN 全季 PBP）喺 EXP-20261101-02 一齊報。

## 檢查
- **leakage-audit**：PASS —— 只讀 `history_date_to` 或之前已完場嘅美東日（`season_lineups` 同 `season_games` 同一個逐日窗口，測試釘死開放日唔 cache）。賽後資料本身就係 as-of 窗口用途，冇讀當日或之後。
- **閘門**：唔適用（數據來源補缺；呢幾個欄位喺現役 C 層冇讀，C 只用賠率＋L10）。`def_rtg` 係 v3 ML shadow 特徵，影響喺 EXP-20261101-02 用 regression gate 量。
- **限制**：parity 只得早季 7 個窗口；`PLAYER_POSSESSION_SCALE` 係擬合常數（吸收咗一個未查明嘅 nba.com 定義差），樣本大咗要再驗。PACE 嘅 r 只有 0.88，因為跨球員差異本身細（SD 5.5）。

## 結論
球隊層面比 box 估算更準；球員層面修正尺度後 OFF/DEF 中位差 1.5、≥100 分鐘 0.9、r ≈ 0.98。**決定：KEEP（數據來源）** —— ESPN 後備由今日起填返球員 OFF/DEF/NET rating 同在場 PACE（`on_court_source: espn_pbp`），PIE 照舊 `None`。上線跟 EXP-20261101-02 一齊等 Kelvin 確認。

## 重跑
```bash
python3 docs/experiments/evidence/EXP-20261101-01-nba-pbp-lineup-selfcheck.py .agents/skills/nba
python3 docs/experiments/evidence/EXP-20261101-01-nba-pbp-lineup-parity.py .agents/skills/nba 1.016 dev
python3 docs/experiments/evidence/EXP-20261101-01-nba-pbp-lineup-parity.py .agents/skills/nba 1.016 test
```
（summary 全部已喺 `~/.cache/wongchoi/espn_http/responses`，重跑零網絡請求。）
