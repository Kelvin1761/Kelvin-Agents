# EXP-20261016-87 — HKJC 分場地／途程歷史差

- 平台：HKJC；日期：2026-10-16。
- 假設：分場地／途程歷史差可取代原有絕對檔位分組。
- 舊記錄：EXP-20261007-01、EXP-20261010-09/13、EXP-20260928-01；新來源是逐日截斷的 rail-tagged results，不重試靜態官方表 raw-rate。
- baseline：`2d7ec14c09a3d6fa0bc5733406a730f7dff344ff`；候選公式見審計 PROTOCOL.md。
- mode：walk_forward_oos；325 場／33 賽日，2026-04-19 至 2026-10-07。逐日只用之前資料，沒有 holdout 擇參。
- 統計篩查：**REJECT / primary_regression**。完整數字、CI、六時間塊、Holm、cohort 見 [審計](../audits/hkjc-draw-review-20261016/README.md) 及 results.json。

| Primary | 場數差 | 配對賽日 bootstrap 95% CI（pp） | Holm p |
|---|---:|---:|---:|
| gold | -4 | [-3.74, +1.54] | 1.0000 |
| good_positional | -6 | [-5.15, +1.26] | 1.0000 |

- 失敗形狀：沙田 Gold −3、Good −7；跑馬地 Gold −2、Good 不變。泥地 +1/+1 只得 15 場，不足以作獨立選擇。
- leakage-audit：FLAG（歷史 artifact 可用時間及訓練 FieldSize 分母尚未認證）。沒有 production promotion。
- golden／data_contract：production 沒有改動；檢查.sh 覆核，不覆蓋 snapshot。
- 決定：不作 production promotion。沒有證據證明現行公式全域最佳，亦沒有依本輪結果追加搜索。
- 重跑命令、數據路徑及來源 SHA256：見審計 README.md／results.json。個別判決原因以上述統計篩查為準；唔可推論檔位資訊無效。
