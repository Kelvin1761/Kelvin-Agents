# EXP-20261015-11 — AU 現行權重有冇過時？（合約 §8 stale arm：B0 vs A0）

- 問題：之前所有 AU 候選都係喺現行 `MATRIX_WEIGHTS` 下測。修好 leaf（例如全程速度、
  sectional）之後，現行權重可能已經唔係最佳。合約 §8（EXP-20261015-08，分支
  `claude-refit-both-arms-20261015`，未 merge）定咗四 arm；呢度量其中 **stale arm**：
  B0（同一份 baseline leaf，walk-forward refit 權重）vs A0（現行權重）。
- 背景：EXP-20261015-02 同一程序 refit 對固定權重打和（Gold +0.20pp CI [−0.39,+0.74]）。
  EXP-20261010-06 證實「全部設中性」差好多，所以唔用中性 arm。
- baseline commit：origin/main `d51796e1`（已含 EXP-20261015-07 全程速度、
  EXP-20261015-04 PIT 修正、六場試閘門檻）。

## 預先登記（跑 refit 之前寫）

1. 工具：`au_walkforward_refit.py`（本實驗新增）。程序完全沿用 EXP-20261015-02 嘅六場
   refit：乾淨語料 2026-08-05 起；label 要有 ≥3 匹入位同頭馬；warmup 30 個賽日；
   每 7 個賽日一窗（尾窗保留）；每窗 256 個 Dirichlet draws（seed 7，偶數 broad、
   單數圍住現行權重 ×25）；place 目標（Gold、Good positional、Pass、Top3 precision）；
   training Gold／Good 唔低過現行權重、目標要升、五個日期塊至少四塊不負；
   逐維度中位數共識再正規化；共識用 production 算術再過同一閘，唔過 fallback 現行權重。
   **唔取 argmax。** 唯一分別：numpy 提案同 production 重算都包埋 `full_time` overlay
   （EXP-20261015-07 之後先存在）。
2. 判決：v3 `evaluate_full_record(mode="walk_forward_oos")`，day bootstrap 2000／seed 7／
   六塊；primary Gold、Good positional；ranking `top3_capture_at5`、`ndcg_at5`、
   `top5_pairwise_auc`。Pass 只報 day-bootstrap CI 做診斷。
3. **一次過**：只跑一次，冇第二組設定、冇揀窗、冇改目標。結果點都照記。
4. **B0 贏都唔換權重。** 合約 §8：stale arm 只報告。要換權重就要當一個獨立純權重候選，
   同用戶傾過先開。B0 輸／打和 = 冇證據話現行權重過時，唔等於證明佢最優。
5. 洩漏：fit 只見窗口之前日期（工具有測試）。歷史來源／label availability 未逐筆
   source-certify，PIT FLAG 照舊；`promotion_authorized=false`。

## 結果

**判決：REJECT（`ranking_evidence_too_weak`）。冇證據顯示現行 AU 權重已經過時。**
唔換權重；亦冇開純權重候選嘅理由。

語料：新鮮 dump（main `d51796e1`）3,258 場 → 乾淨 2,455 場／70 日；warmup 30 日 1,003 場；
OOS **1,452 場／40 日**，六個窗。replica 驗證：production 重算 vs 引擎存檔 ability
max|Δ| = 0.0；numpy 提案 vs production = 0.0；指標表 vs 正典 `_counts` 7e−15。

| 指標 | A0 現行 | B0 refit | Δ | 95% day CI | p | 六塊 Δ |
|---|---:|---:|---:|---|---:|---|
| Gold | 283（19.49%） | 288（19.83%） | **+0.34pp** | [+0.00, +0.73] | 0.094 | +1.24 +0.75 0 0 0 0 |
| Good positional | 384（26.45%） | 386（26.58%） | +0.14pp | [−0.35, +0.60] | 0.648 | +1.24 +0.37 −0.72 0 0 0 |
| Pass（診斷） | 727（50.07%） | 725（49.93%） | −0.14pp | [−1.11, +0.84] | 0.864 | — |
| top3_capture_at5 | | | +0.0005 | [−0.0027, +0.0037] | 0.738 | |
| ndcg_at5 | | | +0.0020 | [−0.0000, +0.0044] | 0.056 | |
| top5_pairwise_auc | | | +0.0005 | [−0.0015, +0.0026] | 0.605 | |

Gold CI 下限啱啱好係 0，唔係 >0，所以唔係 primary win；ranking 只得 `ndcg_at5` 一項
接近，冇一項 CI 全正 → `ranking_evidence_too_weak`。

### 每窗 fit

| 窗 | 訓練到 | 訓練場數 | 過閘 draws／256 | fallback | 權重（stab／pace_perf／JT／class／track／prep） |
|---|---|---:|---:|---|---|
| 0 | 09-04 | 1,003 | 4 | — | .302／.118／.650／.300／.127／.434 |
| 1 | 09-11 | 1,244 | 3 | — | .279／.118／.617／.330／.119／.467 |
| 2 | 09-18 | 1,511 | 6 | — | .326／.130／.645／.371／.115／.344 |
| 3 | 09-25 | 1,788 | 4 | 中位數重檢唔過 | 現行 |
| 4 | 10-02 | 2,030 | 0 | 冇共識 | 現行 |
| 5 | 10-09 | 2,295 | 0 | 冇共識 | 現行 |
| 現行 | | | | | .371／.121／.663／.383／.141／.252 |

### 點讀

- **256 個 draw 得 0–6 個過閘，而且訓練數據越多越少（尾三窗全部 fallback）。**
  即係喺 place 目標下，現行權重附近已經好平；冇乜方向可以穩定咁贏佢。
  後三塊 Δ 全部 0 就係因為 fallback —— 有效比較其實只係頭三窗（~700 場）。
- 頭三窗嘅共識方向一致：**preparation 升（.25→.34–.47）、stability／class 降**。
  呢個係一個可以記低嘅方向，但證據只係 Gold +0.34pp、CI 掂零，唔夠開候選。
  如果將來要試，佢係一個獨立純權重候選，要重新預先登記、用之後嘅新日期驗。
- 同 EXP-20261015-02（六場 refit Gold +0.20pp CI [−0.39,+0.74]）方向一致、幅度相若：
  兩次獨立 dump（前後隔住 EXP-07 全程速度上線）都話 refit 對現行權重打和。
- **對 §8 嘅意義**：stale arm 冇舉旗，所以之後 leaf 候選嘅 B1 vs B0 比較，
  B0 基本上等於 A0 —— refit arm 主要會喺「候選 leaf 改咗資訊量、令最佳權重移位」
  嗰陣先有分別，唔係因為底座權重本身過時。
- 功效：40 日、1,452 場，Gold 嘅 CI 半闊 ~0.37pp。少過 ~0.4pp 嘅權重效應呢個窗口量唔到。

### 證據限制

- 歷史來源／label availability 未逐筆 source-certify（PIT FLAG 照舊）；
  `leakage_audit_passed=True` 只係俾研究診斷計數，`promotion_authorized=false`。
- `evaluate_with_refit_arms` 仲未 merge（分支 `claude-refit-both-arms-20261015`）；
  呢度直接用同一個 stale arm 計法：`evaluate_full_record(mode="walk_forward_oos")`，
  baseline = A0、candidate = B0。

## 工具

`.agents/skills/au_racing/au_wong_choi_auto/scripts/au_walkforward_refit.py`
（測試 `tests/test_au_walkforward_refit.py`，10 項）。

- `predict`：由 leaves dump 輸出逐場 `ability_live`（A）同 `ability_refit`（B），
  兩個都係 production mapper + `compose_matrix_score` + overlay 次序／4dp 重算；
  numpy 只用嚟篩 draws。開跑前先 `verify`，replica 對唔上就拒絕 fit。
- `procedure_hash`：程序設定 + 工具 source 嘅 sha256，俾 §8 判決器驗證 B0／B1 對稱。
  今次 hash：`7207e406e6a16701b46f4d58b0c057e3185a7c330691badae18ac763e02e975d`。
- `arm_metric_rows(predictions, "live"|"refit")`：直接畀 `evaluate_with_refit_arms`
  嘅四組 rows。§8 用法：baseline dump 同 candidate dump 各跑一次 `predict`
  （同一 commit → 同一 hash），A0/B0 嚟自 baseline、A1/B1 嚟自 candidate。
- `stale`：B0 vs A0 嘅 v3 判決 + Pass 診斷 CI。

## 重現

```bash
export PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1
S=<scratch>
python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_dump_engine_leaves.py \
  --out $S/au_leaves_main_d51796e1.json          # 約 26MB，3,258 場
T=.agents/skills/au_racing/au_wong_choi_auto/scripts/au_walkforward_refit.py
python3 $T predict --data $S/au_leaves_main_d51796e1.json --out $S/wf_b0.json   # ~5 秒
python3 $T stale --pred $S/wf_b0.json --out $S/stale_b0_a0.json
```

dump sha256 同每窗權重、完整判決喺
`EXP-20261015-11-au-stale-weights-b0-vs-a0-evidence.json`；逐場 prediction 大檔唔入 repo。
