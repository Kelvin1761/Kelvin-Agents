# EXP-20261105-01 模型第 1 選 × 賠率門檻：Sportsbet vs Betfair BSP

- **日期**：2026-11-05；**平台**：AU；**類型**：純量度（唔改 code）。
- **用戶**：「what if we only place on certain odds for 模型第 1 選? say when it hits 2, i am planning to use betfair in the future,
  but keep compare with sportsbet + betfair」。
- **主規則（用戶指定，事前固定）**：第 1 選、賠率 ≥ 2.0。其他門檻（1.5–6.0）只作描述，唔揀。
- **數據**：EXP-20261104-10 數據集（08-05..11-03，儲存咗嘅賽前預測，晚價 = 中位數開跑前 4.6 小時；冇 warm-up，所以場數多過嗰次 OOS）。

## 三種落法

- **Sportsbet**：落注嗰刻定額價篩選兼結算，計退出馬扣減。
- **BSP（SB 價篩）**：用 Sportsbet 價決定落唔落，Betfair BSP 結算，扣 5% 佣金。
- **BSP 限價（Limit on Close）**：Betfair 支援「BSP ≥ X 先成交」，所以用 BSP 自己篩係可執行、唔係前視。

## 結果（晚價，賽日 bootstrap 95% CI）

| | 注 | 命中 | ROI |
|---|---|---|---|
| 贏 · Sportsbet · 唔設門檻 | 2,747 | 26.4% | −14.8% [−20.7, −8.1] |
| 贏 · Sportsbet · ≥ 2.0 | 2,442 | 22.6% | **−15.7%** [−22.3, −8.5] |
| 贏 · BSP（SB 價篩）· ≥ 2.0 | 2,442 | 22.6% | **+1.0%** [−7.5, +10.5] |
| 贏 · BSP 限價 · ≥ 2.0 | 2,512 | 23.0% | **+1.0%** [−7.4, +9.9] |
| 位 · Sportsbet · ≥ 2.0 | 640 | 30.6% | −23.2% [−32.0, −14.7] |
| 位 · BSP 限價 · ≥ 2.0 | 1,082 | 34.6% | −6.8% [−14.3, +0.8] |

門檻掃描（贏注）：Sportsbet 由 −14.8%（唔設）到 −20.5%（≥ 4.0），BSP 喺所有門檻都係 0% 至 +2%，CI 全部跨零。
位注：門檻越高越差（Sportsbet ≥ 3.0 −34.4%），即係 `au-min-odds-filter-is-antiselected` 嘅位注版本。
早價結果方向一樣（Sportsbet 贏 ≥ 2.0 −18.1%、BSP −0.6%），但早價有 55% 場次有馬冇出（可能包括後備馬），扣減估算較唔準。

## 結論

1. **賠率門檻唔會令模型第 1 選變成贏錢。** 門檻只係揀一個唔同嘅價位段；模型喺每個價位段嘅資訊都一樣（≈ 0，EXP-20261104-10）。
2. **贏注 + Betfair BSP 大約打和（+1%），Sportsbet 同一批注 −15%。** 差距全部係抽水。CI ±9pp，+1% 同 0% 分唔開。
3. **位注唔好加門檻**：≥ 2.0 位賠嘅第 1 選正正係市場睇淡嘅一批。
4. 轉 Betfair 之後要繼續比較，最乾淨嘅做法係 forward 紙上落注：同一隻第 1 選，記低 Sportsbet 價同 BSP，
   兩邊各自結算。贏注每注回報標準差約 2.2（由 2,512 注 CI 半闊 8.6pp 反推），要 CI 半闊縮到 3pp
   大約要 **(1.96 × 2.2 ÷ 0.03)² ≈ 20,000 注**（每日約 30 注 ≈ 兩年）—— 短期內 Betfair 嘅 +1% 同 0% 係分唔開嘅。

## 可重現

    python3 scratch/au_rank1_odds_threshold_20261105.py dataset.json out.json

dataset：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/betting/dataset.json`（由 `scratch/au_betting_edge_dataset_20261104.py` 砌）。
