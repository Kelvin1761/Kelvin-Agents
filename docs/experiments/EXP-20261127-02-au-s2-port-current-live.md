# EXP-20261127-02 S2 移植去現行 live —— C（S2 + 保留速度分 + pace_perf 權重 ×1.64）PASS；消融證實功勞係 S2 leaf

- 日期：2026-11-27　平台：AU　類型：候選（預先登記 `patches/au_s2_port_20261127/PROTOCOL.md`，commit `8f3a7987` 先過結果）
- 來源：S2 forward ship_eligible（EXP-20261127-01）。Kelvin 2026-11-27「要」。
- 語料：現行 live BASE dump（含 F1、速度分），4,260 場；baseline 用 `exact_score` 重算 40,938 匹 0 唔夾。A_sb 覆蓋 88.6%（30,015 場 Sportsbet 事件）。

## 預先登記 arm（對現行 live，log-loss v2，Holm 4）

| arm | Δlog-loss [95%] | Gold Δpp（下界） | Good Δpp（下界） | capture@5 | 頭二 | Holm | v2 |
|---|---|---|---|---|---|---|---|
| A S2＋速度分、現行權重 | −0.00023 [−0.00056, +0.00010] | −0.06 (−0.55) | +0.54 (−0.03) | −0.18 | −0.08 | 0.19 | REJECT |
| B S2 取代速度分、現行權重 | +0.00006 [−0.00037, +0.00049] | −0.28 | +0.25 | −0.12 | −0.03 | 0.60 | REJECT |
| **C S2＋速度分、pace_perf ×1.64** | **−0.00080 [−0.00103, −0.00060]** | +0.06 (−0.36) | +0.42 (−0.09) | +0.02 | −0.06 | **<0.001** | **PASS** |
| D S2 取代速度分、×1.64 | −0.00060 [−0.00091, −0.00033] | 0.00 (−0.40) | +0.48 (−0.20) | +0.14 | −0.03 | <0.001 | PASS |

## 消融（PASS 之後加；分開 S2 leaf、權重、速度分）

| 比較 | 量乜 | Δlog-loss [95%] | Gold | Good（下界） | v2 |
|---|---|---|---|---|---|
| E vs 現行 | 淨權重 ×1.64（冇 S2） | **+0.00042 [+0.00002, +0.00080]** | −0.31 | −0.42 (−0.99) | REJECT（有害，AUC 護欄唔過） |
| F vs 現行 | 淨權重 + 剷速度分 | +0.00063 | −0.23 | −0.51 | REJECT（有害） |
| **C vs E** | S2 leaf 邊際（保留速度分） | **−0.00122 [−0.00171, −0.00072]** | +0.37 | **+0.82 (+0.21)** | **PASS** |
| D vs F | S2 leaf 邊際（剷速度分） | −0.00123 [−0.00173, −0.00073] | +0.23 | +0.99 (+0.30) | PASS |
| **D vs C** | 有 S2 之下剷速度分 | **+0.00020 [+0.00002, +0.00040]** | −0.06 | +0.08 | REJECT（有害） |

## 讀法同揀法

1. 改善**全部嚟自 S2 leaf**（Good CI 下界都正）；淨加權重有害 —— S2 令 pace_perf 準咗，先值得更高權重（同 forward B1 0.177 一致）。
2. **速度分唔應該剷**：D vs C 直接比，剷咗 log-loss 顯著變差。S2（情境標準、mix 入 leaf）同速度分（場地×路程中位、最好 3 仗、overlay）
   同一來源但各有資訊。
3. **揀 C，偏離預先登記嘅 tie-break**：協議寫「取代版同保留版 CI 重疊就揀取代版」，但冇預計可以直接比較 D vs C；直接比較顯示
   唔係打和（D 顯著差）。揀 C 亦係保守做法（保留 live 已有組件）。偏離照實記錄。
4. 下一步：移植 C 入 live 引擎（S2 leaf + pace_perf 權重 ×1.6389），live code 全語料重現 PASS、Sol 覆核、forward 退回監察。

## 上線實作（Kelvin 2026-11-27「要」）

- 引擎：`au_racing_engine/sb_full_time.py`（S2 live 唯一計算位置；研究原版 scratch 檔保留做 S2 forward 凍結紀錄，live 唔 import）。
  `_score_features` 喺 R2 之後混 pace_figure；`dimensions.py` pace_perf 係數 0.0879 → 0.1441（× 0.177／0.108）。
  `WC_AU_S2_LIVE=0` 回退兩樣（process 開始時讀，launchd 重開即生效）。
- 事件表 `AU_SB_FullTime_Events.json.gz` 每晚建（`au_sb_full_time_table.py`，~26 秒，30,062 場），同速度參考表同一個 step。
- **冇表／冇 Formguide**：全場 z 0 照混（Sol 覆核：唔可以「唔混合但權重照乘」—— 即係 E arm 淨權重，有害）；
  每次評分先清走 Logic 殘留嘅舊 `sb_full_time`。
- live code 全語料重現（兩邊都有嘅 4,213 場）：Δlog-loss **−0.00082 [−0.00106, −0.00061]**、Gold +0.06、Good +0.46 —— 同研究 C 一致。
- golden：開 S2 先有變、`WC_AU_S2_LIVE=0` 120 匹全部一致；data contract 重新校準；模型說明重新生成。
- forward 退回監察 EXP-20261127-03（`au_s2_forward.py`，11-28 起，1,000 場，v2 尺；Gold 同 Good 都跌亦建議回退）。

## 已知限制（Sol 覆核，接受）

- going 用 race_context（研究用引擎輸出嘅 race_context going），少數場可能唔同；重現結果一致。
- 事件表包埋之後先抓嘅 Formguide 入面嘅舊賽事（事實資料，標準只用賽日之前）；同研究一樣。
- F1／速度分 forward 用 `exact_score` + 現行權重重算：11-25 → 11-27 嗰三日（S2 前）會用新權重重算，兩個 arm 同一套權重，比較仍然一致。
