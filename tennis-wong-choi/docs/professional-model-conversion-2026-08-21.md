# Player Props 專業做法轉化 — 2026-08-21

## 結論

第一輪轉化已落地，但未有任何 family 喺 untouched holdout 擊敗 de-vig bookmaker probability。所有新 variant 只進入 shadow／`RESEARCH_ONLY`；正式卡嘅 `2.00+` soft preference 不會越過 probability、edge、quality 或 timing gate。

## 已實作轉化

| Family | 專業化改動 | Frozen holdout Brier | Market Brier | 決定 |
|---|---|---:|---:|---|
| Game handicap | fitted serve/return hold + 0.06 match-day dispersion；由 joint margin distribution 定價 | 0.2445 → 0.2185（n=382） | 0.2066 | Shadow |
| Player total games | 同一 fitted joint simulator 直接輸出 player-games distribution | 0.2734 → 0.2665（n=194） | 0.2492 | Shadow |
| Win a set | 與 set handicap／exact score 共用 BO3 multinomial outcomes | 0.2111 → 0.2085 | 0.1820 | Shadow |
| Set handicap | 同一 BO3 multinomial outcomes | 0.1408 → 0.1371 | 0.1257 | Shadow |
| Exact set score | 四個互斥結果共用同一 outcome table | 0.175789 → 0.175788 | 0.1602 | Shadow |
| First-set winner | 測試共用 full-match joint，但表現較差 | 0.2421 → 0.2428 | 0.2084 | 保留首盤專屬模型 |
| Player aces | ace rate × 預期 service games；pre-split 擬合 NB size=3 | 0.3129 → 0.2847（n=48） | 0.2592 | Shadow |
| First-set game handicap | fitted hold joint simulator直接輸出首盤game margin | 0.2552（207場 replay） | 0.2469 | Shadow；paper ROI +1.84%（56注），未可信 |
| Win first set & match | 四個互斥first-set result × match-winner outcome一次去水 | 0.1665（197場 replay） | 0.1615 | Shadow；paper ROI -12.65%（26注） |

以上數值係 probability quality，唔係 ROI；模型未贏市場時，不會靠揀賠率 band 或放寬 threshold 將歷史 ROI「調正」。

## Ace exposure data contract

- `player_match_history.service_games_played` 已加入 schema、Sackmann ingestion 同 serve feature capture。
- 以本地 immutable raw payload 回填 150,633 筆有 ace 統計嘅歷史 rows；回填只更新 service-games exposure，無改賽果、賠率或 prediction。
- Negative-binomial size 只用 2026-08-07 前 117 個 props 選擇；之後 48 個 props 保持 untouched。
- Holdout：舊 raw 0.3129、Poisson 0.3141、純 exposure empirical 0.3134、NB exposure 0.2847、market 0.2592。Poisson 同純 exposure curve 不採用。

## Runtime／correctness

- Elo rebuild 原本逐場執行兩次 opponent update，亦無以 provider 限定 match ID；呢個同時係 performance bottleneck 同 cross-provider overwrite bug。
- 改成 provider-qualified temporary table + set-based update，history insert 用 `executemany`。
- Production DB：168,806 winner rows、17,097 players，Elo rebuild 5.44 秒。
- Daily CLI payload 新增逐 stage timings，方便兩日 canary 設 runtime budget 同告警。

## 下一個實作優先次序

1. 跑兩日 scheduler canary，固定每個 stage 正常時間同 timeout budget。
2. 加 opponent-strength adjustment／partial pooling 到 hold inputs；用 chronological hard-court holdout 重驗 game handicap 同 player games。
3. 增加 first-set 專屬 serve-order／first-set form features，唔借用 full-match probability。
4. Ace exposure 累積至少 100 個 forward settled props，再重新 fit dispersion；期間只記 scorecard／CLV。
5. 完成 immutable analysis run/version contract同 Telegram 7/14/30日 family 分層。
6. 只有 family 同時過 market Brier、calibration、bootstrap ROI downside 同 data-integrity gate，先進 limited live；否則保持「今日無正式推薦」。

## 新增每日 shadow markets

- `player_first_set_game_handicap`：近30日137場有盤、136場可由首盤比分結算；歷史replay 56個formal paper bets，ROI +1.84%，`P(ROI≤0)=43.05%`，未過10%門檻。
- `player_first_set_match`：Sportsbet將四個互斥結果拆成「贏首盤兼贏全場」及「輸首盤但贏全場」兩個市場；系統必須合併四邊先去水。歷史replay 26個formal win-first paper bets，ROI -12.65%。
- 兩個family已進daily board、tracker、settlement及scorecard，但刻意不在`LIVE_FAMILIES`；只顯示`🧪 RESEARCH_ONLY`，paper 1u，實盤0u。
