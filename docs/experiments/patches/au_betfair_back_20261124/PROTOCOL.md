# EXP-20261124-60 預先登記（2026-11-24，睇結果之前寫）—— 現行模型喺 Betfair 落注有冇得贏

- 起因：Kelvin「lets look at 喺 Betfair 落注」。舊結果：EXP-20261104-10（BSP 規則 ≈ 打和、模型對市場冇額外資訊）、
  EXP-20261105-01（第 1 選 BSP 贏 +1.0% [−7.5, +10.5]）。之後 live 加咗 R2、F1、速度分、老馬、練馬師剩餘表現 → 用**現行模型**重量。
- 模型：現行 live BASE dump（main 10095812 時嘅 code：含 F1、速度分）`au-debut-trainer-20261124/BASE.json`，2026-08-05 → 11-23。
- 價：Betfair 公開 BSP CSV（贏＋位），08-06 → 11-23；配對照 `scratch/au_betting_edge_dataset_20261104.load_bsp`（日期＋場地＋場次＋馬名，
  後備日期＋馬名唯一）。BSP 係開跑前「以 SP 落」可執行嘅價；**只用嚟結算同做 Q1 市場基準，唔用嚟揀注**。
- 分段：dev = ≤ 11-03（同舊研究重疊）、new = 11-04 → 11-23（舊研究之後嘅新數據）。兩段各自報。
- **Q1 資訊**：獨贏 —— 條件 logit 頭馬：s = α·log(p_m) + β·z(ability)，p_m = (1/BSP) 場內正規化；位 —— 逐匹 logistic：
  logit(入位) = a + α·logit(p_m,place) + β·z(ability)，p_m,place = (1/BSP位) 正規化到派位數。baseline = 冇 β。
  每賽日只用之前賽日 fit（頭 20 日唔計分）。報每場 Δlog-likelihood（賽日 bootstrap 2,000）。CI 全部有利先算「有額外資訊」。
- **Q2 規則**（只靠模型排名，平注 1u）：R1 第 1 選獨贏、R2 第 1 選位、R3 頭兩選位。結算 BSP，佣金 5%（另報 8%）。
  報 ROI + 賽日 bootstrap 95% CI。**CI 下界 > 0 先算有得贏**；dev 同 new 方向要一致。
- 唔會因結果改規則、佣金、分段或者配對。
