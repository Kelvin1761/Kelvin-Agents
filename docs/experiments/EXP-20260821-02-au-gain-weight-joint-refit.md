# EXP-20260821-02 AU 顯示尺 gain + MATRIX_WEIGHTS 聯合重 fit

- **日期**：2026-08-21
- **平台**：AU
- **假設**：`MATRIX_DISPLAY_GAINS` 喺 2026-08-01 擬合，之後 `sectional_score` 退出排名同
  Sportsbet 資料源切換令各維度原始 SD 漂移。重擬 gain 並同步重 fit `MATRIX_WEIGHTS`，
  可以令（a）權重重新等於實際影響力，（b）三個「啞」維度重新到得 ✅／✅✅。
- **搜索過嘅舊記錄**：[EXP-20260821-01](EXP-20260821-01-au-archive-corpus-blindspot.md)、
  memory `au-matrix-refit-consensus-not-argmax`、`au-dimension-scale-weight-lockstep`、
  `au-matrix-weights-tested-dont-change`、`au-gate-rejects-everything`
- **改到嘅檔案／組件**：無（model code 未改；只改咗枚舉層同閘門工具）

## 零、前置：假設本身建立喺一個盲區之上

我第一輪量度用 `<root>/*/Race_*_Logic.json`，即係 EXP-01 講嘅盲區。獨立核實：

| | 場次 | 場數 | 日期 | 08-05 之後（乾淨 point-in-time） |
|---|---:|---:|---:|---:|
| 頂層 | 89 | 779 | 64 | **1** |
| `Archive/` | 96 | 751 | 21 | **16** |

零重疊，49.1% 隱形。**所以第一輪嗰堆數全部係「賽後重評分過嗰半」嘅數。**

修正枚舉之後同一個量度：

| 維度 | 舊語料 SD | 乾淨語料 SD | 我第一輪報咗 | 真實 |
|---|---:|---:|---|---|
| jockey_trainer | 2.49 | **10.78** | 「−66%，啞」 | 基本達標 (−2%) |
| class_weight | 3.64 | **9.36** | 「−59%」 | −15% |
| stability | 8.05 | 8.30 | −23% | −25% |
| track | 4.47 | 7.32 | −51% | −33% |
| race_shape | 3.03 | 4.44 | −69% | **−60%（真問題）** |
| pace_perf | 6.75 | 18.26 | +38% | **+66%（真問題）** |

band 分佈同樣：乾淨語料之下**冇一個維度係啞嘅**（騎練訊號 14.2% 正面、
檔位形勢 16.5%、級數與負重 18.1%）。「三個維度永遠出唔到正面 band」係盲區造成嘅假象。

即係假設（b）**一開始就係錯嘅**；假設（a）縮窄到只剩 `race_shape` 同 `pace_perf` 兩個。

## 配置
- **baseline**：`c20fe4e5` 出廠 gains + `MATRIX_WEIGHTS`
- **candidate A**：新 gains（由修正後語料重擬）+ consensus 搜索出嘅權重
- **candidate B**：新 gains + 等價權重（按定義複製現行排名）

## 數據
- **語料**：修正枚舉後 **1,413 場 / 14,121 匹**（修正前 721 / 7,642）
- **dev**：1,201 場，5 個時間 fold（240/240/241/240/240）
- **holdout**：212 場，未碰過
- **replica 驗證**：`verify` max|Δ| = 0.0108（14,121 匹中 1 匹 >0.01）→ 過

## 結果

### Candidate A —— 排名重 fit
```
400 條隨機權重：7 條贏 dev，其中 0 條再過 4/5 fold 閘
```
**冇一條過閘。** 現行權重喺修正後語料、balanced 目標之下已經係局部最優。

### Candidate B —— 新 gain + 等價權重（排名理應相同）

| 指標 | holdout baseline | holdout candidate | Δ |
|---|---:|---:|---:|
| gold | 20.28 | 20.28 | +0.00 |
| good_pos | 29.72 | 29.72 | +0.00 |
| pass | 55.66 | 56.13 | +0.47 |
| champ | 29.25 | 29.25 | +0.00 |
| winT3 | 65.09 | 65.09 | +0.00 |
| ndcg5 | 59.93 | 59.91 | −0.02 |

全樣本同 dev 亦一樣：全部 ±0.17 之內（1413 場之下 1 場 ≈ 0.07pp，即 1–2 場噪音）。
如預期 —— 等價變換，殘差來自 0/100 clip。

### Candidate B 買到咩（report band，乾淨語料 709 場）

| 維度 | 現行正面 | 新正面 | Δ | ✅✅ 現行→新 |
|---|---:|---:|---:|---|
| 檔位形勢 | 16.5% | 26.1% | **+9.6pp** | 0.0% → **0.0%** |
| 級數與負重 | 18.1% | 19.3% | +1.1pp | 0.7% → 1.0% |
| 狀態與穩定性 | 28.4% | 28.4% | +0.0pp | 1.6% → 1.6% |
| 賽績線 | 42.1% | 41.9% | −0.2pp | 23.0% → 22.1% |
| 場地與地況適性 | 49.6% | 48.0% | −1.6pp | 7.1% → **3.4%** |
| 騎練訊號 | 14.2% | 12.0% | −2.2pp | 1.6% → 0.8% |
| 速度考驗背景 | 31.7% | 25.3% | **−6.4pp** | 8.6% → **3.1%** |

**一個維度好，四個差，而最想修嗰樣（檔位形勢到唔到 ✅✅）完全冇修好。**

## 檢查
- **leakage-audit**：N/A —— 冇加新特徵，只係重新加權同重新縮放現有維度
- **golden_scoring**：冇郁（AU / HKJC 各 120 匹一致，枚舉修正前後都跑過）
- **data_contract**：AU / HKJC PASS
- **退步**：candidate A 冇過閘；candidate B 喺 4 個維度嘅 band 表達力退步

## 結論

兩個候選都唔留。

**Candidate A REJECT**：唔係「差少少」，係 400 條入面 0 條過 4/5 fold。同
`au-matrix-weights-tested-dont-change` 一致 —— 增益係五六個維度一齊動出嚟嘅，
逐對邊緣搜索讀到「已最優」其實係「平坦」。

**Candidate B REJECT**：排名確實中性（好），但佢存在嘅理由係改善 band 表達力，
而實測係淨負：檔位形勢 +9.6pp 換嚟速度考驗背景 −6.4pp 加場地 ✅✅ 腰斬。
而且 `race_shape` 原始 SD 只有 2.03，就算 gain 推到 5.43（headroom 上限 7.07）
都到唔到 ✅✅ 門檻 —— **問題唔喺 gain，喺 `pace_map_score` 本身喺同場之內
分唔開馬**（實測值域 46.3–63.7）。調尺救唔到一個本身冇 gradient 嘅 leaf。

**真正嘅收穫唔係重 fit，係發現判決層一直盲咗一半語料。** 修完之後我第一輪
報嘅「五個維度失效／三個維度啞」有四項係假象。呢個修正影響所有將來嘅 A/B。

**決定**：REJECT（兩個候選）
**commit**：model code 未改。枚舉修正同閘門工具已 commit（見下）。

## 重跑
```bash
cd .agents/skills/au_racing/au_wong_choi_auto/scripts
export PYTHONDONTWRITEBYTECODE=1
S=/tmp
python3 au_dump_engine_leaves.py --out "$S/leaves_fixed.json"     # 1413 場
python3 au_matrix_refit.py verify --data "$S/leaves_fixed.json"
python3 au_matrix_refit.py gains  --data "$S/leaves_fixed.json"
python3 au_matrix_refit.py refit  --data "$S/leaves_fixed.json" \
    --gains au_refit_gains.json --n 400 --seed 20260821
python3 au_matrix_refit.py compare --data "$S/leaves_fixed.json" \
    --gains au_refit_gains.json --weights "$S/equiv_weights.json"
```
