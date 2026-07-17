# HKJC Readiness Health-Slot — Step 7 Auto Shadow移植

## 實裝結果

- 新增內部shadow profile：`readiness_health_slot`。
- readiness公式與Step 3／5d凍結版本一致：只用休賽日數及體重波幅，可靠度為可用輸入數／2，再向中性60收縮。
- Shadow只替換自身`horse_health`槽；其餘六個matrix dimension直接複製主線分數。
- 沿用現行一般馬及初出馬outer weights；初出／薄證據馬缺資料時維持中性60。
- Shadow JSON記錄分數、可靠度、證據量、排名、rank delta，以及進入／離開Top2。
- Race／meeting CSV新增readiness shadow內部欄位；Markdown完全不展示呢個profile。
- 正式主線`matrix_scores`、綜合分、grade、rank、Top2及verdict保持不變。

## 驗證

- Python compile：5個相關script／test檔全部通過。
- Unit／integration：32 tests全部通過。
- Engine validation：通過。
- Formula validation：readiness分、可靠度、health-slot替換、一般／初出outer formula、grade及ability delta全部通過。
- 缺資料測試：readiness health回中性60，初出馬按官方debut weights計算。
- Mainline isolation：同一Logic分別跑主線及shadow，主線JSON namespace、正式verdict及Markdown完全一致。
- Report validation：通過；同時修正既有L400時間線顯示標籤觸發禁詞嘅問題，內容及排序不變。

## 07-15 Race 8真實Logic Smoke Test

- Base Top2：4／2。
- 現役引擎readiness shadow Top2：4／2；無Top2變動。
- Shadow readiness分成功寫入11匹馬JSON及CSV，可靠度範圍0.5–1.0。
- 主線verdict完全相同；所有馬主線Auto namespace完全相同；Markdown逐字相同。
- 歷史Step 6候選曾由4／2改為2／3，但現役引擎重跑後其他dimension分數已同7月15存檔矩陣有版本漂移，因此本次smoke不再重現3號升格。

## 決策

- `readiness_health_slot`可作現役內部shadow profile使用。
- 暫不取代正式`horse_health`槽。
- 下一個證據步驟應係以現役引擎版本重跑既有歷史樣本，再比較主線與shadow；唔需要先等固定30場future樣本，但不能用舊matrix版本嘅改善直接推斷現役版本同樣改善。

