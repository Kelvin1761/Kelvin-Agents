# EXP-20261121-33 結果：AU 生涯同程往績入分 —— **REJECT（三個 arm）**；路程分改用生涯同程紀錄（純顯示）

協議：`EXP-20261121-33-au-same-distance-record-protocol.md`（D3 係睇完 D1／D2 之後補登記，三個一齊 Holm）。
命令：`patches/au_same_distance/features.py` → `arms.py BASE.json features.json OUT`；3,736 場，v3 `walk_forward_oos`，新尺（EXP-20261121-32）。

| arm | 特徵 | β 中位 | Gold Δpp [CI] | Good Δpp [CI] | 判決 |
|---|---|---:|---|---|---|
| D1 | 生涯同程收縮上名率 | 11.1 | +0.03 [−0.47, +0.48] | +0.19 [−0.42, +0.78] | REJECT `ranking_evidence_too_weak` |
| D2 | 同場同程 | 15.1 | −0.05 [−0.47, +0.34] | +0.08 [−0.47, +0.58] | REJECT `primary_regression` |
| D3（補）| 生涯同程，頭馬計兩次 | 5.8 | +0.05 [−0.32, +0.39] | +0.19 [−0.25, +0.65] | REJECT `ranking_metric_harm`（頭三上名率 −0.31 [−0.58, −0.05]） |

Holm（6 個 primary p 值）：全部 1.0。Ranking 細節：`EXP-20261121-33-evidence/summary.json`；每日 β：`D*.betas.json`。

## 點讀

- 分層差距真（模型名次層內 +1.3–1.7pp），但入排名打和：同程上名同近績、場地、評分重疊，模型已經經其他維度捉咗。
  同 [[au-cohort-gap-is-not-a-gain]]、EXP-20260901-03 一樣嘅形狀；呢次係乾淨 point-in-time 語料（3,736 場 vs 舊 1,804）、生涯紀錄（唔係往績表截斷）、新尺，照樣唔過。
- D2（同場同程，HKJC 上線嗰個）喺 AU 冇用：AU 場地多、同場同程樣本薄。
- Kembla R7：就算 D1 上線，Earn To Burn（同程上名率 4/7）同 Fire Star（3/4）嘅差都只係約 −0.6 分，唔會調轉 2.8 分差距；
  調轉嘅主因係騎練（King 66 vs McEvoy 57，×0.84）同 L600。

## 上咗線嘅（純顯示，零排名影響）

- 路程分（參考分）同首本路程標籤統一用 `track_going.same_distance`（生涯 `同程:`）—— 之前路程分讀往績表見到嗰幾仗，
  同標籤打交（Fire Star 生涯 4戰3上名，往績表 ≤1100m 只見 1 場 →「今仗 ❌」）。
- 路程分 = 60 + 40 ×（(上名 + 1.2) ÷ (出賽 + 4) − 0.30）；未跑過 55；冇完整紀錄 60。
- 驗證：AU golden 120 匹一致；Kembla 11-21 十場 120 匹 main vs 改動版排名同綜合分完全一樣，路程分 117 匹變。
