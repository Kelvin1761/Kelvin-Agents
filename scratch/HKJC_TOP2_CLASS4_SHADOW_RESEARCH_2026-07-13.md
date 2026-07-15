# HKJC Wong Choi — Top 2 優先結構性訊號研究（2026-07-13）

## 結論先行

暫時最值得繼續嘅方向，唔係將新訊號套落所有賽事，而係建立 **Class 4 專用 supporting matrix branch**：

- Class 4：baseline 7D score 加入 trackwork、sectional/variant、historical professional priors、rail/draw supporting matrix；
- 其他班次：保持 frozen baseline；
- 全程冇使用 odds、market movement 或 market ranking；
- 呢個係 race-condition-specific scoring logic，唔係計完 7D 後做人手微調名次。

方向同時改善 Top 2 individual place rate 同平均 Top 4 命中，但統計證據仍未夠強，而且 Class 4 branch 係睇完 slice 後先提出，屬 post-hoc hypothesis。**建議繼續 shadow，未建議正式入 production matrix。**

## Dataset 與資料契約 QA

研究期間修正咗 ranking dataset builder 嘅結構化問題，但冇改 production scoring：

- 中文班次（第一班至第五班）正確映射；
- Group / Griffin 唔再錯當普通班次；
- 沙田全天候跑道正確標準化為 `venue=沙田`、`track=AWT`、`course=AWT`；
- distance、course、Markdown 空欄位跨行吞值問題已修正；
- discovery dataset：13 個 meeting、131 場、1,624 runners；
- forward dataset：11 個 meeting、113 場、1,410 runners；
- forward trackwork coverage 100%；raw L400 coverage 95.7%；adjusted finish-time coverage 81.8%。

兩段研究期冇重疊：

- rolling discovery held-out：2026-04-29 至 2026-05-24，80 場；
- forward：2026-05-27 至 2026-07-12，113 場；
- 其中 2026-05-27 至 2026-07-08 共 102 場，完全早於 2026-07-12 單日 review。

## 原有全場候選未過 Top-2-first gate

以下係較乾淨嘅 102 場 forward scope：

| Model | Top 1 | Top 2 individual place | Both Top 2 placed | Avg Top 4 hits | Top 4 all 3 placed |
|---|---:|---:|---:|---:|---:|
| Baseline | 19.61% | 41.67% | 16.67% | 1.559 | 11.76% |
| Candidate A：trackwork 20% | 21.57% | 41.18% | 14.71% | 1.500 | 8.82% |
| Candidate B：full support matrix，全場套用 | 22.55% | 42.16% | 14.71% | 1.569 | 10.78% |

判斷：

- Candidate A 明確唔值得繼續：Top 2、both-Top-2、Top 4 全部倒退。
- Candidate B 有 Top 1 uplift，但全場套用時 Top 2 增幅只有 +0.49pp，both-Top-2 更下跌；唔符合目前優先目標。
- 主要問題係 signal heterogeneity：同一 supporting matrix 喺唔同班次同跑道配置表現唔一致。

## 最值得繼續：Class 4 專用 full-support branch

### Forward 102 場（Class 4 有 73 場）

| KPI | Baseline | Class 4 branch | 變化 |
|---|---:|---:|---:|
| Top 1 accuracy | 19.61% | 20.59% | +0.98pp |
| Top 2 individual place | 41.67% | 44.12% | **+2.45pp** |
| Both Top 2 placed | 16.67% | 17.65% | +0.98pp |
| Avg Top 3 hits | 1.235 | 1.255 | +0.020 |
| Avg Top 4 hits | 1.559 | 1.588 | **+0.029** |
| Top 4 all 3 placed | 11.76% | 11.76% | 無變 |

Paired test：

- Top 2 hits：每場 +0.049；bootstrap 95% CI `[-0.0196, 0.1176]`；Wilcoxon `p=0.2439`；
- Top 4 hits：每場 +0.029；95% CI `[-0.0490, 0.0980]`；`p=0.5245`；
- both-Top-2：3 場 gained、2 場 lost；McNemar `p=1.0`。

方向正確，但 CI 仍跨 0，未達顯著。

### Full forward 113 場（包括 2026-07-12；Class 4 有 78 場）

| KPI | Baseline | Class 4 branch | 變化 |
|---|---:|---:|---:|
| Top 1 accuracy | 19.47% | 21.24% | +1.77pp |
| Top 2 individual place | 40.71% | 43.81% | **+3.10pp** |
| Both Top 2 placed | 15.04% | 16.81% | +1.77pp |
| Avg Top 4 hits | 1.540 | 1.575 | **+0.035** |
| Top 4 all 3 placed | 10.62% | 10.62% | 無變 |

Top 2 hits 95% CI 為 `[0.0000, 0.1239]`，Wilcoxon `p=0.1205`。加入 7 月 12 日後更接近正面確認，但仍未達一般 `p<0.05` 標準。

### 兩段 disjoint held-out 合計 193 場

呢個合計只用嚟睇方向一致性；Class 4 規則本身係睇完 slice 後提出，唔可視為真正獨立確認。

| KPI | Baseline | Class 4 branch | 變化 |
|---|---:|---:|---:|
| Top 1 accuracy | 21.76% | 22.28% | +0.52pp |
| Top 2 individual place | 43.52% | 45.85% | **+2.33pp** |
| Both Top 2 placed | 18.65% | 19.69% | +1.04pp |
| Avg Top 4 hits | 1.554 | 1.586 | **+0.031** |
| Top 4 all 3 placed | 10.88% | 10.88% | 無變 |

Top 2 paired 95% CI `[-0.0052, 0.1036]`、`p=0.1633`。即係 effect size 值得繼續，但證據未夠批准正式改 matrix。

## 一致性與弱點

Forward 113 場按場地：

- 沙田：Top 2 hits 66 → 72；平均 Top 4 hits 1.597 → 1.636；
- 跑馬地：Top 2 hits 26 → 27；平均 Top 4 hits 1.417 → 1.444。

按 meeting（11 個）：

- Top 2：6 個改善、3 個持平、2 個倒退；
- Avg Top 4：5 個改善、3 個持平、3 個倒退。

最重要風險：

- `C+3` course 表現明顯正面（Top 2 hits +5），但 `B` course 倒退（Top 2 hits -3）；
- Top 4 平均命中有升，但「Top 4 包晒三甲」整體未升；
- discovery 時段 Top 2 有正增幅，但 Top 1 曾輕微下降；
- 所有統計 CI 仍然偏闊。

所以唔應該再加一條「B course 扣分」之類嘅微調規則。正確做法係保留成結構性 Class 4 branch，再用新賽果驗證 course interaction。

## Top 4 challenger ablation

另測咗一個較簡單嘅 Class 4 branch，只保留 trackwork 20% + sectional/variant 10%，移除 professional priors 同 rail/draw：

- 102 場：Top 2 individual place 41.67% → 43.63%；Avg Top 4 1.559 → 1.608；Top 4 all 11.76% → 14.71%；
- 113 場：Top 2 individual place 40.71% → 43.36%；Avg Top 4 1.540 → 1.593；Top 4 all 10.62% → 13.27%；
- discovery 80 場：Top 2 無改善，但 Avg Top 4 1.575 → 1.600、Top 4 all 11.25% → 13.75%。

呢個 ablation 對 Top 4 更吸引，但 Top 2 一致性不及 full-support branch。按目前優先次序，應以 full-support Class 4 branch 做 primary shadow，trackwork+variant branch 做 Top 4 challenger，兩者唔應混成賽後人手選擇。

## 建議下一步（仍然唔改 production）

1. 即時 freeze 兩個 shadow specification：
   - Primary：Class 4 full support（trackwork 20 + variant 10 + priors 10 + rail/draw 10）；
   - Challenger：Class 4 trackwork 20 + variant 10。
2. 非 Class 4 一律用 baseline；唔再測全場 Candidate A/B。
3. 下一批新賽事必須 pre-register 後一次過評估，避免再用同一批結果揀規則。
4. Primary promotion gate：
   - Top 2 individual place 至少 +2pp；
   - both-Top-2 不倒退；
   - Avg Top 4 不倒退；
   - Top 4 all 不倒退；
   - 沙田、跑馬地都至少持平；
   - paired bootstrap 95% CI 下限不低於 0。
5. Challenger 只有喺 Top 2 達到同一門檻、同時 Top 4 all 明顯高過 primary 時，先可取代 primary。

## 決策

- **值得繼續：Class 4 condition-specific branch。**
- **暫停：全場 trackwork-only Candidate A、全場 full-support Candidate B。**
- **暫不正式實裝：統計未過門檻，而且 Class 4 規則仍係 post-hoc。**

