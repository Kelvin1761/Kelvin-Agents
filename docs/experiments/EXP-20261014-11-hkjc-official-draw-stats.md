# EXP-20261014-11 HKJC 官方「檔位統計」入評分（point-in-time 重建）

- **日期**：2026-10-14
- **平台**：HKJC
- **假設**：用官方檔位統計（場地 × 跑道 × 賽道 × 路程 × **逐個檔位**）嘅上名超額，
  取代或混合現行 `draw_score`（1-4／5-8／9+ 三級先驗 + EXP-20261007-01 rail×組別修正），
  會改善 Gold／Good 或排序指標。
- **搜索過嘅舊記錄**：見「舊工作」。
- **改到嘅檔案／組件**：冇（arm 只喺 harness 進程 monkeypatch `DrawScorer.compute`）。

## 舊工作（唔重做）

| 記錄 | 試咗乜 | 結果 |
|---|---|---|
| `features/draw.py` 註釋（2026-07-05） | 官方檔位頁 verdict tier／上名率+35／steep／hybrid 入分 | 全部輸位置先驗（good −5~−7pp）。⚠️ 嗰次用**當日頁面**回測舊場次 = 前視，而且頁面當時凍咗 |
| EXP-20260927-03 | rail × 距離 × 檔位組別資料集（1,755 場） | 資料修復 KEEP；模型 shadow only |
| EXP-20260928-01／03 | draw／fit／trip 拆解 | draw 19/19 fold 正，但冇獨立入分候選過閘 |
| EXP-20260929-01／02 | 跑馬地 V3（draw + 0.45×PIT 場地）／沙田 draw70 | HV experimental live；ST draw70 forward shadow |
| EXP-20261007-01 | PIT venue × rail × 距離組 × 檔位組，收縮 60、門檻 100 匹／20 場、±4 cap | **已上線**（用戶批准） |
| EXP-20261010-13／14 | 模型押內檔太重；每日偏差 ρ≈0 | 冇模型改動；ledger 收集中 |
| EXP-20260910-01 | 檔位轉 10pp 去狀態 | REJECT |

今次同 EXP-20261007-01 唯一分別：**逐個檔位**（唔係三組）、**官方頁面嘅三季窗口**、
**直接取代**先驗而唔係 ±4 修正。

## 重建驗證（開跑候選之前做）

官方頁面冇寫窗口。用我哋 `rail_draw_results.csv`（2024-09-08 起）逐格重建
（`Date < 賽日`），對 10 份存檔頁面（2026-05-31 + 09-09 至 10-14 九份）：

- 2026/27 季九份：478 格入面 437 格（91.4%）五個數（出賽／冠／亞／季／殿）**全部一樣**；
  唔一樣嘅幾乎全部係「出賽 +1、名次數全同」（頁面計埋冇完成／取消資格嘅馬，我哋語料冇）；
  只有 10-04 沙田 AWT 1650 少咗一場。
- 2026-05-31 沙田：0/68 —— 頁面出賽 30，我哋只有 19。
- **結論：頁面窗口 = 今季 + 前兩季（滾動三季）**。2026-09 轉季之後 2023/24 跌出窗口，
  所以以 2024-09 起嘅語料就重建得到；之前嘅賽日要 2023/24 賽果，我哋冇。
- 所以：**2026-09-06 起嘅回放 = live 特徵**；2026-04-12 至 07-15 嘅回放係截短窗口
  （少一季），唔代表 live。

## 預先登記（未睇任何候選結果之前寫）

**特徵**：每匹馬 `res = 上名 − min(3, F)/F`（F = 馬匹數）。格 = 場地 × 跑道 × 賽道（草地）
× 路程 × 檔位；窗口 = 今季 + 前兩季（季由 9 月 1 日起）且 `Date < 賽日`（同日早場都唔用）。
`excess = Σres / (n + 60)`（收縮向 0 = 同場地同路程平均；60 = repo 慣例）。
`official = clip(60 + 270 × excess, 35, 85)`。
k = 270（每 1pp 超額 2.7 分）由**已有記錄**定：現行先驗 1-4 vs 9+ 差 25 分，
EXP-20260927-03 內外檔超額差 沙田 7.3pp／跑馬地 11.2pp，平均 9.3pp → 25/9.3 ≈ 2.7。
冇用今次評估數據 fit 任何數。n = 0 → 保留現行 draw_score。

**Arms**（候選家族 2 個，Holm 調整）：
- **A replace**：`draw_score = official`
- **B blend**：`draw_score = 0.5 × 現行 + 0.5 × official`
- 診斷（唔係候選）**N neutral**：`draw_score = 60`，量 §6 部件預算。

**判決**：Stage 4 v3 `fixed_rule`（冇 fit），`hkjc_eval_harness.py compare`。
- **主窗口 F**（決定性）：2026-09-06 至 2026-10-07（9 個賽日）—— 重建 = live。
- **輔助窗口 S**：2026-04-12 至 2026-07-15 —— 截短窗口，只做方向參考，唔可以救候選，
  但 primary 顯著負都要報。
- **2026-10-11 起係 forward holdout，唔開。**
- §6：喺 F 量每個 ranking metric 嘅 CI 半寬（MDE）同 N arm 嘅 |Δ|（整個 draw leaf 嘅身家）。
  如果部件預算 < MDE 嘅 metric 佔晒，記 **UNRESOLVABLE → NEEDS MORE TESTING（功效不足）**，
  唔記 REJECT；但 primary 點估計負（`primary_regression`）照 REJECT。
- KEEP 要 F 判 WIN（Holm 後），S 冇顯著負，之後仍要 forward holdout 先可以上線。
- 另報：候選 draw 分同現行 draw_score 嘅場內 Spearman（正交性）。

## 配置
- **baseline**：`bc8a7601`（live：先驗 + EXP-20261007-01 rail×組別 ±4，HV V3）
- **candidate**：`docs/experiments/patches/hkjc_arm_official_draw_stats.py`（`DRAW_ARM=replace|blend|neutral`）

## 數據
- **語料**：`hkjc_eval_harness.py run --until 2026-10-07`（36 個賽日入面 35 個；PIT priors）
- **F**：2026-09-06 至 10-07，9 個賽日 / 85 場（剔死欄位後）；baseline Gold 10.59%、Good 16.47%
- **S**：2026-04-12 至 07-15，20 個賽日 / 199–201 場；baseline Gold 13.85%、Good 25.38%
- 覆蓋：F 每匹都有格（fallback 0%），格中位數 29 出賽、三份一 < 20；S fallback 12.5%
- **正交性**：場內 Spearman(現行 draw_score, 官方式分) 中位 0.36（F）／0.29（S）—— 夠正交，唔係重複訊號

## 結果（Stage 4 v3 `fixed_rule`，賽日 bootstrap 2000；pp，名次差係名次）

主窗口 F（重建 = live，85 場）：

| 指標 | A replace | B blend | N neutral（診斷） |
|---|---|---|---|
| Gold | +0.00 [−4.65, +4.76] | −1.19 [−4.82, +2.53] | −3.53 [−13.19, +3.70] |
| Good位 | **−2.35** [−12.94, +6.58] | +1.19 [−2.41, +5.06] | −1.18 [−11.90, +8.24] |
| top3_capture@5 | +1.96 [−0.39, +4.47] | +0.40 [−2.30, +2.96] | +0.39 [−4.53, +5.76] |
| ndcg@5 | −0.23 [−4.67, +3.66] | −0.54 [−3.39, +1.42] | −1.06 [−6.62, +3.79] |
| competitive_recall@5 | +1.39 [−1.31, +4.23] | +0.20 [−1.80, +2.31] | +0.25 [−3.69, +3.73] |
| mean_top3_rank | −0.04 [−0.28, +0.23] | −0.04 [−0.10, +0.02] | +0.00 [−0.26, +0.33] |
| 判決器 | primary_regression | primary_regression | — |

輔助窗口 S（截短窗口，少 2023/24）：

| 指標 | A replace | B blend | N neutral（診斷） |
|---|---|---|---|
| Gold | −2.01 [−5.83, +1.95] | −1.49 [−3.59, +0.50] | **−3.98 [−7.37, −0.50]** |
| Good位 | −4.52 [−11.59, +2.06] | −1.00 [−5.85, +2.99] | **−6.97 [−13.00, −1.95]** |
| top3_capture@5 | −1.51 [−3.70, +0.71] | −0.17 [−1.79, +1.52] | −2.94 [−6.53, +0.50] |
| ndcg@5 | **−2.81 [−5.35, −0.45]** | −0.99 [−2.54, +0.55] | **−3.67 [−7.01, −0.25]** |
| competitive_recall@5 | −1.48 [−3.89, +0.95] | −0.35 [−2.00, +1.28] | −0.83 [−3.59, +1.71] |
| mean_top3_rank | +0.10 [−0.06, +0.26] | +0.01 [−0.05, +0.08] | +0.15 [−0.01, +0.31] |

### 分層（Gold / Good位 差，pp）
| Cohort | A F | B F | A S | B S |
|---|---|---|---|---|
| 沙田草地 | −6.67 / −2.22（45 場） | −4.44 / −2.22 | −0.93 / −6.54（107） | −0.93 / −2.78 |
| 跑馬地 | +3.03 / 0.00（33） | 0.00 / +6.25 | −1.64 / +1.64（61） | −1.61 / 0.00 |
| 沙田泥地 | +28.57 / −14.29（7） | +14.29 / 0.00 | — | — |

### §6 功效
F 嘅閘門 MDE（A 嘅 CI 半寬）：Gold ±4.7、Good ±9.8、capture ±2.4、ndcg ±4.2、recall ±2.8、名次 ±0.25。
部件預算（N：成個 draw leaf 設 60）喺 F：Gold 3.5、Good 1.2、capture 0.4、ndcg 1.1、recall 0.3、名次 0.00。
**六個指標部件預算全部細過 MDE → F 對呢個部件係 UNRESOLVABLE（功效不足）**：
85 場連「完全冇檔位」都分唔出。S（~200 場）分得出（N 嘅 Gold／Good／ndcg CI 全負）。

## 檢查
- **leakage-audit**：PASS —— 格只用 `Date < 賽日` 嘅賽果（同日早場都唔用，同頁面一致：
  10-14 朝早頁面只計到 10-11）；窗口規則同頁面一致（重建驗證）；今場賽道由排位表（賽前）；
  賽果只喺評分之後 join。S 窗口唔係洩漏而係**少資料**（截短），方向係令分數更收縮。
- **golden_scoring**：冇郁（冇 model code 改動）
- **data_contract**：PASS（`./檢查.sh --quick`）
- **退步**：A 喺 S ndcg@5 CI 全負；A／B 沙田草地 Gold 兩個窗口都負

## 結論

按預先登記：A、B 喺主窗口 F 都係 `primary_regression`（A Good −2.35、B Gold −1.19 點估計），
所以 **REJECT**。誠實嘅讀法係：F 只有 85 場，閘門連成個 draw leaf 都睇唔到（UNRESOLVABLE），
所以 F 本身證明唔到好壞；有功效嘅 S 窗口入面 A 明顯差（ndcg CI 全負、所有指標點估計負），
B 所有指標點估計都係負或零。冇任何一個窗口見到改善方向。

**點解失敗**（量到嘅）：官方式分同現行分場內 ρ 只有 ~0.3，即係佢係另一個訊號，
但逐個檔位、三季、中位 29 出賽嘅格太嘈 —— 三份一格 < 20 出賽，收縮 60 之後仍然
令鄰近檔位跳來跳去（例：HV 1800 A 第 10 檔 17 出賽上名 53%）；現行三級先驗 +
EXP-20261007-01 組別修正（門檻 100 匹／20 場）已經食咗穩定嗰部分。
2026-07-05 嗰次（前視 + 凍頁）結論喺乾淨 PIT 重建之下**再次成立**。

**唔好再試**：官方逐檔位統計取代／對半混合現行檔位分。仍然開放：等 2026/27 季
F 窗口累積夠 ~250 場（部件預算先會大過 MDE）再用同一份預先登記重判 —— 屆時
官方頁面嘅窗口會由 2024/25 起，重建一樣準。

**決定**：REJECT（A、B 兩個 arm；F 窗口 UNRESOLVABLE 已註明）
**commit**：未 commit model code；只 commit 記錄同 harness arm／重建驗證 script

## 重跑
```bash
export PYTHONDONTWRITEBYTECODE=1
H=.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py
A=docs/experiments/patches/hkjc_arm_official_draw_stats.py
python3 $H run --until 2026-10-07 --out base.jsonl
for a in replace blend neutral; do DRAW_ARM=$a python3 $H run --arm $A --until 2026-10-07 --out $a.jsonl; done
# 按 meeting >= 2026-09 拆 F / S，再：
python3 $H compare base.F.jsonl replace.F.jsonl --leakage-audit-passed --stage4 fixed_rule
# 重建驗證（對存檔頁面逐格）：
python3 docs/experiments/patches/hkjc_draw_page_reconstruct_validate.py 2024-09-01 -v
```
原始輸出：scratchpad `dsdata/runs/`（唔入 repo）。
