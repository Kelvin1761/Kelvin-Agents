# 實驗記錄

一個實驗一個檔：`EXP-YYYYMMDD-NN-<短 slug>.md`（由 `_TEMPLATE.md` copy）。
`INDEX.md` 一行一個。

**開始一個新假設之前**，先 `grep -ril "<關鍵詞>" docs/experiments/` —— 呢個 repo
已經重複燒過同一批想法。詳細規矩見 `.claude/skills/experiment-review/SKILL.md`。

原始 dump（`leaves.json`、逐匹馬 CSV）**唔好**入 git；記錄裡面只寫路徑同重跑命令。

呢個系統喺 2026-08-21 建立。之前嘅結論散落喺 repo root 嘅 `*-review.md` /
`*-plan.md`、`Guides_and_Plans/`、同各個 harness 嘅 docstring 度 —— 搜索嗰陣兩邊都要睇。
