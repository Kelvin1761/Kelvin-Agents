# EXP-20261124-30 預先登記（2026-11-24，睇賽果之前寫）

- 來源：HKJC EXP-20261119-01 V2（同程上名全喺另一場地，上線）、EXP-20261117-06（轉場，上線）；Codex Sol 對照 AU 搵出未試。
- 語料：`au-rejudge-20261124/BASE.json`（main 4d76680f 前一版 + F1 = 現行 live 排名），2026-08-05 起。
- 特徵：`features.py`（只用今仗之前往績、唔計試閘；場地方向／人造地來自 `au_track_geometry.json` 同場地名）。
- Arm（Holm 家族 3）：V2、T1、T2；每個係 0/1 指標，場內置中，β walk-forward（`au_perf_rating/judge.fit`：每個賽日只用之前賽日，頭 20 日 β = 0）。
- 尺：AU log-loss 尺 v2（`au_logloss_ruler.evaluate` 預設）。PASS 先考慮上線，仲要過 Holm（bootstrap p）。
- 已知功效問題：T1 只有 103 匹（0.3%）—— 預期判唔到，照報。
- 唔會因結果改定義（±50m、頭三、方向來源都喺呢度定死）。
