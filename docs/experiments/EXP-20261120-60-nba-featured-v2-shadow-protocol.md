# EXP-20261120-60 協議：大細盤精選 v2 紙上 arm —— forward 預先登記

- **日期**：2026-11-20（喺任何 forward 數據存在之前 commit）
- **平台**：NBA
- **決定人**：Kelvin（2026-11-20：「精選永遠揀『細』：值得開一個新版本測試，連埋第 2 項 ok go」）
- **凍結**：`docs/experiments/patches/nba_featured_v2/evaluate.py`（規則、修正常數、判決全部寫死），同本文件同一個 commit。
- **唔改 v1**：現行精選（EXP-20261110-01，`nba-featured-ou-v1`）照發、照計 ROI、照跑 F250／F1000。v2 純紙上，唔發 Telegram、唔入 ROI 板。

## 點解
- v1 由 11-11 至 11-19：46 注已結算**全部係細**，32 注係助攻細；+12.35u（ROI +26.8%，95% CI −1.6% 至 +48.3%）。
- 核實（`bias_check.py`，11-05…11-19，2,149 條有模型嘅已結算大細盤線）：**模型 P(大) 平均 45.2%，實際 48.9%，去水價 48.7%**。
  去水價準，模型系統性低估「大」約 3.7pp（線越高越嚴重：10+ 嘅線模型 42.4% 對實際 55.0%）。即係「永遠揀細」係模型偏差，唔係市場偏差。
- 同期對照：全部細盤 −6.1%；模型細 edge 5–8pp 嘅 −15.6%、≥8pp 嘅 −6.8%；模擬「每場揀最高」+2.6%。v1 嘅好成績大部分可能係運氣。
- v1 六注作廢入面五注係 Sportsbet 收盤，四注係助攻細 1.5 呢類低線。

## v2 規則（全部凍結）
1. **修正偏差**：P(大) = sigmoid(logit(clip(p_final, 0.02, 0.98)) + δ[stat])；δ：得分 0.3889、籃板 0.0493、助攻 0.2715、三分 0.0853
   （用上面 2,149 條線擬合一次，令平均等於實際，之後唔郁）。修正後平均 48.9%；log-loss 0.6963 → 0.6917，**仍差過去水價 0.6881**。
2. **剔走 O/U 線 ≤ 1.5**。
3. **edge ≥ 0.03**（v1 係 0.05）。修正後 5pp 好少（過去 15 日每日 1.1 注）；3pp 每日 4.7 注、大 40／細 30。**門檻只按注數揀，冇睇輸贏。**
4. 其餘同 v1：大細兩邊、比例去水、價 ≤ 3.0、每場一注（edge 最大）、每日最多 10 注、平注 1 單位、冇上場 = 作廢。
- 數據全部由 ledger：模型 = 該腿第一個開波前 `production` `model_obs`（21:00 run）；價 = 嗰次模型見到嘅最後一個開波前大細盤價；結果 = ledger 結算。
- **母體**：target_date ≥ 2026-11-21。

## 判決
- **V2_250（中期）**：頭 250 注已結算；ROI 95% CI 上限 < 0 → STOP（停呢個 arm）；中期唔會 PASS。
- **V2_600（終判）**：頭 600 注已結算；平注 ROI 95% CI 下限 > 0 → PASS。
- 按日 cluster bootstrap，2,000 次，seed 20261120；各判一次，結果凍結。夠數由 `nba_forward_tracker` 自動判並 Telegram primary。
- 次要（只報告）：大／細各自 ROI；同期 v1 ROI（dashboard 對照表）。

## 功效（預先講明）
每日約 4.7 注 → 250 注約 53 日、600 注約 130 日（大約到常規賽尾）。600 注 CI 大約 ±8pp：真 edge 要 ≳ +8% 先有機會 PASS。
修正後模型仍然輸畀去水價（log-loss），所以**預期未必有 edge**；呢個測試答嘅係「修正咗偏差之後揀注有冇料」。

## 顯示
Dashboard NBA「⭐ 大細盤精選」tab 加「紙上對照：精選 v2」：同期 v1／v2 注數、中、盈虧、ROI、大／細分佈，同 v2 最新一晚揀咗乜。標明「未發佈 · 唔好跟 · 唔入 ROI」。

## 唔通過
記低點樣失敗；唔准喺同一批數據改 δ、門檻、線下限再判。PASS 亦唔會自動取代 v1 —— 由 Kelvin 決定。

## 重跑
```bash
python3 docs/experiments/patches/nba_featured_v2/evaluate.py status
python3 docs/experiments/patches/nba_featured_v2/evaluate.py evaluate
python3 docs/experiments/patches/nba_featured_v2/bias_check.py   # 偏差核實，對照 bias_check_out.txt
```
