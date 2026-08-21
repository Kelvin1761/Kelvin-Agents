# 唯讀審計：AU / HKJC Wong Choi 現狀（2026-08-21）

- **baseline commit**：`b51793d7`。審計期間 repo 前進到 `1c483561`（另一個 session）——
  **評分路徑冇變**（`git diff b51793d7..1c483561 -- '*racing_engine/*'` 空、golden 120 匹一致），
  所以下面嘅 baseline 數字喺 `1c483561` 一樣成立。
- **性質**：唯讀。冇改 model code、參數、語料、預測、評估方法。冇 commit、冇 push。
- **用到嘅 skill**：`acquire-codebase-knowledge`、`data-quality-audit`、`leakage-audit`、
  `model-regression-gate`、`experiment-review`、`security-review`（部分）
- **未能使用**：`evaluation-contract`、`cross-agent-handoff`（兩個 skill 唔存在，
  upstream `github/awesome-copilot` 都冇）、`quality-playbook`（upstream 有但未安裝）。
  `docs/model-evaluation-contract.md` **唔存在** —— 下面第 2 節係由 code 反推，
  逐項標明係「code 寫死」定「我推斷」。

---

## 1. 架構

100% Python，冇 LLM 喺主線。兩條獨立引擎，**唔係互抄**（589 個 function 只有 5 個逐字一樣）。

| 層 | AU | HKJC |
|---|---|---|
| 主 orchestrator | `au_racing/au_wong_choi/scripts/au_orchestrator.py` | `hkjc_racing/hkjc_wong_choi/scripts/hkjc_orchestrator.py` |
| 評分引擎 | `au_wong_choi_auto/scripts/au_racing_engine/` | `hkjc_wong_choi_auto/scripts/hkjc_racing_engine/` |
| deterministic 執行 | `au_auto_orchestrator.py` | `hkjc_auto_orchestrator.py` |
| logic builder | `build_au_logic.py` | `create_all_skeletons.py` |
| 賽後覆盤 | `au_reflector/scripts/au_reflector_orchestrator.py` | `hkjc_reflector/scripts/hkjc_reflector_orchestrator.py` |
| 語料枚舉 | `shared_racing/scripts/corpus_paths.py`（2026-08-21 新增，見 EXP-01） | 同上 |

### 評分結構（AU，live）

冇訓練步驟。**手工擬合嘅六維加權線性模型**，唔係 ML 模型。

```
ability = Σ_k  clip(60 + (dim_k − 60) · gain_k) · w_k  + wet_form_overlay
dim_k   = clip(60 + Σ_i inner_i · (leaf_i − 60))
```

| 維度 | 權重 | leaf（inner weight） |
|---|---|---|
| stability | 0.3292 | form_score .60, performance_quality_score .40 |
| jockey_trainer | 0.22957 | jockey .333, trainer .286, jockey_horse_fit .381 |
| race_shape | 0.13485 | pace_map_score 1.0 |
| class_weight | 0.12042 | rating_score 0.7 |
| pace_perf | 0.10559 | pace_figure_score .942, trial_score .058 |
| track | 0.08037 | track_score 1.0 |
| ~~form_line~~ | **0（唔喺 MATRIX_WEIGHTS）** | formline .78, form .22 — 計算＋顯示，但**唔入排名** |

`MATRIX_DISPLAY_GAINS` = stability .975, pace_perf .9909, race_shape 4.1142,
jockey_trainer 2.4973, class_weight 2.7489, track 1.5193, form_line 1.0232。
**gain 同 weight 一齊乘落排名**，所以改一邊等於改模型。

`FEATURE_KEYS` 18 個，但只有 10 個（`ABILITY_FEATURE_KEYS`）入 ability。
其餘 8 個（distance / weight / consistency / health / confidence / class / sectional / formline）
係顯示或中間量。

### 排程（launchd，10 個 job）

AU：`morning`、`evening`、`healthcheck`、`bot`。
HKJC：`prerace`、`postrace`、`watch`、`recovery`、`weekly`。加一個 `wongchoi.health`。
⚠️ AU 排程跑**自己個 worktree** `/Users/imac/wongchoi-scheduler`（`au-production` 分支），
改共用 repo 唔會生效。

### 權威 vs legacy

- **權威**：上表所有路徑 + `shared_racing/{eval_metrics.py, scripts/}`
- **legacy / 唔好信**：`.agents/archive/`（38 檔）、`scratch/`（530 檔，ruff 已排除）、
  `_temporary_files/`、`au_retired_meeting_intel_20260821/`、
  repo root 8 個 `*-plan.md` / `*-review.md`（實驗系統之前嘅結論，日期唔明）
- **已被取代但仍在**：`au_matrix_weight_search.py`、`au_clean_7d_weight_search.py`、
  `au_weight_improvement_search.py` —— 三個都係 coordinate descent／argmax，
  `au_matrix_refit.py` 個 docstring 明文講佢哋會 overfit。**唔好用。**

---

## 2. 評估合約（由 code 反推）

`docs/model-evaluation-contract.md` **唔存在**。以下每項標明來源。

| 項 | 值 | 來源 |
|---|---|---|
| 基準命令 | `au_dump_engine_leaves.py --out X` → `au_eval.py --data X` | code |
| 主指標 | 頭 K=5 位**配對場內 AUC**，holdout 95% 配對 bootstrap 區間唔過 0，dev 點估計唔准負 | `au_eval.py` docstring 寫死 |
| bootstrap | 2000 次，**按場**重抽（同場配對唔獨立） | `BOOT=2000` |
| 次要指標 | gold, gold_strict, good_positional, pass, champion, winner_in_top3/5, t3prec, mrr, ndcg5, blowout | `eval_metrics.py` |
| holdout | 尾 15% **唯一日期**，唔切開同一日 | `date_partitions()` |
| fold | dev 內部 5 個時間 fold（`au_feature_ab` / `au_matrix_refit`） | code |
| 訓練期 | **不適用** —— 冇訓練步驟，權重手工擬合 | 推斷 |
| 隨機種子 | `golden_scoring.SAMPLE_SEED=20260821`；bootstrap `_boot_ci(..., seed=7)` **已固定** | code |
| 必需數據 | `AU_Racing/**/Race_*_Logic.json` + `AU_Historical_Raw_Race_Results.csv` | code |
| 排除記錄 | 前三不足 3 匹、冇頭馬嘅場次（`_counts` 直接 `continue`） | code |
| 樣本 | 1,413 場 / 14,121 匹（2026-08-21 實測） | 實測 |

### 合約層面嘅缺陷（記錄，冇改）

1. **「85/15」係錯嘅。** `date_partitions` 取 15% 嘅**日期**，但新見到嘅 Archive 數據每日
   場次密度高好多，實際 holdout = **512 / 1,413 = 36.2% 場次**。所有寫「holdout 15%」
   嘅 docstring 都已經唔準。
2. **HKJC 用完全另一套閘門**（`hkjc_no_regression_gate.py`，maximize keys =
   gold/good/min_threshold/champion/top3_has_champion/mrr/avg_top4_hits），
   同 AU 嘅 AUC 判決規則**唔通用**。冇任何文件講兩者點對應。
3. **場數指標唔按馬群大細正規化** —— 見第 6 節，呢個令 dev/holdout 數字唔可比。

---

## 3. 現行 baseline（`b51793d7`）

命令（可重現，1.0s）：
```bash
export PYTHONDONTWRITEBYTECODE=1
cd .agents/skills/au_racing/au_wong_choi_auto/scripts
python3 au_dump_engine_leaves.py --out /tmp/leaves.json
python3 au_matrix_refit.py verify --data /tmp/leaves.json    # replica 一致性
python3 au_eval.py --data /tmp/leaves.json --output-json /tmp/baseline_au.json
```

**語料**：1,413 場 / 14,121 匹 / 2025-08-02 → 2026-08-20
**replica verify**：ability max|Δ| 0.0108（14,121 匹中 1 匹 >0.01）、matrix max|Δ| 0.0033 ✅

| 指標 | all | dev (901 場) | holdout (512 場) |
|---|---|---|---|
| **頭5位 AUC（主判決）** | 0.6793 | 0.6871 | **0.6631** |
| 全場 AUC | 0.6655 | 0.6725 | 0.6503 |
| gold | 17.79% | 16.13% | 20.70% |
| gold_strict | 6.24% | 6.01% | 6.64% |
| good_positional | 23.53% | 21.47% | 27.15% |
| pass | 46.99% | 43.72% | 52.73% |
| champion | 25.73% | 24.81% | 27.34% |
| winner_in_top3 | 56.13% | 54.62% | 58.79% |
| winner_in_top5 | 75.19% | 74.30% | 76.76% |
| t3prec | 47.51% | 46.13% | 49.93% |

### 分層（Gold，只喺 dev 之內，隔離時間因素）

| 馬群 | 場數 | Gold |
|---|---|---|
| ≤8 | 209 | **31.58%** |
| 9–10 | 260 | 15.38% |
| 11–12 | 228 | 9.21% |
| 13+ | 202 | 8.91% |

**市場基準（舊量度，記憶記錄）**：SP 排序 AUC 0.7393 vs 我哋 0.6530。
⚠️ 呢個數字係喺**半份語料**上量嘅，未重驗。

### HKJC

`hkjc_no_regression_gate.py` 冇 `--baseline` 模式，設計上係比較兩個候選；
我冇跑到一個可引用嘅 HKJC baseline 數字。**HKJC baseline 仍然缺。**

---

## 4. 數據品質

| 級別 | 發現 |
|---|---|
| ~~CRITICAL~~ **已修** | `Archive/` 令 49.1% 已評分場次對判決層隱形（EXP-01，`corpus_paths.py` 已修） |
| **HIGH** | AU 主流程**冇接** per-meeting 數據健康掃描 —— `racing_data_health.py` 只有 `hkjc_orchestrator` 會叫 |
| **HIGH** | 語料庫只有 **11.0% 嘅 dev 場次**係乾淨 point-in-time；其餘係賽後重新評分過（最舊遲 349 日） |
| **MEDIUM** | `au_draw_bias_matrix.json` 係 **2026-08-09 靜態檔**，live 預測用 12 日前嘅偏差表 |
| **MEDIUM** | J/T 組合表有兩份（引擎讀 `resources/`，aggregator 寫 `AU_Racing/`），冇自動同步 |
| **MEDIUM** | HKJC 語料有 22 個 Logic 喺 backup 目錄（`_pre_v52_backup` 等）+ 一個自我嵌套場次；`corpus_paths` 正確排除，但檔案仍在，任何用 `rglob` 嘅新 code 會中招 |
| **LOW** | `2026-07-15_HappyValley` 場次資料夾存在但零 Logic 檔 |
| **LOW** | HK 語料有 `(Heison)` / `(Kelvin)` / `_V2` 後綴嘅疑似重複場次 |

**綠燈項**：`data_contract --check` AU（60 場 / 579 匹）同 HKJC（60 場 / 768 匹）**全部欄位符合基準**。
賽果 CSV 覆蓋 86 個日期到 2026-08-20，Archive 全部 21 個日期都有賽果。
`./檢查.sh --quick` 全部過。

---

## 5. 洩漏審計

問題係：**「呢個確切數值，喺落注嗰刻真係拎得到？」**

| 特徵族 | 判定 | 理由 |
|---|---|---|
| 賠率 / 市場價 | **SAFE** | 引擎 grep `odds/price/win_odds` 零命中 —— 賠率完全唔入評分 |
| 賽果欄位 | **SAFE** | 引擎唔讀 `Race_Results_*.json`；`au_runtime_micro_ablation` 明文喺評分之後才 join |
| form_score / performance_quality | **LIKELY SAFE** | 由 form line 抽，全部係過去賽事。曾經有 Sportsbet form page 洩漏當場（17.1%），已修並有 test |
| jockey / trainer / jockey_horse_fit | **LIKELY SAFE** | 由馬匹自己過去 form line 逐次聚合（`engine_core:5818-5830`），日期全部早於賽日 |
| pace_figure / sectional | **LIKELY SAFE** | 過去 L600 實測，非賽後 |
| rating_score | **QUESTIONABLE** | 官方評分係**時間窗**欄位，RA 個窗只回溯一星期，過咗補唔返；曾因州曆永久 cache 凍結 11 日（已修 6h TTL）。歷史場次嘅 rating 未必係當日真值 |
| **pace_map_score / draw bias** | **僅限歷史評估** | 見下 |
| sire / 血統 | **CONFIRMED LEAKAGE（已剔除）** | leave-one-out +4.9pp 但 point-in-time 全負；LOO 唔係 leakage control |

### pace_map_score / draw bias —— 只影響歷史評估，唔影響 live

`au_draw_bias_calculator.py` 讀 `AU_Backfill_Race_Results.csv`，**只用 `Date` 砌 race_id，
完全冇時間 cutoff**（line 68 讀日期、line 82 砌 id，之後冇比較過賽日）。
產物 `au_draw_bias_matrix.json` 係一個 **2026-08-09 靜態 committed 檔**，
`engine_core:1281` 每次評分都載入佢。

Cell 厚度（728 個 per-track cell）：

| | |
|---|---|
| 中位數 sample_size | **7** |
| < 5 個樣本 | 317 cell（43.5%） |
| < 10 個樣本 | 458 cell（62.9%） |
| < 20 個樣本 | 563 cell（77.3%） |

**⚠️ 我第一版寫錯咗兩樣，已更正：**

1. **draw matrix 係喺 `_pace_map_score()`（`engine_core:1245-1319`）內用**，餵
   `pace_map_score` → **`race_shape`**（權重 0.13485、display gain **4.1142**，
   全部維度中最大嘅 gain）。**唔係** `track_score`。
2. **live 預測唔受影響。** 相對今日嘅賽事，matrix 內所有賽果都係過去 —— 用晒係合理嘅。
   問題**只限歷史評估**：回測一場舊賽事嗰陣，matrix 已經包含咗嗰場自己嘅賽果。

**後果（只限回測）**：任何**早過 2026-08-09**（matrix build date）嘅場次，佢自己嘅賽果
就喺用嚟評佢嘅 cell 裡面。以中位 cell = 7 計，單場自我貢獻約 14% 或以上。
dev 窗（2025-08-02 → 2026-08-07）**全部**早過；holdout（08-08 → 08-20）**幾乎全部**遲過。
即係 **dev 嘅 race_shape 被高估，holdout 冇** —— 呢個同第 6 節嘅馬群混淆同方向，
兩者一齊解釋咗為咩 pooled 數字睇落 holdout 好過 dev。

**repo 已經有專用工具**：`au_draw_walkforward_audit.py`（docstring 明文寫住呢個分野，
逐場按日期重建 draw 訊號、只替換 `pace_map_score`、再送入 `au_eval`）。
所以呢個唔算「未知風險」，而係「有工具但我搵唔到跑過嘅記錄」。
`RollingDrawStats` 已實作，2026-08-21 仲有另一個 session 喺度加 pool baseline。

⚠️ 同記憶記錄 `au-draw-granularity-earns-its-keep`（「per-track 細 cell 睇落似噪音
但實測贏」）相關：細 cell 之所以「贏」，**可能係因為回測洩漏**。假設，**未證實**。

---

## 6. 評估有效性

| 問題 | 嚴重性 | 證據 |
|---|---|---|
| **時間切分等同 regime 切分** | **HIGH** | dev 11.0% 乾淨 point-in-time / 平均馬群 10.51；holdout 100% / 9.08 |
| **場數指標唔按馬群正規化，令 dev/holdout 唔可比** | **HIGH** | dev 內 Gold 由 ≤8 匹 31.58% 跌到 13+ 匹 8.91%（3.5×）。**控制馬群（只取 9–10 匹）之後：dev 15.38% vs holdout 13.33% —— 結論反轉。** 表面「holdout 好過 dev」100% 係組成假象 |
| holdout 實際佔 36.2% 唔係 15% | MEDIUM | `date_partitions` 取日期百分比 |
| 閘門對細改動冇功效 | MEDIUM | ±0.3 中性擾動 40 次，三道閘全過 0/40 —— 假陽性 0，但真 +1pp 大機會被拒 |
| 舊 A/B 結論全部喺半份語料上量 | **HIGH** | 2026-07-15 之後所有數字，包括市場基準 0.6530 vs 0.7393 |
| survivorship / cherry-pick | 冇發現 | `date_partitions` 用全部日期；`_counts` 排除規則對稱 |
| train/test 實體重疊 | 不適用 | 冇訓練步驟；同一匹馬可跨窗出現，但排名係**場內**比較 |

---

## 7. Code / pipeline 風險

| 風險 | 證據 |
|---|---|
| **三個已知會 overfit 嘅權重搜索工具仍然可以跑** | `au_matrix_weight_search.py`、`au_clean_7d_weight_search.py`、`au_weight_improvement_search.py` |
| **曾經 29 個檔只掃一層語料** | `corpus_paths.py` 統一（EXP-01）；`066420c1` 補完餘下 18 個，`1c483561` 補健康檢查。盲區現時為零，但新 code 仍可能寫返 `rglob` 或 `*/Race_*` |
| macOS bytecode 陷阱 | `.pyc` 喺 `~/Library/Caches/com.apple.python`，靠 (mtime, 大細) 判斷；同長度權重改動 = phantom A/B |
| 靜靜吞錯 | 引擎路徑內 4 處 `except … pass/continue`；全 racing 樹 177 處（多數合理） |
| ruff 804 個提示 | 486 F541、200 F401、118 F841。`檢查.sh` 只 gate F821/F811/F823/E9 等**真係壞**嘅規則（刻意） |
| **1 個 test suite 長期紅** | `Agent scripts` —— `test_hkjc_high_quality_features.py` assert 兩個從未 merge 過嘅函數（只存在於 `scratch/`）。由 2026-08-03 起，`AGENTS.md` 已記錄 |
| 排程 config drift | AU 排程跑 `/Users/imac/wongchoi-scheduler`（`au-production`），同呢個 repo 唔同步 |
| **並行 agent 寫入** | 今日一個 session 三次 commit + push 咗另一個 session 嘅 working tree。`git status` 隨時變 |
| AU 主流程冇數據健康閘 | `racing_data_health.py` 只接 HKJC |

**其他 8 個 suite 全部 PASS**（AU / HKJC / Shared / Race compliance / NBA / Dashboard py+node / Tennis）。
security：我新增嘅檔冇 secret；`.claude/worktrees/`（1.2 GB）已加入 `.gitignore`。

---

## 8. 實驗歷史

`docs/experiments/` 今日建立，3 個記錄（EXP-01 語料盲點、EXP-02 gain/權重重 fit **REJECT**、
EXP-03 pace_map 梯度 **NEEDS MORE TESTING**）。之前嘅結論散落喺 85 條記憶記錄同
repo root 8 個 `*-review.md` / `*-plan.md`。

### 已判死，**冇新數據源就唔准重試**

sire signal（洩漏）、Sportsbet Speedmap（AUC 0.5204 輸自家 0.5395）、轉贏注、
位賠 ≥2 門檻、當朝落注、PF backfill（`WC_PF_BACKFILL`）、jockey/trainer 六個公式方向、
layoff 做排名特徵、自己 derive run style、trainer_signal、J/T combo 表入分、
pairwise 權重逐對搜索、gain/權重聯合重 fit（EXP-02）。

### 成功嘅
矩陣重 fit 取共識唔取 argmax（`ae71927`，11 個指標全升）、中性顯示尺修正、
穩定性＋段速能力修正、opponent index 由 form-line 抽（12.8%→99.9%）、
Sportsbet 取代 Racenet、賽果 CSV ingestion 補回（553→688 場）。

### 實驗稀薄嘅區域
- **`track` 維度**（權重 0.08037）—— 唯一嘅相關記錄係 draw baseline 分母 bug 同 granularity，
  **從來冇做過 point-in-time 洩漏測試**
- **`class_weight`**（0.12042，只靠 `rating_score` × 0.7）—— 幾乎冇實驗
- **HKJC** —— 絕大部分實驗都係 AU
- **場數指標嘅馬群正規化** —— 冇任何記錄

---

## 9. 最高價值機會（未實作）

### P1 — 跑 `au_draw_walkforward_audit.py`（工具已存在，唔使新寫）

- **假設**：`au_draw_bias_matrix.json` 係靜態全期檔，dev 場次嘅賽果喺用嚟評佢自己嘅
  cell 內（中位 cell 7 個樣本）。point-in-time 重建之後，`track` 維度嘅實測貢獻會顯著下降，
  而「細 cell 贏」呢個結論可能反轉。
- **點解可能有用**：唔係「令模型變好」，係**令所有 track 維度嘅過去量度變可信**。
  順帶修好 live 用 12 日前偏差表。
- **上升空間**：模型分數本身可能微跌（去掉洩漏）。真正收益係評估可信度。
- **主要風險**：修完之後 `track` 可能證明係淨負，要決定剷唔剷。
- **洩漏風險**：呢個實驗**就係**修洩漏，本身零新增風險。
- **複雜度**：中。要改 `au_draw_bias_calculator.py` 加 as-of cutoff，並且逐場重建。
- **所需實驗**：per-race as-of matrix → 重新 dump leaves → `au_eval` 比較 → `au_paired_significance`。
- **驗收**：頭5位 AUC holdout 配對 bootstrap；同時報 `track` 維度嘅場內 AUC 變化。

### P1 — 場數指標按馬群大細分層（評估修正，非模型改動）

- **假設**：Gold/Good/Pass 唔正規化，令任何改變馬群組成嘅嘢（換語料、換窗）
  都會偽裝成模型變化。
- **點解可能有用**：控制馬群之後 dev 15.38% vs holdout 13.33%，同未控制嗰個
  20.70% vs 16.13% **方向相反**。所有次要指標嘅比較都受影響。
- **上升空間**：唔改模型分數，但避免下一個假結論。
- **風險**：低。要小心唔好變成「改量度令候選好睇」—— 所以呢個必須**獨立於任何候選**先做。
- **洩漏風險**：無。
- **複雜度**：低（`eval_metrics.py` 加分層輸出）。
- **驗收**：喺 40 個已知中性擾動上，分層版本嘅方差應該細過 pooled 版本。

### P2 — 重驗市場基準

- **假設**：SP 排序 AUC 0.7393 vs 我哋 0.6530 係喺半份語料上量嘅，真實差距未知。
- **複雜度**：低（`au_market_benchmark.py` 已存在，行新 leaves 就得）。
- **驗收**：同一份 1,413 場語料上兩個 AUC。

### P2 — `class_weight` 維度（0.12042 權重，只靠 rating_score × 0.7）

- **假設**：一個 12% 權重嘅維度只由單一 leaf ×0.7 驅動，而 `rating_score` 已標
  QUESTIONABLE（時間窗欄位）。可能權重同實際判別力脫節。
- **所需實驗**：`au_leaf_power.py` 量 `rating_score` 場內 AUC → `au_eval --swap-leaf rating_score=60`
  量剷走佢嘅代價。
- **驗收**：頭5位 AUC holdout；若剷走冇損失 = 12% 權重係浪費。

### P3 — `form_line` 維度嘅去留

- **假設**：`form_line` 有 formula、有 display gain，但**權重 0**，即係計完唔用。
  要麼俾佢權重，要麼由 `MATRIX_FORMULAS` 剷走以減少混淆。
- **注意**：記憶記錄講過覆蓋率修好但排名冇郁。**呢個係整理，唔係優化。**

### P3 — HKJC 評估合約統一

- HKJC 冇可引用 baseline，用完全另一套 maximize keys。先寫一份合約文件。

---

## 10. 優化之前必須修

1. **場數指標分層** —— 唔修，dev/holdout 比較會繼續出反方向結論
2. **跑 draw walk-forward 審計** —— 唔跑，`race_shape`（最大 gain）嘅過去量度唔可信
3. **docstring 嘅「holdout 15%」改為實測值** —— 而家係 36.2%
4. **HKJC baseline** —— 而家冇一個數字可以引用
5. **AU 主流程接數據健康掃描** —— 而家只有 HKJC 有

## 可以即刻安全實驗嘅

- 任何**唔碰 `pace_map_score` / `race_shape`** 嘅單 leaf 替換（`au_eval --swap-leaf`）
- `au_leaf_power.py` 量度（純觀測）
- 市場基準重驗
- `feature-ablation` 階梯（工具已強制時間切分同場內 z-score）

## 建議第一個實驗

**P1 draw bias point-in-time 重建。** 唔係因為佢升分最多，而係因為佢係唯一一個
會令「過去嘅量度可信」嘅改動 —— 其餘所有候選都會喺同一個受污染嘅 dev 窗上量。
先做佢，之後嘅實驗才有意義。

**未實作。等指示。**
