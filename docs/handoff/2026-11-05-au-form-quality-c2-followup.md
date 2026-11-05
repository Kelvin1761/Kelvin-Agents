# 交接：AU 近績質素 C2 上線 → 大爛地跟進（2026-11-05）

## 已做

- EXP-20261105-05：近績質素「跑得好先攞獎金分」（C2）**USER-ACCEPTED** 上線，連 C2 §8 refit 權重（`dimensions.py`，舊值寫喺註解做 rollback）。
  §8：fixed Good +1.15 [+0.27, +1.97]；refit Good +0.91 [−0.03, +1.77]、AUC +0.33；Gold 冇升 → 正式判決 REJECT，用戶接受。
- C1（獎金封頂）§8 WIN 但用戶揀 C2；C3（PF 場數收縮）REJECT。研究碼：分支 `claude-au-fq-prize-dominance-20261105`。
- Dump／walk-forward：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/fq-prize/`（BASE、C1、C2、C3、SHIP + wf_*）。

## 如果上線未完成（用量爆咗）

1. `git log origin/main --oneline | grep EXP-20261105-05` 有 "C2" 就已經上線，跳去「下一步」。
2. 冇：worktree `/Users/imac/wt-au-fq-c1-ship-20261105`（分支 `claude-au-fq-prize-cap-ship-20261105`）有未保存改動。
   照 AGENTS.md：`./檢查.sh` → `golden_scoring --platform au --record`（先睇 diff）→
   `data_contract --platform au --calibrate --since 2026-08-05 --limit 2000`（會改 resources json = 評估尺，**另一個 release**）→
   `./Wong\ Choi\ 模型說明/更新模型說明.sh`（HKJC 嗰兩份 `git checkout --` 還原）→ `./保存.sh`（路徑用 `git status --porcelain -z` 收集）。

## 下一步：大爛地（用戶：「later see how we can fix 大爛地」）

v3 fixed（BASE vs C2）分層 `going:heavy:good_positional` CI 全負。要做：

1. 用 `scratch/au_track_simplify_judge_20261103.py` 嘅 cohort 輸出（`/Volumes/.../fq-prize/fixed_C2.json`）睇大爛地場數同 Δ。
2. 假設（預先登記先量）：大爛地場次往績名次受場地影響大 → C2 將「大賽跑唔好」嘅獎金分歸零，對濕地專家唔公平；
   候選例如「往績係濕地嘅場次，名次折算放寬」或者「今場大爛地時用返舊公式」—— 一次最多兩個候選，§8 + Holm。
3. 記錄寫 `docs/experiments/`，冇過閘唔上（除非用戶接受）。

## 俾另一個帳戶嘅 prompt

```
喺 /Users/imac/Antigravity-repo 做 AU Wong Choi。先讀 docs/handoff/2026-11-05-au-form-quality-c2-followup.md
同 AGENTS.md。如果 EXP-20261105-05 C2 未上線就照「如果上線未完成」做完；然後做「下一步：大爛地」：
先預先登記（docs/experiments/），量 C2 喺大爛地場次點解 Good 位變差，最多兩個候選，用 §8（au_walkforward_refit
+ scratch/au_track_sp_s8_judge_20261103.py）判決。用港式中文回覆。
```
