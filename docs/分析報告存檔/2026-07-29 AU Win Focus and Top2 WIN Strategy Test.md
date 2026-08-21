# AU Wong Choi — Win-focused 模型 + Top 2 WIN 投注測試

## 測試口徑

- 歷史可比對：709 場；Betfair WIN BSP files：62。
- 每場 Top 2 各 $1 WIN；Betfair 5% commission 按同一 market 淨盈利計。
- Odds 只用作結算 ROI，冇輸入 win-focused 排名。
- 模型候選用 expanding-date walk-forward；2026-07-25 三地為額外未見 holdout。

## 現行 Top 2 全買 WIN — 全歷史點估

| 策略 | 場次 | Bets | 捉到冠軍 | P&L | ROI @ BSP | 95% bootstrap CI | ROI @ morning |
|---|---:|---:|---:|---:|---:|---:|---:|
| 現行 #1+#2 各 $1 | 708 | 1416 | 39.0% | +110.67 | +7.8% | [-9.3%, +28.1%] | -31.2% |
| 現行 #1 單買 | 708 | 708 | 23.6% | +80.26 | +11.3% | [-9.9%, +35.4%] | — |
| 現行 #2 單買 | — | 708 | 15.4% | +17.03 | +2.4% | [-25.0%, +37.8%] | — |

### 穩定性與可執行 market gate

| 策略 | 全期 ROI | 前半 ROI | 後半 ROI | 95% CI |
|---|---:|---:|---:|---:|
| Top2 全買 @ BSP | +7.8% | -1.3% | +16.6% | [-9.3%, +28.1%] |
| Model Top2 ∩ morning-market Top2，再取 BSP | +15.1% | +12.4% | +17.9% | [+1.6%, +28.4%] |

## Win-focused 候選 — Walk-forward OOS

| 模型 | 場次 | #1 勝率 | 冠軍在 Top 2 | Top2改動 | ROI @ BSP | 前半 ROI | 後半 ROI |
|---|---:|---:|---:|---:|---:|---:|---:|
| 現行 7D | 361 | 21.9% | 37.4% | 0 | +16.6% | +4.4% | +23.2% |
| Trainer-fill 重分 | 361 | 19.9% | 37.7% | 169 | +1.4% | +0.5% | +1.8% |
| Win logistic | 361 | 23.8% | 41.3% | 98 | +14.9% | +7.8% | +18.8% |
| Win GBM | 361 | 25.5% | 41.5% | 157 | +18.0% | -1.7% | +28.7% |

## 2026-07-25 Randwick／Caulfield／Eagle Farm Holdout

| 模型 | #1 勝率 | 冠軍在 Top 2 | Top2改動 | Top2 ROI @ Racenet SP | #1 ROI @ SP |
|---|---:|---:|---:|---:|---:|
| 現行 7D | 28.6% | 42.9% | 0 | +12.7% | +31.2% |
| Trainer-fill 重分 | 28.6% | 42.9% | 0 | +12.7% | +31.2% |
| Win logistic | 28.6% | 35.7% | 18 | -23.9% | +15.0% |
| Win GBM | 32.1% | 39.3% | 19 | -15.0% | +32.9% |

- 三地 holdout：Model Top2 ∩ SP-market Top2 共 21 注，中 7 注，ROI +7.1%。

## Feature ablation：win-focused 提升由邊度嚟

只用原本 `ability_score`、場內標準化分數、Top 分差、原排名同 field size
重訓 winner classifier，361 場 OOS **完全冇改任何排名**。即係將同一個總分
由 place objective 改寫成 win probability，本身唔會憑空產生新排序資訊。

加入額外 pre-race 次序 proxy 後：

| 候選 | #1 勝率 | 冠軍在 Top2 | 相對 baseline 配對得失 |
|---|---:|---:|---|
| Baseline | 21.9% | 37.4% | — |
| Core + trainer relative | 21.9% | 39.1% | Top2 救回12／犧牲6 |
| Core + horse-number order | 21.1% | 40.4% | Top2 救回17／犧牲6 |
| Full logistic | 23.8% | 41.3% | #1 救回16／犧牲9；Top2 20／6 |
| Full GBM | 25.5% | 41.5% | #1 救回24／犧牲11；Top2 33／18 |

配對 exact-binomial：

- Logistic Top2：p=0.009；
- GBM #1：p=0.041；
- GBM Top2：p=0.049；
- Logistic #1：p=0.230。

所以歷史 OOS 嘅 win-capture 提升唔係完全冇訊號。不過最新 2026-07-25
holdout 對 Top2 係倒退：baseline 12/28、logistic 10/28、GBM 11/28；
兩個候選 Top2 ROI 亦變成負數。候選只可進入 shadow／forward validation，
未達 production promotion gate。

## 最終判斷

### 模型

暫時唔改 production 7D ranking。Win-focused GBM/logistic 有研究價值，但
最新 holdout 未能確認泛化，而且盈利冇隨命中率穩定上升。下一步應保存每日
shadow Top2，同現行 Top2 平行累積最少再 100 場。

### 投注策略

唔建議「每場盲買模型 Top2」直接成為正式策略：

- BSP 全期點估 +7.8%，但前半 −1.3%、後半 +16.6%；
- 95% CI 為 −9.3% 至 +28.1%，未排除負期望；
- #1 單買 +11.3%，#2 單買只 +2.4%，第二注明顯較弱；
- 用 morning fixed price 買 Top2 為 −31.2%。

現階段證據最強嘅可執行版本係：

1. 模型維持 odds-blind；
2. 只選 `AU model Top2 ∩ morning market Top2`；
3. 唔鎖 morning fixed price，改用 Betfair take-SP／BSP；
4. 每匹 flat 1 unit，先 paper trade。

呢個版本歷史 674 注，ROI +15.1%，前半 +12.4%、後半 +17.9%，bootstrap
95% CI +1.6% 至 +28.4%；三地 SP proxy holdout 亦為 +7.1%。佢改善嘅係
betting decision layer，唔係將 odds 混入 7D model。
