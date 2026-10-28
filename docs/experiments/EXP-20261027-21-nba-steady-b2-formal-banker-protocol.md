# EXP-20261027-21 NBA 正式穩膽改用 steady（B2）：命中率產品線協議同停損

- **日期**：2026-10-27（Claude Code，用戶喺 EXP-20261027-20 §4 揀咗做法 (a)）
- **性質**：產品決定，**唔係模型改善**。冇改任何機率、L10／L5／CoV 門檻、排序、傷停或者季初保護。
- **前置**：EXP-20261024-02（B0／B1／B2 EV 閘消融，B2 定義喺度）、EXP-20261027-20（版本審計）、EXP-20261026-06（季初穩膽保護，照用）。

## 1. 改咩

正式 combo 1（Telegram 投注卡、dashboard 正式 BET）由「有 EV 閘嘅 combo 1」改為 **B2**：

| 項目 | 之前（`banker-only-v1`） | 而家（`banker-steady-b2-v1`） |
|---|---|---|
| 揀腿 | `select_combo_1`，單腿非負 edge | 同一個 selector，`require_leg_ev=False` |
| 組合 | 建構時要正 EV | `require_combo_ev=False` |
| 報價 | 真實 Sportsbet SGM、已驗證、≥2.0 | **不變** |
| 真價 EV 閘 | `_combo_passes_positive_ev_gate` | **移除** |
| 注碼 | Half-Kelly | **固定 $1 平注**（Kelly 喺負 EV 時係 0） |

結果：正式 combo 1 同 EXP-20261024-02 嘅 B2 arm 逐腿一樣。B0／B1／B2 shadow 照寫，steady 研究候選照寫，dashboard tracking 照用「每場第一個已驗證發佈」計。

## 2. 明確聲明：模型預期 EV 為負

呢條係命中率產品線，唔係有優勢嘅投注策略。

- 10-26、10-27 兩日 21:00 版本嘅 B2（真價 ≥2.0）：**14 注中 5，−1.57u（ROI −11%）**。
- 同一批注，模型自己估嘅組合命中率平均約 **34%**，真價 EV 約 **−12%**（範圍 −25% 至 +6%，只有 1 注正）。實際 36% 命中，同模型一致。
- 即係話：**如果模型準，呢條線長期每注蝕約 12%。** 按每日約 7 注計，大約 80 注（兩至三星期）就會累積蝕到 −10u，觸發下面嘅停損。

點解仍然做：用戶要求投注卡、dashboard 同實際落注用同一個版本，唔好一邊叫 NO BET 一邊追蹤另一套。用停損限制損失，並且量度市場價係咪真係比模型估得更準。

投注卡同 dashboard 每次都要顯示「模型預期 EV 為負」同停損條件，唔准淨係顯示命中率。

## 3. 預先登記停損（寫 code 之前凍結）

**計數範圍**：只計 dashboard tracking 記錄入面 `strategy_profile == "banker-steady-b2-v1"` 嘅已結算注（won／lost；void 同 unpriced 唔計）。10-25 至 10-27 嘅舊記錄（22 注、+2.29u）**唔計**，由零開始。

| # | 條件 | 動作 |
|---|---|---|
| S1 | 累計盈虧 ≤ **−10u** | **自動暫停** |
| S2 | 已結算 ≥ **60** 注，而 ROI 95% 置信區間上限 < 0（按比賽日 cluster bootstrap，2,000 次，seed 20261027） | **自動暫停** |
| S3 | 已結算 ≥ **40** 注，而實際命中率 ≤ 模型平均命中率 **−10pp** | 唔暫停，Telegram 發「需要審查」一次（模型可能高估命中率） |

**S1 同 S2 嘅關係（寫低免得誤會）**：平注 $1 之下，60 注時 ROI 上限要 <0，實際 ROI 大約要差過 −27%，即係已經蝕超過 16u，S1 早就觸發咗。所以 **S1 先係真正會用到嘅停損**，S2 只係大樣本後備（例如將來調高 S1 之後）。呢點喺寫 code 前已經知道，唔係事後發現。

**暫停嘅意思**：
- 每晚檢查一次（賽後 ROI 計完之後）。觸發即刻寫狀態檔，並發 Telegram 一次。
- 暫停之後，報告生成時正式 combo 1 一律係 NO BET，寫明係停損暫停同觸發原因。投注卡顯示「⛔ 停損暫停」。
- steady 研究候選同 B0／B1／B2 shadow **照寫照追蹤**，方便睇恢復係咪合理。
- **唔會自動恢復**。要用戶明確決定，用：
  `python3 .agents/skills/nba/nba_steady_policy.py --resume --actor <名> --reason "<原因>"`
  恢復會記錄喺狀態檔嘅 history；之後停損由恢復嗰日重新計（舊注保留喺 history）。

**唔准做嘅嘢**：觸發之後改門檻、改計數範圍、改 seed、或者換指標去避開停損。要改停損就要寫新協議。

## 4. 唔係停損嘅嘢

- 單日蝕錢、連輸幾場：唔觸發任何嘢。
- S3 只係提示，唔改模型。真係要改機率，照 forward 協議（MS／S 測試）去判。

## 5. 狀態檔

`<NBA ledger 根>/steady_policy_state.json`（預設 `~/WongChoiData/NBA_Market_Eval/`，`WONGCHOI_NBA_STEADY_STATE` 可改）。冇檔 = active。pytest 期間唔讀生產狀態。

## 6. 狀態

預先登記；未有任何 `banker-steady-b2-v1` 記錄。工程正確性（正式 combo 1 = B2 逐腿一致、FW-11 只對正式穩膽放寬負 EV、停損計算）由單元測試驗證。盈利未經證明，而且模型預期係負。

## 7. 交付前真數據隔離重跑（2026-10-27 21:15，唔係收益樣本）

用 21:00 production 嘅 10-28 Sportsbet／game data，喺 scratch 目錄以新 code 重新生成 4 場（冇寫生產資料、冇 deploy）：

- 3 場有正式組合 1（DET_NYK @2.5、POR_LAL @3.2、SAC_SAS @2.75），全部同 B2 shadow 逐腿一致，亦同今晚 production 嘅 steady 研究候選逐腿一致。BKN_BOS 冇組合過到真價 ≥2.0，NO BET。
- 模型 EV：−6.7%、−0.7%、−14.9%（全部為負，同 §2 一致）。
- **重跑捉到一個單元測試冇捉到嘅閘**：FW-13（SGM 報價核對）有自己一條 `probability × price ≤ 1` 正 EV 檢查，令三場全部被擋。已改為只對帶 steady 標記嘅報告放寬（FW-11 負責檢查披露），並加回歸測試（冇修正會紅）。
- 修正後：完整 `validate_file` 三場全過；dashboard 匯出 3 個 BET（`sportsbet_sgm_quoted`，附免責說明）；Telegram 投注卡顯示 EV 為負同停損條件。
