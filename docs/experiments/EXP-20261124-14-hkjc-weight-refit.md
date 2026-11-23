# EXP-20261124-14 — HKJC：成套維度權重重新 fit（表現數字 base）—— REJECT，S 版權重維持

- 日期：2026-11-24｜Kelvin：「個 model 仲有冇嘢 refine」→ go ahead。協議 `patches/hkjc_distance/build_weight_refit.py`（寫喺跑之前）。
- base：全面重測 base（main 13e6454a 回放：表現數字＋初出馬；未含直路／返首本 —— 兩樣只影響少數馬）。
- 重 fit（非初出馬）：stability、trainer_signal、race_shape、horse_health、form_line、class_advantage；walk-forward，L2 C=0.1。

每季新權重（2021→2026）：stability 0.18→0.19（現 0.245）、trainer_signal 0.48→0.41（現 0.330）、race_shape ~0.19（現 0.193）、
health 0.05→0.08（現 0.034）、form_line ~0.07（現 0.070）、class_advantage −0.05→−0.08（現 0）。

| 窗 | Δlog-loss | AUC | Gold | Good | 頭二 PL | 頭二入頭三 | 首選贏 | v5.2 |
|---|---|---|---|---|---|---|---|---|
| dev | +0.00002 [−0.00054,+0.00063] | +0.0007 | +0.56 | +0.08 | −0.0009 | 0 | +3 | REJECT |
| holdout | **+0.00071 [+0.00015,+0.00129]** | −0.0013 | −0.29 | +0.18 | +0.0009 | −13 | −3 | REJECT |

結論：新權重喺 holdout 顯著變差 → S 版維持。class_advantage 每季負（讓磅賽高評分喺其他因素之外略差，同「讓磅官補償過頭」一致），唔入分。
