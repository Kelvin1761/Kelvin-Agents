# EXP-20261016-85 — HKJC 最新code下既定walk-forward權重refit可贏現役

- 日期：2026-10-16；平台：HKJC。
- 假設：最新code下既定walk-forward權重refit可贏現役。
- baseline：dd22b05d；最新production重播、PIT騎練。
- 語料：2026-04-12至2026-10-07，325場／33賽日／4,101次出賽；baseline Gold44、Good81。
- 搜索過：EXP-20261010-05/06、EXP-20261015-02、九維審計、docs/experiments相關form／consistency記錄。
- 工具與候選：docs/audits/hkjc-formula-review-20261016/PROTOCOL.md；無效名次另有INVALID_STATUS_PROTOCOL.md。
- 評估：固定規則全紀錄；ML用只向前walk-forward。無開2026-10-11起賽果；無調閾值／換指標。
- 95% CI：賽日bootstrap2000；六時間塊；五個stability arm共一家族Holm調整；有部件預算／CI半寬。

## 結論

**REJECT：Gold少4場，Good少6場，維持九維權重。**

詳細CI、分層、來源限制、命令、dataset hash：[審查報告](../audits/hkjc-formula-review-20261016/README.md)、[機讀結果](../audits/hkjc-formula-review-20261016/results.json)。
本次候選唔因單一cohort或點估計而上線。原先五個規則候選model code無合入production。
0名次屬獨立正確性修正：scoped leakage PASS（只刪無效歷史，無新資訊）；全部primary逐場無變，SP五桶亦無變。
全archive歷史衍生欄位仍有provenance FLAG，唔用本輪診斷宣稱全模型無洩漏。
Golden保留原snapshot且一致；data_contract重新calibrate，完整檢查另行記錄。
狀態：研究與證據已記錄；只有0名次解析及模型說明修正準備交付。commit由保存流程記錄。
