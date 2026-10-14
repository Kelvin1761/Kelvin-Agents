# AU 市場研究環境：已安裝的操作入口

根目錄：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/tools/au-next-stage-20261014/`。
外置碟必須掛載；啟動器會檢查mount。這是獨立研究環境，沒有更改AU生產pipeline。
完整研究、固定commits及測試範圍見
`docs/audits/2026-10-14-au-market-stage-preparation.md`。

## 使用

版本／本地spec驗證（不需要API key）：

```bash
"/Volumes/Kelvin Hardisk 1/WongChoi-Archive/tools/au-next-stage-20261014/bin/sportsdata-mcp" version
"/Volumes/Kelvin Hardisk 1/WongChoi-Archive/tools/au-next-stage-20261014/bin/sportsdata-mcp" lint
```

手動啟動RacingBoard：

```bash
"/Volumes/Kelvin Hardisk 1/WongChoi-Archive/tools/au-next-stage-20261014/bin/racingboard"
```

開 `http://127.0.0.1:8765`；同一terminal按Ctrl-C停止。
啟動後會向前收集研究資料到external SQLite；沒有定時啟動。
AU thoroughbred only，active cap6，price30秒、Betfair10秒、corporate60秒、discovery90秒。
這個cap不保證所有遠期時間bucket覆蓋；正式資料收集前要量coverage，再決定營運參數。
外部通知被關閉，Kelly paper stake=0，auto-follow confirmations=999。

Standalone MCP（stdio）：

```bash
"/Volumes/Kelvin Hardisk 1/WongChoi-Archive/tools/au-next-stage-20261014/bin/sportsdata-mcp" serve
```

六個只讀資料group共53工具已測catalog；没有自動加到Codex／其他client的全域設定。
也可由external `.venv/bin/python` import `sportsdata_mcp`，不用MCP client或LLM。
wrapper自動設定external temp/cache/state/config；`bin/environment.sh`只能在Bash中source，
一般直接用上述兩個啟動器即可，毋須在zsh手動source。

## 安裝內容

- `odds-fluctuations/`：研究CSV／notebook／Word／PDF／Tableau原檔。
- `betfair-learning/`：78個文字／程式／notebook檔，圖片和大型歷史資料未下載。
- `sportsdata-mcp/`：v0.33.0 editable source，runtime及dev工具。
- `RacingBoard/`：core web/data runtime；optional lightgbm/pyarrow training stack未裝／未啟用。
- `.venv/`、`cache/`、`tmp/`、`state/`、`logs/`：所有本次新安裝及運行內容在external。
- `manifest.json`、`requirements-resolved.txt`：來源commit及實際package版本。
- `validation.json`、`protocol.json`、`live-probes.json`、`price-probes.json`、`board-smoke.json`：驗證證據。

pre-existing Python3.12 base interpreter在本機uv目錄，external venv需要它。
不要只複製venv當成跨機可移植bundle；换機要按manifest及resolved versions重建。
不要刪除原有內置Python，其他工具可能也在用。

研究準備scripts保留在repo `scratch/au-market-lab-20261014/`；不更改upstream source。
安裝未作AU模型A/B、未claim改善、未commit／push／deploy。
