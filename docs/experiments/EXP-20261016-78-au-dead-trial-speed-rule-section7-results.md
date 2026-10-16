# EXP-20261016-78 結果：剷走讀 `timing_trial_600m_avg_speed` 嘅死規則 —— §7 上線

- **預先登記**：[protocol](EXP-20261016-78-au-dead-trial-speed-rule-section7-protocol.md)（`e497990c`，量度之前）。
- **用戶決定**（2026-10-16）：當 §7 上線，寫明只影響 Racenet 年代舊存檔 15 場。

## 驗證（改動前 origin/main `3083316d` vs 改動後，`au_dump_engine_leaves.py` 全語料 32,448 匹）

| | 改變嘅馬 | 排名改變嘅場次 |
|---|---:|---:|
| 乾淨窗（2026-08-05 起，v3 判決用） | **0** | **0** |
| 08-05 之前（Racenet 年代存檔） | 199 | 15 |

## §7 條件

1. 錯處獨立證明：Sportsbet 冇逐駒 600m 分段（EXP-76：試閘行 0%、正式賽 `timing_600m_*` 0%），規則喺任何新場次都唔會觸發。✅
2. 乾淨窗逐位元相同 ✅（所以 v3 冇得、亦唔使跑）。
3. 全語料影響照寫：只喺 Racenet 年代存檔，15 場排名改變 ✅。
4. leakage：冇新資料 ✅。
5. **唔係改善**：live 同乾淨窗行為完全唔變；Racenet 年代存檔回放會同以前差 15 場。

golden 120 匹一致；data contract 重新 calibrate；模型說明重生。
