# EXP-20261026-05 — Simulator 跨盤發球輪轉：單一 correctness 修正

日期 2026-10-26；狀態：先登記，未建立 candidate／未讀 candidate 結果。

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

待 baseline／candidate 同窗比較。
