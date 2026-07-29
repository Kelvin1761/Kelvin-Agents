# HKJC Competitiveness Optimisation

## Goal
令 HKJC Wong Choi 排名反映賽前真實競爭力，而唔係只追逐歷史 Top 3 賽果。

## Tasks
- [x] 盤點 archive、results、Logic/Scoring 覆蓋 → Verify: 25 meetings、245 races、3,054 runners。
- [x] 建立 Top3@4/5、winner rank、NDCG@5、競爭層 recall 等 baseline → Verify: 全體及時序分段均有數值。
- [x] 自動產生全部 0-hit／1-hit structured review → Verify: 192 場都有低估、高估、訊號缺口、系統性/單場、overfit 風險欄。
- [x] 獨立審核直路賽、外隊馬、新馬賽 → Verify: 已列樣本量、baseline、資料缺口及錯誤模式；外隊馬歷史標籤缺失另修正。
- [x] 以賽前可用訊號建立候選改動 → Verify: 每項改動有跨多場因果假設，無使用賠率入分。
- [x] 用時間切分及場景切分驗證 → Verify: shared 7D debut matrix 在 development、temporal holdout、7 月 15 日重播均無退步並改善排名質素。
- [x] 只保留通過 gate 的改動並跑回歸測試 → Verify: 67 Auto + 18 shared evaluator + 4 reflector pytest、12/12 template flow、Auto orchestrator、Reflector 及單 meeting replay 全部通過。
- [x] 重建五個主要弱項並做 full-field matrix gate → Verify: 25 meetings、245 races、3,054 runners；唯一通過候選為 `shape_to_core_equal`。
- [x] 將通過候選上線 → Verify: production contract `HKJC_7D_CONTRACT_2026_07_30_CORE_BALANCE`，並由測試鎖定七維權重。
- [x] 最終回歸驗證 → Verify: 89 pytest、67 Auto unittest、12/12 template flow 全部通過；7 月 15 日 Top-2／Top-5 capture 無退步。

## Done When
- [x] 全 archive 弱場及三個專項均完成可追溯覆盤。
- [x] 新評估框架取代 Gold/Good/Pass 作主指標，而後者保留作輔助。
- [x] 已無其餘候選能在 development、temporal holdout、independent recent、7 月 15 日同時帶來有意義改善。

## 2026-07-30 Final Matrix Review

### 上線改動

舊權重：

- sectional 0.1849
- trainer 0.2209
- stability 0.0919
- race shape 0.2560
- class 0.1335
- health 0.0378
- form line 0.0749

新權重：

- sectional 0.1849
- trainer 0.2309
- stability 0.1019
- race shape 0.2260
- class 0.1435
- health 0.0378
- form line 0.0749

即係由 race shape 減 3%，平均加 1% 去 trainer、stability、class。
呢個係正常 full-field 重排，無 post-ranking micro tie-break、blind swap 或賽果
override。

### 全 archive 結果

所有 `245` 場均保留；無剔除極冷門、受阻、意外或異常賽果先令候選通過。

| 指標 | 舊 | 新 | 變化 |
|---|---:|---:|---:|
| 0-hit races | 62 | 60 | -2 |
| 1-hit races | 125 | 124 | -1 |
| 2-hit races | 58 | 61 | +3 |
| Top-2 total placing hits | 241 | 246 | +5 |
| Top-3 capture@5 | 63.27% | 63.40% | +0.14pp |
| 全部 actual Top 3 在 model Top 5 | 22.45% | 22.86% | +0.41pp |
| Competitive recall@5 | 58.37% | 58.44% | +0.06pp |
| NDCG@5 | 52.78% | 53.20% | +0.41pp |
| Winner in Top 5 | 67.76% | 68.98% | +1.22pp |
| Winner MRR | 45.40% | 45.59% | +0.19pp |

Top-2 層面有 `8` 場改善、`3` 場倒退、`234` 場不變。時間 holdout
亦增加 `2` 個 Top-2 placing hits，Top-3 capture@5、competitive recall@5、
NDCG@5、winner-in-Top-5 同時改善；只有 MRR 微跌 0.13pp，未達 material
harm 門檻。7 月 15 日九場 Top-2／Top-5 capture 不變，無用單一 meeting
帶動上線決定。

### 正常可預測賽事（Adjusted）

另用官方 `full_day_results.json` 建立可審核 anomaly layer：

- 實際 Top 3 獨贏賠率 `>= 30`：只標記為極冷門，賠率絕不進入 scoring。
- 模型 Top 2 未能上名，而官方報告明確記載嚴重受阻、醫療問題、收停或
  其他重大事件：標記為 incident。
- 245 場全部成功配對官方結果；79 場有至少一項標記，正常 adjusted
  樣本為 166 場。Unfiltered 245 場永遠保留作主 gate，無靜默刪除賽果。

新權重在 adjusted 166 場同樣改善：

| 指標 | 舊 | 新 | 變化 |
|---|---:|---:|---:|
| 0-hit races | 27 | 26 | -1 |
| 1-hit races | 85 | 84 | -1 |
| 2-hit races | 54 | 56 | +2 |
| Top-2 total placing hits | 193 | 196 | +3 |
| Top-3 capture@5 | 69.08% | 69.48% | +0.40pp |
| 全部 actual Top 3 在 model Top 5 | 27.71% | 29.52% | +1.81pp |
| Competitive recall@5 | 61.80% | 61.83% | +0.03pp |
| NDCG@5 | 57.91% | 58.62% | +0.71pp |
| Winner in Top 5 | 70.48% | 72.29% | +1.81pp |
| Winner MRR | 49.78% | 50.05% | +0.27pp |

Adjusted temporal holdout 表現更清楚：Top-2 hits `+2`、Top3@5 `+1.89pp`、
NDCG@5 `+1.55pp`、winner-in-Top5 `+3.77pp`，所有主要指標均無倒退。

用 production 新排名重新分類 0/1-hit 場後，原先五大問題喺非異常原因中
變成：

| 問題 | 原先 | 新 production review |
|---|---:|---:|
| 整體競爭群辨識不足 | 88 | 42 |
| 已捕捉競爭群、但 Top 2 排序不足 | 22 | 22 |
| 騎練訊號 | 21 | 9 |
| 班次／負磅 context | 16 | 7 |
| form line | 14 | 7 |

另有 74 場 0/1-hit 已由官方賠率／競賽事件標註為異常結果，保留作案例研究，
但唔再用嚟推動 scoring 改動。Top-2 原因場數維持 22，但實際 Top-2 placing
hits 在全 archive 淨增 5、adjusted 淨增 3，代表排序質素有提升，只係仍有
一批場次屬於「競爭群已捉到、頭二次序未完全命中」。

### 五個主要弱項結論

1. **整體競爭群識別**：新權重改善 0-hit、Top3@5、competitive recall@5、
   NDCG@5 及 winner@5，方向成立但幅度溫和。
2. **Top-2 排序**：全 archive 淨增 5 個 placing hits，8 場改善對 3 場
   倒退；並非強行把第三選換上第二選。
3. **Trainer**：競爭層 AUC 約 0.608，高於 race shape 約 0.571，支持
   trainer 加 1%；更大幅加權候選未通過，故停止。
4. **Class／weight**：class AUC 約 0.613，支持加 1%。直接「較輕磅較好」
   訊號在 archive 呈反向（AUC 約 0.455），所以無加入輕磅 bonus。
5. **Form line**：現有維度 AUC 約 0.515，替代 win-count 公式只有約
   0.475–0.483，減權或重寫均未跨時段改善，因此維持 0.0749，等待更好
   賽前資料而唔係用賽果修補。

### 停止條件

額外 class replacement、form-line redistribution、meta-rank、outer-weight
fit、較大 race-shape 轉移及 stability-led 版本，全部至少在一個時段或一項
主要競爭力指標出現 material regression。現階段再改只會增加 overfit 風險，
所以以上線嘅最小權重重建作為穩定終點。

## Notes
- 極冷門、意外、受阻只作透明標籤；原始成績永遠保留，另報 adjusted metrics。
- 所有模型改動只可使用開跑前可得資料；賠率可作賽後診斷分層，但唔可入 Auto scoring。
