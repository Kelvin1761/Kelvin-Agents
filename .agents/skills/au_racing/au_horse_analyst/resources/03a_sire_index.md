# 血統分析框架 — 條件讀取指引

> **[條件讀取協議]** 種馬特性參考按賽事距離分檔載入，由 Wong Choi 提供 `[DISTANCE_CATEGORY]` 路由標籤：
>
> - `[DISTANCE_CATEGORY: SPRINT]` → 載入 `03b_sire_sprint.md`（≤1300m 短途種馬，10 匹）
> - `[DISTANCE_CATEGORY: MIDDLE]` → 載入 `03c_sire_middle.md`（1400-1800m 中距離種馬，12 匹）
> - `[DISTANCE_CATEGORY: STAYING]` → 載入 `03d_sire_staying.md`（≥1800m 長途種馬，15 匹）
>
> 班次標準時間 `03e_class_standards.md` 為通用參考，每場必讀。

**其他參考資源：**
- `03f_wfa_scale.md` — 澳洲讓磅年齡量表 (Weight-for-Age Scale)，用於 Step 3 WFA 校準
- `03g_gear_codes.md` — 裝備代碼對照表，用於 Step 5 裝備解碼

## 未列種馬處理規則

若馬匹的父系不在對應距離嘅種馬表中，搜索 `"[Sire Name] progeny statistics site:racing.com OR site:breednet.com.au"` 取得 AWD 及場地適性。若搜索無果 → `N/A (血統數據不足)`，裝備與距離維度中的 Sire 投影部分填 ➖。

