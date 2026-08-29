# Release and Approval

## Classification

- `docs_tests`: quick gate；可自動 push 同 fast-forward main；永不自動 activate。
- `code`: full gate；push branch；要批准先 merge。
- `model`: full gate + domain evaluation evidence；要批准先 merge/promotion。
- `evaluation`: 必須獨立 release，唔可以同候選 model 一齊改把尺。
- `automation`: full gate + scheduler/lock/idempotency smoke；要批准先 activate。
- `deployment`: full gate + backup/verify/health/rollback plan；要批准先 deploy。

## Safe Release Sequence

1. 喺 isolated worktree 確認 explicit scope，拒絕 unrelated dirty/staged paths。
2. 跑 policy gate；只 stage exact paths；`git diff --cached --check`。
3. Commit 同 push feature branch；寫 immutable release manifest。
4. Docs/tests-only 重新分類整段 unmerged history，仍然安全先 fast-forward main。
5. 高風險 release Telegram 顯示 short commit、risk、gate、rollback target。
6. Approval 時 fetch remote；branch commit、origin/main、scope、gate freshness任何一項唔一致即失效。
7. Merge／activation 完成後 append event，唔改寫原 manifest。

## Failure Policy

- Gate fail：唔 stage、唔 commit。
- Push fail：保留 local commit，manifest 標記 `push_failed`。
- Main 已變：approval expired，重新 rebase/release。
- Production checkout dirty：block activation，唔還原用戶改動。
- Post-sync verifier／installer／deploy fail：退回activation前captured SHA，expected runtime mapping union保留；發critical Telegram，唔宣稱成功。
- Rollback期間有unrelated dirty path：fail closed，唔reset；failure event要同時記原錯誤、rollback blocked同精確paths。
- Model registry首次遷移：只可由authenticated Telegram chat喺release `merged + activation_succeeded`、四線production同SHA、已入main、evidence audit ok兼registry空白時執行；重覆同版本只讀回覆。
