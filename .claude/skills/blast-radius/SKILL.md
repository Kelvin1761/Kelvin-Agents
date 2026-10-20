---
name: blast-radius
description: 'Before keeping any non-model code change in the Wong Choi repo (renames, moves, parser or table-header edits, extraction changes, "display-only" changes, anything on a scheduler/dashboard/Telegram/launchd entry path), find what it can silently break downstream and prove the one fact its safety rests on by running code. Use before commit when a change touches a name, a format, a path, a column or a file another component reads. Complements model-regression-gate, which only covers model changes.'
---

# blast-radius

model-regression-gate 問「呢個模型改動有冇證據」。呢個 skill 問另一樣：
**呢個改動會唔會令下游靜靜死？** 呢個 repo 最貴嘅幾次事故都係呢個形狀 ——
改咗一樣嘢，嘢仲喺度、code 仍行、test 全綠，但另一個讀佢嘅地方靜靜變空：

- package 改名（`racing_engine` → `au_racing_engine`）：單行 regex 漏 5 個
  `sys.path`，生產死咗一晚。
- 引擎表頭 `權重％` → `合成係數`：dashboard parser 對唔到行 = 零個維度。
- 「純顯示」改動靜靜改咗排名（HKJC 三個位全中：grade 字串、排序讀邊個數、golden）。
- 排程冇傳 `WC_DASHBOARD_BASE_SNAPSHOT`，deploy 原封重發 live；deploy 回 0 唔代表上到板。

## 做法

**1. 讀改動。** `git diff`，列出加／改／刪咗嘅 symbol、檔名、欄位、格式，連隱含嘅
行為差異。

**2. 搵「一個安全事實」。** 大部分風險改動只係因為一個原因先安全（例如「所有
reader 都經 `X` 讀」）。證實咗佢就清晒一批情況，唔使列一長串猜測。

**3. 睇 grep 睇唔到嘅下游。** 逐個問：

| 下游 | 點查 |
|---|---|
| 生產排程行 `/Users/imac/wongchoi-scheduler`，唔係你個 worktree | 改共用 repo 唔會生效；確認佢食邊個 commit |
| Telegram bot 觸發嘅 HKJC run 行**主 checkout** 入面嘅 runner | 主 checkout 落後 main = 行舊 code |
| dashboard parser（`Horse_Racing_Dashboard/`） | 對住真輸出跑，數維度數目；改表頭／標籤必查 |
| `golden_scoring` | `--platform au/hkjc` 逐匹馬 diff；「純顯示」改動都要跑 |
| launchd 入口、`install_macos_launchd.sh` | 入口 script 路徑／參數有冇變 |
| 其他語言／文件 parse 嘅格式 | CSV 欄名、JSON key、markdown 表頭 |
| `sys.path` / import 鏈 | **用 AST 掃，唔好用 grep**（`./檢查.sh` 1b 已做）；改名要真 `import` 成條入口鏈 |
| 資料根 marker（`.wongchoi_*root`） | 唔喺 git 入面，新 worktree 唔抄就寫錯地方 |

搜尋搵唔到下游係合法結論。**唔准捏造 caller。**

**3b. 對每個風險老實評估：** 可能性、嚴重性、真實 `file:line`。確認咗嘅風險同已清除
嘅分開寫。

**4. 用跑 code 證明個安全事實**，唔係用文字論證。信心階梯，盡量爬高：

1. 我話冇事 —— 單獨成立等於冇用。
2. 引用具體 `file:line`。
3. 逐步推演失敗路徑，證明壞情況發生唔到。
4. **跑一段 script／test 對住真 code，錯就大聲紅。** 目標至少去到呢級。
5. 喺真系統重現（真跑 orchestrator、真行 dashboard parser）。

一段 10 行嘅 script import 真 module、call 真 function，通常已經夠。

## 輸出

- **改咗乜：** 包括唔明顯嘅部分。
- **一個安全事實：** 講明去到邊一級、貼實際輸出；證明唔到就寫 *unproven*。
- **風險：** 失敗模式、位置、可能性、嚴重性、點驗證。
- **已清除：** 查過乜、點解冇事。
- **合併前：** 最平、最能捉到真 bug 嘅 test／repro（附 script）。

## 唔好做

- 唔好用嚟代替 model-regression-gate：改評分 code 仍要跑評估。
- 唔好只列 caller —— grep 做得到，呢個 skill 嘅價值係 grep 做唔到嗰部分。
- 見到「test 全綠」唔好當證據：呢個 repo 每個貴 bug 都係 test 全綠。

出處：做法參考 cursor/plugins `pstack` 嘅 `blast-radius`（MIT）。下游清單同事故係
本 repo 自己嘅。
