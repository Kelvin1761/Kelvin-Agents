# AU Wong Choi — Verified Signal Map (2026-07-17)

> 用途：日後升級/重建時知道邊啲嘢真係影響排名、邊啲純顯示、邊啲係死碼。
> 呢張地圖由 `tests/test_signal_map.py` 鎖定 — ability 方程有任何隱藏改動
> 都會令測試爆，逼令呢份文檔同步更新。

## 排名方程（唯一真相）

```
ability_score = Σ MATRIX_WEIGHTS[d] × mx[d]   (七維，form_line 權重 = 0.0)
              + wet_form_feature(今日場地, 地狀分拆線)
排序 = ability_score 降序；#3/#4 分差細先觸發檔位 micro tie-break
```

## 特徵分類（分離度 = 2026-07-17 修復後審計）

### A. 真正影響排名（14 個 + 1 overlay）

| 維度（權重） | 輸入特徵（內部權重） | 分離度 |
|---|---|---|
| stability (0.299) | form 0.60 / consistency 0.40 | 3.32 / 4.18 |
| pace_perf (0.188) | pace_figure 0.759 / sectional 0.194 / trial 0.047 | 6.49* / 1.41 / 2.25 |
| jockey_trainer (0.194) | jockey 0.28 / trainer 0.20 / fit 0.52 | 1.61 / 1.22 / 0.47 |
| race_shape (0.149) | pace_map 1.0（內含檔位 bias＋收縮） | 0.52 |
| class_weight (0.045) | class 0.159 / rating 0.70 / weight 0.141 | 0.62 / 1.73 / −0.41 |
| track (0.124) | track_score 1.0 | 0.64 |
| overlay | wet_form_feature（只喺濕地非零） | Heavy +4 g2 / Soft −3 gp |

*pace_figure 有覆蓋先至 6.49（覆蓋 33%，PF 回填進行中）。

### B. 純顯示層（改咗唔影響排名 — 剪嘅時候要保留報告內容）

- `health_score`（分離度 0.10）、`confidence_score`（0.22）、`distance_score`（0.60）
- `formline_score` + form_line 維度（權重 0.0 — 計出嚟乘零）
- 各種敘事 notes / detail lines / grades 文字

### C. 已知死碼／凍結

- `_pace_bias_adjustment`：預設 OFF（WC_PACE_BIAS=1 先開），A/B 證實 wash
- form_line 維度喺 ability 內係乘零 — 未來 rebuild 可以直接攞走
  （連鎖：MATRIX_KEYS、cache schema、報告七維顯示要一齊改，屬專項 SIP）

## 剪裁守則（2026-07-17 訂）

1. B 類可以簡化實現，但報告輸出要 byte-diff 驗證
2. A 類任何改動行標準晉升閘（+1.5pp / 非倒退 / 4/5 folds）
3. 剪 C 類要有 rank-identity 證明（全庫 A/B max diff < 0.01）
4. 每次剪完更新呢份地圖 + `test_signal_map.py`
