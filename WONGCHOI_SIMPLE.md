# 旺財簡明指南

日常只需要一份程式碼、四個現有引擎，同一個操作入口。AU、HKJC、NBA、Tennis 各自保留評分及資料格式，共用操作方式。Stage5 暫停；現有安全檢查及模型狀態照舊。

| 想做咩 | 指令 |
|---|---|
| 睇四線狀態 | `./旺財.sh status` |
| AU 分析 | `./旺財.sh run au "場次資料夾或URL"` |
| HKJC 分析 | `./旺財.sh run hkjc "場次資料夾或URL"` |
| NBA 分析 | `./旺財.sh run nba --date YYYY-MM-DD` |
| Tennis 分析 | `./旺財.sh run tennis --date YYYY-MM-DD` |
| AU / HKJC 覆盤 | `./旺財.sh review au "場次資料夾"`（或 `hkjc`） |
| NBA / Tennis 覆盤 | `./旺財.sh review nba --date YYYY-MM-DD`（或 `tennis`） |
| 睇各線選項 | `./旺財.sh run au --help`（換線名即可） |
| 營運檢查 | `./健康.sh` |
| 外置碟備份 | `./備份.sh`（按原有範圍備份，唔代表所有 DB 都有獨立可還原副本） |

入口沿用現有引擎及設定；會優先使用既有虛擬環境，亦可用 `PYTHON_BIN` 指定 Python。普通覆盤會跳過 AU archive backtest、HKJC archive review、NBA 歷史 ML 評估；Tennis 沿用本機 review。覆盤仍會寫本機結果及結算資料，唔係唯讀預覽。

現有自動排程繼續用原本入口。資料根目錄沿用各機 `.wongchoi_*root` 設定，唔需要搬資料庫或重建歷史。完整安裝及進階指令仍可查 `SETUP.md`、`AGENTS.md`。

## 精簡及保存原則

- GitHub 保存程式及分支；資料庫、認證、原始數據唔上傳 GitHub。
- 舊中間檔及可重建快取，先複製到外置碟、核對內容，再清內置碟。
- 舊開發工作區只喺工作已保存、冇人使用時移除；分支保留。
- 活躍資料庫、原始歷史頁面、近期工作、模型及回退證據繼續保留。
- 暫停嘅 Stage5 源碼先封存；未核對引用及排程前唔整批刪共享模組。

2026-11-16 精簡前主線已另存 GitHub 分支 `archive-wongchoi-before-simplify-20261116`。未完成研究另外保存在原有非 main 分支，唔當作已發佈功能。
