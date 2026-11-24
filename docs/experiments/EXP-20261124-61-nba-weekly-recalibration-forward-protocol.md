# EXP-20261124-61 協議：NBA 每週重校準層 —— forward 預先登記

- **日期**：2026-11-24（喺任何 forward 數據存在之前 commit；11-25 嘅 ledger 檔當時未存在）
- **平台**：NBA
- **決定人**：Kelvin 2026-11-24：「happy to wait until 26」「im ok to 定期重擬合」「continue」
- **凍結**：`docs/experiments/patches/nba_recal_forward/evaluate.py`（arm、係數、判決全部寫死），同本文件同一個 commit。
- **唔改發佈機率**：`p_final`、穩膽、精選、SGM 全部照舊；呢個係紙上量度，唔發 Telegram content、唔入 ROI 板。

## 點解（EXP-20261124-60 同設計量度）
- `p_final` 中段（20–60%）低估 5–6pp、頂段（≥90%）高估 3.4pp；事後校準 R2 喺 holdout −0.0035，但假設來源同 holdout 重疊 → NEEDS MORE TESTING。
- **定期重擬合點做**（`patches/nba_ms_recal/rolling_sim.py`，11-12…11-24 walk-forward，描述性）：
  R2 用晒之前數據每日重擬合 −0.0036、**每週** −0.0036、只用最近 7 日 −0.0028、最近 14 日 −0.0035；R1 約 −0.0019。
  → 每週一次、用晒 MS 上線以嚟數據就夠，唔使每日。
- **重要**（`patches/nba_ms_recal/market_only.py`）：同一個 walk-forward，**淨係用市場價嘅去水曲線**（唔用 `p_final`）−0.0033，同 R2 一樣；
  R2 − 純市場 +0.0001 [−0.0000, +0.0003]。即係話而家 `p_final` 喺「去水去得啱嘅市場價」之上冇加到資訊，改善全部嚟自去水形狀。
  全期擬合嘅 R2 係數亦一樣：`p_final` 權重 0.03、市場 0.95。

## Arm（全部喺同一批腿上計）
`logit p = a_stat + b·logit(p_final) + c·logit(m) + d·logit(m)²`，m = 1/`price_at_model`，`p_final`、m 都 clip 0.02–0.98。
- **RW（主）**：每週（target_date 星期一至日）用該星期一之前所有 MS 腿（由 2026-11-05 起）重擬合一次。
- R2F：同一形式，係數凍結（11-05…11-24，21,894 腿）：a = −0.130982／−0.190218／−0.132677／−0.021445（PTS／REB／AST／3PM），b 0.028416，c 0.94972，d −0.059996。
- R1W：每週重擬合 `a_stat + b·logit(p_final)`（冇價項）。
- MKT：每週重擬合 `a_stat + c·logit(m) + d·logit(m)²`（冇 `p_final`）。

## 母體
target_date ≥ **2026-11-25**；每條腿最早一個開波前 `production` `model_obs`，`probability_model_id = nba_engine:ms:a140747bfae0c724`，有非 void 嘅 ledger 結算。
如果之後某日出現其他 `probability_model_id`（例如 S2 判咗之後換 MS2），母體喺嗰日之前截止，結果標 `interrupted`（要對新 `p_final` 重新登記）。

## 判決（只判一次，結果凍結）
- **夠數**：≥14 個 target day 而且 ≥10,000 腿；用到兩樣都夠嗰日為止（成日計）。
- **主指標**：Δ = 平均 log-loss(RW) − 平均 log-loss(`p_final`)，按日 cluster bootstrap 2,000 次，seed 20261125。
- **PASS**：Δ 95% CI 上限 < 0 → 可以申請將「每週重校準」接入發佈機率，要過 `model-regression-gate`、由 Kelvin 決定。
- 次要（只報告，唔判）：R2F、R1W、MKT 各自對 `p_final`；**RW − MKT**（`p_final` 喺市場之上有冇加到嘢）；逐 stat；校準分段。
- 夠數由 `nba_forward_tracker` 自動判一次，Telegram primary 推一次。

## 點讀結果（預先寫低）
- RW PASS 而 RW − MKT CI 跨零：校準修好咗，但模型自己冇 edge；**大細盤精選同穩膽嘅「edge」應該當係去水誤差**，要另外諗精選規則。
- RW PASS 而 RW − MKT CI 上限 < 0：模型喺市場之上有資訊，校準層值得上線。
- RW 唔 PASS：記低點失敗；唔准喺同一批數據換形式、換窗再判。

## 功效（預先講明）
每日約 1,100 條腿 → 14 日約 15,000 腿，大約 12-08 夠數。EXP-60 holdout 12 日 CI 闊約 ±0.0014，真改善 ≳0.002 先判得出。

## 洩漏
`p_final`、`price_at_model` 都係 21:00 production run 寫低嘅賽前值；每週係數只用該週之前已結算嘅腿；`y` 只做標籤。

## 顯示
Dashboard NBA 加「模型校準（紙上 · 未入分）」：進度、forward 腿嘅校準分段（實際 vs `p_final` vs 每週重校準 vs 純市場）、目前 Δ（註明「未夠數，唔係判決」）。
