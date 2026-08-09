# HKJC Readiness Health Slot — Promotion Audit

## Decision

**HOLD / DO NOT PROMOTE.** 官方default維持`legacy_health_v2`；`readiness_health_slot`只保留explicit opt-in及內部shadow用途。

## 點解原先PASS失效

原先118場current-engine replay錄得總Top2 hits +4、頭馬Top2 +3及0-hit -1，但正式晉升前嘅mainline parity audit發現比較並非單一變量：

- mainline先完成原矩陣，再套用SIP enhancement；
- 舊readiness shadow喺SIP之前已經完成排名，沒有按自己嘅ability／grade套用同一SIP；
- 所以舊shadow同時改變health槽及SIP exposure，原先改善不可歸因於readiness dimension。

舊證據檔只保留作provisional／root-cause紀錄，不可作正式promotion evidence。

## 修正

SIP而家會獨立套用到mainline及每個shadow profile，並以各profile自己嘅ability及grade判斷是否觸發；validation亦按相同公式核對。新增integration test確認mainline／shadow SIP互不借用狀態。

## SIP-matched replay（118場）

| 指標 | Legacy mainline | Readiness shadow | Delta |
|---|---:|---:|---:|
| 0-hit races | 34 | 33 | -1 |
| 1-hit races | 59 | 61 | +2 |
| 2-hit races | 25 | 24 | -1 |
| Total Top2 hits | 109 | 109 | 0 |
| Winner in Top2 | 45 | 45 | 0 |
| Winner ranked first | 30 | 29 | -1 |
| Effective / harmful replacements | — | 3 / 3 | net 0 |
| Rank3 effective / harmful promotions | — | 3 / 3 | net 0 |

### Split check

- 2026-07-15 Happy Valley（9場）：hits +1、0-hit -1、頭馬Top2 0；1場改善、0場轉差。
- Independent recent（109場）：hits -1、0-hit 0、頭馬Top2 0；2場改善、3場轉差。
- Split non-harm：**FAIL**。

因此07-15單日正面訊號不足以支持正式晉升；較大嘅109場獨立樣本反而輕微轉差。

## Safety state

- 官方default：`legacy_health_v2`
- Readiness：explicit `--health-profile readiness_health_slot`或shadow診斷先會啟用
- Regression：35/35 passed
- Python compile：passed
- Source meetings：read-only；replay使用temp cache

## Evidence

- Corrected JSON：`scratch/hkjc_readiness_sip_matched_replay.json`
- Corrected race rows：`scratch/hkjc_readiness_sip_matched_replay_races.csv`
- Corrected generated report：`scratch/hkjc_readiness_sip_matched_replay_report.md`
- Provisional evidence（invalid for promotion）：`scratch/hkjc_readiness_promotion_evidence.json`

## Next experiment

下一個最有信息量嘅實驗係固定health為legacy，對SIP scoring layer做獨立ablation（SIP on vs off／分解其weight與draw觸發來源）。呢個係rating-matrix層測試，唔係micro tie-break或blind swap；目的係確認原先表面改善究竟來自邊一部分SIP suppression。
