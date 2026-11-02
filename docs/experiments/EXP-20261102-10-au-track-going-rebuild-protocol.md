# EXP-20261102-10 預先登記：AU 場地／地況／濕地重建 + 濕地處理審查

> 量度之前寫。結果另寫 `EXP-20261102-10-au-track-going-rebuild-results.md`。做法同 EXP-20261102-04（班次）、-09（檔位）：
> 先 1:1 搬入一個簡單模組（A/A 全語料一樣），再逐條消融，冇訊號嘅剷。

- **日期**：2026-11-02；**平台**：AU；**baseline**：`origin/main` `ed4ac6f8`。
- **用戶**：「開 also can you review if we are handling wet correctly」「happy for you to rebuild this part as well in simplest code and formulas」。
- **搜索過**：EXP-20260823（濕地另一 bucket 半份）、EXP-20260831-08（WET_FORM_PRIOR 0.3758）、EXP-20260901-05（track 去 going 部分 REJECT）、
  EXP-20260905-04（爛地重磅剷）、EXP-20261016-70（六項審計：T1x／T3x／T4x 保留、T5x base 60）、EXP-20261016-72（going 集中、比率 REJECT）、
  EXP-20261101-38（overlay 消融：濕地保留）。
- **今日診斷**（唔係判決）：track_score AUC 0.545；同近績質素分場內 ρ 0.150、同濕地 overlay 0.500；整個維度剷走 Gold −0.09pp／Good −0.06pp（CI 跨零）。
  **地況錯配**：08-05 起 3,528 場，分析用嘅地況同賽果官方地況 24.2% 唔同一級；419 場分析當濕實際乾（406 場 Soft 5–6 → Good），82 場相反。

## 第 1 步：結構（唔改分數）

新模組 `au_racing_engine/track_going.py`：同場往績、地況往績（②）、爛地專項（未驗證／重地）、濕地 overlay、today 地況分級，全部純函數。
引擎方法只砌說明。**判決**：全語料重評同 baseline 逐匹 `features`／`ability` 0 差。

## 第 2 步：逐條消融（一個 family；全部 v3 `fixed_rule`，08-05 起全紀錄，對 baseline）

| arm | 改動 |
|---|---|
| **ST** | 剷同場往績成段（上名 +5／贏 +2.4（封頂 9）、多戰 0 上名 −8.81、1 戰 0 上名 −0.81） |
| **STP** | 只剷同場兩個 0 上名扣分 |
| **GO** | 剷今場地況往績 ②（上名 +0.8×、濕地曾贏 +3.77、0 上名 −4.75／−3.46／−4.14／−3.0） |
| **WU** | 剷爛地「未經驗證」−6.4 |
| **WU0** | 「未經驗證」只罰有濕地出賽但 0 上名嘅馬；從未跑過濕地唔罰（EXP-70：該組只 −1.2pp） |
| **HV** | 剷重地專項三條（曾贏 +3.87／曾上名／多戰 0 上名） |
| **WO** | 剷濕地 overlay |
| **WOS** | 濕地 overlay 只喺 Soft 7+／Heavy 開（同 `_wet_state` 嘅爛地定義一致；Soft 5–6 唔開） |
| **TR0** | 整個 track 維度 = 60 |

**採用**：每條「冇代價簡化」—— Gold、Good 點估計 ≥ 0，冇 ranking metric CI 上界 < 0，冇預先聲明分層 CI 全負 → 採用。
多條合資格 → 合併後用真引擎 dump 再驗一次同一規則。ranking metric `top3_capture_at5`、`ndcg_at5`、`top5_pairwise_auc`；
bootstrap 以賽日 2000 次、seed 7。分層：馬匹數、首選 SP、路程、首選跑法，另加 **今場地況（好地／Soft 5–6／Soft 7+／Heavy）**。

## 第 3 步：地況來源診斷（只報告，唔採用）

**OFFICIAL**：用賽果官方地況（比賽時掛牌）代替分析時地況重評。賽前會公佈（每場前更新），但而家排程只喺 22:00／10:00 抓，
所以呢個 arm 量嘅係「如果日間開跑前再更新一次地況」值幾多。結果決定要唔要另開排程改動，**唔會直接上線**。

## 唔准做

睇完結果改任何常數、加 arm、換窗或者指標。
**Leakage**：OFFICIAL 用嘅係比賽時地況，屬開跑前已公佈資料，但歷史上我哋冇喺嗰刻抓過，所以只做診斷。
