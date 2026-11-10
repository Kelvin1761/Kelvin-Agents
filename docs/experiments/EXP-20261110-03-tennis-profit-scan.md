# EXP-20261110-03 — Tennis：盈利全掃描（模型對市場有冇增量、有冇軟位）

- 日期：2026-11-10；平台：Tennis；類型：**唯讀診斷**（冇改模型、選注規則或前向測試）。
- 提問（Kelvin）：全面掃一次，有冇任何方法令 Tennis Wong Choi 賺錢。
- 已搜舊記錄：EXP-20260826-09、EXP-20261026-03、EXP-20261027-05、EXP-20261105-10、EXP-20261106-01、
  `docs/plans/2026-11-05-tennis-strategy-and-rebuild-plan.md`（階段六）、統一研究計劃 15 個 REJECT_DEV。
- Baseline：main `5b45a24e`；模型 `tennis-v1` 冇郁。

## 語料

live DB `tennis-wong-choi/tennis_wc.db`（`mode=ro`，2026-11-10）。`prop_tracker` 只取
`is_point_in_time=1`、`result_status IN ('WON','LOST')`、賽事唔係 DISPUTED：
**13,964 行／3,336 場，match_date 2026-08-11 至 2026-11-10**。
CI：按場 cluster bootstrap，seed 20260826，95%。全部係歷史探索，冇 holdout、冇揀參數。

## 結果

### 1. 模型對市場冇額外資訊

`y ~ a + b·logit(market_prob_fair) + g·(logit(model_prob_raw) − logit(market_prob_fair))`：

| Family | n | b（市場） | g（模型分歧） | g 95% CI |
|---|---:|---:|---:|---|
| 6 個 live family 合計 | 6,654 | 0.946 | −0.106 | [−0.283, +0.106] |
| first_set_winner | 3,402 | 1.076 | +0.054 | [−0.150, +0.253] |
| player_win_a_set | 1,560 | 0.975 | −0.128 | [−0.456, +0.240] |
| player_game_handicap | 989 | 0.961 | −0.208 | [−0.647, +0.244] |
| player_set_handicap | 308 | 0.924 | −0.002 | [−0.426, +0.449] |
| player_total_games | 202 | 0.080 | −0.167 | [−0.878, +0.452] |

每個 live family 嘅 Brier 模型都輸市場（例：首盤勝方 0.2420 vs 0.2096；讓局 0.2508 vs 0.2238）。

### 2. 抽水同盲買

| Family | 抽水 | 盲買全部 ROI |
|---|---:|---:|
| first_set_winner | 7.5% | −7.8% |
| player_win_a_set | 7.7% | −9.6% |
| player_game_handicap | 8.8% | −7.0% |
| player_set_handicap | 9.5% | −4.3% |
| player_first_set_game_handicap | 9.9% | −6.8% |
| player_total_games | 8.8% | −7.8% |

### 3. 模型 value 注

全部 1,376 注／684 場：**−11.4% [−19.1, −3.4]**，差過盲買。
逐 family（−6.1% 至 −16.0%）、逐月（08 −22.5%、09 −13.1%、10 −7.0%、11 −8.5%）、Tour −13.1%／Challenger −9.0%、
ATP −10.7%／WTA −12.3%、edge 段（0.30 以上 −29.9%，49 注）、賠率段：**冇一格係正而 CI 唔跨零**。
live family 10-28 起 288 注 −3.6% [−19.1, +12.9]。

### 4. 唔靠模型嘅軟位（熱門／冷門偏差）

6 個 live family × 7 個賠率段盲買：冇一格 CI 下限 > 0。最高係首盤勝方 1.6–1.9（+1.2% [−6.1, +8.2]，531 注）。

### 5. 精選前向測試現況（EXP-20261105-10，唔影響判決）

40 注，已結算 34（1 注 VOID），19 中，+3.45u，ROI +10.2%。250 注先判；按 1–3 預期值約為 −6% 至 −8%。

### 6. 獨贏盤移動 → props 跟慢：**量唔到**

4,405 場有 ≥2 個賽前獨贏快照，但 4,107 場首尾相隔 <1 個鐘（價變 0.4%）。相隔 12–24 個鐘 37 場有 81.1% 變價、
≥24 個鐘 15 場 100%。即係 Sportsbet 價會郁，我哋冇記錄到。`prop_price_log` 嘅「88.6% 冇郁」受同一限制。
知道獨贏移動嘅 props 行入面，移動 ≥0.5pp 只有 124 行，冇功效。**唔係 REJECT，係未有數據。**

## 判斷

- **喺「自己模型 + Sportsbet 單一莊」之內，冇證據支持任何可盈利嘅 family、分層或選注方法。** 再收窄精選或者再調模型，
  同之前 15 個以上 REJECT 一致，唔建議重開。
- 未試過而有機制嘅方向：(a) 外部參考價（Betfair exchange／Pinnacle）做真值，Sportsbet 價高過先落；
  (b) 多莊比價（計劃階段六第 1 項，Kelvin 11-06 暫緩）。兩者都需要新數據來源，要 Kelvin 拍板，開始前要預先登記。
- 第 6 點要有答案，需要同一場相隔多個鐘嘅快照（11-06 起精選場次每 30 分鐘 near-start capture 會慢慢累積）。

## 限制

歷史探索、多重比較冇校正（結論係「全部都唔過」，所以校正只會更保守）；`decimal_odds` 係最後一次賽前定價價；
family 之間同場相關（已按場 cluster）；08 月行受當時盤口錯標影響（EXP-20261015-05）。

## 重現

```bash
PY=tennis-wong-choi/.venv/bin/python; P=docs/experiments/patches/tennis_profit_scan_20261110
PYTHONDONTWRITEBYTECODE=1 $PY $P/scan.py            # 第 1–4 節
PYTHONDONTWRITEBYTECODE=1 $PY $P/ml_move.py         # 第 6 節
python3 $P/snapshot_span.py                         # 快照時間跨度
```

腳本寫死 live DB 路徑（`/Users/imac/Antigravity-repo/tennis-wong-choi/tennis_wc.db`，唯讀）；DB 每日變，數字會隨之郁。
