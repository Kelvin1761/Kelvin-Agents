# ADR-004: Policy-based Automated Release, Never `git add -A`

## Status

Accepted — Stage 4, 2026-08-26.

## Context

現有`保存.sh`用`git add -A`，多agent／多worktree時可以誤收其他session改動；commit、push、main、production checkout同Cloudflare狀態亦冇一個共同記錄。完全無條件watch-and-deploy會將模型／評估尺改動直接推入production，違反evidence discipline。

## Decision

- 每次交付必須提供explicit scoped paths；中央release manager只stage嗰批paths。
- 所有類別可自動check、commit、push同產生immutable release manifest。
- docs/tests-only變更可喺全部gate通過後自動fast-forward main。
- model、evaluation、automation、deployment及未分類code必須經白名單Telegram approval先merge／activate。
- approval只引用immutable release ID／commit；remote main有新commit、gate過期、scope改變或rollback target缺失即失效。
- production activation只准fast-forward；先backup，後deploy verifier、health smoke，失敗即保留舊production commit。

## Trade-offs

大部分機械步驟全自動；高風險改動仍保留一次人手確認。呢個成本換取唔會因「方便」而靜靜改production model、evaluation ruler或scheduler side effects。
