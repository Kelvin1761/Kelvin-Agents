# EXP-20260822-03 名次修好之後重 fit 權重；同濕地 overlay 嘅證據厚度

- **日期**：2026-08-22
- **平台**：AU
- **假設**：(A) EXP-01 令 `form_score` 場內 SD 由 8.09 闊到 10.65（+32%），而
  `MATRIX_WEIGHTS` / `MATRIX_DISPLAY_GAINS` 係喺舊分佈上 fit —— 重 fit 應該收返
  嗰個綜合打和。順帶預期會**減 `pace_perf`**（leaf ΔAUC +0.0000、全模型最弱），
  而 Gunroom 嘅優勢正正嚟自 `pace_perf`。
  (B) 濕地 overlay 係 Race 1 嘅決定性一項（+3.05 相對差），值得獨立審視。
- **搜索過嘅舊記錄**：[EXP-20260821-02](EXP-20260821-02-au-gain-weight-joint-refit.md)（重 fit REJECT ×2）、
  [EXP-20260822-01](EXP-20260822-01-au-unplaced-run-placings.md)；
  memory `au-matrix-refit-consensus-not-argmax`、`au-dimension-scale-weight-lockstep`、
  `au-gate-rejects-everything`、`au-matrix-weights-tested-dont-change`
- **改到嘅檔案／組件**：無（純量度）

## 配置
- **baseline**：4882ff8c 嘅 live 權重
  `{stability .38119, pace_perf .12203, jockey_trainer .26527, class_weight .13909, track .09242}`
- **candidate**：`au_matrix_refit.py refit`，3,000 條隨機向量、dev 揀、5 個時間 fold
  過 4/5 閘、**取過閘候選嘅逐維度中位數（共識），唔取 argmax**

## 數據
- **語料**：EXP-01 candidate arm（已修 + 已評分）→ `ds_cand.json` **603 場 / 5,762 匹**
- **dev / holdout**：512 / **91** 場（holdout 未碰過）
- **walk-forward**：首個訓練段 250 場、窗口 92 場、共 3 個窗口
- **replica verify**：max|Δ| **0.0091**、>0.01 **0 匹**（純 2dp 捨入）→ 離線搜索可信

## 結果 (A) 重 fit

### 四個 seed 收斂得好緊

| 維度 | live | seed1 | seed2 | seed3 | seed4 | 方向 |
|---|---|---|---|---|---|---|
| stability | .38119 | .41368 | .43045 | .41425 | .41485 | **↑** |
| pace_perf | .12203 | .13461 | .13485 | .13588 | .13966 | **↑**（同預期相反）|
| jockey_trainer | .26527 | .24604 | .24242 | .26337 | .25947 | ↓ 輕微 |
| class_weight | .13909 | .09488 | .08718 | .09128 | .09210 | **↓** |
| track | .09242 | .09404 | .09772 | .09190 | .08754 | 持平 |

### 但 holdout 唔跟

| | gold | good_pos | pass | champ | winT3 | t3prec | mrr | blowout | compet | ndcg5 |
|---|---|---|---|---|---|---|---|---|---|---|
| dev (512) | +0.00 | +0.39 | +0.78 | +0.39 | +0.20 | +0.13 | +0.23 | +0.59 | +0.78 | +0.09 |
| **holdout (91)** | **+2.20** | **−3.30** | +1.10 | −1.10 | **−3.30** | +0.00 | −1.07 | +2.20 | **−3.30** | −0.62 |

### walk-forward（repo 指定嘅閘）：OBJ 只贏 **2/3** 窗口

三個未見過嘅未來窗口平均：gold +0.36、good_pos −1.09、pass −0.72、champ +1.09、
winT3 +0.36、t3prec −0.60、mrr +0.62、blowout +0.36（差）、compet −0.36、ndcg5 +0.23。

**呢個語料冇 power**：holdout 91 場、窗口 92 場 → **1 場 = 1.09pp**。上面所有 ±3.30
都係 3 場。已 ship 嗰次重 fit 用 805 場。

## 結果 (B) 濕地 overlay 嘅證據厚度

`wet_form_feature = 14.852 × (收縮後濕地上名率 − 0.5)`，clamp ±6.18。收縮用
4 個 pseudo-start，所以**一場濕地往績就可以動 ±1.49 分**。

| 濕地往績場數 | n | top-3 | 超額 | 平均\|overlay\| | 最大\|overlay\| |
|---|---|---|---|---|---|
| 1 場 | 439 | 31.89% | +1.75pp | 1.338 | 1.391 |
| 2 場 | 261 | 28.74% | −1.41pp | 2.241 | 2.318 |
| 3-5 場 | 851 | 32.78% | +2.64pp | 2.329 | 3.864 |
| 6-10 場 | 890 | 32.02% | +1.88pp | 2.981 | 4.968 |
| **11+ 場** | 1,036 | **25.97%** | **−4.18pp** | 3.298 | **5.790** |

**≤2 場濕地往績但 overlay ≥1.0 分嘅有 700 匹（濕地場 20.1%）**，其中 261 匹 ≥1.4 分。
呢批實際 top-3 率 30.71% vs baseline 30.14% → **超額 +0.57pp，即係噪音**。

即係 overlay 嘅幅度**最大嗰邊（11+ 場，最大 5.79 分）落喺表現最差嘅 cohort**，
而幅度細嗰邊（1-2 場）嘅證據值零。

早前（EXP-01 同一語料，423 個濕地場次）測過嘅五個修法，全部 CI 跨零：

| 候選 | ΔAUC | 95% CI | Δt3prec |
|---|---|---|---|
| **完全剷走 overlay** | +0.0018 | [−0.0030, +0.0067] | ±0.00 |
| 按今日地況分開（軟／重） | +0.0000 | [−0.0017, +0.0018] | +0.28 |
| 只用對應地況 | +0.0004 | [−0.0025, +0.0032] | ±0.00 |
| 收縮加到 12 | +0.0006 | [−0.0023, +0.0035] | ±0.00 |
| 幅度減半 | +0.0000 | [−0.0030, +0.0031] | −0.17 |

## 檢查
- **replica verify**：PASS（max|Δ| 0.0091，>0.01 為 0）
- **leakage-audit**：PASS（只重配權重，冇加特徵）
- **golden_scoring / data_contract**：不適用（冇改 model code）

## 結論

**(A) 重 fit：NEEDS MORE TESTING，唔係 REJECT。** 四個 seed 收斂得好緊
（stability ↑、class_weight ↓），方向可信；但 holdout 91 場同 92 場窗口令
1 場 = 1.09pp，量唔到 ±1pp 級數嘅差異。**呢個唔係「重 fit 冇用」，係「呢個語料答唔到」。**
要答就要更多乾淨 point-in-time 場次自然累積（08-05 之前嘅一半係賽後重評分嘅，
見 `au-archive-rescored-post-race`，補唔到數）。

⚠️ **我預期錯咗一樣**：以為重 fit 會減 `pace_perf`（因為佢個 leaf 完全冇改善）。
實測四個 seed 都係**加** `.122 → ~.135`。所以重 fit **唔會**降 Gunroom 嗰個優勢來源。

**(B) 濕地 overlay：可以剷，但係基於「簡單而穩健」而唔係基於量到嘅收益。**
五個修法全部打和，剷走亦係打和（+0.0018，CI 跨零）。但同時量到：20.1% 嘅濕地
runner 攞緊 ≥1.0 分（最多 2.32 分，場內 ability SD 約 6，即係最多 0.4 SD）而背後
只有 ≤2 場往績，實測超額 +0.57pp。Race 1 就係實例 —— Isawyou 由**一場**重地
（1:0-1-0）攞 +1.485，Gunroom 由 5 場攞 +2.475 而 Clear Proof 由 9 場攞 −0.571。

按 AGENTS.md「簡單而穩健 > 複雜而邊際」同「分唔開嘅就唔留」，剷走係站得住嘅；
但**唔可以講成「改善」** —— 佢係打和 + 少一個能夠單場翻轉頭名嘅項。呢個係
Kelvin 嘅決定，唔係我可以當成 measured win 去 ship。

**決定**：(A) **NEEDS MORE TESTING**（語料唔夠 power）　(B) **打和；剷走與否交由決策**
**commit**：無 model code 改動

## 重跑
```bash
export PYTHONDONTWRITEBYTECODE=1
python3 mk_dataset.py out_cand ds_cand.json
python3 au_matrix_refit.py verify      --data ds_cand.json
python3 au_matrix_refit.py refit       --data ds_cand.json --n 3000 --min-folds 4 --seed 1
python3 au_matrix_refit.py walkforward --data ds_cand.json --n 3000 --min-folds 4 --seed 1
python3 wet_thin.py    # overlay 證據厚度分層
python3 wet2.py        # 五個 overlay 修法 + 配對 bootstrap
```
