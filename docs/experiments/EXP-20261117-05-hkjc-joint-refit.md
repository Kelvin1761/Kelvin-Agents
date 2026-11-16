# EXP-20261117-05 — HKJC：「有訊號但單獨入唔到分」嘅組件一齊 refit（線性 L2 ＋ GBM）—— 預先登記

- 日期：2026-11-17｜Kelvin「after all these updates, refit／ML test，factor in all the components that has signals but cannot add to scoring」
- 尺：HKJC 歷史回放尺 v4（`compare_v4_holm.py`）；Holm 家族 2（J1、J2）；dev 過先開 holdout。
- base = 現行 live = `v4/dist_D1.jsonl`（I1 事件報告 ＋ D1 大幅增程）。
- 寫於跑任何結果之前。

## 特徵（全部賽前；場內減場均）
| key | 定義 | 來源 | 之前結果 |
|---|---|---|---|
| ride_q | 上仗騎法被查詢／獲指示／告誡 | 事件報告 | dev +3.4、holdout +3.0；R1 REJECT（EXP-16-11） |
| wide2 | 上上仗走外疊、上仗冇 | 事件報告 | +2.1／+2.3；W2 REJECT（EXP-16-18） |
| blocked2 | 上仗或上上仗受阻 | 事件報告 | +1.1／+1.3（EXP-16-11） |
| slow | 上仗出閘慢 | 事件報告 | +1.8／+0.9 |
| rb_placed | 上仗入位＋評分 ≤ 贏馬分（唔降班） | 馬匹頁 | +4.3／+1.8（EXP-17-02） |
| rb_any | 評分 ≤ 贏馬分（唔降班） | 馬匹頁 | +1.9／−0.3 |
| drop_rb | 降班＋評分 ≤ 贏馬分 | 馬匹頁 | +5.3／+3.7 |
| old_won | 老馬（≥35 仗）上仗贏、非高班 | 馬匹頁 | −11.2／−9.7；C2 REJECT（EXP-15-15） |
| gear_off | 今仗比上仗少咗配備 | 馬匹頁配備欄 | +1.1／+0.8 |
| gear_on | 今仗戴咗之前從未戴過嘅配備 | 馬匹頁配備欄 | −1.3／−0.3 |
| dist_down | 今仗比上仗短 ≥400 米 | 馬匹頁 | +1.5／−0.2 |
| class_pos | 讓賽（三至五班）：(今仗評分 − 班頂)/10；其他 0 | 馬匹頁 | holdout −1.4pp／10 分（EXP-16-12） |
| backup10 | 距上仗 ≤10 日 | 馬匹頁 | 冇一致方向 |

## 候選（固定，唔調）
- **J1 線性 L2**：每季 walk-forward（2019/20 起只用之前季），logistic(入頭三 ~ raw 置中 ＋ 13 個特徵標準化)，L2 C = 0.1（raw 一齊收縮）；
  raw' = raw + Σ β_k·(f_k − 場均)，β = 特徵係數 ÷ raw 係數（同之前候選一樣換算）。
- **J2 GBM**：每季 walk-forward，`HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200, min_samples_leaf=200, l2_regularization=1.0)`，
  輸入 = raw 置中 ＋ 13 個特徵置中；raw' = logit(p̂)（v4 尺每季重新校準，所以尺度唔重要）。
- 判決：v4 規則（log-loss CI 上界 < 0、Gold／Good 下界 > −1pp、好過 95% null），Holm 2。過 dev 先開 holdout。
- 冇做：練馬師專屬 pattern（300 格，假陽性多）、分級賽專用模型（G2a 喺 forward）、報名表熱身（冇歷史數據）。

## 結果（跑完先寫）
J1 β（2026/27 walk-forward，raw）：ride_q +1.66、wide2 +1.03、blocked2 +0.77、slow +0.64、rb_placed +1.21、rb_any +0.29、drop_rb +2.68、
old_won −4.13、gear_off +0.76、gear_on −0.32、dist_down +0.09、class_pos −0.30／10 分、backup10 +0.20。逐季穩定（2021 起每個 β 方向唔變，slow 2020–21 例外）。

| 候選 | 窗 | Δlog-loss | AUC | Gold | Good | 頭二 | 判決 |
|---|---|---|---|---|---|---|---|
| **J1 線性** | dev | **−0.00062 [−0.00105,−0.00018]**（Holm p≈0.0015） | +0.0005 | +0.04 | +0.24 | −0.52 | PASS |
| J1 | holdout | **−0.00108 [−0.00164,−0.00050]**（p≈0） | **+0.0019 [+0.0001,+0.0036]** | +0.18 [−0.64,+1.00] | −0.29 **[−1.28,+0.65]** | +0.70 | **REJECT（Good 下界穿 −1pp 護欄）** |
| J1 | terminal（186 場） | −0.00125 [−0.00322,+0.00078] | +0.0002 | +1.08 | −0.54 | −1.61 | 參考 |
| J2 GBM | dev | +0.00048 [−0.00013,+0.00110] | −0.0003 | −0.04 | +0.72 | −0.40 | REJECT |

## 解讀
- 一齊加嘅效果係單獨任何一個嘅 ~6 倍（D1 單獨 holdout −0.00013；J1 −0.00108）：單獨細過閘門、一齊就量得到 —— 同 AU「閘門判唔到細 leaf」一致。
- 機率準咗好多（log-loss、AUC 兩個窗都顯著），但 Good 點估計 −0.29、CI 好闊，下界 −1.28 → 按預先登記規則 REJECT，唔救（唔改尺、唔改窗）。
- GBM 輸線性：同 AU「特徵集已飽和，ML 輸線性組合」一樣；資訊唔係非線性。
- 處理：J1 凍結做 forward shadow `joint_signals_shadow`（150 場，`patches/hkjc_arm_joint_signals_shadow.py`），Gold／Good／NDCG 全部 ≥ 0 → 建議入分，Kelvin 決定。
  live 特徵係近似（配備用排位表代碼、贏馬分用近 6 仗＋贏馬表）；事件報告表加咗 B（受阻）／S（出閘慢）旗（唔入分）。
