# EXP-20261104-10 預先登記：AU 模型點樣贏錢 —— 對市場有冇優勢、用邊個價、避開邊類場、注碼

- **日期**：2026-11-04（寫喺砌數據集同睇任何結果之前）；**平台**：AU；**引擎**：只用**儲存咗嘅賽前預測**（唔重新評分）。
- **用戶**：「how can we leverage this model to 贏錢, like what strategy, is there any races or race course we should avoid? should we use kelly」。
- **類型**：純研究，唔改模型、唔改 `au_betting.py`。

## 已知（唔再重驗）

EXP-20260905-01（08-13..09-04，823 場）：當朝 Sportsbet 位盤抽水 21%，所有門檻 ROI ≈ −19%；價位段內我哋 AUC 0.5054；
晚更價 ≥2.0 −7.5% [−16.8, +2.8]。2026-07 嘅 Betfair BSP 正數係舊語料（賽後重評分 + 往績頁洩漏），唔作準。

## 數據（固定）

- 窗口：**2026-08-05 .. 2026-11-03**（乾淨 point-in-time）。
- 模型：`au_window_review.build_dataset` 規則 —— 每場開跑前最後一個預測快照（冇開跑時間就悉尼 11:00 前最後一個）。
  另砌「晚更」版本：賽日之前最後一個快照。
- 價：(a) Sportsbet 定額贏／位（`Odds.json`，**只用 captured_at 早過開跑**，同時唔早過所用預測快照 —— 即係落注嗰刻真係見到嘅價）；
  (b) Betfair BSP 贏／位（公開 CSV，扣 5% 佣金；BSP 喺開跑先定，但「以 SP 落注」可以賽前預早下，所以係可執行價）。
  BSP 唔准做模型特徵（係結果時先知）。
- 賽果：`Race_Results_Reflector.md` + canonical results CSV（同 window review）。退出馬剔走。
- 配對：BSP 用 (日期, 場地, 正規化馬名)。報告配對率；< 90% 就停低先查。

## 問題同判決（全部預先固定）

**Q1 —— 模型有冇市場冇嘅資訊（決定性）。** 場內條件 logit（贏 = 頭馬；位 = 入位）：
`logit ∝ a·log(p_mkt) + b·z(模型分)`，p_mkt = 1/價 場內正規化。**walk-forward**：頭 4 個星期 warm-up，之後逐星期用之前全部數據 fit、
預測下一星期。主指標 = OOS 對數損失 Δ(混合 − 純市場)，按賽日 block bootstrap 2,000 次。
**有優勢 = Δ 95% CI 全部 < 0。** 分開報四個市場：BSP 贏、BSP 位、Sportsbet 贏（落注時價）、Sportsbet 位（落注時價）。
Q1 冇優勢嘅市場，Q2–Q4 照計但只作記錄，結論寫「冇優勢」。

**Q2 —— 用邊個價、揀咩注。** 規則：OOS 混合機率 p，落注當 `p × 淨賠 − 1 ≥ 5%`（淨賠：BSP 扣 5% 佣金；Sportsbet 原價）。
報 ROI、注數、命中率，賽日 bootstrap CI。另報兩個對照：「模型第 1 選全部落」同「市場熱門全部落」（同一個價）。

**Q3 —— 避開邊類場次。** 預先固定分層：州（NSW／VIC／QLD／其他）、場地級別（metro／provincial／country）、馬匹數（≤8／9–12／13+）、
價位段（<3／3–6／6–15／15+）、地況（好地／黏地／大爛地）。做法：前半窗口（08-05..09-19）同後半（09-20..11-03）各自計 Q2 規則 ROI；
**「應該避開」= 兩半都負、而且後半 CI 全負**；其他一律「分唔到」。唔准由分層揀出一個「正數子集」當策略（多重比較）。

**Q4 —— 注碼。** 只喺 Q1 有優勢嘅市場：OOS 注單上模擬平注、¼ Kelly、½ Kelly（Kelly 用混合 p），報最終資金、最大回撤、
破產機率（bootstrap 重排注單 2,000 次）。

## 唔做

- 唔用失手體檢、唔睇 holdout 再改規則；EV 門檻 5%、warm-up 4 星期、分層定義全部唔准事後改。
- 結果正數都唔會直接建議真錢：先登記 forward 紙上落注（forward tracker + Telegram）。
