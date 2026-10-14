# EXP-20261014-10 — HKJC 市場基準 + 騎練 snapshot 前視審計

- 日期：2026-10-14；平台：HKJC；性質：**純量度，冇改模型、冇改評分 code**。
- 起因：對照外部項目 `stevw-repo/HKJC-Horse-Racing-ML-Research-Project`（MIT，2026-06-21）。
  佢 15,083 場 OOS 結論係「每個模型都輸返抽水，冇市場以外優勢」，並明文禁止用當季騎練 snapshot 計率。
- 搜索過：`docs/experiments/*hkjc*`（冇 HKJC 市場基準）、記憶 `au-market-benchmark`、`au-people-stats-have-lookahead`。
- Baseline HEAD：`0116c740`；dataset：`scratch/hkjc_race_weight_oracle_20261013/dataset.csv`（sha256 前綴 `3e73537b5200c3d6`）。
- Harness：`docs/experiments/patches/hkjc_market_benchmark.py`（`PYTHONDONTWRITEBYTECODE=1 python3 …`）。

## A. 市場基準

市場排名 = 各場次 `*全日賽果.json` 嘅**最終**獨贏價由低到高（同價按馬號）。只係評估用，市場唔入模型。
最終價包含我哋落評分之後先出現嘅資訊，所以呢個係上限參考，唔係公平對手。
指標一律用 `eval_metrics.race_metrics`（gold = 頭三全部喺 Top4；good = `good_positional`）。
配對 race bootstrap，10,000 次。終端段 = 最後 15% 日期（2026-09-23 起）。

三個模型排名：
- **replay** = dataset 嘅 `current_live_recomputed_ability`（現行引擎重播；時點 FLAG，見 B）
- **archived** = 場次資料夾 `HKJC_Auto_Scoring.csv` 嘅 rank（= dataset `current_live_rank`）
- **snapshot** = immutable 賽前 snapshot，取賽日 12:00 HKT 之前最後一份。**只有呢批係乾淨嘅 point-in-time。**

| 樣本 | n | 市場 gold | 模型 gold | 市場 good | 模型 good | 市場 AUC | 模型 AUC |
|---|---:|---:|---:|---:|---:|---:|---:|
| replay，全部 | 356 | 18.54% | 13.20% | 28.93% | 22.47% | 0.7622 | 0.6863 |
| archived，全部 | 356 | 18.54% | 10.67% | 28.93% | 21.35% | 0.7622 | 0.6769 |
| **snapshot（乾淨）** | **96** | **20.83%** | **7.29%** | **35.42%** | **22.92%** | **0.7589** | **0.6491** |

- 差距 CI：
  - replay：gold +5.34pp [+0.56, +10.11]；AUC +0.0759 [+0.0582, +0.0944]
  - snapshot：gold +13.54pp [+4.17, +22.92]；AUC +0.1098 [+0.0702, +0.1492]
  - capture@5、ndcg@5 喺每個樣本都顯著輸。champion（首選勝出）全部跨零。
- 同 AU 好相似：AU 係 SP AUC 0.7393，我哋 0.6530。
- 首選同市場一樣只有 39.0%；場內 Spearman(模型, 市場) 0.615。

**Benter 測試**：模型喺市場之外有冇資訊？做法係 conditional logit 預測頭馬，效用 = b₁·log(市場機率) + b₂·z(模型排名)。

| 排名來源 | n | b_model | 95% CI（300 次 bootstrap） | LR |
|---|---:|---:|---|---:|
| replay | 356 | +0.214 | [+0.063, +0.383] | 8.51 |
| archived | 356 | +0.103 | [−0.048, +0.246] | 1.95 |
| snapshot（乾淨） | 96 | +0.115 | [−0.144, +0.392] | 0.69 |
| replay，同一批 96 場 | 96 | +0.165 | [−0.116, +0.446] | 1.42 |

- 判讀：**唔確定**。唯一 CI 唔跨零嘅係 replay，而 replay 嘅 dataset 經 `build_hkjc_ranking_dataset`，正正係 B 段揾到仲有前視嘅 caller 之一。
- 乾淨 snapshot 方向一樣係正，但 96 場冇 power。
- dev-fit 套落終端 61 場：NLL 由 2.0928 跌到 2.0898，細到唔算證據。
- 要等 snapshot 累積到幾百場先判得到。

## B. 騎練 snapshot 前視審計（唯讀）

| 路徑 | 判決 |
|---|---|
| live 賽前（`build_comprehensive_stats.py --write` → `live_priors`） | CLEAN：跑嘅時候當日賽果未入庫。FLAG：`temporal_source_is_safe` 對 `as_of_date=None` 或 `>= date.today()`（悉尼時區）一律放行（`live_priors.py:33`） |
| `pit_backtest.py` | CLEAN（`Date < meeting_date`，再剷嵌入 prior） |
| `rescore_backtest`／`score_race` | 而家 CLEAN，但退返人手 tier 表（2026-05／07 寫成，對舊場次帶事後知識，未量化） |
| 2026-08-21（`55899b3c`）之前嘅非 PIT 回放 | LEAK |
| 直接 call `RacingEngine(...)` 嘅 caller | **仍然 LEAK**：`build_hkjc_ranking_dataset.py:752`、`review_auto_weighting.py:705/1503/2178`、`hkjc_pi_ablation_probe.py:51`、`scratch/hkjc_dimension_ruler_20260904.py:36`。1,686 份 Logic 入面有 282 份冇 `race_date`，入面會攞全季 snapshot |
| 歸檔 Logic 嵌入嘅 `_data.jockey_trainer_combo_prior`（引擎優先用，`engine_core.py:1344`） | 2026-04：700/700 匹係賽後重寫（141 匹包當日賽果，559 匹包未來賽果）。2026-05：部分（243／138）。06–07：乾淨 |

量化：961 場，比較全季 snapshot 同嚴格 as-of。
- 平均勝率偏差好細（騎師 0 至 −0.24pp），但洩漏**同賽果相關**：騎師分 Δ 頭馬 +0.159，非頭馬 −0.090。
- 騎師分 + 練馬師分嘅場內 AUC：
  - 頭馬：+0.0162 [+0.0090, +0.0242]
  - 頭三：+0.0122 [+0.0069, +0.0172]
- 每個時間段都正。

受影響（FLAG，未逐個重跑）：
- 2026-08-21 之前用 `rescore_backtest`／`review_auto_weighting`／`walk_forward` 嘅 `trainer_signal` 數字，包括 07-09 `JT_RATING_PARAMS` 調參、07-17 `trainer_signal` 判決
- EXP-20260902-03
- 經 `build_hkjc_ranking_dataset` 嘅 EXP-20260928-01／03／06、EXP-20261013-08，**同埋本實驗 A 段嘅 replay 行**

唔受影響：EXP-20260904-*、20260905-03、20261004-01、20261005-01（用 PIT 注入）。

## 最細修正（未做，要另外開改動）

1. `temporal_source_is_safe(None)` 唔再放行；live caller 明確宣告 live。歷史場次冇 `race_date` 就唔讀嵌入 combo prior。
2. 直接 caller 用路徑日期 `setdefault("race_date")`。
3. `build_hkjc_ranking_dataset`／`review_auto_weighting` 改用 `pit_backtest.inject_as_of`。

修完之後要重新砌 oracle dataset，再重跑 A 段 replay 嘅 Benter 行。

## 驗證唔到

- 當年 live 用嘅 snapshot 內容：檔案只會覆蓋，冇留版本。live 乾淨係由流程推斷，唔係逐場核實。
- B 段量化用原始騎師分同練馬師分，未計組合／同程／換騎調整，亦唔係 ranking KPI。
- 審計 scratch：session scratchpad `jt_audit/`（唔入 repo）。

## C. 修正（2026-10-15）＋ 修正後重量

修正（§7 正確性修正，冇改權重／公式）：
1. `live_priors.temporal_source_is_safe`：`race_date` 缺失或無效時 **fail closed**（之前當 live 放行），stderr 警告一次。
2. `engine_core._jockey_trainer_prior`：Logic 嵌入嘅 `jockey_trainer_combo_prior` 只准 live（賽日 ≥ 今日）用；回放一律忽略。
3. 直接 call `RacingEngine` 嘅研究 caller（`build_hkjc_ranking_dataset`、`review_auto_weighting`、`validate_trainer_health_candidates`、`review_draw_weights`；`hkjc_pi_ablation_probe` 經 `review_auto_weighting`）用 meeting 資料夾日期補 `race_date`。
4. 回歸測試：`hkjc_wong_choi_auto/tests/test_jt_prior_as_of_guard.py`（6 個）。

Live 冇影響：live Logic 全部有 `race_date`（10-14 跑馬地 9/9、10-11 沙田 11/11），AU／HKJC golden 120/120 不變，`./檢查.sh` 全綠。

同一語料（362 場／4,500 匹）用修正前後 code 各砌一份 ranking dataset（只差呢個改動）：

| 量度 | 修正前 | 修正後 | Δ（配對 bootstrap 95% CI） |
|---|---:|---:|---|
| 能力分有變嘅馬 | — | 3,280／4,500（04–07 月幾乎全部；09–10 月 0%） | 平均 \|Δ\| 3.50，最大 14.12 |
| 頭四順序有變嘅場次 | — | 242／362 | |
| 場內 AUC（頭馬） | 0.7240 | 0.7196 | −0.0045 [−0.0151, +0.0055] |
| 場內 AUC（頭三） | 0.6915 | 0.6919 | +0.0004 [−0.0065, +0.0072] |
| Benter b_model（replay，356 場） | +0.214 [+0.058, +0.391] | **+0.215 [+0.069, +0.389]** | |

判讀：
- 前視主要喺冇 `race_date` 嘅舊歸檔（04–07 月）；09 月之後嘅 Logic 有日期，本身已經乾淨。
- 修走前視之後，能力分大幅郁、排序大量變，但整體排名質素**冇顯著變化**——騎練前視虛增嘅係騎練分本身（+0.016），喺綜合分入面被其他維度攤薄。
- **A 段「模型喺市場之外有資訊」唔係前視造出嚟**：修正後 replay 仍然 b_model +0.215，CI 唔跨零。但 replay 仍有其他 PIT provenance FLAG（歸檔 Logic 衍生欄位冇 immutable 時點證明），乾淨 snapshot 96 場仍然 CI 跨零。結論維持「方向一致、未證實」，要等 snapshot 累積。
- 舊 `review_auto_weighting` 自己讀 `25_26` 季度 CSV 做候選特徵（唔經引擎）嘅部分**未修**，用佢嘅 candidate 數字對 2026-04～07 場次仍然有前視，FLAG。
