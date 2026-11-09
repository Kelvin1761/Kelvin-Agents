# EXP-20261109-04 協議：NBA 上場時間風險（M）＋臨場缺陣接手隊友（T）—— forward 預先登記

- **日期**：2026-11-09（喺任何 forward 數據存在之前 commit）
- **平台**：NBA
- **要求人**：Kelvin（2026-11-09：「A」—— 預先登記兩個測試）
- **凍結腳本**：`docs/experiments/patches/nba_forward_mt/evaluate.py`（同本文件同一個 commit）
- **追蹤**：`.agents/skills/nba/nba_daily_auto/nba_forward_tracker.py`，每晚 postgame 跑；第一次夠數會自動評估一次、凍結結果去
  `~/WongChoiData/NBA_Market_Eval/reports/EXP-20261109-04-<M|T>-result.json`，並推 Telegram（primary）一次。
- **永遠唔會自動改模型或者落注規則。**

## 點解有呢兩個測試
2026-11-09 覆盤（只做分析，未記錄成實驗；數字出自 tracking 89 注同 ledger 19,899 腿）：
- 正式穩膽 64 注中 21，模型預期 20.8 —— 跟足模型預期咁輸，唔係唔好彩。「差 1 先中」嘅比例（28%）仲低過全市場同價位腿（48%）。
- 揀出嚟嘅腿模型估 73.5%，實際 66.3%。
- **輸嘅揀腿入面 24% 上場時間少過近期平均 6 分鐘以上，中嘅只有 4%** → M。
- 唔睇賠率嘅 S 模型同莊家意見唔同時多數錯（S 話抵買嘅腿 ROI −14%～−18%）：要贏，就要有莊家未消化嘅資訊 → T。
- EXP-20261104-12 H2（21:00 後臨場缺陣、全隊所有腿）冇效應，而 21:00→收市嘅價中位唔郁；嗰度已經寫低「只計接收出手嘅隊友」係
  下一步，而且**唔准喺同一批數據再試** —— 所以 T 只用 forward 數據。

## 共同設定
- **只讀 forward 數據**：`target_date ≥ 2026-11-10`，之前嘅一律唔讀（腳本硬性過濾，有測試守住）。
- 賽前資料**一律攞 21:00 第一個 production snapshot 自己嗰份**（`_prediction_snapshots/<snapshot_id>/` 入面嘅
  `nba_game_data_<tag>.json`、`Sportsbet_Odds_<tag>.json`），唔用之後 refresh 過嘅檔。
- 賽果：ledger `settlement`（over，hit/miss）。
- CI：按場次 cluster bootstrap，2,000 次，seed 20261109，百分位 95%。
- 每個測試**只評估一次**（夠數嗰晚自動跑）；結果檔存在就唔會重算，`--force` 要喺本文件寫明理由。

## M：上場時間風險
**問題**：有上場時間風險旗標嘅腿，`p_final` 係咪高估得比冇旗標嘅多？

- **母體**：21:00 發佈嘅 over 腿，`p_final ≥ 0.60` 且 `price_at_model < 2.00`（穩膽區），PTS／REB／AST／3PM；
  球員喺 snapshot L10 ≥5 場且平均上場 ≥20 分鐘。
- **旗標**（任何一個成立 = flagged；全部賽前已知）：
  1. 大比數：`|spread_away| ≥ 10`（snapshot 嘅 Sportsbet 讓分）
  2. 上場時間波動：L10 分鐘標準差（母體）≥ 6
  3. 傷患標籤：snapshot 傷停表有佢而唔係 Out／Doubtful／Suspension（即 Day-To-Day／Questionable／Probable），或球員 status 唔係 Active
  4. 背靠背：佢上一場（L10 日期）係今場美東日期前一日
- **主指標**：Δ = mean(y − p_final | flagged) − mean(y − p_final | 冇旗標)。
- **通過**：Δ ≤ −3pp **而且** 95% CI 上限 < 0。
- **描述性（唔用嚟判）**：每個旗標單獨嘅殘差同 ROI、揀中腿嘅分拆、旗標組 vs 非旗標組單注 ROI。
- **檢查點**：≥21 個 target date **而且** ≥800 條有旗標腿（機制試跑：每日約 330 條有旗標，即係日數先到門檻，約 2026-12 上旬）。
- **通過代表乜**：只代表模型系統性高估呢類腿。改 B2 揀腿（例如排除旗標腿）係另一個候選，要另外預先登記、用檢查點之後嘅數據、過
  `model-regression-gate`，**唔可以用同一批數據即刻上線**。
- **唔通過**：記低，唔再喺同一批數據試其他旗標組合。

## T：臨場缺陣，接手嘅隊友
**問題**：主力喺 21:00 之後先被列 Out，接手出手／組織嘅隊友喺下一次價錢更新時係咪被低估？

- **事件**：球員 X 喺 21:00 snapshot 冇被列 Out／Doubtful／Suspension、ledger 亦冇 snapshot 時間或之前嘅 Out 記錄；之後、開波前，
  `availability_obs` 第一次記佢 `espn_level` 或 `official_level` = out。X 要係輪換主力（L10 ≥5 場、平均 ≥24 分鐘）。
  每隊每場只計最早嗰宗。
- **接手者**（同隊、未 Out、L10 ≥5 場、平均 ≥24 分鐘）：L10 平均 FGA 最高嘅 2 個 → 計 PTS；L10 平均 AST 最高嘅 2 個 → 計 AST。
- **腿嘅揀法**：每個接手者每個 market，取 Out 第一次記錄時間 −10 分鐘之後、開波前**每條線第一個價**，揀最接近 1.90 嘅線
  （打和揀低線），要有賽果。
- **對照**：同期冇事件嘅隊，用同一個接手者規則（排除所有已知 Out），每條線取最後一個開波前價，同一個「最接近 1.90」揀法。
- **主指標**：Δ = mean(y − 1/價 | 事件腿) − mean(y − 1/價 | 對照腿)。
- **通過**：Δ ≥ +5pp、95% CI 下限 > 0、**而且**事件腿平注 ROI 點估計 > 0（要真係落到注先算數）。
- **描述性**：PTS／AST 分拆、事件腿 ROI 嘅 CI。
- **檢查點**：≥60 宗事件 **而且** ≥200 條事件腿（試跑：每日約 2.7 宗，約 3–4 個星期）。
- **功效限制（預先講明）**：200 條腿嘅校準 CI 大約 ±7pp，即係只捉到好大嘅效應。如果 Δ 點估計 ≥ +5pp 但 CI 跨零，**准延長一次**
  到 ≥120 宗／≥400 腿，用同一把尺、同一個腳本（`--force`，理由寫入本文件）；之後唔再延長。
- **通過代表乜**：一個研究訊號，唔會自動落注。要用，就要另外設計「消息一出即 refresh 價、人手落注」嘅流程同停損。

## 已知限制
- `availability_obs` 只喺排程 refresh 時間記錄（大約 21:00 後每 1.5–2 個鐘一次），所以「消息時間」最多遲一個 refresh 窗口；事件腿用嘅價係
  呢個窗口實際攞到、落得到注嘅價。
- Sportsbet 單邊 milestone 盤、冇去水；校準數已包抽水，所以 T 用「事件 − 對照」做主指標，唔係絕對值。
- 試跑（只計數量，冇睇命中）發現 ledger `availability_obs.name_key` 冇空格（`asanewell`），同 `player_name_key()`（`asa newell`）唔一致；
  腳本一律用 `player_name_key(player)`。

## 重跑
```bash
python3 docs/experiments/patches/nba_forward_mt/evaluate.py status     # 只顯示進度，唔顯示命中
python3 docs/experiments/patches/nba_forward_mt/evaluate.py evaluate   # 未夠數會拒絕；已凍結就讀返結果
```
