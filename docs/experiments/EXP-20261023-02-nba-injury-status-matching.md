# EXP-20261023-02 NBA 傷病排除：名稱配對同狀態分類（正確性修正，唔係模型改善）

- **日期**：2026-10-23
- **平台**：NBA
- **假設**：`build_leg_candidates` 用「精確字串」搵傷病狀態，而且只認字面 `Out`／`Day-To-Day`，會漏掉有重音符號嘅名同其他狀態。**可證偽**：以真實 11 場輸出比較，如果改後組合同選腿完全一樣，就只係防禦性修正。
- **搜索過嘅舊記錄**：`grep -il "injur" docs/experiments/` —— 冇相關記錄。
- **改到嘅檔案**：`generate_nba_reports.py`（`classify_injury_status`、`injury_status_for`、`build_leg_candidates`）、新測試 `test_nba_injury_status.py`。
- **唔係**：冇改機率、權重、揀腿規則本身。**冇聲稱改善。**

## 發現
1. 查表 `injuries[team][player_name]` 係精確比對：賠率來源寫 `Luka Doncic`，ESPN 寫 `Luka Dončić`，查唔到就當健康。
2. 排除只認 `status.lower() == "out"`：`Out For Season`、`Doubtful`、`Suspension` 全部當健康；`Questionable` 唔會被當 day-to-day 排出穩膽。

## 修正
- 用 `nba_identity.player_name_key`（全名、去重音、去 `.`；唔做姓氏單獨配對，只喺同隊名單入面查）。
- `Out*`／`Doubtful`／`Suspension`／`Inactive`／`Injured Reserve` → 排除；`Day-To-Day`／`Questionable`／`Game-Time Decision` → 只排出穩膽；其餘照舊。

## A/B（2026-10-22 十一場真實 extractor JSON；舊＝origin/main，新＝本分支）
- 11 場組合：**0 場有分別**；選腿：0 條有分別。
- 當日 extractor 嘅傷病狀態只有 `Out`（45）同 `Day-To-Day`（19），所以呢個修正喺呢個樣本冇可量到嘅效果，只防止將來出現其他狀態或重音名時靜靜漏排。

## 限制
- 冇找到一個真實會被修正改變結果嘅日子，所以**冇證據顯示改善**；測試只證明新規則按設計運作。
- 未處理：usage redistribution 係用「冇 game log」推斷缺陣，唔係用傷病名單（獨立問題，未改）。
