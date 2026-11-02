# EXP-20261102-10 結果：場地／地況／濕地重建 —— 一個模組、剷兩組冇訊號規則；濕地處理審查

- **預先登記**：[protocol](EXP-20261102-10-au-track-going-rebuild-protocol.md)（`f776bd07`，量度之前）。
- **語料**：全語料重評 4,086 場；判決 08-05 起 3,283 場，v3 `fixed_rule`，bootstrap 以賽日 2000 次。baseline `ed4ac6f8`。

## 第 1 步：結構 —— A/A byte-identical

計算搬入 `au_racing_engine/track_going.py`（同場、地況往績、爛地專項、濕地 overlay、今場地況分級）。全語料重評同 baseline **逐 byte 一樣**。
同時剷死開關 `WC_TRACK_NO_GOING`（EXP-20260901-05 已 REJECT）。

## 第 2 步：逐條消融（Δ pp）

| arm | 郁咗場數 | Gold | Good | top3 capture | NDCG@5 | 分層 CI 全負 | 決定 |
|---|---:|---|---|---|---|---|---|
| ST 剷同場成段 | 2,954 | −0.24（塊 2/6） | −0.03 | +0.11 | −0.01 | 首選守中 Gold | 保留 |
| STP 剷同場 0 上名扣分 | 2,436 | **−0.18 [−0.34, −0.06]** | 0.00 | +0.02 | −0.04 | Soft 5–6 Gold | 保留（有訊號） |
| GO 剷地況往績 ② | 1,546 | +0.09 | **−0.03**（塊 3/6） | **+0.16 [+0.02, +0.31]** | **+0.14 [+0.04, +0.23]** | — | 保留（見下） |
| **WU** 剷爛地未經驗證 −6.4 | 305 | +0.03 | +0.03 | −0.03 | −0.02 | — | **剷** |
| WU0 未跑過濕地唔罰 | 179 | 0.00 | +0.03 | −0.02 | −0.02 | — | 合資格，但 WU 更簡單 |
| **HV** 剷重地專項三條 | 169 | 0.00 | 0.00 | +0.01 | +0.01 | — | **剷** |
| WO 剷濕地 overlay | 1,681 | −0.27 | **−0.52**（塊 2/6） | +0.26 | +0.00 | ≤8 匹 Gold、首選後上 Gold | 保留 |
| WOS overlay 只開 Soft 7+／Heavy | 1,255 | −0.27（塊 1/6） | −0.37 | +0.29 | +0.08 | 同上 | 保留（Soft 5–6 都要開） |
| TR0 成個維度 = 60 | 3,054 | −0.09 | −0.06 | +0.18 | +0.09 | — | 保留 |
| **採用組合 WU＋HV**（真引擎 dump） | 369 | +0.03 [−0.10, +0.18] | 0.00 [−0.12, +0.13] | −0.03 | −0.02 | — | 合資格 |

**決定**：剷「爛地未經驗證 −6.4」同「重地專項三條（曾贏 +3.87／曾上名 +2.0／多戰 0 上名 −5.94）」—— **冇代價簡化，唔係改善**。
同場往績（兩個 0 上名扣分有真訊號）、濕地 overlay（剷走 Good −0.52pp）保留。

**GO（地況往績 ②）係值得跟進嘅發現**：剷走之後三個排序指標 CI 全部 > 0（NDCG p 0.006），Gold +0.09，只係 Good −0.03pp（3,283 場入面 1 場）
令佢唔合「Gold、Good 都 ≥ 0」嘅登記規則。照規則唔郁；要另開登記（例如 forward 或者用 v3 正式判 RANKING_WIN），唔可以睇完結果改規則。

## 第 3 步：濕地處理審查

1. **地況錯配**：分析用嘅地況同比賽時官方地況 **24.2%** 唔同一級（3,528 場）—— 主要係日間轉乾：406 場用 Soft 5–6 分析、實際 Good 跑；
   104 場 Soft 7+ → Soft 5–6；相反方向 82 場。
2. **OFFICIAL 診斷**（用比賽時官方地況重評，只報告）：Gold −0.18pp、Good −0.12pp、top3 capture +0.14（CI > 0）、首選前置 Gold CI 全負 ——
   **用「啱」嘅地況冇令排名變好**。所以日間再抓地況唔值得做排程改動；錯配主要係顯示問題（報告寫住軟地但實際好地）。
3. **兩把濕地尺唔一致（已處理一半）**：overlay 喺 Soft 5+ 開，「未經驗證」只喺 Soft 7+ 罰 —— 後者已剷，而家只剩 overlay 一把尺（Soft 5–6 都開，WOS 證實要開）。
4. **好地往績唔入分**：Facts 第一段冇「好地:」標籤，好地 bucket 永遠係 0；code 註釋講明係刻意（舊 A/B 唔過），照舊。
5. **冇數字嘅 Soft**（13 場）：overlay 開但 `wet_state` 當乾；影響細，冇改。
6. **合成跑道**：`normalise_synthetic_going` 處理掛牌；往績冇 `Synth:` 段，冇得做合成跑道專項（EXP-70 已記）。

## 驗證

定稿 code 全語料重評同採用組合 dump **逐 byte 一樣**；golden 120 匹一致；AU tests 1,223 passed；data contract 重新 calibrate。

## 重跑

```bash
S="/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/track-rebuild"
python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_dump_engine_leaves.py --out $S/final.json
python3 scratch/au_track_official_going_dump_20261102.py --out $S/OFFICIAL.json   # 地況來源診斷
python3 scratch/au_track_rebuild_judge_20261102.py BASE.json CAND.json OUT.json
```
arm 開關版本喺 commit `03f38481`＋ `track_going.py` 嘅 `WC_AU_TRACK_ARM`（已拆走；判決 JSON 喺 `EXP-20261102-10-evidence/`）。
