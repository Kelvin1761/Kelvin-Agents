# EXP-20261102-11 §7 正確性修正：英愛港法 `CLn` 班次標籤當咗澳洲 Class 讀

- **日期**：2026-11-02（Melbourne Cup 前一日）；**平台**：AU；**類型**：§7 正確性修正 —— **唔係已證實改善**。
- **用戶**：「聽日 Melbourne Cup 有好多外地馬同騎師，我哋個 model 睇唔睇得清楚」→「fix all」。

## 錯處（獨立於績效）

Sportsbet 將英國、愛爾蘭、香港、法國往績嘅班次照當地寫 `CL1`…`CL6`，嗰度 **Class 1 最高**（英愛 Class 1 = Group／Listed）。
引擎當澳洲標籤（Class 1 最低）讀：`exact_race_class_level("CL1")` = 62（低過 BM78 嘅 78）、`race_class_tier("CL1")` = 7（最低）。
即係 Royal Ascot／Curragh Group 馬嘅「高班實績」同近績班次係數被當成鄉鎮 Class 1。

## 修法

`au_racing_engine/overseas.py`：海外往績（場地清單；Ascot／Sandown／Newcastle／Hamilton 等同名場地要匹馬另有明確海外往績）嘅 `CLn`
先換成澳洲對等標籤：CL1→LR、CL2→BM88、CL3→BM80、CL4→BM72、CL5→BM64、CL6→BM56（固定判斷，冇擬合）。
接入 `horse_proven_class_level`（高班實績 overlay）同 `_record_entries` 嘅 `source_race_class`（近績班次係數）。紐西蘭用澳洲式標籤，唔轉。

## §7 驗證（08-05 起 3,283 場，v3 fixed_rule）

- 郁咗 35 場（341 匹，有海外往績馬嘅場次；同場其他馬因場內 z 重算輕微移動）。
- Gold −0.03pp [−0.10, 0.00]（1 場）、Good 0、排序指標 +0.00~+0.01；冇分層 CI 全負 → 零顯著退步，合 §7。
- Caulfield Cup 2026：Enfjaar 排名冇變（10）、Wine Dark Sea 12 → 11。**修正啱，但效果細**：外地馬被低估嘅主因係
  近績質素分用獎金（海外獎金數字偏低）、海外往績冇 L600（速度分中性 60）、外地騎師冇數據（騎師分中性 60 ≈ 大賽全場中位）。

## 冇做（記錄）

- 海外獎金：Sportsbet 數字似已換算（兩場唔同賽事同一個數，例如 183,922），但海外同級賽獎金本身細過澳洲，近績質素分會偏低。
  要以標籤而唔係獎金量班次，係另一個改動，要另行登記。
- 外地騎師／練馬師：冇資料源；中性 60 約等於大賽全場騎師中位，唔係重罰。
- 海外段速：冇資料；中性 60 = 全場有數據馬平均，唔會系統性偏幫澳洲馬，但會將強外地馬拉到平均。
