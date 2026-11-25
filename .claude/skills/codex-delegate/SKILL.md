---
name: codex-delegate
description: 'Claude-led delegation to Codex CLI. Use proactively, without being asked, whenever a task has a self-contained chunk of tiring/repetitive work (writing tests, bulk edits, data-audit scripts, wide code searches, log digging) for Terra, or whenever a conclusion deserves an independent second opinion (leakage audit, experiment verdict, diff before ./保存.sh, a surprising result) for Sol. Checks both quotas first via .agents/scripts/codex_delegate.py.'
---

# codex-delegate

Kelvin 2026-11-24：佢唔再自己用 Codex，全部交畀 Claude 決定。**你係主導**，Codex 係下屬：
你計劃、派工、核實、拍板。唔使等 Kelvin 講「畀 Codex 做」。

## 1. 每次開工（同每次派之前）：睇兩邊額度，揀分工模式

先用 `mcp__ccd_session_mgmt__get_usage` 攞 Claude「Weekly · all models」嘅 `percentUsed` 同 `resetsAt`，再：

```bash
python3 .agents/scripts/codex_delegate.py status --claude-weekly <percentUsed> --claude-resets <resetsAt>
```

佢會印 Codex 狀態同**分工模式**（Kelvin 2026-11-24：按 quota 調整 offload 幾多，Opus 唔好用爆）：

| 分工模式 | 幾時 | 做法 |
|---|---|---|
| offload-max | Claude 用得快過時間 ≥10pp、或本週 ≥85%；或者 Codex <2 日重置仲剩好多 | 實作同重活一律派 Terra（我寫 brief、睇 diff）；覆核派 Sol，**唔開 Opus subagent**；讀 log／grep／摘要派 Luna；Opus 只做計劃、判決、保存、Telegram |
| balanced | 兩邊都正常 | 照下面第 2 節常規分工 |
| offload-light | Claude 緊但 Codex 都 tight | 只派 review／quick／chore；Claude 本週 ≥85% 先 `--force` 派 grunt 並寫原因 |
| keep-claude | Codex tight、Claude 慢過時間 ≥20pp | Opus 自己做多啲，Codex 留畀 review |
| claude-only | Codex stop | 唔派，喺回覆講一句「Codex 額度停派中」；Claude subagent 用平啲嘅模型 |

**「放心用 Opus」開關**（Kelvin 2026-11-24：佢有時特登快啲用 Opus，因為之後有額外 reset）：
`codex_delegate.py pacing --spend-freely-until <Claude 每週重置 ISO> --reason "..."` 開；`pacing --clear` 閂；過期自動失效。
開住嗰陣唔理 Claude 用得幾快（照 balanced），只有本週 ≥85% 先轉 offload-max。Kelvin 講「呢個禮拜放心用」先開，唔好自己開。

**Claude 自己嘅 subagent 都要慳**：搵 code、讀 log、掃檔呢類 Explore／research subagent 一律傳 `model: "sonnet"`（純搜尋用 `"haiku"`）；
只有要判斷／設計嘅先用 Opus。offload-max 時先考慮派 Luna。

Codex 狀態本身：normal 照派；tight 只派 review／quick／chore（`--force` 只越過 tight，越唔過 stop）；unknown 可以派但每次之後再 `status`。

## 2. 派唔派：角色同例子

| 角色 | 模型 | 派咩 | 唔派咩 |
|---|---|---|---|
| **grunt** | Terra 最新 | 寫／補測試、批量改名或改文檔、寫一次性資料審計腳本、喺大量檔案搵 pattern、整理 log、重複性 refactor | 改評分邏輯本身、改 `config.json` 係數、任何要判斷「好唔好」嘅嘢 |
| **review** | Sol 最新 | leakage 審計（逐欄問「落注嗰刻拎唔拎到」）、實驗結論覆核、`./保存.sh` 之前覆核 diff、一個好得出奇嘅回測結果 | 叫佢代你判 KEEP／REJECT |
| **quick** | Luna 最新（唯讀） | 搵 code／pattern、睇 log 搵錯、摘要長檔、列出受影響嘅檔、核對兩份輸出差異 | 要判斷好壞嘅嘢 |
| **chore** | Luna 最新（寫入） | 改名、改格式、補 docstring／type hint、照樣板加測試、改文檔字眼、update 路徑 | 要理解模型邏輯嘅嘢 —— 升 Terra |
| **deep** | Astra 最新 | Sol 同你意見唔同、而結論影響上唔上線，而且 third 都講唔清 | 日常覆核 |
| **scan** | Gemini Flash 最新（唯讀，經 `agy`） | 要一次過讀好多嘢：成堆 log、成份語料摘要、全部實驗記錄搵舊假設、長 diff 摘要。~1M context，用 Kelvin Google 訂閱，唔食 Codex／Claude 額度 | 要判斷好壞、要寫檔 |
| **third** | Gemini 非 flash 最新（而家 Hydrogen） | 第三家獨立意見：Sol 同 Opus 唔同意見時先問佢；Codex tight／stop 時頂替 Sol 做 review | 代你判 KEEP／REJECT |

**Luna 先行（Kelvin 2026-11-24：當免費勞工用）**：機械式、答案易核實嘅嘢一律先派 Luna（quick／chore）；
Luna 答錯或者冇改到，先升 Terra。Luna 都係食同一個 Codex 額度，只係每次食得好少，所以收緊（tight）都照派。
同一時間可以派幾個 Luna 去做互不相干嘅細嘢（各自 worktree／唯讀）。

**Gemini（scan／third）**：同一個 `run`，例如 `codex_delegate.py run third --cd <worktree> --prompt-file brief.md --out r.md`。
一律唯讀（agy `--mode plan`）；agy 唔讀 stdin，腳本自動將 brief 寫入臨時檔叫佢讀。冇得睇額度：撞 429 會自動停派 5 個鐘，`status` 會顯示。
2026-11-25 實測：third（Hydrogen high）覆核一個 diff 63 秒、input 4.5 萬 tokens，搵到 5 類真 bug；scan（Flash）摘要一節文件 27 秒。

**Luna 要窄，唔好叫佢探索**（2026-11-24 實測）：叫佢「自己搵積壓」會淺——一個做一半收工、一個 log 掃描乜都搵唔到，
唯讀 sandbox 入面 `git ls-files` 有時都用唔到。叫佢「改 X 檔第 N 行做 Y」就好準（兩個文檔 chore 各 <50 秒、全部啱）。
所以：**Claude 先劃範圍、列清單（檔案:行號＋要改成點），Luna 逐項執行**；要開放式探索就派 Terra 或者自己做。

值唔值得派，問兩條：
1. **呢舊嘢可唔可以用一份 brief 講清楚、獨立核實？** 唔得就自己做 —— 解釋背景嘅 token 會多過慳返嘅。
2. **細過 ~5 個 tool call？** 係就自己做 —— 除非係 Luna 做得嘅唯讀查詢，平到唔使計。

**一定要 review 嘅情況**（只要額度唔係 stop）：改模型嘅 KEEP 判決之前、任何 leakage-audit、回測結果好過預期。

## 3. 寫 brief

腳本會自動加上「唔准 commit／push／保存／Telegram／再委派」嘅前言，你只寫任務本身：

```markdown
## 背景（3–6 句）
## 要做
- 具體到檔案路徑同函數名
## 完成標準
- 例如：`pytest .agents/scripts/tests/test_x.py` 全綠；或者「列出每個欄位 + 拎唔拎到 + 證據行號」
## 唔好做
```

review 嘅 brief **唔好講你自己嘅結論**，否則唔係獨立意見。畀佢睇原材料（diff、實驗記錄路徑、命令），問佢搵錯。

**review 要窄先平**（2026-11-24 量度：8 次 Sol review 食咗 1,240 萬 input tokens，平均每次 150 萬，因為佢自己周圍搵嘢讀）：
- 將 `git diff` 直接貼入 brief（或者寫入檔再講路徑），**列明只准讀邊幾個檔**，講明「唔使掃成個 repo」。
- 細改動（< ~200 行、唔涉模型判決）用 `--effort medium`；改模型 KEEP 判決、leakage 審計先用預設 high。
- 每次派完睇 `status` 嘅「近 7 日委派」，review 每次平均 input 應該跌到 50 萬以下。

## 4. 派

```bash
# 唯讀覆核：用自己（Claude）嘅 worktree，唔好用主 checkout
python3 .agents/scripts/codex_delegate.py run review --cd <worktree> \
  --prompt-file <scratchpad>/brief.md --out <scratchpad>/review.md --title "覆核 EXP-xxx leakage"

# 寫嘢：一定要佢自己嘅 worktree
git worktree add -b codex-<題目>-<YYYYMMDD> <路徑> origin/main && cp .wongchoi_*root <路徑>/
python3 .agents/scripts/codex_delegate.py run grunt --cd <路徑> --prompt-file brief.md --title "..."
```

- 長嘢（>2 分鐘）用 Bash `run_in_background`，同時做自己嗰份；唔好兩邊改同一批檔。
- 寫入角色會自動用 `--add-dir` 開返 `.agents`／`.claude`；`.git` 保持唯讀，所以 Codex commit 唔到。
- 退出碼：0 成功、1 Codex 失敗、2 用法錯（例如喺主 checkout 寫）、3 額度唔准派。

## 5. 收貨

- 寫入角色完成後腳本會印「worktree 改動：N 個檔」；0 個就睇 Codex 答覆搵原因。
- **grunt**：自己 `git diff` 睇過、自己跑測試先信。合返自己分支用 `git cherry-pick` 或者 `git diff | git apply`；Codex 分支唔好 push 去 main。用完 `git worktree remove`。
- **review**：逐點判斷，唔好照單全收。同意嘅改、唔同意嘅講原因。有分歧而影響重大 → 先 third（唔同家族、唔食 Codex 額度），再唔清楚先 deep。
- 回覆 Kelvin 嗰陣寫一行：「已交 Codex（Sol）覆核 X：<結果>」。唔使問佢准唔准派。
