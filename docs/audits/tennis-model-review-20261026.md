# Tennis Wong Choi 全面模型及資料審計 — 2026-10-26

## 判斷

**現時未有證據支持 Tennis 解除 `RESEARCH_ONLY` 或提升模型。優先修資料同量度工具，再考慮模型。**

本次用唯讀方式檢查 live SQLite、評分／特徵、賠率／盤口、回測、校準、結算、推薦閘同排程接線。
有四類離線工具／報表正確性問題已修正，修正保存於獨立分支供 review；冇改 production 評分公式、權重、投注門檻，冇重算或改寫 live DB。
本次係審計交付，**唔係模型 promotion 或 production activation**。

- 起點：`36101baa8d4638f7c7a62f876ec105f3eee8e2d4`，最新 `origin/main` 嘅獨立 worktree。
- 資料：`/Users/imac/Antigravity-repo/tennis-wong-choi/tennis_wc.db`，約 1.7GB；所有審計連線用 `mode=ro`。
- 固定資料掃描時間：2026-10-26 04:06:45 UTC／15:06:45 Sydney。
  掃描前後 SQLite `data_version` 一致，冇發現期間被另一條連線更新。
- 9,681 fixtures、15,632 predictions、418,233 player-history rows、25,454 prop rows。
- [機讀摘要](tennis-model-review-20261026-summary.json) 保存原始計數、現有評估器輸出及 shadow 配對結果。
- 審計有覆核舊記錄：`EXP-20260826-09`、`EXP-20261009-01`、`EXP-20261015-05`、
  `tennis-wong-choi/docs/performance-audit-2026-08-21.md`、frozen `tennis-v1` ruler。
  下文清楚區分新修正同已知但仍存在嘅問題。

## 現有表現：paper record，唔係實盤盈利

| 指標 | 本次實測 | 解讀 |
|---|---:|---|
| 可證明賽前、已結算 value paper bets | 973 | 只計 `is_point_in_time=1` |
| Paper P/L／ROI | −155.046u／**−15.93%** | 固定 1u research book，並非正式卡實際下注組合 |
| 最近 100 注 research ROI | −43.78% | 現有固定觀察窗，冇按結果改窗口 |
| 符合正式 per-leg profile 嘅 player props | 886；ROI **−16.28%** | 呢啲亦唔代表每日卡真係選中／有人下注 |
| Raw prop Brier／市場 Brier | **0.2082／0.1921** | 9,576 個 canonical scorecard rows；越低越好 |
| Raw prop log loss／市場 log loss | 0.6025／0.5654 | 概率質素仍輸市場 |
| 正式推薦閘 | `RESEARCH_ONLY`，enabled families = `[]` | 保護仍然有效 |
| 記錄咗嘅 prop live bets | **0** | 無實盤 ROI 可以聲稱 |

唔好將全部 25,454 行一齊算：11,294 行係已標記賽前、8,578 行 post-start、
5,582 行不可核實。現有 prop scorecard／ROI 正確使用賽前子集。
不同盤、同場多條 line 互相關連；以上係現有評估器嘅描述統計，唔係 9,576 個獨立比賽嘅信心證據。
儲存賽果亦有下文嘅來源衝突，所以唔將呢份數字當成已清理完成嘅 promotion benchmark。

### Player family 摘要

| Family | 正式 profile paper bets | ROI | Raw model／market Brier |
|---|---:|---:|---:|
| 首盤勝方 | 313 | −7.27% | 0.2419／0.2101 |
| 球員贏至少一盤 | 241 | −13.01% | 0.2159／0.1938 |
| 球員讓局 | 224 | −29.41% | 0.2557／0.2267 |
| 球員總局數 | 39 | −32.18% | 0.2677／0.2512 |
| 球員讓盤 | 29 | +1.46% | 0.2300／0.2175 |
| 球員 ace | 16 | −14.94% | 0.3106／0.2510 |

讓盤嘅正數只有 29 注，而且 Brier 輸市場；唔構成解鎖理由。
`match_total_games` 係少數帳面 Brier 贏市場嘅 family，但有已知歷史錯標污染，而且本身唔係正式 player-prop 主卡 family。

## 已修正：四類正確性問題

### F1 · 高：模型量度混用歷來最低賠率、賽後預測及今日重建 Elo

`scripts/measure_match_model.py` 原本分別取兩邊所有 snapshot 嘅 `MIN(odds)`，
並用最新 prediction，亦由今日嘅 `player_elo_history` 重建舊骨幹。
兩個最低價可以來自完全不同時刻，當中包括走地；最新 prediction 可以係事後 rebuild；
今日重建嘅 Elo 亦唔等於當時模型真係見過嗰份資料。

影響證據：6,455 個有 match-odds snapshot 嘅 fixtures，1,110 個最低價組合同首個 snapshot 唔同；
6,317 個有最新 prediction 嘅 fixtures，2,147 個最新版本喺開賽後寫、489 個冇已知 start time。
前者係 pair-level 機制計數，唔聲稱每一個都落入原腳本最終 sample。

修正新增共用 `evaluation/match_corpus.py`：首個有效賽前預測、兩邊同一筆 `MIN(id)` 賽前 odds pair、
同一場只得一個一致 winner。缺時間、錯 player id、衝突／退賽／不完整賽果會排除。
Elo baseline 只讀 forecast 保存嘅骨幹；舊 payload 冇保存骨幹標記為「unavailable」，唔當成球員冇 Elo。
亦移除 AUC 嘅平方級逐對迴圈，保留 ties=0.5 語義。

修正後 3,743 場有合資格預測／賽果，其中 3,461 場有可核實首筆 odds pair。
有保存骨幹嘅 1,677 場：model Brier 0.2331、market 0.1934；log loss 0.6593／0.5682。
呢個係同一批場嘅模型對市場診斷；**開盤價同預測寫入時鐘可以唔同，唔用作可執行 ROI 或 promotion 證據**。

### F2 · 高：歷史校準／讓局驗證重複計賽果、讀到後來先寫嘅預測或結果

`modelling/probability_calibration.py::fit_as_of` 原本只限制 `match_date < cutoff`，
但用最新 prediction，仲會將每個 result provider 當另一個 sample。
`scripts/holdout_validation.py::_margin_rows` 同樣直接 join 多來源結果同讀最新 prediction。
現庫 7,567 場有結果，provider 額外結果行達 5,299；唔去重會令有多個來源嘅場次獲額外權重。

兩個 reader 改用共用賽前語料。校準／train window 同時要求 forecast 同 result 已喺 cutoff 前寫入；
game-margin fit 對一場只讀一個一致 margin。
空 train／test 明確回報 `insufficient_evidence` 同 exit 1，避免空樣本 bootstrap 出錯。

**限制：** 現有 result upsert 會改 `created_at`，所以無法從 mutable DB 完整還原每個過去時刻嘅 label availability。
新 reader 保守排除無法證明當時已知嘅結果；需要 immutable result-observation history 先能補回。
呢個係量度工具正確性修正，**冇通過模型表現閘，唔係已證實嘅預測改善**。

### F3 · 高：資料檢查吞 SQL error，當成「零問題」

`validation/checks.py::_rows` 原本 `except Exception: return []`，
令缺表、缺欄位或查詢失敗變成 count=0，檢查仍然綠燈。
新測試用缺表 DB 證明可重現；移除吞錯後，亦揭出 fresh DB 未有 optional
`players.canonical_player_id` 時，duplicate-identity check 本身會失敗。

修正：查詢失敗向上拋，由 `run_checks` 收集為帶 error 原因嘅 critical failure，並繼續跑其他獨立 check。
identity check 對尚未安裝 optional merge schema 嘅合法 DB 計全部未合併 player，保持純讀取。

### F4 · 中：指定日期回測讀全帳期 ledger，metadata 缺失會掉 prediction

`modelling/backtester.py::run_backtest` 原本 predictions 有日期限制，但 `ledger_summary()` 讀成個帳期。
inner join tournament metadata 會靜靜掉走冇 metadata 嘅 predictions；ROI denominator 亦混入未結算注碼。

修正：ledger 同 match-date window 對齊，只用 WON／LOST stakes 作 ROI 分母，
metadata 改 optional、每場只讀一筆，並拒絕倒轉日期範圍。
報表清楚標記 prediction counts 係 stored-latest inventory（可能含 rebuild），唔會冒充 PIT 策略回測。
回歸 fixture 覆蓋六月贏注、六月 pending 同七月輸注；六月只計自己期間，pending 唔攤薄已結算 ROI。

## 仍需處理：資料及模型風險

| 優先 | 問題／證據 | 建議及本次處理 |
|---|---|---|
| 高 | **WTA serve history 過期**：模型讀嘅最新 hold／ace rows 仍然係 2026-05-18。10 月已出 props 嘅 460 個 WTA player/date sides，341 個最後 hold row 超過 90 日、119 個完全冇。 | 已知 10-14 問題，今次確認仍存在。官方獨立表已收集 329 場／658 sides（10-08..10-24），但六月至九月未 backfill。先補足資料、身份及日期對照，再做原模型／新資料兩邊同窗 comparison；唔直接插第三份 result 入 history。 |
| 高 | **賽事開始日當比賽日**：rank buckets、tournament-level、H2H、pressure、big-match 等 feature readers 只用 `match_date < as_of`，未接 `history_asof` ingestion guard。 | 會令 historical rebuild／research 讀到同一賽事後面輪次。414 個已預測 fixtures 有同 pair、13 日內、start 後先入庫嘅 season-file row 候選，需 raw event 對照，唔將全部稱為已確認 self-leak。serve readers 已有 guard，match-feature readers 未齊。實時真正賽前預測唔會因為事後回填而自動變成洩漏，但重跑歷史不能當忠實 PIT。 |
| 高 | **歷史可能重複**：6,903 組 player／opponent／date keys，額外 11,052 行；多個 win-rate／sample-size reader 直接 count 全部 provider。 | 已知問題仍在。先以 source event id、round、日期語義建立 canonical observation；呢個粗 key 亦可能撞到真實多場，唔准一鍵刪晒。去重會改特徵／Elo，需獨立回測。 |
| 高 | **來源對贏家有衝突**：6 個 fixtures。shadow 用到嘅 match 20251（2026-10-11，Jay Friend 對 Alibek Kachmazov），TennisExplorer 同 TML 指唔同 winner。 | 新 audit readers 會排除。native prop settlement 未以 winner-consensus 做閘；6 場牽涉 48 個 graded props，其中 12 個 PIT rows、1 個 PIT value row。唔代人揀贏家；要逐場 raw／獨立來源核實，另作有審計軌跡嘅 settlement 修正。 |
| 高 | **BO5 被 BO3 prop 模型處理**：daily path 有多處 `best_of=3`；set handicap distribution 只包含 ±1、±2，卻可以收到 Slam 男單 ±2.5。 | 10-15 已記錄而未解決。屬格式支援錯誤；先加入明確 format／unsupported 閘，再評估 BO5 模型。唔將開放更多市場當成改善。 |
| 高 | **日常 ready／integrity 未接齊**：8-27 後 11,668 個新 props，2,730 個 post-start／不可核實（23.4%）；`validate-data --strict` 紅，但 `run_daily` 未呼叫 `run_checks`。 | 有啲係合法 research／after-start logging，PIT scorecard 會排除；唔代表 23.4% 正式下注受污染。應分開本日可發布資料同歷史研究記錄，將當前 slate integrity 摘要接入 daily readiness，唔直接用全歷史紅燈永久封卡。 |
| 中 | **歷史錯標盤仍污染 scorecard**：10-15 已記錄 125 個 player-total 行曾當 match total，119 行已結算、當時 stake 全 0。 | parser 已修；歷史 evidence 未隔離。要以保存嘅 feed identity 做版本化 exclusion／修正，唔改 immutable forecast 冒充當時已修好。本次引用舊已測範圍，唔聲稱重新確認咗每一行。 |
| 中 | **品質分可被後來 snapshot 改寫**：`family_reliability` 同正式 ROI profile 用 `LATEST_QUALITY_CTE`，serve quality 亦由今日 history 重算。 | forecast 本身 PIT 並唔保證 quality selection PIT；後來補資料可能令舊樣本進出 fit。應 freeze 每條 forecast 真正使用嘅 quality／history sample IDs，再驗證變化。 |
| 中 | **壞 history rows 未被值域閘攔截**：Sackmann 有 17 個 hold-rate 越界、2 個 first-serve／2 個 return-rate 越界；TML 有 19 行自己對自己。 | 明確列出 raw id，先查上游／身份 merge，再隔離。另有 3,406 個舊 Unknown Player self rows；12 個 mock rows 只屬 Player A／B，該兩個 ids 冇 prediction，冇證據佢哋影響現有卡。 |
| 中 | **查詢缺索引**：live `predictions` 同 `odds_snapshots` 冇 index；舊 per-date calibration 每次相關子查詢反覆掃表。 | 新 reader 改一次 group scan；本次冇寫 live schema。可以另加 `(match_id,id)`／時間查詢索引，用 EXPLAIN 同實際時間量，屬工程效能工作，唔係預測提升。 |
| 中 | **文檔／註釋同實際 gate 有差異**：README 主要講 Brier 勝市場，實際 strategy 仲有 credible-profit／probe route；set table 註釋稱 input 已校準，今次量度未支持呢個說法。 | 以 code 為準，整理唯一可生成策略說明；唔用改文字方式放寬 gate。 |

## 有證據值得繼續嘅改善：既有 frozen Elo shadow

用 `EXP-20261009-01` 已登記嘅 start-of-day Elo、surface weight 0.35；
今次冇 fit 新參數、冇掃 threshold、冇揀最佳日期。沿用既定 shadow 開始日 2026-10-10，
讀同一 forecast 保存嘅 production／shadow probabilities，再用既有 paired bootstrap（match 為單位，4,000 次，seed 20260826）。

舊 `shadow-report` 輸出 370 場，但包含 winner 衝突及 retirement／incomplete 結果。
按上文獨立資料規則剔除 21 場後，以下係 **349 場敏感度診斷**，唔係另開新 holdout 或 promotion 判決：

| 群體 | N | Production LL | Shadow LL | 市場 LL | Δ shadow−production，95% CI |
|---|---:|---:|---:|---:|---|
| 全部 | 349 | 0.68794 | 0.68002 | 0.60636 | −0.00792 [−0.01506, −0.00129] |
| 現有 tour／challenger allowlist 群體 | 214 | 0.67295 | 0.66303 | 0.63058 | −0.00993 [−0.01832, −0.00095] |
| Tour | 141 | 0.66873 | 0.65760 | 0.65198 | −0.01113 [−0.02381, +0.00129] |
| Challenger | 73 | 0.68111 | 0.67351 | 0.58924 | −0.00760 [−0.01403, −0.00132] |
| ITF／UTR | 115 | 0.70652 | 0.70010 | 0.54826 | −0.00642 [−0.02080, +0.00617] |

全部 Brier：0.24658 → 0.24305，Δ −0.00353 [−0.00672, −0.00052]；市場 0.20963。
allowlist 群體 Brier：0.23945 → 0.23529，Δ −0.00416 [−0.00798, −0.00021]；市場 0.22067。
UNKNOWN 層只有 20 場，點估計略差，CI 跨零；唔隱藏呢層。

**判決：繼續 shadow／NEEDS MORE TESTING，唔 promotion。**
呢批資料支持「相對現役有初步前向增量」，仍然唔支持「贏市場」或「會賺錢」。
樣本少於 frozen ruler 嘅 600-floor，亦未有完整 calibration／CLV／ROI／power promotion 證據。
尤其唔用 subgroup 好睇嘅數字去救總模型或改 allowlist。

## 建議工作次序

1. 先處理 conflicting results、BO5 unsupported 同本日 integrity 接線，建立可追蹤嘅資料排除／修正。
2. 補足 WTA 官方 history，同 canonical history／PIT knowledge clocks；保留原模型作可退回 baseline。
3. 再以同窗、同樣本做 WTA data／去重／age bounds 各自 ablation，唔一次過改幾樣。
4. 繼續累積 frozen Elo shadow 前向證據；唔重試已被否決嘅 Platt、layoff 或 arbitrary weight 搜索。
5. 最後先討論提升模型／加注；本次唔放寬任何投注 gate。

## 驗證與重跑

起點 `./檢查.sh --quick` 全過；baseline Tennis `713 passed`。
新增測試覆蓋：賽後 rebuild、unknown start、重複／衝突 winner、遲到 label、首個 odds pair、
單場 margin 去重、退賽、保存骨幹、SQL fail-closed、純讀取 audit、date-scoped ledger。
最終 Tennis **730 passed**；`./檢查.sh --quick` 同完整 `./檢查.sh` 全過，**16／16 suites PASS**。
首次 sandbox 全量執行有四個 NBA relocation tests 因 `ps` 被禁止而失敗；
正常權限下先獨立 13／13 通過，再完整重跑全綠，冇改 NBA code 或 skip 測試。
共用 Wong Choi 1,751、NBA 624、Tennis 730 tests 通過；兩邊 racing goldens 不變。
最終 source／test hashes 同 full-check log digest 已寫入機讀摘要。

```bash
# 以下命令喺修正分支 codex-tennis-model-audit-20261026 執行。
cd tennis-wong-choi
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=src
PY=/Users/imac/Antigravity-repo/tennis-wong-choi/.venv/bin/python
DB=/Users/imac/Antigravity-repo/tennis-wong-choi/tennis_wc.db

# 唯讀 warehouse scan；有 critical findings 會 exit 1，唔係執行失敗被吞掉。
"$PY" scripts/audit_model_data.py --db "$DB" --with-roi
"$PY" scripts/measure_match_model.py --db "$DB"

# 舊 shadow harness，原始輸出有上文品質限制；不可直接當 promotion。
"$PY" scripts/tune_elo_backbone.py shadow-report --db "$DB" --since 2026-10-10
"$PY" -m pytest -q

# 相同 frozen shadow，按獨立資料規則排除不合資格結果；重現報告敏感度診斷。
"$PY" ../docs/audits/tennis-model-review-20261026-shadow.py --db "$DB"
```

本次未做大型 replay／複製 1.7GB DB，亦未改 live SQLite、賽果、推薦閘、模型 registry 或排程。
active-SQLite／archive watermark 審計已返回 `status=ok`：本機 DB 同 catalog 四份 archive snapshots
全部 SQLite quick-check 通過，三個 monotonic tables 冇跌穿 archived row watermarks；catalog status `ok`。
呢個只證明已登記 DB snapshots 嘅完整性同 row-watermark，唔代表每個 provider／日期都齊資料。
凍結判決尺、production 權重及 golden snapshots 都冇改。
