# 借鑑開源模型補盲位 —— 執行計劃（2026-10-14）

來源：同日 GitHub 研究（NBA props／網球／賽馬三份報告）＋ repo 摸底。
原則：**唔係抄人哋模型**（研究結論：冇一個開源模型贏到市場），而係用佢哋做過、
我哋未做過嘅嘢，去補我哋睇唔到嘅位。每項寫明：補邊個盲位、點量、點先算成功。

所有改模型嘅項目照 AGENTS.md「改模型嘅規矩」：先 grep `docs/experiments/`、先量
baseline、記錄落 `docs/experiments/`、失敗 model code 唔 commit、release 串行。
每個工作流用獨立 worktree（主 checkout 有其他 session 未 commit 嘅改動）。

## 已剔除（做過或者唔值得）

| 想法 | 點解唔做 |
|---|---|
| Plackett-Luce／條件 logit 擬合維度權重 | HKJC EXP-20260902-03 已 REJECT（likelihood 平到揀唔到權重）；AU 特徵集飽和、重配份額五次過唔到 holdout |
| GBM／LambdaRank 取代線性組合 | AU 已實測 GBM 輸現行線性組合 |
| 相關場地 Elo／MOV Elo（網球） | EXP-20261009-01：Elo 方向全部做晒只收窄 ~5% 缺口；排最後，有時間先做 |
| 抄 ATPBetting／高 star HKJC repo | 全部有洩漏（W/L 欄、賽後欄位、place 用 win 賠率派彩） |

## 要 Kelvin 拍板（唔係研究問題）

**D1. 賽馬係咪開一個「明文市場層」？** EXP-20260826-08 已證實 `ability + k·z(−log odds)`
每個 k 都過閘（Gold +2.36pp），但 AGENTS.md 規定賠率唔准做隱藏 proxy，除非
methodology 明文寫佢係模型一部分。狀態一直係「等 Kelvin 決定」。
選項：(a) 唔開，賠率只做顯示；(b) 開，作為獨立發佈層（原排名照保留並排顯示）。
R1／R3 嘅結果會影響呢個決定，但唔阻住佢哋開工。

## Phase 0 —— 正確性／基建（唔使「改善」證據，行 §7 正確性修正）

| ID | 盲位 | 做乜 | 完成條件 |
|---|---|---|---|
| T0a | 網球收市價可能係走地價 | `fetch_closing_odds_for_date` 存「最新」snapshot 做 close，冇 `< start_time_utc` 界線 | 加界線＋測試；量受影響行數 |
| T0b | 數據源壞咗冇人知 | run-daily `source_errors` 唔入 Telegram 健康行；Sackmann 404 只記 `csv_not_found` | 健康行顯示 source_errors；記錄 WTA 發球數據 2026-05 起斷咗 |
| T0c | CLV 只追落咗注嘅 | props `clv_tracker` 只同步 `is_value=1 AND stake>0` | 每個評估過嘅盤都記最早價＋收市價（借 mlb-kalshi-bot 做法） |
| N0 | NBA 由來冇同市場比過 | `nba_backtest.db` 0 行；標籤係固定盤口格唔係 Sportsbet 價 | 每個評估過嘅 prop 記 Sportsbet 最早價／收市價＋賽果，出 Brier／logloss vs 去水市場。**2026-10 下旬新球季開波前要駁好** |
| R0 | HKJC 冇任何賽前賠率 | 只有賽果頁最終 `win_odds` | 排程加賽前獨贏／位置賠率快照（只向前收集） |
| X0 | 共用去水 | 賽馬零去水（`au_ml_program` 直接 1/SP）；網球只有比例去水，ace 階梯除死 1.06 | `shared_racing`／`tennis_wc` 各一個 devig module：proportional／power／Shin／odds-ratio，有單元測試（≥14 匹馬場合都要啱） |

## Phase 1 —— 量度（唯讀，結論記錄落 docs/experiments）

| ID | 問題 | 方法 | 借自 |
|---|---|---|---|
| R1 | 我哋 AU 模型對市場有冇**任何**增量資訊？ | Benter 第二階段：`p ∝ exp(α·log p_model + β·log p_market)`，條件 MLE，walk-forward；市場價用**最早快照**唔用 SP；報 α 嘅 CI 同每場 nats 增量 bootstrap CI；加 placebo（打亂 model 分數） | hkjc-edge-lab、Benter 1994 |
| X1 | 邊種去水最準？ | AU（Sportsbet 獨贏／位置）＋網球（match／total games／aces）逐個方法比 OOS logloss vs 賽果；重現 k≈1.10–1.20 | penaltyblog、mberk/shin、goto_conversion |
| R3 | Sportsbet 位置價同獨贏價一唔一致？ | 由去水獨贏機率用 Harville＋Henery 折扣推頭三機率（λ 喺 dev 擬合），對比 Sportsbet 位置價；量「位置價偏貴／偏平」嘅價位段同實際入位率 | Harville／Henery／Lo-Bacon-Shone |
| L1 | 洩漏不變性 | 通用測試：攞一個歷史日，加一日未來賽事入語料，重算 → 過去所有 feature 行要 bit-identical。AU 同 HKJC 各一個 | hkjc-edge-lab |

## Phase 2 —— 候選（要過 model-regression-gate 先可以留）

| ID | 盲位 | 候選 | 量度 |
|---|---|---|---|
| T1 | ITF 細樣本發球率一冇數就跳去 `LEAGUE_HOLD` | `hold_model` 加 Efron-Morris／James-Stein 收縮（樣本少→拉向場地／級別均值），Elo-induced 發球率做 prior | 只用 PIT 行；props logloss vs 去水市場＋ValueProfile 子集 ROI CI |
| T2 | props 由零開始估，冇用市場已知嘅嘢 | 市場反推：total games 兩條半盤 → 預期局數；ace 階梯 → 負二項均值；模型只喺正交資訊（場地 ace 率、對手接發）上調整，再過現有選注閘 | 同上；拆 shared／only-A／only-B 逐注 join |
| N1 | SGM 用獨立相乘 × 人手相關懲罰 | 用現成 `monte_carlo_nba.py` 加場級共享因子（節奏／上場時間／大比數），同一次模擬入面數組合命中 → 聯合機率；**shadow 模式**同舊法並排記錄 | 要 N0 累積到足夠已結算 SGM 先判；未判之前唔准改發佈 |
| R4 | （視乎 D1）市場層 | 如果 D1=(b)，R1 嘅 α/β 做發佈層 | 照 EXP-20260826-08 閘 |

## 次序同依賴

1. 即刻：X0、T0a、T0b、T0c、N0（並行，各自 worktree）＋ D1 問 Kelvin
2. X0 完成 → X1、R1、R3；L1 獨立並行
3. X1 揀好去水 → T2；T1 獨立
4. N0 有數據 → N1 判決（預計要等幾星期球季數據）
5. R0 只向前收集，HKJC 市場相關分析最早幾個星期後先做得

## 唔會做嘅事

- 唔會因為 Phase 1 結果好睇就直接改評分（要過 Phase 2 閘）
- 唔會用 holdout 調參；唔會用 SP／收市價做落注回測價
- 失敗候選嘅 code 唔 commit；結果照記
