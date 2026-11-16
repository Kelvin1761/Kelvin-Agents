# EXP-20261116-12 — Tennis：Sportsbet 獨贏價對 Betfair 交易所收市價（外部參考價第 1 步）

- 日期：2026-11-16；平台：Tennis；類型：**唯讀研究**（冇改 live code、冇開帳戶）。
- Kelvin：重點係盈利；要搵 edge、贏市場。下載 tennis-data 已獲 Kelvin 批准。
- 起因：EXP-20261116-08／-10 —— 自己模型校準後 ≈ 市場，冇 edge。今次測「Sportsbet 慢過 sharp 市場」，唔使模型。
- 預先登記：`patches/tennis_sharp_reference_20261116/PROTOCOL.md`（讀價之前鎖定）。

## 數據

- tennis-data.co.uk 2026 ATP／WTA xlsx（2026-11-16T09:09:53Z 下載，SHA256 見 PROTOCOL；路徑而家有前綴
  `hrjk-85HytOjkhth76j_ygh4jf7/`，舊路徑會 redirect 去 parking 頁）。
- **Amendment A（睇覆蓋率之後、配對同賽果之前）**：Pinnacle（PSW/PSL）只得 2026-01 共 172 行，同我哋 Sportsbet
  窗口（05-08 起）零重疊 —— 應該係 Pinnacle 2025-07 關 API 嘅後果。改用 **Betfair Exchange 收市價 BFEW/BFEL**（每月都有）。
- 配對：763 場；有開賽前 Sportsbet 快照：**506 場**（dev 148：05-09..08-31；holdout 358：09-01..11-14）。
  抽查冇配對到嘅 tennis-data 行：DB 有場次但 **0 個 Sportsbet 快照** —— 限制喺我哋嘅獨贏價覆蓋，唔係配對 bug。

## 結果

| | |
|---|---|
| Sportsbet 獨贏抽水（中位） | **5.76%** |
| Betfair 收市 overround（中位） | 0.63% |
| Sportsbet 公平價同 Betfair 公平價差距 | 中位 1.51pp，p90 3.89pp |
| 每一邊對 Betfair 收市嘅 EV | 中位 −5.53%；>0 嘅 8.8%；>2% 5.8%；>5% 2.3% |
| 熱門邊平均 EV／冷門邊平均 EV | **−4.44%／−8.40%** |

主規則（最早快照、比例去水、EV>0）：

| | 注數 | ROI | 95% CI |
|---|---:|---:|---|
| dev | 30 | +6.1% | [−39.3, +55.1] |
| **holdout** | 59 | **−3.9%** | [−34.5, +29.3] |

全部 506 場、EV>0：89 注，**以 Betfair 收市計嘅理論 EV +4.62%**，實際 −0.6%。EV>5%：23 注理論 +11.5%、實際 −4.8%。
次要（最後快照、power 去水、門檻 2%／5%）全部 CI 跨零。

## 判斷：**INCONCLUSIVE（功效唔夠）**

- 按預先登記規則，holdout CI 跨零 → 唔判得。59 注 ROI 嘅 CI 闊 ±30 點，冇可能分到 ±5% 嘅 edge。
- 有用嘅結構性發現：
  1. **Sportsbet 獨贏價大部分時間貼住 Betfair 收市**（差距中位 1.5pp），抽水 5.8%，所以 91% 嘅邊都係負 EV。
  2. **Sportsbet 冷門抽水差唔多係熱門兩倍**（−8.4% 對 −4.4%）。呢個係 EXP-20261116-08「odds >3 蝕」嘅另一面：
     就算模型完美，買 Sportsbet 冷門都要先輸 8 點。
  3. 約 9% 嘅邊對收市有正 EV，平均 +4.6%。如果落注嗰刻有可靠嘅 sharp 價做參考，呢批就係唯一有機會賺錢嘅地方，
     但收市價係事後先知，**唔係可執行策略**。
- 下一步要嘅係「落注嗰刻」嘅 sharp 價（同 Sportsbet 快照同一時間抓），先量到可執行 EV 同 CLV。
  候選：Betfair Exchange API（延遲 key 免費，要 Kelvin 自己開 Betfair AU 帳戶同 app key）、The Odds API
  （`betfair_ex_au`，主要係獨贏）。Betfair 仲有首盤勝方／讓局／總局市場，可以做 props 參考（流動性要量）。
- 另一個瓶頸：我哋只有大約 37% 嘅 tour 場次有 Sportsbet 獨贏快照。

## 限制

樣本細；收市價係事後資料；Betfair 收市喺細場流動性薄；tennis-data 只有 ATP／WTA 正賽（冇 Challenger／ITF）；
Sportsbet 快照大部分只係開賽前一個鐘內（EXP-20261110-03 第 6 點）。

## 重現

```bash
P=docs/experiments/patches/tennis_sharp_reference_20261116
# 下載：見 PROTOCOL.md 嘅 URL 同 SHA256，放 $DL/atp2026.xlsx、$DL/wta2026.xlsx
python3 $P/study.py tennis-wong-choi/tennis_wc.db $DL
```
