# EXP-20260902-08 — Bacetti／表現質素分診斷

## 預先登記（未讀本次 ablation 結果）

使用 EXP-06 固定 1,822 場／18,216 匹語料，日期切法不變，今日 Ipswich 與
Warwick Farm 僅作個案，不加入調參或驗證集。以同一套 mapper 重算 baseline
和每個 ablation，先核對與真引擎排名一致度。

固定三個描述性消融，不搜索參數、不挑最優：表現質素分設 60、偏離 60 減半、
用原有 consistency_score 代替。全部報 dev／terminal 的 Gold、Good、排序指標
與配對場次 bootstrap；terminal 只描述預先固定干預，無候選 promotion。
目的是分辨「指標有無資訊」與「個別情境是否過度沿用舊資料」。賠率不入分。

另外獨立檢查可證明的正確性錯誤：定磅／WFA 賽仍用重磅當能力代理。
候選只在明確定磅（Set Weights、MDN-SW、Maiden Plate、WFA）時停用
handicap_weight_proxy，沿用現有無代理 fallback；未知條件不猜測。
此項按 evaluation contract §7 正確性修正審核，預先 cohort 為四個 field-size、
五個首選 SP、定磅場。任何顯著 primary／cohort regression 不上線。

## 賽前個案資料

- Bacetti：2026-09-02 00:25:50 UTC immutable snapshot，13:18 AEST 開跑前。
  模型第三，67.99；當時市場 $34，非賽後 SP。四場 PQ 樣本距離
  1630／1650／1800／1400m，最新正式賽 2026-04-01（相隔 154 日）。
  PQ 79.60；近績 59.90；人馬 65.12。
  試閘最近三次 4／4／5，無前三；同程 2:0-0-0。PQ 沒有日曆衰減或途程轉移。
- Ipswich R2 是 F&M MDN-SW 1200m、Soft 5、$40,000。模型卻使用
  「頂磅＝讓磅官評為能力最高」代理。58kg 與 55.5kg 的定磅差不可作此推論。
- 官方賽果 Bacetti 第五／九匹、輸 3.57L、SP $81；研訊只記三疊。
  不將「大幅離群」當成已核實的 Bacetti 終點事實。

官方來源：
[Racing Queensland 賽事條件](https://www.racingqueensland.com.au/racing/full-calendar/thoroughbred/meeting/ipsw/20260902/race/2)、
[Racing Australia 賽果](https://www.racingaustralia.horse/FreeFields/Results.aspx?Key=2026Sep02,QLD,Ipswich)、
[研訊報告](https://www.racingqueensland.com.au/racing/full-calendar/thoroughbred/meeting/ipsw/20260902/stewards-report)。

## 固定消融結果

同語料 1822 場／18216 匹，dev 1310、terminal 512（2026-08-18 至 09-01）。
sample hash `16bc9a24be537b2e598862a181bc41fb870658e8d9257d8005e3e642f331c9f7`。
baseline/candidate 同一 mapper；重播與真引擎的逐場 Gold／Good **全部一致**，
最大分差 0.009915（匯出兩位小數）；3873 匹 PQ 數值等於 consistency。

以下是干預相對 baseline 的百分點差，負數表示移除／改動後較差：

| 固定干預 | dev Gold | dev Good | terminal Gold | terminal Good |
|---|---:|---:|---:|---:|
| PQ 全部設 60 | -1.0703 | -0.9174 | -2.3438 | -0.9766 |
| PQ 偏離 60 減半 | 0 | -0.2294 | -0.3906 | +0.3906 |
| PQ 改用 consistency | -0.3058 | -1.2232 | -1.9531 | +0.3906 |

完全移除的 terminal Top-5 pairwise AUC 差為 -0.009380，95% CI
[-0.017234, -0.001155]。因此「整個指標只是噪音」不符合現有證據；但 PQ
含缺資料 fallback 和舊檔 recovery，不能把全部邊際貢獻當作純粹輸距／班次訊號。
三個干預都不符合 promotion，**沒有將失敗的縮分／刪除方案放入模型**。

PQ 的實際計法：最近四場完整正式賽，以 1／0.8／0.6／0.4 權重平均
`-min(20, 輸距) + 4*log10(獎金/50000)`，再按場內相對位置計分。
這是往績質素，不是今日適用性；未直接處理日曆陳舊度、轉途程或合成轉草地。
少於兩場完整資料則沿用 consistency，舊檔恢復的資料只以 10% reliability 融合。

## Bacetti 的影響拆解

以原始賽前特徵逐項設 60（其他項不變）：PQ 托高 ability 約 2.9109 分；
騎師 1.0800、練馬師 0.8730、人馬 1.2923，合共 3.2453；rating 0.7182。
全場 PQ 設 60 後，Bacetti 65.0845，**仍第三**。所以不能宣稱刪 PQ 能解決個案。
修正定磅識別後 rating 62.6833 → 60，總分約 67.28，仍第三；Stevie's Spirit
則由約 59.87 → 60.46。這項修正也**未解決 Bacetti 排名偏高的全部原因**。

## 正確性修正：Maiden Plate／SW 條件識別

舊 `_is_wfa_or_sw_race` 漏 Maiden Plate，並用 `"sw" in text`，會把 Ipswich／
Swifts 等贊助名稱當作定磅。改成明確詞界與條件別名；保留未知條件的原本處理。
共 160 場條件識別有變，1307 匹 rating／ability 有變。權重沒有重配。

- dev Gold／Good 都 0；terminal Gold +0.390625pp（2 場）、Good 0。
- terminal Gold 配對 CI [0, +0.9765625]pp；Good CI [0, 0]。
- 四個馬群大細、五個 baseline 首選 SP、條件改動 cohort，無 primary CI 全負。
- 正式表現判決仍是 `REJECT / ranking_evidence_too_weak`。
- **此項按合約 §7 作正確性修正，沒有通過表現閘，不是已證實的改善。**
  即使績效方向相反，也不應用年齡定磅推論 handicapper 能力排序；若顯著退步，
  應隔離問題和停止部署，而非保留錯誤的能力聲稱。11 個專項測試及 quick gate 通過。

Leakage：只讀目標場賽前 class title、既有 features／field weights，賽果只作 label。
當日兩匹個案不在鎖定語料內；賽前 $34 與賽後 SP $81 均未入分。SP 只作預先 cohort。

## 與其餘意見的關係

Sunburnt Country 的合成轉草地、Bacetti 的久休轉短途，都說明需要改善「舊表現
對今仗的適用程度」，不是把舊表現質素與今日能力畫等號。EXP-07 的直接縮減合成
PQ 候選曾令 dev Good 退步，未上線；本次也沒有因個案而搜尋新扣分。

已查 HKJC `_formline_strength_score`：對手質素與自己跑近程度分開，沒有 competitive
evidence 時封頂 60。AU EXP-07 已試同類保護，但整體仍未過閘。AU 已準備移除賽績線
中的近績重複、保存逐個對手後續日期／本駒名次輸距；純賽績線仍不直接入排名。
尤其 Bacetti 的較強對手線來自自身第八的往績，不能單憑碰過強手寫成可靠爭位優勢。

## 重現與發佈

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scratch/au_bacetti_quality_20260902.py --engine-root /tmp/au-feedback-main-final --data /tmp/au-matrix-feedback-after.json --out /tmp/au-bacetti-pq-evidence.json
PYTHONDONTWRITEBYTECODE=1 python3 scratch/au_set_weights_20260902.py --engine-root /tmp/au-feedback-main-final --data /tmp/au-matrix-feedback-after.json --out /tmp/au-set-weights-evidence.json
```

引擎 baseline 為 latest main `926eac54` 上 EXP-06 修正，三個評分來源逐 byte 等於
`fbf14998` 上同一修正。固定 data SHA256 和詳細 evidence 見同目錄
`EXP-20260902-08-pq-evidence.json`、`EXP-20260902-08-set-weight-evidence.json`。

公開 push 尚未完成：自動批准審查要求用戶明確授權公開模型 payload 到
`Kelvin1761/Kelvin-Agents`。不能把工作樹修正說成 main 或 automation 已啟用。
