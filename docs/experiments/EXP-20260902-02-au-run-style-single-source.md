# EXP-20260902-02 跑法收成一個來源、剔走預設守中，再測佢做排名特徵

- **日期**：2026-09-02
- **平台**：AU
- **假設**：跑法標籤之所以「量落去冇用」，係因為 68.7% 嘅 runner 頂住一個**預設**
  守中。收成單一來源（Sportsbet 走位證據）＋ 三態化之後，跑法應該落得到排名。
- **搜索過嘅舊記錄**：[EXP-20260902-01](EXP-20260902-01-au-track-geometry-and-run-style.md)
  （同一日，量到剔走預設守中之後場內 AUC 0.5489 [0.5241, 0.5781]、對模型 ρ +0.079）；
  memory `au-run-style-mostly-unpredictable`、`leaf-auc-gains-do-not-convert-to-ranking`。
- **改到嘅檔案／組件**：
  - `.agents/scripts/inject_fact_anchors.py`（`weighted_au_running_style`、速度圖分組）
  - `au_racing_engine/engine_core.py`（`_running_style`、`_expected_position_label`、
    `_tactical_scenario_text`、剷走 `run_style_bonus`）
  - `au_racing_engine/scoring.py`（`run_style_bonus` 由 MICRO_WEIGHTS 剷走）
  - `build_au_logic.py`（分叉副本改為 import 引擎嗰份）
  - 新增 `tests/test_run_style_single_source.py`

## 一：跑法本來有四個來源

| # | 來源 | 問題 |
|---|---|---|
| 1 | `running_style_line`（Sportsbet 走位證據加權） | 唯一應該存在嘅來源 |
| 2 | `race_shape_summary` | 舊 Racenet 場面摘要，Racenet 本身已剷走 |
| 3 | `facts_section` token 掃描 | 由敘述文字撈「前領／後上」，撈到嘅可以係**對手**嘅跑法 |
| 4 | `tactical_plan.expected_position` | 我哋自己推嘅：冇跑法證據時**由檔位**寫「守中 / 內欄」或「守中 / 居中」，而呢個 label 又被 `_running_style()` 當 fallback 讀返 —— 自己餵自己 |

2–4 全部剷走。`_expected_position_label()` 由收三個輸入（加權跑法 + 上仗跑法 + 檔位）
改成只收 Sportsbet 加權跑法，冇證據就返空字串，戰術劇本轉為「冇走位證據，跑法未定」
嘅純檔位講法。`build_au_logic.py` 嗰份分叉副本改為 import 引擎嗰份。

## 二：預設守中拆成三態

`weighted_au_running_style()` 本來將**兩種完全唔同**嘅情況都寫成守中：冇證據、
同有證據但唔一致。改為 `unknown` / `mixed` / 實測跑法三態；速度圖加 `unclassified`
組，唔再將「唔知」掃入 `mid_pack`。

實跑一場（2026-09-02 Warwick Farm R1，5 匹早期生涯馬）：
舊輸出 `5 × 守中/守中(低)`，新輸出 `4 × 未知/未知(無) + 1 × 多變/多變(低)`，
`mid_pack: []`、`unclassified: [8, 1, 5, 7, 2]`。

## 三：跑法做排名特徵 —— dev 升，terminal 唔跟

⚠️ **第一次判錯，已更正。** 初版我用咗一個**自己發明**嘅閘（「gold 同 good 喺
5 個 dev fold 全部唔跌」），仲引咗 `pass` / `t3prec` 倒退做 REJECT 理由。
兩樣都唔啱：`docs/model-evaluation-contract.md` 嘅 Stage 4 v2 寫明 primary KPI
**只有** `gold` 同 `good_positional`，而 `pass` / `t3prec` 連預先登記嘅 ranking
metric 名單都唔喺入面。用一把自己嘅尺去 REJECT，同用一把自己嘅尺去 PASS
係同一種錯。下面係用 canonical `model_evaluation_decision.py` 重判。

- **語料**：1,020 場（2026-08-05 起乾淨 point-in-time）
- **覆蓋**：有實測跑法 38.8%（其餘 z = 0，唔郁佢）
- **k**：2.0，**只由 dev 側揀**（六個 k 入面 dev Gold +0.69 / Good +1.15 最好）
- **切法**：判決器按**整日**切，terminal 15%，配對逐場 bootstrap
- **terminal 只開過一次**，開之前 k 已鎖死

| 指標 | dev | terminal | terminal 95% CI |
|---|---|---|---|
| **gold** (PRIMARY) | **+0.573pp** | **−0.676pp** | [−3.378, +1.351] |
| **good_positional** (PRIMARY) | **+1.147pp** | **−1.351pp** | [−4.730, +2.027] |
| top3_capture_at5 | −0.306pp | −0.225pp | [−1.577, +1.351] |
| ndcg_at5 | +0.084pp | +0.242pp | [−0.962, +1.570] |
| competitive_recall_at5 | −0.269pp | −0.045pp | [−1.137, +1.070] |

**判決：`REJECT` / `primary_regression`。**

Cohort guardrail 全部冇倒退（馬匹數 ≤8 gold +0.58 / good +2.31；9-12 +0.34/+0.00；
13+ 0.00/0.00；好地 +0.85/+1.13；濕地 +0.15/+0.60）—— 即係話個訊號喺 dev 側
**唔係一個 cohort 撐起嘅**，佢真係全面向好。問題純粹係**out-of-sample 唔跟**：
同樣兩個指標，喺未見過嘅日子度符號調轉。

⚠️ **功效**：terminal 得約 150 場，gold 嘅 CI 半寬 ±3.4pp，遠大過 dev 嗰 +0.57pp。
所以呢個 REJECT 嘅意思係「**證明唔到**」，唔係「證實有害」。要判得實，需要
terminal 場數大約再多一倍。呢個候選值得留喺 shadow 向前監測，唔值得而家上線。

## 四：順帶捉到一個永遠 fire 唔到嘅計分項

`run_style_bonus`（w = 5.2，「近 N 場正式賽跑法全部一致」）讀 Facts 往績表嘅
**走位跑法**欄。語料庫實測：**26,381 條往績行，呢欄 100% 係 `-`**。

根因唔係抽取漏咗，係**來源冇**：呢欄由逐仗賽評文字 (`extract_run_profile_from_video`)
產生，Racenet 落畫轉 Sportsbet 之後，sportsbetform 表格頁根本冇賽評 ——
抽取層寫死 `Video: / Note: / Stewards:` 三個空欄。隨機抽 60 個 cache 頁核實，
**0 個**含 stewards / comment 字眼。所以呢個 +5.2 分嘅條件永遠 False。

已剷走。golden 120 匹馬全部一致 —— 證實佢真係死嘅。

真正嘅走位證據而家喺「跑位軌跡」欄嘅 `S<n>` 起步位：正式賽 18,634 行有 10,530 行
（56.5%）攞得到。

## 檢查
- **leakage-audit**：PASS —— 只用 2026-08-05 起 point-in-time 場次；特徵由賽前
  Facts 往績重建；holdout 冇打開。
- **golden_scoring**：AU / HKJC 各 120 匹馬全部一致（剷走死 code 前後都係）。
- **data_contract**：PASS。**模型說明**已重新生成。
- **退步**：冇。`./檢查.sh` 五項全綠、九個 suite 全 PASS。

## 結論

單一來源同三態化係**正確性**改動，唔改排名（golden 冇郁），但令「跑法」呢個
標籤第一次代表一件可以量嘅嘢：以前 68.7% 嘅守中入面，一部分係冇證據、一部分
係跑法多變、一部分係真守中，而報告一律寫「守中，信心低」。

跑法做排名特徵**證明唔到**。EXP-01 量到嘅 AUC 0.5489 同正交性 ρ +0.079 都係真嘅，
dev 側 Gold +0.57 / Good +1.15 而且**每個 cohort 都唔倒退**，但 terminal 兩個
primary 都調轉符號（−0.68 / −1.35）。呢個係第三次見到同一形態（連 `class_score`、
`WinningTime 速度評分`）：**leaf 準唔代表加落去贏**。

同時記低一個**我自己犯嘅方法錯誤**：第一次判決我用咗自己發明嘅 fold 閘，
仲攞咗兩個唔喺合約入面嘅指標（`pass` / `t3prec`）做 REJECT 理由。
把尺喺 `docs/model-evaluation-contract.md`，唔喺 harness 作者手上 ——
呢個同「換指標去救候選」係同一種錯，只不過方向相反。

**決定**：
- 跑法收成單一來源、三態化、速度圖 `unclassified` → **KEEP**（正確性，排名不變）
- 剷走 `run_style_bonus` → **KEEP**（死 code，golden 證實）
- 跑法做排名特徵 → **REJECT / primary_regression**（canonical Stage 4 v2；
  dev Gold +0.57 / Good +1.15，terminal −0.68 / −1.35；terminal 開過一次就鎖返）。
  ⚠️ terminal 只有 ~150 場、CI ±3.4pp → 「證明唔到」而非「證實有害」，
  值得 shadow 向前監測，等 terminal 場數翻倍再重判。

**commit**：未 commit

## 重跑
```bash
python3 -m pytest .agents/skills/au_racing/au_wong_choi_auto/tests/test_run_style_single_source.py -q
./檢查.sh
```
