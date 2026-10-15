# EXP-20261015-02 HKJC 三個 point-in-time 洩漏修正 + 受影響結論清單（§7 正確性修正）

- **日期**：2026-10-14（Sydney）／記錄編號用 2026-10-15
- **平台**：HKJC
- **性質**：§7 正確性修正，`mode = fixed_rule`。唔係績效假設；冇 fit 任何數值，冇改任何權重。
- **觸發**：L1「加未來唔可以改過去」不變性測試
  （`hkjc_wong_choi_auto/tests/test_hkjc_future_append_invariance.py`）三個 `expectedFailure`。
- **搜索過嘅舊記錄**：EXP-20260902-03（回放前視、守衛 fail-open 嘅原形）、EXP-20260902-08（PIT 注入）、
  EXP-20260904-06（PIT metadata 由排位表補）、EXP-20261010-06／-09（外層權重、race_shape 幅度）。

## 修正

| # | 洩漏 | 修正 | 檔案 |
|---|---|---|---|
| A | Formguide 往績行冇 as-of 閘：`--race-date` 只剔馬匹頁 profile | `parse_hkjc_formguide(as_of_date=)` 只留**賽日之前**嘅往績行（日期解唔到亦剔，fail-closed），剩低嘅行 `idx` 重新編 1..n；`main()` 一律傳 race_date（main 本身冇日期會 exit 2）。同 AU `parse_formguide_for_horse(as_of)` 對齊 | `.agents/scripts/inject_hkjc_fact_anchors.py` |
| B | 歷史回放 master stats 被守衛換成中性之後，`JockeyScorer`／`TrainerScorer` 跌落冇日期嘅 `05_jockey_trainer_tiers.json`（即「今日嘅層級表」）；小樣本 blend 嘅 prior 亦讀同一張表 | `score_tier(..., as_of_date=)` + `tiers_available()`：live（賽日 ≥ 今日）照用；歷史賽日只有當表本身有 `as_of_date` ≤ 賽日先用，否則中性 60（`歷史回放：層級表冇該日版本，中性60`）。四個 call site 全部傳 race_date | `features/tier_loader.py`、`features/jockey.py`、`features/trainer.py` |
| C | `temporal_source_is_safe(None)` 回 True（fail-open） | 新 `is_live_race_date()`：未知日期 = 唔係 live → 唔安全（中性），stderr 每個 process 警告一次 | `hkjc_racing_engine/live_priors.py` |

測試：三個 L1 case 拆咗 `expectedFailure`（14/14 綠）；`hkjc_reflector/tests/test_pit_replay_contract.py`
加 `TemporalGuardFailClosedTests`（未知日期、live 日期、層級表日期閘）同 `FormguideAsOfTests`；
`test_auto_outputs.test_chinese_jockey_and_trainer_names_are_scored` 原本用空 race_context 測 live 行為
（即係依賴 fail-open），改為傳今日日期，並加「未知日期 → 60」斷言。

**B 嘅取捨**：客串騎師（例如布浩榮）第一次喺香港策騎時，層級表嘅名將先驗**可能**係賽前已知嘅資訊。
但張表冇日期、冇版本，證明唔到。要恢復，就喺 JSON 加 `as_of_date` 並由 git 歷史砌每個版本 —— 唔喺今次範圍。

## live 有冇變

- 生產路徑全部有 race_date：`run_prerace_pipeline` 由資料夾名傳 `--race-date`（inject 冇日期會拒絕行）；
  live 資料夾一律 `YYYY-MM-DD_<Venue>`（HK_Racing 根目錄 36/36 個賽日資料夾符合）；
  `score_race` 由資料夾名推 race_date 並寫返入 `race_analysis`（2026-10-14 跑馬地 Logic 實測有
  `race_date: 2026-10-14`）。
- **今日 2026-10-14 跑馬地 9 場 101 匹**：舊 code（HEAD `fb001d47` export）vs 新 code 用同一份 Logic 重評，
  feature／matrix／ability／rank／grade **逐位一樣**。
- Formguide 閘：2026-10-14 嗰份 賽績.md 冇任何賽日當日或之後嘅行 → Facts 不變。
- `golden_scoring.py --platform hkjc`：120 匹全部一致（golden 只行 feature → matrix → ability，
  唔重算 leaf；改動喺 leaf 之前，所以預期唔郁）→ **冇 `--record`**。
- `data_contract --platform hkjc`：全部欄位符合基準；引擎 fingerprint（`ENGINE_FILES`）冇變，
  冇 stale-baseline → 唔使 recalibrate。模型說明新鮮度 ✅（唔使重生成）。

會被 fail-closed 改變行為嘅只有**冇日期嘅離線工具**（`rescore_backtest`／`review_auto_weighting`／
`train_hkjc_7d_ml_weights` 等食舊 Logic 嘅路徑，如果資料夾冇日期前綴）：佢哋以前靜靜讀 latest
快照，而家會中性兼印警告 —— 呢個就係修正本身。

## 回放影響（同一語料、同一 harness）

命令（`PYTHONDONTWRITEBYTECODE=1`，`TMPDIR` 指外置碟）：

```bash
S="/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/hkjc-pit-leak-fix-20261015"
# leaky = HEAD fb001d47 嘅 git archive；clean = 本 commit
python3 $S/old/.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py run --dump-matrix --out $S/leaky_base.jsonl
python3 .agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py      run --dump-matrix --out $S/clean_base.jsonl
python3 .agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py compare $S/leaky_base.jsonl $S/clean_base.jsonl --stage4 fixed_rule --leakage-audit-passed
```

語料：`hkjc_eval_harness.discover_meetings` 36 個賽日（2026-04-12 → 2026-10-11）、362 場
（6 場 `runner set differs` 兩邊一樣出錯 → 356 場有分；compare 預設剔 speed_score 死日 → 297 場）。

**A 喺語料入面實際觸發次數 = 0**：36 個賽日 26,404 條往績行，賽日當日或之後嘅 0 條
（全部 formguide 都係賽前抽）。A 係結構性修正，對過往回放冇數值影響。

**C 喺 harness 實際觸發次數 = 0**：harness 只收 `YYYY-MM-DD_<Venue>` 資料夾，日期一定有。

**B**：4,477 匹入面得 **7 匹**郁，全部係 `trainer_signal`（`jockey_score` 經騎練訊號傳導）：

| 賽日 | 騎師 | 原因 | trainer_signal | 綜合分 raw |
|---|---|---|---|---|
| 2026-04-22 跑馬地 R1/R3/R4/R6/R7/R9（6 匹） | 布浩榮 | PIT 冇紀錄 → 跌落層級表「客串名將」 | 67.2–70.6 → 59.0–62.4（−8.25） | −1.95 |
| 2026-09-09 跑馬地 R6 #9 | 巴度 | 小樣本 blend 讀層級表 prior | 67.77 → 65.52 | −0.53 |

排名：5 場前六名次序郁（全部 04-22 跑馬地，嗰日 speed_score 死，canonical compare 本身剔走）；
297 場 canonical 比較 **0 場改變**，Stage 4 v3 primary／ranking delta 全部 0.0000。

### 新 canonical HKJC replay baseline（356 場，唔剔死日）

| 指標 | 舊（leaky） | 新（clean） | Δ |
|---|---:|---:|---:|
| gold | 13.48% | 13.48% | 0 |
| gold_strict | 4.49% | 4.78% | +0.29pp（1 場：04-22 R1） |
| good_positional | 23.60% | 23.60% | 0 |
| champion | 25.56% | 25.56% | 0 |
| top3_capture@5 | 0.6273 | 0.6273 | 0 |
| NDCG@5 | 0.5323 | 0.5324 | +0.0001 |
| competitive_recall@5 | 0.5792 | 0.5792 | 0 |
| mean top3 model rank | 4.8684 | 4.8703 | +0.0019（差少少） |
| 場內 top-3 AUC（raw 綜合分） | 0.7007 | 0.7005 | −0.0002 |

即係：**2026-10-10 之後用 `hkjc_eval_harness` 量嘅 HKJC 數字冇被呢三個洩漏實質污染**。
污染只喺**之前**嘅 harness：EXP-20260902-03 嘅「乾淨版」係全部人跌落層級表（3,318/3,318 匹
trainer_signal 改變、平均 70.20）—— 嗰個「乾淨版」本身就係 B 洩漏。

## 高風險決定重判（clean harness，同一工具同一 flag）

工具：`hkjc_weight_study.py <dump> --arm …` → `hkjc_eval_harness.py compare`（current 為 baseline）。

| 決定 | arm | leaky 判決 | clean 判決 | clean Gold Δ | clean Good Δ | clean NDCG Δ |
|---|---|---|---|---|---|---|
| 現行外層權重 vs 全中性（EXP-20261010-06） | neutral | REJECT primary_regression | **REJECT**（不變） | −1.68pp [−5.84,+2.36] | **−7.41pp [−12.03,−3.01]** | −0.048 [−0.076,−0.023] |
| 現行外層權重 vs walk-forward refit（EXP-20261010-06） | wf_refit | REJECT | **REJECT**（不變） | −0.67pp [−4.05,+2.45] | −1.01pp [−3.55,+1.33] | −0.005 [−0.015,+0.004] |
| race_shape 27.37% 幅度 walk-forward（EXP-20261010-09） | wf_shape_k | REJECT | **REJECT**（不變） | −1.01pp [−3.44,+1.34] | −1.35pp [−3.85,+0.98] | −0.003 [−0.023,+0.016] |

（wf_refit Good 由 −0.67pp 變 −1.01pp：多 1 場；其餘逐位一樣。）**現行外層權重同 race_shape 權重
喺乾淨 harness 上照樣係最佳已知答案。冇一個 REJECT 翻案，冇一個 KEEP 倒下。**唔建議任何 refit。

## 受影響結論清單

判斷準則：證據係咪經「歷史場次行真 scorer」得出（→ B），係咪食冇日期 Logic／`--no-pit`／
賽後重評嘅 `python_auto`（→ C／master stats 前視），係咪用賽後重抽嘅 formguide（→ A）。
因為 B 喺 PIT harness 只郁 7 匹、0 場 canonical 排名，凡係 PIT 注入之後嘅回放都判「部分，可忽略」。

| 記錄／產物 | 證據來源 | 依賴洩漏？ | 理由 | 結論仲成立？ |
|---|---|---|---|---|
| 現行 9D 外層權重（`dimensions.py`，race_shape 0.2737） | 原始值係 2026-08 之前嘅舊回放（memory：最後真 fit 0.2260 喺 08-09 merge 消失），之後由 EXP-20260902-03／20260928-06／20261010-06 喺 PIT 回放覆核 | 原始 fit：**係**（C／master stats 前視）；覆核：部分，可忽略（B） | 今次 clean 重判 neutral／wf_refit 照 REJECT | ✅ 維持 |
| EXP-20260902-03 七維 refit + 回放前視 | 舊 replay；「乾淨版」= 守衛生效但全部跌落層級表 | **係**（「洩漏版」= C；「乾淨版」= B 100% 匹） | 乾淨版 gold_strict 3.03%／good 23.48% 唔係真 PIT 數字 | ⚠️ 數字作廢；refit REJECT 結論已由 EXP-20261010-06 喺 PIT harness 重做並今次再確認 |
| EXP-20260902-08 PIT 修復 + race_shape 組件審核 | `pit_backtest`（PIT 注入） | 部分（B，小樣本／客串騎師） | 組件消融唔郁騎練維度；配對 delta 兩臂共用同一 B | ✅ |
| EXP-20260904-03 顯示尺 + 級數優勢 12 候選 REJECT | `pit_backtest` | 部分，可忽略 | 顯示尺由 stored 分佈量（排名不變）；12 候選全部唔郁騎練 | ✅ |
| EXP-20260904-04 賽績線行修正 SHIPPED／班次入分 REJECT | `pit_backtest` + formguide 解析 | A：否（語料 0 條未來行）；B：部分 | 修正係解析正確性 | ✅ |
| EXP-20260904-05 七把尺 | stored 分佈 | 否 | 純顯示 | ✅ |
| EXP-20260904-06 PIT metadata／race_shape 消融唔再做 | `pit_backtest` | 部分，可忽略 | 同上 | ✅ |
| EXP-20260904-09 負磅方向 SHIPPED | `pit_backtest` | 部分，可忽略 | 唔郁騎練 | ✅ |
| EXP-20260905-03 騎練訊號 combo leaf／場地拆分 | `rescore_backtest`＋`pit_backtest` | 部分（**B 直接相關**：騎練維度） | B 只郁 7 匹且 canonical 0 場排名；但嗰陣語料細，未逐臂重跑 | ✅ 原 arm 重跑，修正前後逐位一樣（見下節） |
| EXP-20260907-05 race_shape 功效 + 前向 holdout | 功效計算 | 否 | 冇用回放數值做判決 | ✅ |
| EXP-20260928-01／-03／-04／-05／-06／-07／-08／-09／-10、20260929-01／-02／-03 | `scratch/patches` harness（PIT 注入） | 部分，可忽略 | 全部唔係騎練候選；配對 delta 共用同一 B | ✅（-06 hierarchical refit REJECT 同今次 wf_refit 重判一致） |
| EXP-20261004-01 季初 current-season priors（KEEP） | PIT priors 換季 | 部分（**B 直接相關**） | 候選本身就係騎練先驗；B 只影響 PIT 冇紀錄嘅人 | ✅ 原腳本重跑，修正前後逐位一樣（見下節） |
| EXP-20261005-01 練馬師 recency（REJECT） | patch harness | 部分 | REJECT 方向唔會因移走一個樂觀洩漏而翻案（洩漏喺兩臂） | ✅ |
| EXP-20261007-01～05、20261008-01～07 | patch／harness | 部分，可忽略 | 非騎練 | ✅ |
| EXP-20261010-01 騎練季節加權 | `hkjc_eval_harness`（含一次 `--no-pit` 忠實度檢查） | `--no-pit` 嗰次：**係**（設計上就係 live priors，記錄已寫明有前視）；正式判決：部分，可忽略 | REJECT | ✅ |
| EXP-20261010-02 擴大語料篩選 | 獨立 as-of 重建（唔經 scorer） | 否 | 每匹馬只用賽日之前 | ✅ |
| EXP-20261010-03～05、-07、-08（賽績線衰減）、-10～-16 | `hkjc_eval_harness` v3 | 部分，可忽略 | canonical 297 場 0 場排名差 | ✅ |
| EXP-20261010-06 9D 外層權重 | harness dump + `hkjc_weight_study` | 部分，可忽略 | **今次 clean 重跑，判決不變** | ✅ |
| EXP-20261010-09 race_shape 幅度 WF | 同上 | 部分，可忽略 | **今次 clean 重跑，判決不變** | ✅ |
| EXP-20261013-12 剷 PI（HKJC REJECT） | 362 場 harness | 部分，可忽略 | 非騎練 | ✅ |
| `train_hkjc_7d_ml_weights.py` 輸出 | 食 Logic `python_auto` | 視乎輸入：舊 Logic 冇日期 → **係**（C）；而家 fail-closed | 今次未核實現行權重有冇直接用佢嘅輸出（現行權重已由第一行重判覆蓋） | ⚠️ 將來重跑會得到唔同（更保守）結果 |
| HKJC golden snapshot | stored feature 向量 → matrix → ability | 否（唔重算 leaf） | 120 匹一致 | ✅ 唔使 `--record` |
| data_contract HKJC baseline | live stored `python_auto` | 否 | live 不變、fingerprint 不變 | ✅ 唔使 recalibrate |
| 顯示尺 gain／centre（EXP-20260904-03／-05） | stored 分佈 | 否 | live 分數不變 | ✅ |

## 建議跟進（唔喺今次做，冇新權重上線）

1. **唔需要 refit。**三個最高風險決定喺 clean harness 判決不變，baseline 指標 Δ ≤ 0.3pp。
2. ~~EXP-20260905-03、EXP-20261004-01 用原 arm 重跑~~ —— 2026-10-15 已做，見下節。
3. 層級表加 `as_of_date` + 由 git 歷史生成每個版本，令客串騎師首戰喺回放都有合法先驗。
4. 已知旁漏（唔入分，L1 測試已記）：`get_draw_summary_block` 唔對賽日；`--draw-stats` 冇被 parse
   —— `claude-hkjc-drawstats-20261014` 分支正處理，今次唔掂。

## 騎練候選原 arm 重跑（2026-10-15）

兩個騎練候選理論上最受洩漏 B 影響，用原腳本對修正前（`fb001d47` export）同修正後 code 各跑一次：

| 記錄 | 腳本 | 語料 | 修正前 vs 修正後 | 判決 |
|---|---|---|---|---|
| EXP-20260905-03 Q1 組合（A0–A5） | `patches/hkjc_combo_ab.py` | ≤ 07-12 嘅 26 賽日，193 場 | **逐位一樣**（baseline gold 14.51／good 25.39；A4 gold −2.60 [−5.18,−0.52]） | UNRESOLVABLE 不變 |
| EXP-20260905-03 Q2 場地（B1–B5） | `patches/hkjc_venue_ab.py` | 同上 | **逐位一樣**（B4 gold −2.09 [−4.15,−0.52]） | UNRESOLVABLE 不變 |
| EXP-20261004-01 季初 priors | `patches/hkjc_season_aware_priors_ab.py` | 09-06 → 10-01，7 賽日 67 場 | **逐位一樣**（Gold／Good Δ 0.00 [0.00,0.00]；Champion +1.49 [0.00,+4.48]） | KEEP D1/D2、HOLD M1 不變 |

點解完全唔郁：唯一受 B 影響嘅 04-22 跑馬地被 `rescore_backtest` 當 legacy schema 跳過（布浩榮馬一匹都冇入
193 場）；09-09 R6 嗰匹喺 67 場窗口內但兩臂排名不變。兩份記錄同原表嘅差距係之後引擎演進，唔係今次修正。
腳本只改咗 code root／語料清單（`hkjc_bt.lst` 由 HK_Racing 根目錄 ≤ 2026-07-12 有賽果嘅賽日重建）／輸出路徑，
輸出喺外置碟 `rerun_leaky/`、`rerun_clean/`。

## 可重現性

- base commit：`fb001d47`（origin/main `33705b78` + L1 測試 `6779d3a3` cherry-pick）
- 語料：`/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/HK_Racing`，36 賽日
- 輸出：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/hkjc-pit-leak-fix-20261015/`
  （`leaky_base.jsonl`、`clean_base.jsonl`、`compare_leaky_vs_clean.json`、`ws_*`、`cmp_*`）
