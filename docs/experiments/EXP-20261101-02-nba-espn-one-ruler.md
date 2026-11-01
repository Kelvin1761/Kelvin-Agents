# EXP-20261101-02 NBA：ESPN 做唯一數據來源 —— 一把尺重建訓練語料 + regression gate

- **日期**：2026-11-01
- **平台**：NBA
- **假設**：用 ESPN 重新計晒訓練語料嘅全部特徵（一把尺），現役 C 層嘅輸出唔會變差（non-inferior）；防守者表（`defender_pm`）同 DvP 可以由特徵表移除。
- **搜索過嘅舊記錄**：EXP-20261023-06（v2 驗證語料、RF 協議、C 嘅 terminal 診斷）、EXP-20261030-01（ESPN 賽績 94.7% 逐場一樣）、EXP-20261031-01（ESPN 聯盟數據表；冇追蹤數據對機率零影響）、EXP-20261101-01（PBP 陣容 parity）。
- **改到嘅檔案**：
  - 數據合約：`nba_data_contract.py`（contract v3：唔再要求防守者表；每個 package 寫 `stat_source`；`primary_source()`）
  - 主來源：`nba_wong_choi/resources/nba_stat_source.json`（`primary: espn`）、`nba_api_breaker.py`（ESPN 主來源時 stats.nba.com 一個請求都唔發、cache 都唔讀）、`nba_league_snapshot.py`（ESPN 模式唔讀 nba.com 快照）、`nba_daily_schedule.py`（狀態 `not_used` 唔再發封鎖／恢復通知）
  - 抽取：`nba_extractor.py`（`meta.stat_source`）
  - 特徵／訓練：`nba_ml_features.py`（contract `nba-ml-features/v3`：剷 `defender_pm`，26 個特徵；`check_single_source`）、`build_nba_ml_dataset.py`（每行 `stat_source`）、`train_nba_xgboost.py`（混合來源拒絕，`--allow-mixed-sources` 先放行並印比例）、`nba_ml_predictor.py`
  - 位置：`nba_espn_lineups.espn_position`（ESPN G/F/C 一個尺度）

## 預先登記（跑閘之前寫，commit 先於結果）

**語料**：EXP-20261023-06 嘅 strict priced manifest —— 49 個賽事、24 個美東日期（2026-04-15..06-10，2025-26 季後賽／附加賽），已驗證標籤。baseline 同 candidate **同一批行**（兩邊都有、都有標籤先入；只喺一邊出現嘅行照數報，唔補）。

**兩把尺**：
- baseline（`stat_source=nbacom`）：原本 nba.com package，經今日嘅特徵建構器（v3，冇 `defender_pm`）。
- candidate（`stat_source=espn`）：同一個 package（陣容、傷停狀態、賠率、擷取時間不變），所有數據換成 live ESPN 路徑：extractor 自己嘅 `fetch_player_gamelog`／`fetch_player_splits`／`compute_fatigue_adjustment`（stats.nba.com stand down），球隊／球員表由 ESPN 2025-26 常規賽 box score 計（nba.com 喺季後賽用嘅都係常規賽終值，已核對），球員 OFF/DEF 由 PBP 陣容計，位置用 ESPN G/F/C。
- point-in-time：所有 ESPN 輸入都係賽事美東日之前已完場嘅日子（`history_date_to`），同原本 nba.com 窗口一樣；`validate_capture` 會再查 L10 日期。

**主要判決（現役 C 層，live）**：`p_final = calibrated_prob(stat, 價, hit_rate_l10)`，全部配對行；ESPN − nba.com 嘅 Brier，美東日期 cluster bootstrap 2,000 次、seed 20261101。
- **KEEP**：95% CI 上限 ≤ **+0.002**（non-inferior；約 C Brier 嘅 1.2%）
- **REJECT**：CI 下限 > 0（顯著變差）
- 其餘 **NEEDS MORE TESTING**
- 同時報：log-loss 差、`hit_rate_l10` 一樣嘅比例、有變嘅腿數、平均／最大移動、跨 50/60/70/80% 嘅數目。

**次要（只係 shadow，唔影響判決）**：v2 固定 RF 協議（`train_model`，前 19 日 dev 五折、尾 5 日 terminal），三個 arm：
- A：v2 dataset 27 特徵（含 `defender_pm`，2026-10-23 重現）
- B：nba.com 尺 26 特徵（剷 `defender_pm`）
- C：ESPN 尺 26 特徵
- 報 terminal Brier、B−A（剷防守者）、C−B（換尺），配對 CI。呢段 terminal 已經睇過（EXP-20261023-06），唔係新盲測，**唔准用嚟調參或者揀特徵**。

**唔做**：唔 refit C、唔改 C 係數、唔換窗口、唔換指標救候選。

## 結果（2026-11-01）

### 數據重建
- 外置碟抓 2025-26 季 ESPN：1,235 場常規賽 box score + PBP、附加賽／季後賽、313 份球員賽績（全部經 `nba_espn_http`，每次請求之後再等 1 秒；冇觸發熔斷）。**8 場季後賽 ESPN 冇 summary（404）**，只影響 ESPN id／位置對照，唔影響 L10（由賽績嚟）同聯盟表（常規賽）。
- 50 份 package（49 個賽事）、1,745 名球員全部攞到 ESPN 賽績；1,736 名用名對到 NBA id（2026 語料 package 本身冇 `player_id`）。配對有標籤行 **8,286**，兩邊冇一行單邊。
- 位置：ESPN G/F/C（G 4,339、F 2,112、C 1,274；561 行 ESPN 冇位置）。位置唔係訓練特徵。

### 全季球員 parity（309 人，nba.com 常規賽終值 vs ESPN）
| | 中位 \|Δ\| | p90 | 偏差 |
|---|---|---|---|
| OFF_RATING | 0.6 | 2.0 | −0.26 |
| DEF_RATING | **0.7** | 2.1 | −0.26 |
| PACE | 0.7 | 2.18 | +0.45 |
| USG_PCT | 0.5 | 1.0 | +0.54 |
| TS_PCT | 0.0 | 0.1 | 0.0 |
| AST_PCT | 0.4 | 1.6 | −0.21 |

全季樣本下 `PLAYER_POSSESSION_SCALE=1.016`（早季擬合）偏差只剩 −0.26，即係 EXP-20261101-01 嘅常數喺大樣本企得住。

### 特徵 parity（8,286 行）
- L10 系列 99.9% 逐位一樣；`hit_rate_l10` **99.98%**；`l3_avg`、`hit_rate_l3`、`is_home`、`line_value` 100%。
- `def_rtg` 中位差 0.5、`usg_pct` 0.6、`opp_def_rating` 0.1、`opp_def_rank` 1 位、`opp_pace` 0.35。
- **ESPN 補返 nba.com 原 package 冇嘅值**（只會由缺變有，冇一行反方向）：對手 NYK／SAS／GSW 嘅球隊表 1,997 行（原 package 呢三隊冇 `team_stats`，似係球隊代碼別名缺口）；`rest_days`／`b2b_flag` 7,722 行；`home_ppg` 39 行。
- ⚠️ 兩邊都有 `rest_days` 嘅 564 行，ESPN 一律少 1 日 —— 呢個係**今日 `compute_fatigue_adjustment` 同 4 月版 extractor 嘅計法分別**，唔係 ESPN 數據分別。即係次要 RF 比較 C−B 混埋咗「換來源」同「4 月至今嘅 code 改動」，唔係純來源效果。

### 主要判決：現役 C 層
| | 值 |
|---|---|
| Brier nba.com / ESPN | 0.170251 / 0.170247 |
| ΔBrier（ESPN − nba.com） | **−0.000003 [−0.000009, 0.000000]** |
| Δlog-loss | −0.000007 [−0.000018, 0.000000] |
| p_final 有變嘅腿 | **2 / 8,286**（平均 0.0003pp，最大 1.5pp） |
| 跨 50／60／70／80% | 0／0／0／0 |

CI 上限 0.000000 ≤ +0.002 → **KEEP**。C 只讀賠率同 L10 命中率，而命中率兩把尺幾乎完全一樣，所以呢個結果係意料之內，亦係轉尺最重要嘅保證。

### 次要：RF shadow（固定 v2 協議，terminal 5 日 942 行，已睇過嘅窗口）
| arm | terminal Brier | AUC |
|---|---|---|
| A v2 27 特徵（含 `defender_pm`） | 0.18172 | 0.7966 |
| B nba.com 26 特徵 | 0.18194 | 0.7965 |
| C ESPN 26 特徵 | 0.18205 | 0.7978 |
| 現役 C（同一批行） | 0.17107 | — |

- B−A（剷 `defender_pm`）：+0.00022 [−0.00034, +0.00077] —— 冇證據有影響（同 EXP-20261031-01 一致）。
- C−B（換尺，連 code 漂移）：+0.00011 [−0.00166, +0.00193] —— 冇證據有影響；5 個日期 cluster，功效低。
- 三個 RF 全部輸現役 C（同 EXP-20261023-06 一樣），唔晉升、唔部署。

## 檢查
- **leakage-audit**：PASS —— ESPN 輸入只讀賽事美東日前已完場日子；`validate_capture` 對重建 package 再查 L10 日期全部 `verified`；賠率、陣容、傷停狀態同擷取時間沿用原 package。ESPN 賽績係 2026-11 先抓，理論上包含之後嘅官方數據更正，但 L10 99.9% 同 4 月嘅 nba.com 快照一樣，影響可忽略。
- **model-regression-gate**：同語料、同行、同窗口；預先登記嘅規則（commit a503e4a1 先於結果）→ **KEEP**。
- **feature-ablation**：剷防守者（B−A）同換尺（C−B）分開量咗。
- 冇 refit C、冇改係數、冇用 terminal 調任何嘢。

## 結論
**KEEP —— ESPN 可以做唯一數據來源。** 現役 C 層喺兩把尺下幾乎一模一樣（8,286 腿得 2 腿郁，最多 1.5pp）；`defender_pm` 退出特徵表冇可量度影響；混合來源嘅訓練語料由今日起會被拒絕。**未上線**：分支 `claude-nba-espn-primary-20261101`，合併＝上線，要 Kelvin 確認；合併之前要睇 11-14 嘅 stats.nba.com 狀態（合併之後狀態紀錄只寫 `not_used`）。

## 重跑
```bash
S="/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/claude-nba-espn-primary-20261101"
R="/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/codex-nba-remediation-20261023"
# 1. 抓（已抓，重跑全部 cache hit）
WC_NBA_ESPN_HTTP_RESPONSES_DIR="$S/espn_responses" python3 docs/experiments/evidence/EXP-20261101-02-nba-espn-season-backfill.py .agents/skills/nba 2025-10-01 2026-06-10
# 2. 重建（輸出目錄要全新）
PYTHONDONTWRITEBYTECODE=1 WC_NBA_STAT_SOURCE=espn WC_NBA_ESPN_HTTP_RESPONSES_DIR="$S/espn_responses" \
  python3 docs/experiments/evidence/EXP-20261101-02-nba-espn-one-ruler-rebuild.py . "$R" "$S/rebuild"
# 3. 閘
PYTHONDONTWRITEBYTECODE=1 NBA_WC_PROB_LAYER=1 python3 docs/experiments/evidence/EXP-20261101-02-nba-espn-gate.py . "$S/rebuild" "$R/verified_dataset_v2/dataset.csv"
```
輸出：`$S/rebuild/{dataset_nbacom.csv,dataset_espn.csv,rebuild_report.json,gate_result.json,espn_packages/}`。C 模型 id：`calibrated:C-2026-10-22:06bc5c85…`。
