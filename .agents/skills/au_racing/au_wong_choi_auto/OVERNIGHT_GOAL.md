# 通宵目標（2026-08-03）

貼呢個做 prompt。**目標係「量到真改善先 ship」，唔係「跑完所有步驟」。**
每一步唔通過就停低寫低原因，唔好為咗行完而放寬條件。

---

## 硬規則（違反咗即刻停）

1. **絕對唔好 deploy Cloudflare。** 每個 `au_orchestrator` 都要
   `--skip-cloudflare-deploy`。
2. **絕對唔好寫入 Google Drive 嘅 AU_Racing。** 所有輸出去 scratchpad。
3. **洩漏黑名單** —— 呢兩個欄位唔可以入任何歷史 fit 或者驗證：
   * 網站個 `J/H`（`Jockey N: w-p-s`）—— 含今日嗰仗。加門檻**解決唔到**：
     全部 0.940 / 賽前≥3 次 0.815 / ≥5 次 0.660，乾淨版先係 0.568。
   * `Win Range` —— 含今日嗰仗（41 匹今日贏嘅馬，今日路程逐匹都係範圍端點）。
   要用嘅話，一律**由我哋自己過濾過嘅賽前往績行重新數**
   （見 `au_unused_field_power.runner_features`）。
4. **新特徵入 fit 之前一定要驗 provenance。** 同一版嘢 `Career`/`Prizemoney`/
   `Ave $` 賽前乾淨，`J/H`/`Win Range` 賽後。**逐個欄位驗，唔可以整版通過。**
   驗法：搵首戰馬（賽前零往績）——今日跑咗甚至贏咗，個欄位仲係咪 0？
5. **holdout 升幅大過 dev = 洩漏警號**，唔係好消息。停低查個欄位。
   （`in_win_range` 就係咁：5/5 fold 全過、holdout winT3 +17.58pp，係假嘅。）

## 優先次序（Kelvin 指定）

1. **段速（sectional）最優先** —— 乾淨咁由 Racenet 換去 Sportsbet
2. 盡量用 Sportsbet 嘅**乾淨**數據
3. 剷走唔健康／殘缺嘅訊號同噪音
4. 榨盡新數據

## 步驟

### A. 收尾抽取（背景繼續行，唔好等佢完）
騎練頁抓取仲跑緊（瀏覽器 loop + `sb_browser_bridge`）。**唔使等 1,130 個** ——
按出現次數排咗序，80% 覆蓋已經到手。夠鐘就用手上嘅做。

### B. 補完管道（全部離線、零網絡請求）
```
cd .agents/skills/au_racing
python3 - <<'PY'   # 由已抓嘅個人頁砌 AU_Sportsbet_People_Cache.json
# 見 scratchpad/run_people_chain.sh 入面嗰段
PY
python3 sb_backfill_archive.py --run --max-meetings 999 --cache-only --out-root <OUT>
# ↑ 呢步會填返 (LY:) token（`ly_hit`/`ly_miss` 會印出嚟，0 hit = 有問題）
# 逐個場次行 au_orchestrator --auto --skip-cloudflare-deploy
python3 au_wong_choi_auto/scripts/au_source_compare.py --new <OUT> --old <DRIVE> --json <J>
```
**檢查點**：`jockey_score` / `trainer_score` / `formline_score` 三個覆蓋率要
明顯高過而家嘅 63% / 51% / 69%。唔升就係 wire 壞咗，查 `ly_hit`。

### C. 三段對比（Kelvin 想睇）
| 階段 | 數據 |
|---|---|
| 換之前（現有源）| Drive archive，604 場 |
| 換完未修 | 只有 9 場（當時未抽歷史）。可以把修正逐個關返造一個 604 場版本 |
| 修完＋優化 | B 步之後嘅 `<OUT>` |

### D. 矩陣重 fit —— 照 `REFIT_PLAN.md`
```
au_dump_engine_leaves.py --out <leaves>.json
au_matrix_refit.py verify      --data <leaves>.json   ← 一定要先跑，唔過就停
au_matrix_refit.py gains       --data <leaves>.json
au_matrix_refit.py refit       --data <leaves>.json
au_matrix_refit.py walkforward --data <leaves>.json
au_matrix_refit.py compare     --data <leaves>.json --weights <new>.json
```
* **共識（逐維度中位數）唔取 argmax**
* 只用**往績深度 ≥4 仗/匹**嘅 604 場，唔好溝埋淺嗰 166 場
* 把 `ave_prize`（0.613）同 `dist_place_rate`（0.588）當**候選新維度**放入搜索
  空間 —— 兩個 additive 都過唔到閘，但重新分配權重之下可能得
* 三個 0.5 以下嘅現有 leaf（`track_score` 0.487 / `sectional_score` 0.469 /
  `weight_score` 0.463）**唔好手動剷**，用 `compare` 餵一份歸零嘅 weights 量咗先
* 記住 wet overlay 要跟 ability 散佈一齊郁

## Ship 嘅條件（唔夠就唔好 commit 改動）

* `walkforward` 5 個窗口至少贏 4 個
* **未碰過嘅 holdout** 主指標（`t3prec` / `winner_in_top3` / `champion`）
  至少 2/3 向上，而且冇一個大跌
* holdout 升幅**唔可以**大過 dev 太多（見硬規則 5）

過到 → commit（訊息要寫低量到嘅數字同用咗邊個語料）。
過唔到 → **唔好 commit 權重**，但要 commit 一份寫低「試過、輸咗、幾多」嘅紀錄。
負面結果同正面結果一樣值錢 —— 今日已經慳返好多時間就係因為有呢啲紀錄。

## 收工前

* 更新 `REFIT_PLAN.md`：邊樣做完、量到幾多、下一步係乜
* 記憶：有新嘅失敗模式就寫低
* 留一份 morning summary：做咗乜、量到乜、ship 咗乜、**冇** ship 乜同點解
