# NBA 重寫交接（2026-11-03，分支 claude-nba-rebuild-20261103，未 merge）

## 已完成（全部 commit + push 喺分支，未入 main，production 未受影響）
- 新引擎 `.agents/skills/nba/nba_engine/`（768 行）：MS 機率 + B2 穩膽 + sidecar 防火牆。
- EXP-20261103-13：S 單獨輸 C；MS 贏 C（holdout −0.0039）→ 上 MS；揀腿 B2 保留（88/89 場同舊版一樣）。
- EXP-20261103-14：全部 forward 測試中止（冇判決）。
- 刪舊引擎／MC／ML／fit／prob／LLM 年代 docs：−19k 行。NBA 469 個測試全過。

## 未做（下次由呢度開始）
1. `./檢查.sh` 全套：上次喺背景跑緊未有結果 → 重跑，紅燈唔准保存。
2. 最後一個 commit 之後改咗 `nba_engine/run.py`、`banker.py`（banker_pool 診斷）同
   `nba_daily_schedule.py` 嘅 NO BET 文字 —— 已 commit 喺 2d31e608 之後？用 `git status` 確認。
3. Live 乾跑：等 Sportsbet 開 11-05 球員盤，喺 worktree 對一場跑 orchestrator（輸出去 scratch），確認真 SGM 報價流程。
4. 切換：**11-04 13:05–18:55 悉尼**之間 `./保存.sh --path <scope> --expected-result ...`。排程每次 run 前會
   自動 ff 去 origin/main，所以 merge 咗之後 19:00 warmup 就係新引擎第一個完整 run。唔好喺 21:00–13:00 之間 merge
   （同一日會兩個引擎混住）。
5. Stage 2：dashboard 改讀 JSON（剷 Markdown parsing）、`generate_nba_sgm_reports.py` 改讀 sidecar、重寫 extractor／orchestrator／scheduler。

## Dashboard「21:00 顯示翌日」
已查：有賽日排程 21:06–21:12 已 deploy，前端 10-31 起已顯示明日（`nbaSlateEnd`）。11-04 冇賽事所以今晚冇嘢顯示。
如果 Kelvin 見到嘅情況唔同，要佢講邊一日、邊個 tab。
