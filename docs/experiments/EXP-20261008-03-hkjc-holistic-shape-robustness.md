# EXP-20261008-03 — HKJC holistic race-shape robustness

- **日期**：2026-10-08
- **平台**：HKJC
- **狀態**：USER-ACCEPTED EXPERIMENTAL LIVE — Stage 4 原判保留；用戶接受一場 Gold 噪音換整體排序與穩定性
- **假設**：race-shape 27.37% 過重，尤其極端 shape 分會令每日一兩匹馬被高估／低估。
  應對全場每匹馬使用同一條公式，量度減權收益與 Gold 成本；不鎖名次、不只修
  Top-5 邊界、不利用結果決定誰可調整。
- **撤回設計**：原定 Top-2 lock／rank 3–8 rerank 因會人為保護 Good／Champion，
  在 evaluation 前撤回，未運行、不可作 production 證據。

## Existing evidence being extended

- EXP-20260928-08：全場 shape 降至 14% 時 Capture@5 +2.07pp、Recall +1.93pp、
  NDCG +1.21pp，但少 5 場 Gold；連 26% 都少 1 場 Gold。
- EXP-20260928-09：shape→stability 2pp，Capture +0.97pp、Recall +0.75pp，但少
  1 場 Gold、只有 2/5 folds primary 非負。
- 新實驗用目前 340 場語料與現役完整公式，並加入「保留一般 shape 訊號、只壓極端
  deviation」的 robust family；呢個機制直接對應逐日一兩匹離群錯排。

## Baseline and leakage

- commit：`c89a2f09e79c559de512845a22608073ac06c705`；
- baseline = `current_live_recomputed_ability`；
- 所有候選對全場全部 runner 生效，初出馬亦無排名保護；
- 只用 pre-race production matrix，同場中位數亦只由今場賽前分數計算；
- 不用賠率、市場 rank、賽果、incident 或未來資料；結果只作 evaluation join。

## Locked candidate families

### A. Global deweight／reallocation

1. `shape26_core`：shape 27.37% → 26%，差額按 horse-core 現役比例分配。
2. `shape24_core`：shape → 24%，差額按 horse-core 比例分配。
3. `shape20_core`：shape → 20%，差額按 horse-core 比例分配。
4. `shape24_stability`：shape → 24%，差額全交 stability。
5. `shape24_proportional`：shape → 24%，差額按其餘六維現役比例分配。

`horse-core = sectional + stability + class_advantage + form_line`。

### B. Robust race-shape contribution

外層權重保持 27.37%，只將每匹馬 `matrix_race_shape` 對同場中位數的 deviation 作
統一 robustification：

1. `shape_winsor12`：deviation 封頂 ±12。
2. `shape_winsor10`：deviation 封頂 ±10。
3. `shape_winsor8`：deviation 封頂 ±8。
4. `shape_huber8_half`：首 ±8 原值，超出部分只保留 50%。

呢個 family 唔知道現役 rank 或結果，只係防止一個 27.37% 維度以離群幅度支配總分。

## Locked selection

- 日期排序；最後 15% 日期 terminal，只可在 development 揀定一個候選後開一次；
- development Gold／Good 不得回歸，至少 3/5 chronological blocks primary 非負；
- Capture@5／Recall@5／NDCG@5 至少兩個正；
- 漏出 Top-5 實際前三與 model Top-5 跑第 8+ 不得惡化超過 0.01 匹／場；
- meeting Top-5 hits SD 不得上升，complete-capture SD 最多 +0.005；
- 合資格者選三個 ranking delta 總和最大；同分選平均絕對改分較小者；
- terminal Gold／Good 不回歸、至少一個 ranking metric 正、tail 與 volatility 過閘，
  並仍須 Stage 4 通過才可接 production。

沙田／跑馬地 development 與 terminal 分開報，但 selection 不做 venue-specific override。

## 結果

### 全面減權的收益／成本

| Candidate | Gold | Good | Capture@5 | Recall@5 | NDCG@5 | Top-5 hits SD |
|---|---:|---:|---:|---:|---:|---:|
| shape 26% → core | −0.36pp | +0.71pp | +0.71pp | +0.52pp | +0.00349 | −0.0154 |
| shape 24% → core | +0.36pp | −0.36pp | +0.48pp | +0.20pp | +0.00437 | −0.0301 |
| shape 20% → core | 0.00pp | +1.79pp | +2.02pp | +0.95pp | +0.01326 | −0.0099 |
| shape 24% → stability | +0.36pp | −0.71pp | +1.07pp | +0.55pp | +0.00389 | −0.0232 |
| shape 24% proportional | +0.36pp | −1.07pp | +0.83pp | +0.54pp | +0.00505 | −0.0325 |

數字確認 race-shape 減權幾乎單調改善 smooth ranking，但 Gold／Good 在不同日期與
分配方法間換位；並非將差額交去某一維就可以消除 trade-off。shape 20% 平均改善
最大，但只有 2/5 時段同時守住 Gold／Good，穩定性不足。

### Robust family

預先規則選中 `shape_winsor10`：不改 27.37% 外層權重，只把 shape 相對同場中位的
極端 deviation 封頂 ±10。

| 指標 | Development 280場 | Terminal 60場 | 全340場 |
|---|---:|---:|---:|
| Gold | +0.36pp | **−1.67pp（少1場）** | 0.00pp |
| Good | 0.00pp | 0.00pp | 0.00pp |
| Champion | +0.36pp | +1.67pp | +0.59pp |
| Capture@5 | +0.83pp | +1.67pp | +0.98pp |
| Recall@5 | +0.21pp | +0.83pp | +0.32pp |
| NDCG@5 | +0.00435 | +0.01624 | +0.00645 |

全 34 meeting Top-5 hits 平均 1.8229 → 1.8527，SD 0.3006 → 0.2896（−3.6%）；
完整 capture SD 0.1665 → 0.1633。terminal Gold 損失集中沙田：沙田 −1/43，
跑馬地 0/17；跑馬地 terminal Capture +3.92pp、NDCG +0.02538。

## 決定

**正式排名 REJECT。** 儘管全樣本 Gold 打和、排序與逐日波幅全面改善，terminal 的
一場 Gold 回歸觸發 Stage 4 `primary_regression`，不可聲稱已達 mainline 改善。

`shape_winsor10` 是目前最有機制根據、最接近解決每日一兩匹離群錯排的 holistic
候選；cap、方向、venue 均固定，不准再按已見 terminal 調參。

## 2026-10-08 explicit user decision

用戶明確裁定 terminal 少一場 Gold 可視為噪音，優先採用全 340 場 Gold 打和、Good
打和、Champion／Capture／Recall／NDCG 全升，以及 meeting volatility 下降的整體
證據。依此將 `shape_winsor10` 以 **user-accepted experimental live** 接正式排名；
不是改寫 Stage 4 判決，原 `primary_regression` 照錄，亦不聲稱無條件通過合約。

安全措施：

- env `WC_HKJC_RACE_SHAPE_ROBUSTNESS=legacy_unbounded` 可即時回退；
- 每次 prediction 同時保存 `race_shape_legacy_unbounded` immutable rollback shadow；
- forward 最少 80 active races 後，舊公式若淨贏至少 2 場 Gold 或 Good、另一 primary
  非負，monitor 出 `recommend_rollback`；不會靜靜自動改 production release；
- 修正所有 weight/race-shape shadow 過往漏帶獨立 distance adjustment 的 correctness
  問題，確保往後比較只差候選本身。
