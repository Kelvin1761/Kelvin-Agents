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

## Transactional activation production status

2026-08-29 production release已補captured pre-activation SHA同post-sync rollback：
verifier／installer／deploy或unexpected exception失敗會逐個deduplicated production checkout
退回舊commit；`sb_archive_meeting_ids.json`做union而runtime值優先。Rollback前再查dirty
paths，任何unrelated concurrent write會fail closed而唔reset，原錯誤同rollback結果一齊寫
immutable event／Telegram。真git fast-forward→failure→rollback、mapping conflict同concurrent
write三條測試已覆蓋。Activation而家亦會喺每個allowlisted installer前做外部狀態
snapshot；後續installer／deploy／verifier失敗時，先用candidate版本installer restore launchd
plist，再退回Git SHA。統一runtime installer只切HKJC、NBA、Tennis同Central；AU poller係
approval caller所以保持loaded，並先驗證佢已指向同一production checkout。Tennis只切versioned
code，現有SQLite／logs／Google Drive output唔搬唔刪。read-only verifier會逐個installed plist
同loaded state核對，任何一條未aligned即rollback。authenticated Telegram已批准immutable
release `cb17d2f0860e`；event chain係`approval_granted → merged → activation_started →
activation_succeeded`，origin/main同production checkout一致，AU／HKJC／NBA／Tennis及Central
installed launchd全部loaded／aligned。

同日一個AU automation fix直接將`origin/main`同production推到`cfb3a9747cc3`，但冇Central
release manifest；舊status因HEAD已push兼已入main而顯示正常。Central而家會對
`origin/main`同每個production checkout嘅exact HEAD核對merged release manifest；缺trail會
明確報`origin_main_without_release_manifest`／`production_commit_without_release_manifest`，
Telegram亦顯示Main trail ⛔。呢個偵測唔會retroactively偽造approval，只會令治理繞過
fail visible。

## Trade-offs

大部分機械步驟全自動；高風險改動仍保留一次人手確認。呢個成本換取唔會因「方便」而靜靜改production model、evaluation ruler或scheduler side effects。
