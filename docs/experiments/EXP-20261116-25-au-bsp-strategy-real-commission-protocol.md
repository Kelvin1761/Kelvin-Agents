# EXP-20261116-25 預先登記：AU 用 Betfair BSP 落注 —— 計真實佣金，應該用邊個策略

- **日期**：2026-11-16（寫喺下載 holdout 數據、計任何結果之前）；**平台**：AU；**類型**：純落注層研究，**唔改模型、唔改 `au_betting.py`、唔改評分 code**。
- **用戶**（Kelvin）：「ok Let's use Bet fair's odds, please also count in the commissions as well and let's work out what strategies we should use」。
- **分析腳本**（喺睇結果之前寫好，同呢份文件一齊 commit）：`scratch/au_bsp_strategy_20261116.py`；佣金率讀取：`scratch/au_bsp_mbr_probe_20261116.py`。

## 點解要再做

EXP-20261104-10 同 EXP-20261105-01 嘅 BSP 數字全部假設 **5% 佣金**。2026-11-16 用 Betfair API
`listMarketCatalogue`（`MARKET_DESCRIPTION.marketBaseRate`，只讀）實測：**VIC（Sandown、Kyneton）8%、NSW（Warwick Farm、Scone）10%**，
贏、位市場一樣。Betfair 官方說明頁（`betfair.com.au/hub/help/racing-nsw-race-fields-fees-explained/`）寫明 Racing NSW 市場
2017-07-01 起由 8% 升到 10%。即係舊記錄低估咗佣金 3–5 個百分點（以贏錢計），而 BSP 嗰邊本身得 ≈ 0%，所以要重做。

## 已知（唔再重驗）

- 模型對市場冇額外資訊（EXP-20261104-10 Q1，6 個市場 Δlogloss CI 全部跨零）。所以預期大部分策略扣真實佣金後係負。
- Sportsbet 定額乜規則都蝕（−8% 至 −17%）；現行 `au_betting` 位注實盤 2,214 注 −23.6%。呢個研究唔再計 Sportsbet 結算。
- Kelly = 0（冇優勢）。注碼唔喺呢次範圍，一律平注 1 單位。

## 數據同切分（固定）

- **dev**：2026-08-05..11-03，即現有 `/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/betting/dataset.json` 嘅 `late` 情境（開跑前最後一個預測快照，中位數開跑前 4.6 小時；
  Sportsbet 價 = 預測時間 +30 分鐘內、早過開跑嘅最新快照）。⚠️ **dev 唔係新鮮數據**：S1–S5 喺 5% 佣金下 EXP-20261104-10／-05-01 已經睇過（CI 全部跨零）。
- **holdout**：2026-11-04..11-15，用同一個 builder（`WC_SINCE=2026-11-04 WC_UNTIL=2026-11-15`）由儲存咗嘅賽前預測 + 新下載嘅 BSP CSV 砌，**從未用 BSP 睇過**。
  11-16 唔入（賽果未齊）。預計約 450–550 場，所以 holdout 只係**方向覆核**（贏注 ROI CI 半闊約 ±20pp），唔係功效測試。
- BSP 配對率要 ≥ 90%，唔夠就停低先查。
- Betfair 市場走勢記錄（EXP-20261106-02 盲測）**唔用**。

## 執行模型（點樣落注先叫「可執行」）

- 全部係 **SP 注**（以 BSP 成交），喺最後一個賽前預測之後、確定退出馬之後、開跑之前落。BSP 喺開跑先定，所以**揀注唔准用 BSP**，
  只可以用模型排名 + 落注嗰刻嘅 Sportsbet 價；唯一例外係 Betfair 自己支援嘅 **Limit-on-Close**（買注設最低 BSP、鋪注設最高 BSP），呢個係可執行。
- **退出馬**：數據集已剔走冇出賽嘅馬，並喺出賽馬入面重新排名（第 1 選 = 真係出賽嘅最高排名馬）。SP 注喺開跑前退出就作廢、
  BSP 喺退出之後先 reconcile，所以 BSP 注冇定額注嗰種退出馬扣減。reconcile 之後先退出（極少）嘅 reduction factor CSV 冇，唔計。
  冇 BSP 嘅馬（CSV 缺）→ 嗰注唔計。
- 贏注結果 = 官方名次第 1；位注結果 = Betfair 位市場 CSV 嘅 `win_lose`（Betfair 自己嘅派位數）。並頭馬（dead heat）唔特別處理（少）。

## 佣金模型（固定）

- 佣金 = **MBR × 該市場淨贏**（同一個市場內所有注嘅盈虧加埋，正數先收；輸咗唔收）。贏市場同位市場係兩個市場。鋪注贏咗（馬輸）一樣收佣。
- **主方案 `primary`**：NSW 10%、ACT 10%、VIC 8%（API 實測 + 官方頁）；**QLD／SA／WA／TAS／NT／未知場地 = 10%**（未實測，按保守假設）。
- 敏感度（只報，唔用嚟判）：`others8`（未實測州 8% —— 二手資料話係 8%）、`flat10`、`flat8`、`flat5_old`（舊記錄假設）、`gross0`（零佣金，即市場本身嘅偏差）。
- 唔假設其他收費。**已知但唔模擬**：Racing NSW 市場嘅 Turnover Charge（一個星期喺 RNSW 市場買注成交 ≥ $6,000 而佣金 < 成交 1.25% 先收）——
  以平注細注碼唔會觸發，但如果將來大注碼喺 NSW 落，蝕錢策略佣金少，反而會觸發，要另計。
- 未實測州嘅率：本研究期間再用 `au_bsp_mbr_probe_20261116.py` 讀未來市場，讀到就記入結果檔，但**主方案唔改**（避免睇完結果先揀率）。

## 策略（固定 9 個，唔准加減）

| id | 規則 | 市場 |
|---|---|---|
| S1 | 模型第 1 選，全部場 | 贏 BSP |
| S2 | 模型第 1 選，全部場 | 位 BSP |
| S3 | 市場熱門（落注嗰刻 Sportsbet 贏賠最低；同價揀模型排名較前） | 贏 BSP |
| S4 | 市場熱門 | 位 BSP |
| S5 | 模型第 1 選，Limit-on-Close 買注 BSP ≥ 2.0（EXP-20261105-01 用戶規則） | 贏 BSP |
| S6 | 模型第 1 選 **而且** 佢係市場熱門（一致） | 贏 BSP |
| S7 | 模型第 1 選 **而且** 佢唔係市場熱門（分歧） | 贏 BSP |
| S8 | 現行 `au_betting` 規則：頭兩選、Sportsbet 位賠 ≥ 2.0、兩隻都合格而兩隻都 ≤ 3.0 就只落首選 | 位 BSP（同場兩注同一市場淨計佣） |
| S9 | 鋪模型最後一選，Limit-on-Close 鋪注 BSP ≤ 30（每注 1 單位買家注額，責任 = BSP−1） | 贏 BSP 鋪注 |

S9 嘅理由：模型冇資訊，但冷門偏差（favourite-longshot bias）理論上令鋪冷門嘅毛利 > 0；佢係唯一一個唔靠模型有優勢都可能有正毛利嘅結構。
S9 ROI 以責任額做分母。

## 指標

- ROI = Σ盈虧（扣佣後） ÷ Σ投入（買注 = 注額；鋪注 = 責任額）。報注數、命中率。
- 95% CI：按**賽日** block bootstrap，2,000 次，seed 20261116，percentile。
- 單邊 p = (bootstrap ROI ≤ 0 嘅次數 + 1) ÷ 2,001；dev 同 holdout 各自對 9 個策略做 **Holm**（α = 0.05）。

## 判決規則（固定）

- **USE（只係開 forward 紙上測試，唔係真錢）**：dev 主方案 ROI > 0 **而且** Holm 後 p < 0.05；holdout 主方案 ROI 點估計 > 0；dev `flat10` ROI 仍然 > 0。
- **NEEDS_MORE_DATA**：dev 同 holdout 主方案點估計都 > 0，但未過 Holm。→ 唔落真錢；可以 Kelvin 決定開 forward 紙上測試。
- **REJECT**：其他。
- **冇一個 USE ⇒ 結論係「唔好用真錢落」**。會報「蝕得最少」嗰個，但明寫唔係建議。
- 唔准睇完結果先加門檻、價位段、州篩選、或者換指標去救一個策略；任何新規則 = 新 EXP。

## 更正舊記錄（唔係新測試）

用同一個 dev 數據集、跟返原腳本定義，報 5%（對數，要對得返原記錄）同真實佣金下：
EXP-20261104-10 Q2 晚價 BSP 四格（第 1 選／熱門 × 贏／位，warm-up 後）；EXP-20261105-01 第 1 選贏 BSP（SB 價 ≥ 2、BSP 限價 ≥ 2）、位 BSP 限價 ≥ 2。

## 可重現（計劃）

    set -a; source ~/.wongchoi_betfair.env; set +a
    python3 scratch/au_bsp_mbr_probe_20261116.py "<scratch>/mbr_probe_YYYYMMDD.json"
    # holdout BSP CSV：promo.betfair.com/betfairsp/prices/dwbfpricesaus{win,place}DDMMYYYY.csv，04..15/11/2026
    WC_SINCE=2026-11-04 WC_UNTIL=2026-11-15 python3 scratch/au_betting_edge_dataset_20261104.py <bsp_holdout_dir> <scratch>/dataset_holdout.json
    PYTHONDONTWRITEBYTECODE=1 python3 scratch/au_bsp_strategy_20261116.py <scratch>/dataset.json <scratch>/dataset_holdout.json <scratch>/bsp_strategy_report.json

`<scratch>` = `/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/betting/`。
