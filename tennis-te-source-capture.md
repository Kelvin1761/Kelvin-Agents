# TennisExplorer：按日保留原始來源

目標：停止 history 只連到summary的缺口；不改parser／評分／判決，不追認缺失的歷史原文。

- [x] provider提供request date／URL、實際fetch時計及精確decoded HTML；保留既有results-only API。
- [x] 每日先存source，再parse／寫history；parse失敗仍可追溯，沒有source則不寫history。
- [x] 28針對測試：跨日source IDs、重跑、空日、壞fetch／parse、UTC／URL、body hash、retention及舊raw link不追認。
- [x] 同公開HTML311場作baseline／candidate比對，622雙側facts／522玩家／兩版592行Elo相同；原文體積及限制記入EXP-20261102-01。
- [ ] quick／完整gate、exact-scope保存；工程source修正與準確度改善分開。

前置證據在研究分支 `codex-tennis-point-input-delivery-20261101` 的 EXP-20261101-44；不把該分支未完成研究工具帶入這次release。
