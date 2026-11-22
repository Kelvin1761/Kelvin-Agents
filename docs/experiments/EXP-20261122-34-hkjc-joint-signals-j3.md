# EXP-20261122-34 — HKJC：聯合訊號 J3（J1 13 項 ＋ 同程 4 項）—— v5.1 dev／holdout PASS；Kelvin 決定暫時唔上（頭二冇改善）

- 日期：2026-11-22｜Kelvin：「做護欄檢討，之後 J1 加埋同程一齊入」
- 協議（寫喺跑之前）：`patches/hkjc_distance/build_joint_plus.py` docstring。尺：v5.1（EXP-20261122-33）。家族 1。
- 特徵：EXP-20261117-05 J1 嘅 13 個 ＋ sd_worse（EXP-31 R1）、sd_hicls／sd_locls（EXP-32 K2）、sd_rate（EXP-20261118-05 S1）。
  做法同 J1 一樣：線性 L2 C=0.1、每季 walk-forward、場內置中。
- **披露**：J1 嘅 holdout 喺 EXP-20261117-05 睇過（舊護欄判死）。J3 係新家族（特徵、base、尺都唔同），但 13 個特徵重疊。J3 holdout 連**舊護欄都過**，結論唔靠護欄改動。

## 結果（base = base_venue_age）
| 窗 | Δlog-loss | 場內 AUC | Gold | Good | v5.1 | 舊護欄 |
|---|---|---|---|---|---|---|
| dev | −0.00103 [−0.00162,−0.00043] | +0.0017 [−0.0001,+0.0036] | +0.24 | −0.12 [−0.96,+0.77] | PASS | ✅ |
| **holdout** | **−0.00152 [−0.00227,−0.00075]** | **+0.0032 [+0.0010,+0.0054]** | +0.64 [−0.41,+1.65] | +0.99 [−0.18,+2.05] | **PASS** | ✅ |
J1（同一做法、冇同程 4 項）dev −0.00062 → 同程 4 項加咗大約七成。

## live base 重 fit（上線用）
期間另一個 session 上咗 X1 連續藉口（EXP-20261119-06）同薄證據收窄（EXP-20261119-05）。重建 `v4/cons/base_live_20261122.jsonl`
（= base_venue_age ＋ X1 ＋ S1 收窄），喺上面重 fit J3：dev −0.00100 [−0.00159,−0.00040]（v5.1 PASS），β 同之前差 ≤0.1 → 同 X1 冇重複計數。holdout 冇再開。
β（raw，2026/27）：ride_q +1.65、wide2 +0.95、blocked2 +0.66、slow +0.63、rb_placed +1.13、rb_any +0.47、drop_rb +2.89、old_won −3.62、
gear_off +0.75、gear_on −0.41、dist_down +0.39、class_pos −0.54／10 分、backup10 +0.20、sd_worse −2.51、sd_hicls +0.56、sd_locls −0.91、sd_rate +1.44。

## 實作（已寫，未上線）
引擎 code 喺分支 `claude-hkjc-joint-signals-j3-20261123`（efcb3b85，**冇入 main**）：`hkjc_racing_engine/joint_signals.py`（薄證據收窄之後）、
validation、manifest、chip 升級（已有 chip 嘅概念變「已入分」）、forward 退回監察 `joint_signals_post_live`。
live 定義同 J1 forward shadow 一樣；同程四項用 `_data.hk_history`；班次編碼同回放一模一樣（第一版漏咗 G1／4R 當最高，11-22 三場二級賽令
「只喺低班上名」live 17% vs 回放 6%，已修）。觸發率（11-22 live vs 2025/26 回放）大部分對得上；近似差異：評分跌返 5%／15%、除去配備 10%／25%。

## 點解唔上（Kelvin 2026-11-23）
11-22 沙田副本：J3 令 R2 飛來霸（第 3）、R6 紫荊傳令（贏）跌出頭二；頭二入面入頭三嘅馬舊 14 → 新 11（頭四都係 21）。
回放成批量（`patches/hkjc_samedist_record/top2_swap.py`、`top2_by_feature.py`）：
- dev 3,323 場，J3 改咗頭二 727 場（22%）：推上頭二 736 匹入頭三 38.2%，擠出 38.5% → **頭二擲毫**；頭二選有中 dev −0.60、holdout +0.23。
- 按主導訊號分：藉口類 dev −6.3pp／holdout +13.1pp（方向相反＝雜訊）；評分跌返 +6.2／0.0；同程 +0.4／+6.2；
  老馬贏後 −6.5／−7.7（唯一兩窗一致：擠出嘅老贏馬跑得好過頂上嗰匹 → −3.62 對有實力爭頭二嘅馬可能扣太重；72 對，未夠證據）。
- 即係 J3 嘅改善喺第 3 名之後同機率校準，頭二冇幫助。Kelvin 最睇重頭二 → 唔上；方向繼續研究（點樣令聯合訊號幫到頭二）。
- 冇登記 forward shadow；J1／form_patterns shadow 照舊行。
