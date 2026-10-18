# EXP-20261018-04 — 騎練調整項死咗要識報警 ＋ 統計生成器寫整數路程

- **日期**：2026-10-18；平台：HKJC；**監控 + 生成器修正**（唔改評分）
- **觸發**：EXP-20261018-02 —— 騎師同程／練馬師同程 live 由 2026-10-07 起每匹馬都消失四個賽日，冇任何警報

## 1. 生成器：Distance 寫整數

`build_comprehensive_stats.build_all`：`dist_rows` 有 NaN 就成欄變 float，CSV 寫 `1200.0`。而家先 `to_numeric`、
剔走冇路程嘅行，再轉 `int`。`test_build_comprehensive_stats_seasons` 加咗「CSV 文字係 `1200` 唔係 `1200.0`」——
**改之前呢個 test 會失敗，改之後通過**。loader（`1528d16e`）已經對兩種格式穩陣，呢度係根治。

另外發現（未修）：`build_all("26_27", extend=False)` 會喺 `build_change_priors` 因為 `Odds` 係 object dtype 爆；
排程用 `extend=True`，今日 13:36 照常重建，所以唔影響生產。

## 2. 監控：`field_health` 新來源「騎練調整項」

- `field_health.py` 逐週記錄 HKJC 每個加減項（人馬歷史、騎練組合、騎師同程、練馬師同程、換騎）帶住嘅馬匹比例
  （`python_auto.trainer_signal_detail.adjustments`，±0 都計）。0 次都寫一行，所以係「死」唔係「消失」。
- 判斷沿用結果 CSV 嗰套：出現率 ≤1% 而以前曾經 ≥30% → 💀；比前 4 週中位數跌 ≥20pp → 📉。門檻 100 匹（單日週都判到）。
- HKJC 每週 review（`hkjc_daily_schedule.field_health_section`）已經叫 `record` + digest，唔使另外接線。
- 測試：`tests/test_field_health_adjustments.py`（重演 W35 同程兩項死咗、健康週安靜、AU 唔寫呢個來源）。

## 回放真數據（scratch ledger，2026-07 起）

| 週 | 騎師同程出現率 | 換騎出現率 |
|---|---:|---:|
| W36 → W40 | 99–100% | 54–63% |
| **W41**（10-07、10-11） | **0%** | 27% |
| W42（10-14） | 0% | 49% |

`--trend --week 2026-W41` 會出：

```
💀 [騎練調整項] 練馬師同程: 出現率 0%，以前最高 100%（今週新出現）
💀 [騎練調整項] 騎師同程: 出現率 0%，以前最高 100%（今週新出現）
📉 [騎練調整項] 換騎: 出現率 27%，前 4 週中位數 57%
📉 [騎練調整項] 騎練組合: 出現率 50%，前 4 週中位數 94%
```

即係**大約 10-13 嗰份每週 review 就會報**，比人手發現早五日、兩個賽日。
W41 嘅換騎／組合下跌係 10-07 個別賽日（組合 0、換騎少）；10-11 已經回復，原因未查。
W27（7 月初）全部 0 係 `trainer_signal_detail` 未上線（07-09），因為以前從未 ≥30%，唔會誤報。
