# EXP-20260831-11 採用 Stage 4 v2 判決規則，並重判今日全部候選

**狀態：把尺已對齊（`8664ea9b` cherry-pick 落開發線）｜十個候選全部重判**
- **日期**：2026-08-31 ・ **平台**：AU
- **決定人**：Kelvin（「i feel like it should be Gold/Good primary + ranking evidence」）
- **性質**：**獨立改把尺**，冇同任何候選一齊改（`AGENTS.md` 要求）

## Stage 4 v2 係咩（讀完 code 之後）

唔係「只用場數指標」，係**兩層規則**：

1. **守門**：baseline／candidate 同 sample hash、同場數、holdout 鎖定、
   leakage audit 通過、預先聲明 cohort 冇 regression
2. **Primary** = `gold` ＋ `good_positional`。任一項 dev **或** terminal 點估計
   回歸 → 即刻 `REJECT`（`primary_regression`）
3. **`PRIMARY_WIN`**：Gold 或 Good 有 dev>0 **且** terminal>0 **且**
   terminal paired CI 下界 >0，另一項無回歸
4. **`RANKING_WIN`**：Primary 無回歸時，五個已登記 ranking metric
   （`top3_capture_at5`、`mean_top3_model_rank`、`competitive_recall_at5`、
   `ndcg_at5`、`top5_pairwise_auc`）入面 ≥2 個 dev 同 terminal 都正、
   ≥1 個 terminal CI 下界 >0、冇一個 terminal CI 全負

判決器：`.agents/skills/shared_racing/model_evaluation_decision.py`（289 行，
只食已計好嘅配對 evidence，唔會讀 holdout 揀參數）。

## 點解值得換：兩把尺對同一個改動得出相反判決

| | AUC-only（v1） | Stage 4 v2 |
|---|---|---|
| 個體化 `pace_figure` | holdout **+0.0010** [−0.0049, +0.0066] → 「呢把尺分唔開」 | `gold` holdout **+2.99pp** [+1.00, +5.19] → **`PRIMARY_WIN`** |

原因喺我今日量到嘅功效問題：**14 個 leaf 有 11 個連「完全剷走」都細過 AUC 閘門
嘅 MDE（±0.0058）**，所以 `top5_pairwise_auc` 單獨做判決係量唔到大部分改動嘅。
而 `gold` 喺同一個改動上動咗 3pp 而 CI 清零。

⚠️ 但 v1 對場數指標嘅批評（2026-08-04：±0.3 中性擾動 40 次，三道閘全過 0/40）
**唔係無效** —— 嗰個係「dev 5-fold + walk-forward + holdout」三道閘嘅組合。
v2 用嘅係「dev 符號 + terminal CI」，結構唔同，所以嗰個校準唔直接適用。
v2 嘅 `gold` MDE 實測 ≈ **2.1pp**（CI 半寬）。

## 重判結果（1,780 場，同一份語料同一個 split）

| 候選 | v1 判決 | **v2 判決** | v2 理由／證據 |
|---|---|---|---|
| **個體化 `pace_figure`**（已上線）| 過唔到 | **`PRIMARY_WIN`** ✅ | `gold` dev +0.39pp、holdout **+2.99pp** [+1.00, +5.19] |
| **今日兩個一齊**（已上線）| 全語料 CI 清零 | **`PRIMARY_WIN`** ✅ | `gold` dev +0.55pp、holdout **+3.39pp** [+1.20, +5.59] |
| 濕地 `prior` 0.5 → 0.3758（已上線）| 過唔到（作正確性修正）| `REJECT` | `primary_regression`：`good_positional` dev −0.16pp / holdout −0.20pp |
| 重配權（共識，`pace_perf` +37%）| REJECT | `REJECT` | `primary_regression`：`gold` holdout **−1.00pp** |
| `weight_score` 內部權重 0.10 | UNRESOLVABLE（正）| `REJECT` | `gold` holdout −0.20pp |
| `weight_score` 內部權重 0.141 | UNRESOLVABLE（正）| `REJECT` | `gold` holdout −0.20pp |
| `weight_score` 內部權重 0.20 | UNRESOLVABLE（正）| `REJECT` | `gold` holdout −0.40pp |
| E 節 中性點（三個一齊）| REJECT | `REJECT` | `gold` dev −0.08pp / holdout −0.20pp |
| E 節 中性點（只騎師）| REJECT | `REJECT` | `gold` dev −0.08pp |

**冇一個 REJECT 被推翻。** 唯一改變方向嘅係 `pace_figure` —— 由「證明唔到」
升級為 `PRIMARY_WIN`。

⚠️ 注意 `weight_score` 由 v1 嘅「每個 w 喺 holdout 都正（但 << MDE）」變成
v2 嘅明確 `REJECT`。唔矛盾 —— v1 量嘅係 `top5_pairwise_auc`（正但量唔到），
v2 量嘅係 `gold`（負而且睇得到）。**兩個 metric 方向唔同**，而 v2 明文話
primary 有回歸就 REJECT。

## 合約改動

1. **Stage 4 v2 升為唯一判決規則**，v1 兩段標為「歷史記錄」
2. **功效前置條件**（我今日加嘅）由 v1 段搬去 v2 之下第 6 節，
   改寫成**管排名證據層** —— 一個 ranking metric 嘅部件預算細過佢自己嘅 MDE
   就唔可以用嚟做 `RANKING_WIN` 嘅訊號，亦唔可以用佢嘅「CI 跨零」當反證
3. **新增第 7 節「正確性修正」** —— 修一個可以獨立證明係錯嘅嘢
   （常數註釋同實測唔符、regex 掉走一整類數據、閘門睇唔到自己要守嘅嘢）
   唔需要證明 primary 升，但要零顯著退步 ＋ leakage PASS ＋ 記錄明文寫
   「唔係已證實嘅改善」。
   **判斷標準：如果績效數字係相反方向，你仍然會改佢嗎？** 答唔到「會」
   就要走候選流程。

## 檢查
- `run_tests.sh` 十個 suite 全綠（新增 `test_model_evaluation_decision.py`
  同 `test_hkjc_stage4_gate.py`）
- `檢查.sh --quick` 全綠
- 零 model／feature／weight 改動 —— 純把尺 ＋ 重判
