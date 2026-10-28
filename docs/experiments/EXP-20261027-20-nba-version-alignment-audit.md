# EXP-20261027-20 NBA 版本一致性審計同修正（ROI、dashboard、投注卡）

- **日期**：2026-10-27（Claude Code，用戶喺 Telegram 見到唔一致之後要求審計）
- **性質**：審計加報告層修正；冇改任何機率、揀腿或者判決規則。

## 1. 審計：而家有幾多個「版本」

| 版本 | 揀法 | 出現喺邊 |
|---|---|---|
| 正式 combo 1（穩膽） | `select_combo_1`，有單腿 edge 閘同組合 EV 閘 | dashboard 正式 BET、Telegram 投注卡；大部分日子係 NO BET |
| steady 穩膽候選 | `banker_shadow_review`，即 B2：冇 EV 閘、真價 ≥2.0 | dashboard tracking（每場第一個發佈）、latest analysis 卡；**用戶實際跟呢個落注** |
| B0／B1／B2 shadow | EXP-20261024-02 嘅 EV 閘消融 | 舊 Telegram「穩膽 EV 影子比較」，同 reports JSON |
| 舊組合 2、3、X | 已經停用（只保留穩膽） | 舊 Telegram 累計 ROI 仍然包括（例如 Value Bomb 0/10） |
| 快照版本 | dashboard tracking 用每場**第一個**已驗證發佈；`bet_version` 用**最新**嘅 production 快照（包括 21:45 補跑） | 兩者差別只會喺 21:00 嗰場被擋、要補跑嘅時候出現 |

**問題**：Telegram ROI 混合咗舊組合同研究 shadow，同 dashboard tracking 完全唔同。截至 10-27，dashboard tracking 係 22 中 12、+2.29u（ROI +10%），但 Telegram 寫 B2「12 注 +60%」，因為後者係最新版本，而且包括 10-25 嘅舊 steady 定義。

## 2. 修正（今次交付）

1. **Telegram ROI 改用 dashboard tracking 同一套計法**（`nba_tracking.export_tracking` 加 `nba_combo_roi.bet_tracking_lines`）。今日同累計都只計 dashboard 記錄：每場第一個發佈，即 21:00 版本嘅穩膽，$1 平注。舊組合同 B0／B1／B2 唔再喺訊息度出現，reports JSON 照樣寫，方便研究。真數據試過，同 dashboard 一致：今日 3/7、+0.53u；累計 12/22、+2.29u。
2. **實驗準備度通知**：`INVALID_DATA` 同 `REJECT_HARM` 改用警告格式（⚠️／⛔），唔再寫「可以開始判斷」。
3. **MS1、MS2、MS2-REB／3PM、MS3 嘅 epoch 改為 2026-10-27**：10-26 嘅數據喺 S 接線之前抽取，覆蓋率 0%，令四個測試誤報 `INVALID_DATA`。10-27 嘅覆蓋率係 100%。修訂記錄喺各自協議嘅「修訂」一節，同時更新咗 SHA。

## 3. 排程健康檢查（2026-10-26 至 10-27）

- 10-27 嘅 final refresh（06:30、08:30、10:00、11:30）全部真正重新分析，並且產生快照，冇重新發佈推介（`final_refresh_not_republished`）；13:00 因為全部比賽已開波，`dormant`。
- 21:00 production（10-27 嘅比賽）完成，dashboard 有部署，投注卡有發；19:00 warmup（10-28 嘅比賽）完成；10:30 health ok。
- `temporary_failure` 全部係盤口未開導致嘅部分快照，幾分鐘後重試成功。
- **次要問題**：賽後流程嘅 `settlement_evidence`（Stage 5 研究證據）時好時壞，10-25 同 10-27 係 `blocked: incomplete NBA settlement result chain`，10-26 正常。唔影響 dashboard、ROI 或者出注，未修。

## 4. 未解決：要用戶決定

**正式穩膽同用戶實際落注嘅組合唔係同一個**：
- 投注卡同 dashboard 正式 BET 用 combo 1（有 EV 閘），大部分日子係 NO BET；
- 用戶跟嘅係 steady（B2）候選，系統標住佢係 OBSERVE。

所以系統一邊話「唔好落」，一邊又將用戶落嘅注計入追蹤。要真正一致，要喺以下兩個做法之間揀一個：
- **(a)** 將 steady（B2）升做正式穩膽：投注卡同 dashboard BET 就係佢，清楚標明模型預期 EV 為負，並且附上停損條件。即係 2026-10-25 傾過嘅「命中率產品線」，要先寫協議。
- **(b)** 維持正式 combo 1，用戶只跟正式 BET。

**未決定之前**，Telegram ROI 跟 dashboard tracking（即用戶實際落注嗰套）。
