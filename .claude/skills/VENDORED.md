# Vendor 返嚟嘅 upstream skills

以下 skill 係由 `github/awesome-copilot`（MIT，Copyright GitHub, Inc.）逐字 copy
落嚟嘅，**唔好手改** —— 改咗就同上游脫節，之後更新會覆蓋你嘅改動。要改行為就
另開一個自己嘅 skill 包住佢。

- 來源：https://github.com/github/awesome-copilot/tree/main/skills
- Upstream commit：`bbaa5872640e6cbae953beb22a71ae337398ca12`
- 抓落嚟日期：2026-08-21
- 抓落嚟嘅方法：直接由 `raw.githubusercontent.com` 讀，**唔係** `gh skill install`
  —— 呢部機冇 `gh`，亦冇 Homebrew 裝得到（見下面）。內容同 `gh skill install
  github/awesome-copilot <name> --agent claude-code --scope project` 會放落嚟嘅一樣。

## Vendor 咗邊幾個

| Skill | 用嚟做咩 |
|---|---|
| `acquire-codebase-knowledge` | 掃 repo 出架構／慣例／測試文檔（有一個 read-only `scripts/scan.py`） |
| `pytest-coverage` | 跑 pytest + coverage，補未覆蓋嘅行 |
| `review-and-refactor` | code review + refactor |
| `security-review` | 追數據流嘅安全掃描 |
| `github-actions-hardening` | `.github/workflows/` 嘅 Actions threat model 審查 |

## 要更新嗰陣

重新由上面個 URL 抓，然後 diff。**抓落嚟之後要睇 `scan.py`** —— 佢係唯一一個
可執行檔。2026-08-21 審過：只係 read-only `git log` subprocess，冇網絡、冇刪除、
只寫 `--output` 指定嘅檔。

## `gh` 未裝

`gh --version` → command not found。`brew` / `port` 都冇。裝 `gh` 要 Kelvin
自己決定（Homebrew 安裝要密碼），所以呢度冇代裝。裝好之後就可以改用
`gh skill install` / `gh skill list` 管理呢批 vendor skill。
