# EXP-20261027-05 — Tennis：固定短賠熱門假設嘅盈利可行性覆核

- 日期：2026-10-27；開始先登記，未讀本次分組輸贏。
- 平台：Tennis；只量度，唔改正式模型／下注規則。
- 假設：EXP-20260826-09 留待驗證嘅 `odds <= 1.6` 群體，在新增賽前紀錄下，對市場仍有可重現增量，值得獨立前向研究。
- 已搜舊記錄：EXP-20260826-09、EXP-20261009-01、EXP-20261026-03/04/05、performance-audit-2026-08-21。唔重試已否決 Platt、任意 shrink、WTA fresh-history 接線或 market-residual 擬合。
- Baseline source：`97eaa7f902747ace9fea28144c18ff35c36c78da`；正式 Tennis 修正 `063c8799e71098775c8f8284ca6dd1a7fee8cbdc`。

## 固定方法（睇結果前鎖定）

- Primary cohort 沿用全 tour、所選球員 opening odds `<=1.6`，唔掃 1.4/1.8/2.0，唔改 2026-07-15 原 walk-forward 分界。
- 只用保存嘅 forecast，唔用今日 history 重算。用現有 `prematch_outcomes`／`earliest_match_odds`：一場最早有效賽前 forecast、一對 `MIN(id)` 開盤價、單一同意 outcome；排除 disputed／mock、無法證明時間嘅紀錄。另用嚴格 aware-clock 分類檢查。
- 舊 `measure_short_favourites._load` 用 latest forecast、冇完整時間／結果一致性閘，唔將其舊漂亮數字當有效 baseline。今次係獨立診斷，唔修改舊 harness、ruler 或 live code。
- 報模型及去水市場 LL／Brier，paired bootstrap by **match**，4,000 次、seed 20260826、95% CI；600 floor、power、calibration、CLV、ROI 門檻不變。
- 盈利對照以同一 eligible universe、每筆 1u：baseline=保存嘅 `decision=BET`，candidate=同一政策再加 `odds<=1.6`；同時報筆數、P/L、ROI、drawdown及配對 P/L 差，唔靠少下注或只報百分比隱藏代價。EV>0 pool只作描述，唔揀最好政策。
- Opening quote 早於 forecast 唔等於仍可取得。額外報 10 分鐘（現行 config default）內、保存 odds 相符嘅 execution-timing-compatible subset，同 frozen fixture identity、later pre-start quote coverage；呢啲係可用性診斷，唔取代 primary cohort或改門檻。
- 此批係 legacy stored forecasts／mixed code regimes，唔宣稱 post-repair untouched OOS，亦唔用新資料更改模型或挑 subgroup。即使方向正亦只可 NEEDS MORE TESTING，正式 promotion 要獨立前向證據。

## 語料及重現

先跑 Central `corpus-audit --domain tennis --active-sqlite ...`。檢查未過唔用縮細語料代替。研究投影完整保留所有需要嘅 tables／rows，不篩選 outcome；原 live DB 唯讀，模型權重及真實注單不動。投影小於 1GB，附 manifest、snapshot time、row counts、hash及命令。大於 1GB 改用已掛載外置 scratch。

## 結果

原 live DB corpus-audit：ok；4 份已登記 snapshot 完整性／watermark 核對通過。完整投影 223,174,656 bytes，SHA256 `b4fa1d2af45480f567e5e36a47bb52a2f1b7adaf15f6111fd35db3286d910aa7`。窗口 2026-05-10..2026-10-26；3774 個一致結果賽前 forecasts，首價時間不足／賽後 282 場排除，剩 3492 個獨立 fixture。

短賠模型 vs 市場：n269（未達600）；LL 0.673798 vs 0.631212，模型−市場差 +0.042586，95% CI [+0.016498,+0.070020]；Brier 0.235902 vs 0.220885。

| 紙上原卡BET、平注1u | baseline | 再加短賠過濾 |
|---|---:|---:|
| 筆數 | 257 | 35 |
| P/L | −43.037u | −8.602u |
| ROI | −16.75%，CI [−30.24%,−2.67%] | −24.58%，CI [−48.37%,−1.84%] |
| 以開賽次序估drawdown | −48.527u | −13.345u |

少下注減少咗總損失，但每注 ROI 更差；整個 eligible universe 嘅配對 P/L 差 CI 跨零，唔係可驗證盈利改善。原 07-15 分界唔改：before n7、after n262；post-registration 描述 n220 亦落後市場，唔揀另一窗救結果。

3481/3492 個 opening quote 符合10分鐘／保存價一致診斷，但全部缺新 fixture frozen identity；later pre-start quote 只覆蓋450場。原卡257單有42單後續賽前價；本地 `prop_live_bets` 記錄0，唔係實盤盈利。未補造古老 pricing receipts。

**研究判決：NEEDS MORE TESTING／不足原定樣本及PIT完整證據。部署決定：不採用短賠收窄策略。** 不調門檻，不擴新家庭，不把舊數字混成新修正版表現。

初始 protocol hash／UTC lock、全部 paired rows、manifest、輸出及命令留外置 scratch；只保存濃縮結果到main。

## 重現及保存

研究程式只在 `codex-tennis-profit-research-20261027`，commit `61902276459403df6a6576800fac51b75976d986`；未合併main或部署。Python3.9.6／NumPy2.0.2。以下在該commit嘅研究checkout執行：

```bash
PYTHONDONTWRITEBYTECODE=1 /Users/imac/Antigravity-repo/tennis-wong-choi/.venv/bin/python \
  docs/audits/support/tennis-profit-feasibility-20261027.py \
  --db "/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-profit-20261027/tennis-profit-corpus-20261027.db" \
  --output /private/tmp/tennis-profit-rerun.json
```

原始結果、事前protocol內容／hash／UTC lock、v1原始程式與所有paired rows見上述外置目錄及artifact_manifest.json。正式權重／下注規則未改。
