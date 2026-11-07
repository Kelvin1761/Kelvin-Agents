# EXP-20261107-01：位置修正 L600 與賽事環境分離（預先登記）

- 日期：2026-11-07；平台：AU；baseline：`bdf64d23c`（現行 C2 及權重）。
- 用戶授權：更準確的位置修正若改善結果則採用；「go ahead」。
- 已讀：EXP-20261101-40／41／42、20261013-10、model-evaluation-contract v3 + §6 + §8。
- 假設：EXP-40 的位置修正移除了現行 leaf 帶有的賽事環境資訊；把環境 E 與本駒末段 P 明確分離，再固定合併，可能改善最終排名。
- 這是新結構測試，不改 EXP-40／42 判決，不搜索混合比例，不用 R10 個案調參。

## 資料與固定構造

重新以現行引擎 dump 同一份 AU corpus，包含 Archive 及現有 corpus 排除規則；只判 2026-08-05 至 2026-11-06（今日未完賽不讀）。
dump 需保留現行 draw overlay，否則不能重現引擎。baseline 先量，禁止混用 11-01 舊 leaf dump。

位置模型訓練沿用 EXP-40 的已凍結 `speed-rebuild/training.json`，不另抓資料；OLS 特徵、2,000 匹次門檻、缺失後備均照原研究。
每個目標日 D 只 fit 往績事件日期 < D 的記錄。這批真值只覆蓋昆士蘭，跨州泛化仍有風險。
PF 每仗日期必須 < 目標日。其他 leaf、full_time/wet/proven_class/draw overlays 不改。

- **BASE**：現役 `pace_figure_score`。
- **P**：EXP-40 位置修正，每仗 `l600_delta + g_D(x)`；近期加權 0.8^k；場內 `clip(60-20z)`。作為單部件消融及現行 C2 下的重測。
- **E**：同一組正式往績，只聚合賽事 `l600_delta`（不加輸距），0.8^k；場內 `clip(60-20z)`。
- **EP**：`0.5 * P_score + 0.5 * E_score`。比例預先固定，禁止結果後加 arm／調比例。
- E/P 場內至少 3 匹有值；缺失為中性 60。P 的來源／位置缺失 fallback 照 EXP-40；逐場報覆蓋。
  候選場內完全相同值亦為中性 60：研究 smoke test 發現三個 0.2 用既有加總會得到微小假 SD；以 exact equality 辨認常數池，避免浮點噪音造假 z。此數值防護於任何候選績效量度前加入，production 不動。
- **N**：pace_figure_score=60，只作 §6 部件預算與功效前置診斷，不可入選。

## 程序與判決（結果前鎖定）

1. baseline A/A：speed replica 與引擎逐匹差 ≤1e-6；exact_score vs engine ≤1.01e-4（既有 dump 六位小數容差）；排名相同，否則停。
2. §6：BASE vs N 的三個 ranking metric |delta| 與賽日 bootstrap CI 半寬先報，標記非資訊性 metric，不事後更改。
   另報凍結 RQ 真值表上逐日只用更早資料 fit 的 MAE/RMSE，確認位置式確實改善時間估算；此診斷不選參、不作排名判決。
3. P/E/EP 全部用同一 `au_walkforward_refit.PROCEDURE`（warmup 30 日、7 日窗、256 draws、seed 7、place 目標、中位數共識、同一 fallback）；記 procedure hash。
4. v3 / §8 四 arm：A1 vs A0、B1 vs B0、B1 vs A0、B0 vs A0。位置 OLS 本身是 fitted，所以 A1 vs A0 亦標記 walk_forward_oos；不偽稱 fixed_rule。
5. 三候選為同一 family：arm 內 Holm，再跨 P/E/EP Holm。Primary Gold、Good 及時間塊照 v3，ranking=(top3_capture_at5, ndcg_at5, top5_pairwise_auc)；2000 次賽日 bootstrap，seed 7。
6. 消融報 EP-P、EP-E（同窗口，固定與 refit 均報），只有 EP 能證明組合需要兩個部件，才保留合併複雜性。
7. 分層：baseline 首選定義 field ≤8/9-10/11-12/13+、SP <3/3-6/6-11/11-21/21+、路程 ≤1200/1201-1600/>1600、going、venue、首選跑法、初出/久休；報顯著退步。
8. A/A 必須 REJECT。沿用 harness 的 source availability FLAG：正式判決不得把無法證明賽前可得的歷史資料標 PASS。另報 conditional research diagnosis，不能當 promotion WIN。
9. 歷史窗口重用，不稱 untouched holdout。若研究 WIN，下一步只登記 2026-11-08 起 41 個有完整資料及賽果的賽日 forward（新 family 一次確認），依 AGENTS 登記 tracker；本輪不先開 forward。

## 保存與限制

大型輸出及 TMPDIR：外置碟 `WongChoi-Archive/scratch/au-position-environment-20261107/`；不複製整份 corpus。
記錄資料 hash、baseline SHA、腳本 hash、完整命令、覆蓋、fallback、A/A、分層與判決。
研究工具不改 production；失敗只保存研究程式／紀錄至研究分支，不合併失敗模型。
