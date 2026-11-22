# EXP-20261122-34 — HKJC：聯合訊號 J3（J1 13 項 ＋ 同程 4 項）—— v5.1 dev／holdout PASS，上線

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

## 上線
- `hkjc_racing_engine/joint_signals.py`（薄證據收窄之後、grade／排名之前；validation SCORE-004、後置組件 manifest、grade_transparency「聯合訊號」行）。
- live 定義同 J1 forward shadow 一樣；同程四項用 `_data.hk_history`。班次編碼同回放一模一樣（非數字班次 G1／4R／GRIFFIN 當最高）——
  第一版漏咗，11-22 有 3 場二級賽令「只喺低班上名」live 17% vs 回放 6%，已修（修後 6%）。
- 觸發率（11-22 live vs 2025/26 回放）：騎法被查詢 6%／6%、受阻 18%／17%、出閘慢 8%／7.5%、班內位置 76%／82%、只喺低班上名 6%／6%；
  近似差異（已知，同 J1 shadow 一樣）：評分跌返 5%／15%、除去配備 10%／25%、走外疊上上仗 3%／7%、同程高班 7%／13%。
- 11-22 沙田副本重算：131 匹 45 匹排名郁、5 場頭四變；遨遊氣泡 7→4、天將龍駒 6→5、極上紗瓏 5→2。
- Dashboard：已有 chip 嘅概念（老馬贏後、降班＋評分跌返、評分跌返、騎法被查詢、上上仗走外疊、除去／首次配備、相隔再出、首本路程）直接升級做「已入分」＋影響；
  冇 chip 嘅（近兩仗受阻、出閘慢、大幅減程、評分喺班內位置、同程三項）另出一個（|影響| ≥ 0.3）。一樣嘢一個 chip。
- forward：`joint_signals_post_live`（退回監察，60 場）；`joint_signals_shadow`、`joint_signals_lean_shadow`、`form_patterns_shadow` 標 decided（被取代）。
