# EXP-20261101-30 結果：L600 環境分近期加權（R）／路程相近度加權（P）—— 全部 REJECT

- **預先登記**：[protocol](EXP-20261101-30-au-l600-recency-distance-protocol.md)（`8b5a9cc7`，量度之前）。
- **語料**：`scratch/au_l600_weighting_dump_20261101.py`（main `5edea8c9` 引擎），4,049 場／39,745 匹；
  v3 乾淨窗 2026-08-05 起 3,246 場；§8 扣 warmup 後 2,243 場／57 個賽日，refit 程序 `f92c8377…` 兩邊一樣。
- **Leakage**：dump 斷言每條 PF 行 `run_date < 今仗日期`，零條違反。權重只用往績日期同路程。
- **replica**：`pace_figure_score` 對引擎 0／31,246 匹差 > 1e-3（最大差 0.0），綜合分最大差 0.0001。
  第一次 replica 有 1,677 匹對唔上：dump 嘅逐行 `source` 有 24,035 行係空，引擎會跟馬匹整體 source
  （dump 只有 sportsbet 同空兩種，冇 mixed）。補咗呢條規則之後完全一致，**之後先睇任何 arm 結果**。
- **決定**：R、P、RP 全部 **REJECT**。冇改動上線，所以冇嘢要 forward 監察。

## leaf 層面（只報告，唔入判決）

場內配對 AUC，baseline 0.60233，賽日 bootstrap 2000：

| arm | Δ AUC | 95% CI | p |
|---|---:|---|---:|
| R 衰減 0.8^k | **+0.0053** | [+0.0022, +0.0084] | 0.002 |
| P 路程相近度 | +0.0005 | [−0.0022, +0.0032] | 0.742 |
| RP | +0.0034 | [−0.0003, +0.0070] | 0.071 |

R 重現咗 EXP-20261016-01 D3c（+0.0055）：**近期加權令 leaf 本身準咗，呢點係真嘅。**
P 對 leaf 冇幫助。Trend 診斷：每匹馬 own L600 對時間嘅斜率（≥3 仗，覆蓋 82.5%）單獨 AUC **0.5203**，弱。

## 判決

| arm | 改到場數 | v3 fixed：Gold | Good | ranking | §8 fixed Gold／Good | §8 refit Gold／Good | 結果 |
|---|---:|---|---|---|---|---|---|
| R | 3,226 | −0.18pp [−0.72, +0.33] | +0.28pp [−0.23, +0.77] | 全部跨零 | −0.22／+0.36 | +0.09／+0.45 | primary_regression；refit ranking_evidence_too_weak |
| P | 3,222 | −0.28pp [−0.67, +0.08] | +0.06pp [−0.42, +0.52] | 全部跨零 | −0.22／+0.27 | +0.05／+0.45 | primary_regression |
| RP | 3,226 | −0.34pp [−0.88, +0.21] | +0.46pp [−0.06, +0.99] | **top3@5 −0.0032 [−0.0059, −0.0005]** | −0.45／+0.45 | −0.13／+0.22（NDCG −0.0039 CI 全負） | primary_regression |

§8：三個都 `both_arms_reject`，live guard 全部 `primary_regression`，Holm p 1.0／1.0，`baseline_weights_stale = False`。
冇分層 primary CI 全負（分層 → `EXP-20261101-30-evidence/v3_*.json`）。

## 解讀

- **同一個模式第 N 次出現**：leaf 準咗（R +0.0053，CI 唔跨零），但落到排名就冇咗
  （memory `leaf-auc-gains-do-not-convert-to-ranking`）。三個 arm 都係 Good 升、Gold 跌，
  即係改變咗「前三入面揀邊匹」，冇改變「揀唔揀得中」。
- 可能原因（未驗證，只係假設）：近期加權嘅資訊同近績質素分（本身已經按近期加權）重疊。
  原本平均數嘅 L600 同 form 幾乎正交（ρ ≈ 0.02）；加權之後佢更似 form，正交性嘅價值就蝕咗。
- 路程相近度加權連 leaf 都冇改善，即係將唔同路程嘅 L600 標準化之後直接平均，已經夠用。
  標準表（場地 × 路程，內插 + 單調）做咗主要工作。
- 用戶問題嘅答案：**速度唔應該好似狀態與穩定性咁近期加權，亦唔使加 Trend**。唔係因為理論錯，
  而係量到佢喺現行模型入面冇增益。現行「全部往績平均 + 同場比」保留。

## 唔做嘅嘢

依登記唔試 0.7^k／0.9^k、唔改路程核寬度、唔將 Trend 升做候選。EXP-20261009-05（WinningTime 近期加權）
盲測照舊進行（1,415／2,000 場），同今次唔係同一個量，結果唔受影響。

## 重跑

```bash
export PYTHONDONTWRITEBYTECODE=1 X=<外置碟 scratch>
python3 scratch/au_l600_weighting_dump_20261101.py --out $X/dump_base.json            # @5edea8c9 引擎
python3 scratch/au_l600_weighting_eval_20261101.py --dump $X/dump_base.json --outdir $X/arms
python3 scratch/au_l600_weighting_judge_20261101.py $X/arms/base.json $X/arms/R.json $X/v3/R.json
python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_walkforward_refit.py predict --data $X/arms/R.json --out $X/wf/R.json
python3 scratch/au_paceperf_s8_20261016.py --base $X/wf/base.json --cand $X/wf/R.json --label R --out $X/s8/R.json
```

證據：`EXP-20261101-30-evidence/`（describe、v3_*、s8_*）。完整 dump 同 arm 喺外置碟
`WongChoi-Archive/scratch/EXP-20261101-30/`。
