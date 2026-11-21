# EXP-20261121-31 Sportsbet 價明顯高過 Betfair 係咪訊號？（AU 頭兩選，紙上 forward，預先登記）

- 日期：2026-11-21　平台：AU　狀態：**forward 進行中（盲測）**
- 提出：Kelvin 2026-11-21「could that be a signal when sportsbet odds is higher than betfair? … only looking at top 2」
- Code：`.agents/skills/au_racing/au_daily_auto/au_sb_betfair_forward.py`；排程 `step_sb_betfair_forward`（evening，每晚）；
  追蹤表 `au_forward_tracker.FORWARD_TESTS["sb_over_betfair"]`

## 背景

- EXP-20261104-10：模型對市場冇額外資訊；EXP-20261105-01：同一批注 Sportsbet −15%、BSP ≈ 打和，差距全部係抽水。
- 所以如果有 edge，只可能嚟自「Sportsbet 定價慷慨過 sharp 市場」，唔係嚟自模型揀馬。
- BSP 開跑先知 → 回測用 BSP 做篩選係前視。只可以用落注嗰刻嘅 Betfair 即時價（`betfair_odds_history.json`，11-17 起有記錄）。

## 設計（睇任何賽果之前定死）

| 項目 | 規則 |
|---|---|
| 群體 | 每場模型頭兩選（`au_betting.top_two`），唔設 2.0 門檻 |
| 凍結點 | 賽日**第一個**早更 Sportsbet 快照（`morning-refresh`／`morning-rebuild`，過入錯場守衛 `odds_quality.outside_field`） |
| Betfair 價 | ±30 分鐘內最近嘅 Betfair 早更快照，按馬名（字母數字小寫）配對；位賠 > 獨贏 = 壞價，唔用 |
| 凍結 | 寫入 `work/au-sb-betfair-forward-picks.jsonl`，之後唔改 |
| 高價組 | Sportsbet 位賠 ÷ Betfair 位賠（未扣佣金）≥ **1.10** |
| 結算 | Sportsbet 位注 1u，凍結嘅位賠；派位數同落注單（`au_reflect_notify.places_paid`）；遲退出 = 退注、未有賽果唔計 |
| 樣本 | 高價組 **1,000** 注已結算先判一次，判完凍結 |
| P1 | 高價組 ROI 95% CI 下限 > 0 |
| P2 | 高價組 − 其餘 ROI 差 95% CI 下限 > 0 |
| 判決 | P1 同 P2 都過 = PASS；否則 REJECT。Bootstrap 按賽日抽，2,000 次，seed 20261121 |
| 次要（只報唔判） | 比例分段 ≤0.9／0.9–1.0／1.0–1.1／>1.1 嘅位注 ROI；高價組獨贏 ROI |
| 盲測 | 未夠數只報數量（凍結、配對、結算、高價組注數），**唔報 ROI** |

### 門檻點樣定（只用賽前價錢）

初次運行（2026-11-21，11-18→11-21 共 434 匹有配對）：位賠比例中位 1.06，74% > 1；獨贏比例中位 1.02，77% > 1。
即係「Sportsbet 高過 Betfair」係常態（早上 Betfair 盤薄、back 價偏低），本身冇篩選作用，所以門檻定 1.10 ≈ 最高四分一。
定門檻時冇睇過任何賽果或 ROI。

## 限制

- Betfair 早上流動性薄，價唔一定落得到；判決係 Sportsbet 位注 ROI，唔係 Betfair。
- 落注單實際時間可能遲過凍結點；凍結用第一個早更係為咗唔可以揀價。
- PASS 都唔會自動落注；點用由 Kelvin 決定。dashboard forward 面板 Kelvin 延後咗（2026-11-20），進度經 forward tracker Telegram。
