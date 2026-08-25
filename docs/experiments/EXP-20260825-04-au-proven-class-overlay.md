# EXP-20260825-04 高班次 × 當仗實際表現 overlay

- **日期**：2026-08-25
- **平台**：AU Wong Choi（Sportsbet-only）
- **baseline**：`origin/main@233b0512`
- **假設**：純班次容易高估「參加高班但大敗」的馬；只有將歷史班次同
  當仗實際表現乘合，才應當成高班實績證明。
- **決定**：**USER-ACCEPTED EXPERIMENTAL KEEP**。指標方向一致但 holdout
  bootstrap CI 跨零，未通過標準 promotion gate；用戶在了解不確定性後
  明確要求作 daily automation 的 experimental production signal。

## 鎖定公式

1. 將最近四場有 Sportsbet 原始班次、名次及馬數的正式賽映射成
   class level：G1 100、G2 92、G3 86、Listed 82、Open 78、HCP 72、
   BM n = n、CL/C n = 60 + 2n、Maiden 56。
2. `finish_quality = 1 - (place - 1) / (field_size - 1)`。
3. `raw = weighted_mean((class_level - 56) × finish_quality)`，衰減權重
   鎖定為 `1.0/0.8/0.6/0.4`。
4. 同場至少三駒有效馬才標準化；
   `proven_class_feature = 0.5 × field_z(raw)`。
5. 個馬缺班次／名次／馬數、或同場不足三駒有效數據，一律中性 0；
   不將 missing 當成低班或差表現。

公式在開 terminal holdout 前鎖定；沒有用 odds／SP，亦沒有以 Randwick
R1/R2 的賽果搜 threshold。

## 評估證據

同一份 point-in-time Sportsbet cache，共 **1,286 場**：

| 指標 | 結果 |
|---|---:|
| development 頭 5 場內 AUC | **+0.003050** |
| 連續時間 folds | **4/5 非負** |
| terminal holdout 頭 5 AUC | **+0.003005** |
| 95% paired bootstrap CI | **[-0.000662,+0.006798]** |
| 全樣本 Gold | **+0.78pp** |
| 全樣本 Good | **+0.23pp** |
| 頭馬在模型 Top 3 | **+0.31pp** |

點估計全部正數，但 holdout CI 下限低於 0，依
`docs/model-evaluation-contract.md` 標準決定規則本應 **REJECT**。今次 KEEP 是
明文用戶 override，不是修改把尺，亦不可宣稱「已證明改善」。

## Randwick R2 replay

生產引擎同離線 A/B 逐駒完全對齊：

| 馬 | ability 調整 |
|---|---:|
| Lovecats | **+0.4766** |
| Dee Dee Express | +0.1374 |
| Zubba Storm | **-0.2680** |

方向符合用戶對 R2 的診斷，但幅度不足以改變三駒的 baseline 次序。
所以它不是 R2 的事後特例修正。

## Archive 限制與 forward monitoring

舊 archive Facts 在 exact-class transport 落地前沒有保存原始班次，所以最新
engine dump 中 16,062 匹舊 runner 的 `proven_class` 都是中性 0。這是資料不存在，
不是特徵沒有作用。Daily automation 由新抽取的 Sportsbet 班次開始才會
正常啟動；後續要向前追蹤覆蓋、分佈、Gold/Good 及 winner Top 3，不可
用舊 archive 的全 0 結果當成成功回測。

## 實作與驗證

- live scorer、renderer、validation、dump/eval/refit 都同步包含
  `proven_class_feature`，避免 live 有訊號但離線評估靜默漏掉。
- 專門單元測試鎖定 exact-class 語義、高班大敗不加分、missing neutral、
  少於三駒不啟動及 canonical evaluators 公式對齊。
- AU golden 舊樣本預期全部不變，因為它們沒有 exact-class evidence；不重錄
  因 archive 新增會期而漂移的抽樣名單。
