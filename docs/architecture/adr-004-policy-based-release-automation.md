# ADR-004: Policy-based Automated Release, Never `git add -A`

## Status

Accepted — Stage 4, 2026-08-26.

## Context

舊`保存.sh`用`git add -A`，多agent／多worktree時可以誤收其他session改動；commit、push、main、production checkout同Cloudflare狀態亦冇一個共同記錄。完全無條件watch-and-deploy會將模型／評估尺改動直接推入production，違反evidence discipline。

## Decision

- 每次交付必須提供explicit scoped paths；中央release manager只stage嗰批paths。
- 所有類別可自動check、commit、push同產生immutable release manifest。
- docs/tests-only變更可喺全部gate通過後自動fast-forward main。
- model、evaluation、automation、deployment及未分類code必須經白名單Telegram approval先merge／activate。
- approval只引用immutable release ID／commit；remote main有新commit、gate過期、scope改變或rollback target缺失即失效。
- production activation只准fast-forward；目標contract係先backup，後deploy verifier／health smoke，任何失敗退回舊production commit；現役差距見下節。
- repo root `保存.sh`只係中央release manager wrapper；冇`--path`會fail closed，唔再提供`git add -A`或`--no-check`逃生門。

## Known activation gap

現役activation會喺任何post-sync失敗寫immutable failure event同Telegram，唔會扮成功；
但跨checkout自動rollback仍未獲獨立高風險批准。因此上面「失敗即保留舊commit」係
目標contract，未可當現役證據。完成transactional rollback前，post-sync verifier／
installer失敗要按failure event做人手reconciliation。

## Trade-offs

大部分機械步驟全自動；高風險改動仍保留一次人手確認。呢個成本換取唔會因「方便」而靜靜改production model、evaluation ruler或scheduler side effects。
