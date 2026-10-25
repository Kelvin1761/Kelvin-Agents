# EXP-20261026-02 傷停處理：NBA 官方傷停報告、狀態記錄、開波前刷新

- **日期**：2026-10-26（Claude Code，用戶問 Day-To-Day／Questionable／GTD 點處理之後批准）
- **性質**：數據來源同排程工程。**冇改任何機率或模型**；穩膽篩選只會更嚴，唔會放寬。
- **唔影響**：S_v3（EXP-20261026-01）凍結咗用 ESPN 規則，官方報告唔會入 S_v3。

## 點解要改

| 問題 | 證據 |
|---|---|
| ESPN 名單只有 `Out`／`Day-To-Day`，Questionable、GTD、Probable 全部混埋一齊 | 10-24 ledger 樣本：Out 43、Day-To-Day 14 |
| ESPN 會同官方唔一致 | 2026-10-25 08:15 ET 官方報告：Ben Sheppard 喺 ESPN 係 Day-To-Day，官方係 **Out**；Aaron Nesmith 喺 ESPN 係 Day-To-Day，官方係 **Probable** |
| 最後一次更新太早 | 舊排程最後一次 final refresh 係 06:30 悉尼時間；今季 44 場入面大約 90% 喺 10:00–13:30 開波（美國轉冬令時間後會推遲一個鐘），即係離開波 3.5–7 個鐘 |
| 冇記錄 DTD 最後有冇落場 | 所以冇數據校準任何部分權重 |

## 改動

1. **`nba_official_injuries.py`**：讀官方報告索引頁，攞最新一份 PDF（每 15 分鐘出一次，時間係美東時間），用 pdfplumber 按 x 座標分欄解析。
   - 每頁標題同頁碼唔當資料行。
   - 隊名同比賽會沿用到下一頁。
   - 「NOT YET SUBMITTED」按**比賽日期**記錄。份報告會包括之後幾日嘅比賽，所以背靠背嘅球隊唔會撈錯場。
   - 名字配對處理黏埋嘅後綴（`JacksonJr.`、`WalkerIV`），只會喺大楷後綴緊接細楷字母時先剪，唔會剪錯以 v 結尾嘅姓。
   - 失敗一律記錄，唔會拋出錯誤；cache 10 分鐘。
   - 實測 2026-10-25 08:15 ET 報告：41 行、全部有隊名；Out 29、Questionable 7、Probable 3、Doubtful 1、Available 1。
2. **Extractor**：每次 extraction 同每次 `--refresh-availability`（final refresh 用）都寫入 `official_injuries`。
3. **穩膽篩選（只會更嚴）**：腿嘅可用性 = ESPN 同官方兩者之中**較嚴**嗰個。
   - ESPN DTD ＋ 官方 Out → 剔走。
   - 官方 Questionable（ESPN 冇列）→ DTD，唔入穩膽。
   - 官方 Probable **唔會**放寬 ESPN DTD。要放寬，一定要有下面第 4 點嘅數據支持，再另外批准。
4. **`availability_obs`（ledger）**：每個快照為每個喺任何一份名單上嘅球員記錄 ESPN 同官方狀態。
   - `nba_availability_outcomes.py` 只讀，會將最新賽前快照對返 Results_Brief 嘅實際上場分鐘，按狀態計上場率。
5. **開波前刷新**：final refresh 由 06:30 一次，改為 06:30、08:30、10:00、11:30、13:00 五次，全部只刷新未開波嘅場次。
   - 每次有自己嘅 control-plane slot。如果冇咗呢樣，後面幾次會當重複被跳過（10-23 試過 `duplicate_skipped`）。
   - final refresh 嘅 Telegram 投注卡同營運通知改為按**推介內容**去重（賽事＋選擇＋決定，唔包括賠率）。只有推介真係改變先再發；21:00 production 行為不變。

## 預期同未知

- **預期**：穩膽唔會再揀官方已經列 Out／Questionable 嘅球員；傷停有變嘅場次會喺開波前 30–90 分鐘更新；Telegram 唔會因為賠率郁而多發卡。
- **成本**：每日最多多四次 final refresh。每次重做未開波場次嘅分析，大約要 8 分鐘一場（並行處理），dashboard 每次有變都會重新部署。
- **未知**：
  - 官方報告抽取嘅長期穩定性（PDF 格式可能會改）。解析失敗只會令官方欄位留空，退返 ESPN 規則。
  - Questionable／Probable 實際上場率要累積幾個星期先有。
- **之後**：用 `nba_availability_outcomes.py` 睇上場率。如果 Probable 嘅上場率夠高，可以另開協議考慮放寬，並且考慮 S_v3b 用部分權重。

## 執行

```bash
cd .agents/skills/nba/nba_daily_auto
PYTHONDONTWRITEBYTECODE=1 python3 nba_availability_outcomes.py --since 2026-10-27
```
