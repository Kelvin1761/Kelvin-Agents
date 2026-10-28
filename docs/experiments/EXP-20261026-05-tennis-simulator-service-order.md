# EXP-20261026-05 — Simulator 跨盤發球輪轉：單一 correctness 修正

日期 2026-10-26；狀態：已量度。Protocol `e0c1ce4f` 先入 main；baseline 完成後先改 candidate。

## 已重現問題與固定修正

Baseline `007fbc628ec4ca157da68f1d9a439291901d68bf`，`match_simulator.py` 每盤後無條件
`a_serves_first = not a_serves_first`。Controlled `_play_set` 固定第一盤 6-4、第二盤 6-3，
observed 首發 `[True, False]`；應為 `[True, True]`。6-3／7-6 後應交換，6-4／6-0 後不交換。

依據 [ITF 2026 Rules of Tennis](https://www.itftennis.com/media/7221/2026-rules-of-tennis-english.pdf)
Rule 14（PDF p10）及 Rule 5(b)（p8）：每局延續發球輪轉；tie-break 首發方下盤先接發。
修正只按前盤 games 奇偶延續 server，唔改第一盤 server、hold、dispersion、trials、seed 或策略。

## 固定評估

- 先取得 baseline，再改 candidate；使用 EXP-04 同一個 checksum DB，唔新增／重選日期窗。
- Corpus 擴至全部可核實賽前 BO3 singles：ATP／WTA；排除 main-draw BO5、未知 Slam 賽制、
  winner conflict、非 canonical side、integer push lines、mislabeled player totals。
- 同 scope：player_games／game handicap／first-set handicap／first-set winner；原 MIN(id) 同時雙邊
  opening quote 及 feature cutoff 政策不變。只讀 legacy history；唔接 WTA 新 source。
- 同場、同合約、同 quote 配對；B0/B1 只差 server-order kernel。4,000 次 match bootstrap，seed 20260826。
- Raw Brier／LL 對 baseline 及 market，按 tour／family／surface；flat 1u edge≥0.04 只次要診斷。
- 不按結果改阈值、不改 ruler／split；first-set 純理論應不受後續發球次序影響，有限 MC seed stream
  可因後續抽樣數改變而出現差異，必須報告，唔當獨立訊號。
- Correctness proof 不等於 profitable；未過 tennis-v1 唔升級投注 family。若有退步照報，
  不以新 WTA source 或新權重抵銷。

## 結果

**Correctness：FIX。Predictive improvement：未證明。投注 family：唔 promotion。**
665 matches／1,230 props，固定 corpus／quote／outcome 完全一致，無 coverage 變化；ATP 483 場、WTA 182 場。
| 版本 | Brier ↓ | Log loss ↓ |
|---|---:|---:|
| baseline | 0.251512 | 0.701830 |
| candidate | 0.251835 | 0.703654 |
| market | 0.233667 | 0.659996 |

候選 ΔBrier +0.000322，95% match CI [-0.0009015235907742399, 0.0015308431812515529]；
ΔLL +0.001824，CI [-0.001351276718879943, 0.005011989942559916]。兩者跨零，唔聲稱準確率改善，point estimate 輕微退步照報。

| Family | matches / props | B0 Brier | B1 Brier |
|---|---|---:|---:|
| player_first_set | 627 / 627 | 0.250037 | 0.249879 |
| player_first_set_game_margin | 64 / 64 | 0.271143 | 0.269554 |
| player_game_margin | 124 / 414 | 0.246756 | 0.248678 |
| player_games | 62 / 125 | 0.264613 | 0.263029 |

所有 family ΔBrier／LL CI 均跨零。627 場 first-set winner 理論不受後盤 server 影響，
有限 MC stream 因後續局數改變，首盤 sample sequence 亦會改變；其微小升跌唔作獨立 signal。
市場仍明顯較好；無 CLV 或交易 edge 結論。現役 shadow／family eligibility／stake 規則不變。
次要 raw edge≥0.04 平注：B0 −28.683u /473（−6.06%），B1 −36.093u /480（−7.52%）；
唔將 correctness fix 包裝成 profitability upgrade，亦唔用 ROI 反調權重去救結果。

## 工程及證據
- 原 kernel deterministic red proof：4 failed／3 passed；按 game parity 修正後 native Tennis 748 passed（16.58s），quick 全綠。
- GROUP BY MIN(id) reader 同 sequential first-id reader，全部 baseline records／probabilities／quotes 完全一致（1,230 records）；只係讀法改善。
- Source 只讀 legacy history，無 WTA overlay；WTA 直接接線 REJECT 結論獨立保留。
- 修正係符合 ITF 規則嘅 deterministic correctness fix；唔係參數 search，唔宣稱有 market-relative 性能勝出，唔據此啟用任何新投注 family。
- 呢份係同輸入 counterfactual A/B，唔係當時已保存嘅 candidate forecasts；legacy history 對超過 13 日舊 rows 主要靠日期，確切 capture availability 未全部證明。仍標 FLAG，唔作正式 PIT／live promotion 證據。
- Rollback：發佈前 baseline `007fbc62`（後續 docs commit 亦無改 kernel），immutable manifest 保留回退 SHA。
- Candidate file SHA256：`f2527c25c83be89c56ba0640a544345462fb8985a84dc0ad148a50940ee17e21`。
- 資料 SHA256 同 EXP-04；原始逐合約 baseline／candidate 同 comparison 存外置 scratch，唔進 git。

## 重跑
研究 driver 係 non-main 分支 `codex-tennis-refine-20261026` 嘅 `scripts/evaluate_service_order.py`。
先無 candidate 參數生成 baseline，再用 `--baseline <baseline.json> --candidate <fixed match_simulator.py>` 生成候選與 comparison。
固定 `PYTHONDONTWRITEBYTECODE=1`、`PYTHONPATH=src`；DB 路徑同 EXP-04；研究 driver SHA：`2a873f64a7150209a6346e7959d51f4d98338c72`。


```bash
cd tennis-wong-choi  # research driver checkout at 2a873f64a7150209a6346e7959d51f4d98338c72
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python scripts/evaluate_service_order.py \
  --db "/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-refine-20261026/tennis_research.db" \
  --output "/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-refine-20261026/service_order_baseline.json"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python scripts/evaluate_service_order.py \
  --db "/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-refine-20261026/tennis_research.db" \
  --baseline "/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-refine-20261026/service_order_baseline.json" \
  --candidate "/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-refine-20261026/service_order_candidate_kernel.py" \
  --output "/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-refine-20261026/service_order_candidate.json"
```


Correctness release `02b19954bf17c3dbdf18f3a94c98ac5e4c6c746e` 已經 full 16-suite gate／immutable quick recheck／merge／activation，scheduler runtime HEAD 已核對相同。無啟用新投注 family。
