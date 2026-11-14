# 目標 prompt：HKJC 歷史研究計劃（一次過做完）

> 新 session 直接貼呢段（或者講「讀 docs/plans/2026-11-14-hkjc-history-goal-prompt.md 跟住做」）。
> Kelvin 2026-11-14 授權：照計劃做晒所有測試；過到預先登記閘嘅改動可以自己發佈同部署去 dashboard；
> 要佢決定嘅嘢列清單，唔好卡住等佢。

---

用港式中文回覆。你係接手 HKJC Wong Choi 歷史研究計劃嘅 agent。目標：**照計劃完成全部測試，過閘嘅改動上線，最後交一份總結同決定清單。**

## 必讀（開工前）
1. `AGENTS.md`（規矩：worktree、`./保存.sh`、證據紀律、大檔放外置碟、forward 測試登記、Telegram 收件人）
2. `docs/plans/2026-11-14-hkjc-history-research-programme.md` —— **主計劃**：語料切法（寫死）、次序、holdout 登記簿、§2a／2b／2c
3. `docs/plans/2026-11-13-hkjc-historic-engine-replay.md` —— 回放做法同忠實度閘門檻
4. `docs/model-evaluation-contract.md`、`.claude/skills/` 嘅 `model-regression-gate`、`leakage-audit`、`feature-ablation`、`experiment-review`
5. 記憶：`kelvin-sectional-is-core`、`hkjc-weights-are-real-gold-peak`

## 現狀（2026-11-14 上午）
- 數據全部喺 `/Volumes/Kelvin Hardisk 1/WongChoi-Archive/hkjc-history/`：分段頁 6,036 場（+2026-05-03 補抓中）、馬匹頁 4,525 匹（224 匹現役馬有「所有往績」版）、
  `parsed/*.jsonl.gz`、`analysis/replay_index.pkl`。每季馬匹頁覆蓋 100%。
- 回放工具（worktree `/Users/imac/wt/claude-hkjc-replay-20261114`，分支 `claude-hkjc-replay-20261114`，**未 commit 嘅改動要先 commit + push**）：
  `hkjc_reflector/scripts/hkjc_history_replay_{build,run,eval,fidelity,pit}.py`；`backfill_history.py`（兩位數年份修正 + `horse_all`）。
- 2026-10-01 試生成：往績列同真 formguide 逐欄一樣 731/806，差異已修（退出往績、第一仗日數、2026-05-03 新格式）。
- 真版 baseline dump：`analysis/replay_gate/real.jsonl`（449 場，現行 code）。

## 要做（按主計劃次序；每步完成先做下一步）
0. **忠實度閘**：build 2026-04-01..2026-11-12 → `hkjc_history_replay_run.py` 離線行真流程 → `hkjc_history_replay_eval.py run --meeting-root <replay> --dump-matrix`
   → `hkjc_history_replay_fidelity.py real.jsonl replay.jsonl`。對照「真版減能量」。門檻寫死：raw 場內 Spearman 中位數 ≥ 0.90、首選一致 ≥ 80%、Gold／Good 差 ≤ 2pp。
   唔過：逐維度搵原因、修生成器（唔准改門檻、唔准改引擎）；修完再跑。**三輪都唔過就停，推 Telegram 講卡喺邊。**
1. 全量回放 2019/20–2026/27（大檔寫外置碟，`export TMPDIR=` 外置碟 scratch；開工前 `df -h`，< 10GB 唔開）；baseline 分段表現（泥地、直路、初出、國際日、班次、路程）
2. 現有 forward 測試（AU 唔郁；HKJC `hkjc_forward_tracker.py` 嘅 FORWARD_TESTS）用回放判（歷史證據，forward 照跑）
2b. 現有訊號審計（§2b）
3. 診斷性 refit
4. 段速候選（EXP-09 三個 arm）＋ 負磅換算（§2c：先量逐段每磅秒數）
5. 重試因 power 唔夠而死嘅 REJECT
6. 泥地 → 7. 直路 → 8. 初出馬 → 9. 國際賽日（描述＋規則，冇統計結論）→ 9b. 評分／配備／馬房出擊（§2a）→ 10. 新訊號搜尋 → 11. 整合 refit

## 規矩（硬）
- 每個實驗記 `docs/experiments/`（連失敗）＋ INDEX；holdout 每次睇都記 `docs/experiments/holdout-ledger-hkjc-replay.md`。
- 判準：Gold、Good 都唔可以負；要贏隨機洗牌 null；dev 揀、holdout 確認一次；同一家族 Holm。
- 賠率唔入模型；每個新欄位做 leakage-audit（賽前攞唔攞到）。
- 改評分 code：清 bytecode（`PYTHONDONTWRITEBYTECODE=1`）、golden_scoring／data_contract 重錄、`./Wong Choi 模型說明/更新模型說明.sh`。
- **上線**：只有過咗預先登記閘（dev + holdout + null）嘅改動先用 `./保存.sh --path … --expected-result …` 發佈（會自動部署 dashboard）。
  新加嘅 live 改動要同時登記 forward 監察（`hkjc_forward_tracker.py`）。邊緣結果（點估計正但 CI 跨零、或者有取捨）**唔上線**，列入決定清單。
- 失敗實驗嘅 model code 唔准入 main（記錄可以）；未完成嘅嘢 commit 去自己分支再 push。
- HKJC 日期一律用香港日期；香港賽馬時段唔好抓網（`backfill_history.py` 已自動暫停）。

## 通知（Telegram，`racing_telegram.send_message`）
- 每完成一步：`audience="primary"` 一句結果（過／唔過、主要數字）。
- 卡住要 Kelvin 決定：`primary`，講清楚選項。
- 全部完成：`primary` 推總結；寫 `docs/plans/2026-11-14-hkjc-history-results.md`（每步結果、上線咗乜、決定清單）。

## 決定清單（遇到就加，唔好停）
- 邊緣候選（要唔要上線）
- 國際賽日／初出馬嘅規則型改動（冇統計證據，係判斷）
- 來港前往績新來源（澳紐英愛網站）係咪值得開項目
