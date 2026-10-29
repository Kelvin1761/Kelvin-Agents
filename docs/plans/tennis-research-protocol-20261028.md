# Tennis 統一研究：資料、對照、實驗及判決協議

2026-10-28（Australia/Sydney）凍結設計；2026-10-29 已進入執行，狀態見主計劃。本文件保留執行前定義嘅次序及預設設計；實際 data/code SHA、樣本、baseline 與 power 由各批 immutable manifest 記錄，先開始相應階段。唔因候選結果改本協議，亦唔將本文件當績效報告。

入口：[一頁主計劃](../../tennis-research-execution-plan-20261028.md)。來源：[八項目筆記](tennis-external-project-review-notes-20261028.md)、[來源及 frozen URL manifest](tennis-external-project-sources-20261028.json)。新項目可加筆記；已鎖定批次唔中途加 arms。

## 1. 研究界線及權威

- 本批做賽前 ATP/WTA 勝負，先 main tour；Challenger／ITF 只報 coverage 及適用限制，唔將成功外推。Props 係之後獨立 family；走地模型暫停。
- 判決依據係 [frozen tennis-v1](../../.agents/skills/shared_wong_choi/resources/evaluation_rulers/tennis-v1.json) 及其 [authority](../../tennis-wong-choi/docs/performance-audit-2026-08-21.md)。[賽馬 evaluation contract](../model-evaluation-contract.md) 屬 AU/HKJC，唔搬其樣本／重抽單位過嚟。
- Ruler 所記 baseline commits 係歷史依據，唔假定係今日 approved runtime。先由 release manifest／runtime 確認 production SHA、model release、feature/config 及資料根；不同就同時記錄並解釋，唔靜靜換基準。
- `props/strategy.py` 嘅 recommendation tiers／profitability 替代路徑係營運選注邏輯，唔取代模型 promotion ruler。保留原政策，分開報告。現有 `elo-v2-start-of-day.surface-0.35` forward shadow 保持原版本／起點／計數，唔混入新試驗。
- Calibration、ROI downside、CLV、coverage 嘅實際 gate 數值／缺值政策，須追溯已批准 contract 並凍結 hash。若只有定性要求或同 runtime 衝突，先開**獨立規則澄清紀錄**；未解決可審計資料，唔可以邊睇候選結果邊定數值或聲稱過 promotion。
- 計劃於 2026-10-28 凍結時未開始訓練、訂閱 API、改排程、落注或部署。其後執行進度／交付另記主計劃及 audit；研究可用其他莊家歷史資料／ROI，按用戶 2026-10-28 補充，唔倒改舊實驗約束及判決。

## 2. Gate 0–2：來源、語料及 baseline

### 一次凍結，保留完整排除流水

輸出 `run_manifest.json`、`source_manifest.json`、`cohort_flow.csv`、`excluded_rows.csv`、`feature_availability.csv`。Raw／DB／逐場輸出放 repo 外，repo 收方法、hash、摘要及可重跑命令。

Manifest 必有：執行 UTC／Sydney 時間、repo/production/model/config/ruler SHA、Python／依賴版本、命令／seed、來源精確 URL／commit／檔名、下載時間、涵蓋期、授權／attribution、local path、bytes、row counts、SHA256、split match IDs hash。API key／私隱資料唔入記錄。

- 生產 DB 唯讀；用 SQLite consistent backup／projection 建一份研究 snapshot，唔對運行中 DB 用普通 `cp` 假設 WAL 一致。先解決 runtime path，唔用 worktree 同名 DB 冒充 live。
- 先套 observation cutoff，再按 [canonical history policy](tennis-canonical-history-20261027.md) 去重。同場雙方視角、mirror、多 book 係相關觀察；衝突留置，唔按結果揀來源。配對＋日期只係候選 group，唔係完整 event identity。
- 分清 `event_time`、`available_at`、`ingested_at`；賽事日期唔等於當時已發布。只得 tournament start date 嘅歷史資料可沿用 21 日隔離作 **dev 敏感度研究**，唔升格為已證明 PIT。
- 核對身份／賽果／賽制、排名生效日、surface、points、minutes、retirement／walkover、當時報價；缺值、0、固定 sentinel、過期分開記。
- 固定 row-flow：raw → canonical → 時間可用 → label/contract eligible → baseline parity → feature coverage → market eligible → settlement eligible；逐步列 N／原因／tour/surface/level。不以賽後 stats 有無篩選當場預測。
- 來源缺失標 `MISSING_SOURCE`，停止依賴嗰份來源嘅 arm；唔靜靜縮 corpus、換 mirror 當新樣本或用不同群體比較。

### 三種對照及完整重現

| 對照 | 用途 | 保存資料 |
|---|---|---|
| B_live：執行時 approved model | 現役增量／forward | snapshot、selection orientation、raw probability、nudges、market probability、segment-risk shrink、最終 probability |
| B_simple：同 cohort／同訓練流程簡單 logistic | feature/head attribution | 共同 feature matrix、fit 範圍、preprocessor、係數／artifact SHA；唔當 B_live 替身 |
| B_market：同書同 snapshot 去水市場 | 主要市場增量 | book、兩邊價格、market/line/selection、quote ID、captured_at、start time、devig 版本 |

Stored replay 先重現 B_live 最終機率至 **≤1e−6**；EXP-20261027-06 已證明漏方向／risk shrink 會錯。失敗紀錄隔離並列原因；不得用今日 Elo／level／折扣補舊 snapshot。報全體及 parity subset coverage，唔將小 subset 稱全模型。

候選同對照用相同 eligible IDs／價格／outcome。缺 feature 用事前 fallback 加 missing/count flags；complete-case 診斷亦兩邊同一 subset，並報全體效果。先過 A/A、A/B swap、當場／未來結果注入不影響較早預測、同日凍結、source cutoff、冷啟動、train/inference parity。

## 3. 多 book 及 ROI（C10）

- 可以用其他 book 逐場賠率／賽果訓練、校準及開發期策略研究。公開總 ROI 唔係逐場標籤，唔當球員實力特徵。收益若作 auxiliary target，只用訓練期，唔將同場事後收益輸入當場模型。
- Book roster 固定為 snapshot 中全部可識別、同書兩邊成對、同 market/line/quote type 嘅書；不按 ROI 揀 book。每場多 book 訓練權重合計 1，全部 rows 同一時間 fold，bootstrap 同一 match cluster。
- 明示 opening／closing／unknown。Closing 只作收市診斷或訓練期 auxiliary target，不能倒流入較早預測。無 captured_at 價格只作未驗時鐘嘅 dev；`MaxW/MaxL` 不拼成單書可執行價。
- 有可信時鐘先採 earliest verifiable pre-match；SQLite `MIN(id)` 只用於同場／書／合約、已驗賽前且 append-order 可信嘅群體，唔自動證明賽前。走地價排除。
- 先鎖 quote eligibility、vig range、retirement／void／push 規則，兩邊相同。CLV 只用有時鐘、同合約 closing benchmark，缺時計 N/A。
- 固定研究 policy：EV>0、每場最多一個勝負方向；兩邊有 edge 取較高 EV，完全相同按 canonical selection ID；1u 平注，不掃 edge／odds cutoff／Kelly。Production policy 另原樣 replay，唔混算 ROI。
- 全 book、逐 book、Sportsbet 分報 P/L／stake／N／ROI／drawdown／不確定性。Multi-book 訓練須有 **Sportsbet-only inference** 測試；需其他書即時價嘅候選明列依賴，唔假定符合目前輸入。

## 4. 時間切分及統計

- 已讀 2020–25、2026 歷史及舊 holdout 全部標 **SEEN_DEV**，包括 2026-07-15／08-07 舊起點；擴充 book 唔重設 untouched。
- 沿用 2020 暖身、2021 起 expanding training；外層 dev 五段：2023H1、2023H2、2024H1、2024H2、2025H1。2025H2 如用只係已看確認診斷；額外年份先記資格，唔替換失敗 fold。
- 有選擇嘅 arms 只用外層窗之前兩個完整半年度作 inner chronological validation，inner training 只讀當時可用資料。Scaler／imputer／feature selection／calibrator 只 fit training。Fitted head 凍結於窗起點；online Elo／歷史特徵只按可用時間更新。
- 預設無 grid search。B_simple：無截距 L2=1 logistic、A/B 差分與 missing flags、training-fold 標準化。鎖 loss normalization／optimizer tolerance／版本；原研究 head 不同就加原控制，唔將 refit 增量歸功 feature。
- 不能用差分嘅設計先提供 swap-equivariant 表達；唔靠 outcome 方向欄名。Book／point／A-B 鏡像唔跨 folds。
- `gain = control_loss − candidate_loss`，正數較好；對 B_live、B_simple、B_market 各報 LL/Brier。先固定每場方向／family 聚合，match bootstrap **4,000 次、95% CI、seed 20260826**；prop lines 不當獨立 matches。
- 預登記有效性比較（arms／主要指標／基準）用 Holm 控制 family-wise α=.05；歷史 F03–F09 合共一個比較 family，唔每批重設 .05。總比較清單於 F03 前凍結，前置 gate 失敗嘅 arms 列未執行，不縮比較名額。未調整 95% CI 照報並標示。AUC／accuracy／drawdown 只描述；C13 係數符號唔代替配對勝出。
- 開發候選需 LL/Brier 對直接控制五段均不退步、pooled 兩項 gain 正且多重比較過關；失敗即 `REJECT_DEV`，不換窗／子群／單項救主候選。未贏市場或 CI 跨零可保留資訊診斷，不能稱盈利改善或直接 promotion。
- 校準固定報 10 個等寬 bins、ECE、intercept/slope，沿用已批准數值 gate。分層 tour、surface、level、odds；另報雙方歷史數 0／1–4／5–19／20+、missing。分層只診斷，不事後開下注條件。

## 5. 實驗批次及 C01–C17 去向

F 編號係研究批次，唔係 betting family。每批開始先搜尋 `docs/experiments/`，分配未用 `EXP-日期-編號`，鎖 arm／直接控制／資料 IDs／參數／停止條件及 SHA；未鎖不跑。設定係待驗假設，唔係聲稱最佳值。

| 批次 | 候選／來源 | 固定設計及依賴 |
|---|---|---|
| F00 基建 | C04/C10/C17；P01–06 | 第 1–4 節時間、identity、train/inference、ROI lineage、parity；先做，唔算模型改善 |
| F01 資料資格 | C07/C16；P02/P05/P08 | MCP、兩種 PBP 分開 schema；metadata／sample 後才全量品質。identity/clock/licence/coverage 未過不入 feature corpus |
| F02 kernel | C08；P02/P04/P07 | 現有 kernel 對獨立 DP／MC invariants；BO3/5、1-2-2、跨盤首發、歷年7/10-point TB、terminal state。先核對已修 EXP-20261026-05，唔重做舊修正 |
| F03 去水 | C02；P01 | 同書同價 proportional 控制，power／Shin 各一 arm；不改 winner head。先驗收斂／swap；inner-dev 選一，外層比較 |
| F04 surface Elo | C03；P01/P03 | 原 approved 固定混合控制；只改 surface 權重 `n/(n+20)`，n=此前可用 canonical surface matches。K／更新規則／nudges 不動；20 不掃值；獨立於舊 shadow |
| F05 serve profile | C06；P02/P04 | 同 cohort／head。控制等 match-weight 無時間衰減；R=half-life180日；E=真實 point exposure；S=training-only tour prior、100 pseudo-points。R/E/S、RES、合併 leave-one-out 共7候選 |
| F06 對手強度 | C12；P03 | 共同 Elo／排名／opponent-bucket 控制，只加最近10場對手當場前 Elo 平均相對自身當時 Elo 差及 count；無歷史=0加flag，不換 final Elo |
| F07 workload | C14；P01/P04 | rest-only 控制；W1=14日實際minutes；W2=14日盤數＋距上場結束hours；W1/W2/合併，單項亦作消融。缺時計不填假hours，不用盤數推斷minutes |
| F08 H2H | C15；P04 | Elo-only、+raw H2H 控制；候選 `sum(y_i−p_i)/(n+5)`，只此前meeting、當時pre-match Elo、swap改號。全場地，不掃window；缺當時Elo不計該meeting並報coverage |
| F09 head／市場 | C11/C01/C13；P01/P03/P06 | 開發合格且 inference 可得嘅同 features；先simple、再nonlinear、再fixed-market-offset。C13條件資訊只診斷 |
| F10 joint props | C09；P02/P07 | F02及合格serve/exposure之後；先totals/game handicap，再set families；ace等exposure/label/clock齊。每family獨立登記 |
| 去重／暫停 | C05；P01/P02及舊實驗 | Serve/rank/game-share只去重；舊REJECT、走地、未校準傷患／情緒、layoff decay暫停，不作救援arm |

**F01**：P08 與 Aneeshers 相同 blob 唔重複算資料。PBP 字串與 Slam matches/points 分別驗 keys、順序、發球、比分、TB、terminal label、retirement、空值／sentinel；MCP 另量選樣偏差。來源額外資料效應用原來源 vs 加新來源獨立對照，唔混入 F05 權重增量。

**F02**：DP/解析差 ≤1e−8；MC 固定種子、每 case 100,000 simulations，用預登記 case 數嘅 Bonferroni family-wise .01 simultaneous binomial intervals 比較 DP。先固定 symmetric/extreme/BO3/BO5/TB grid，唔按誤差挑 case；記耗時／peak memory。外部引擎已見缺陷，唔整個當 oracle。正確性修正另寫 bug／影響比較，唔當獲利候選。

**F05**：各率用真實 numerator/denominator，service games 唔冒充 points；S 用對應 exposure。所有 arms 同 lookback=最多此前25個 canonical matches；無 denominator 全部同樣 fallback／報缺值。假設係時間／曝光／prior，與 EXP09 已失敗嘅 opponent-adjusted online S/R 更新有實質分別；若實作等同舊候選就取消，唔重試。

**F09**：非線性只試一個 histogram gradient-boosting head，learning_rate=.05、max_iter=200、max_leaf_nodes=7、min_samples_leaf=30、l2=1、early_stopping=False、seed=20260826；同 logistic 用相同 matrix，鎖 library 版本。Offset：`logit(p)=logit(p_market)+beta·x`，market 固定 offset，beta ridge=1、無截距；對 market-only 及同 x tennis-only logistic 分別比較。係**明示價格輸入模型**。與舊 props residual 係不同目標／family，仍先查舊證據。

F04–08 通過嘅單項先合成一個鎖定組合及逐項 leave-one-out；邊際增量未證實就不納入最後候選，原完整組合結果照報。F09 feature-set 喺睇 F09 結果前鎖定，不跑所有組合。歷史揀選仍係 dev，每 market family 最多一個最終候選入 forward。

**F10**：同一 joint distribution 推導 winner／set score／total games／handicap；驗 sum=1、complement／swap、合法比分、邊際一致。同 winner probability 可以有不同 hold/total，唔當單一勝率已識別 props。Price contract 不明、player total 被當 match total、retirement/void 不可重現嘅 family 暫停；point rows 唔補足市場／settlement 證據。

## 6. 新 forward：凍結後才開始

凍結 data/features/code/model/calibration/price policy、候選及基準後，將**下一個 Sydney 午夜**轉 UTC 記入 protocol，先於起點登記；錯過就順延，不回填。唔預寫 2026-10-29 當 untouched。每份 prediction 保存 raw／final、來源及可用時間、market snapshot／SHA；結果後才 settlement，backfill 不算 frozen evidence。

- 每 family 獨立 match 數 `N=max(600,ceil(power_N_LL),ceil(power_N_Brier))`。Dev paired loss variance、雙側 family-wise α=.05、power=.80；design MDE 固定 LL=.002、Brier=.002，**只作樣本規劃，不改 ruler 勝出門檻**。凍結比較總數以 Bonferroni 保守 α；`power_N=(z(1−alpha/2)+z(.80))²*s²/MDE²`。非有限 variance／無法估 N 就暫停；既有 guardrail 若需更多 N 取最大。
- 鎖最大收集期365日；達 N 後一次正式判決。期滿未夠 N=`NEEDS_MORE_TESTING`，不降 power／重試顯著。日後延長另記協議，已睇資料不當新 holdout。
- 每200場只查輸入／coverage／settlement／安全stop，不反覆統計揀贏家。現有 stop 如觸發照停；data incident freeze、修正另版本，唔覆寫舊預測。Shadow 不因此變實盤。
- 報 family-specific market LL/Brier、CI／多重比較、calibration、CLV、ROI downside、固定短期 ROI、coverage，另同 B_live 配對避免退步。CI跨零／underpowered／閘不齊=不確定；明確退步=REJECT；門檻衝突未解=停promotion。
- 通過只標 `ELIGIBLE_FOR_RELEASE_REVIEW`，再經 model/regression/leakage/release gate；研究唔自動改正式模型。

## 7. 工具、儲存及交付

現有工具只作起點，唔冒充已有完整統一 runner：

```bash
# repo root；先設定已驗證 snapshot 及含所需依賴嘅 Python 絕對路徑
: "${TENNIS_RESEARCH_DB:?Set verified research snapshot path}"
: "${TENNIS_RESEARCH_PY:?Set verified Python executable path}"
PYTHONDONTWRITEBYTECODE=1 "$TENNIS_RESEARCH_PY" tennis-wong-choi/scripts/audit_model_data.py --db "$TENNIS_RESEARCH_DB" --with-roi
"$TENNIS_RESEARCH_PY" .agents/skills/central_wong_choi/scripts/central_wong_choi.py corpus-audit --domain tennis --active-sqlite "$TENNIS_RESEARCH_DB" --json
```

`audit_model_data.py` 唯讀盤點唔代替 earliest-price／stored-parity harness。`tune_elo_backbone.py`、props evaluation scripts／過往研究分支可重用部件，先驗相同 eligibility／metric；唔跨 harness 直接比數字。`--quick` bootstrap 只掃描，唔判決。

**要實作嘅研究 harness**：snapshot/cohort export、完整parity、availability、grouped nested time splits、arm registry、paired rows／multiplicity、forward power/protocol lock、joint kernel checks。先提供 help／schema、A/A／leakage fixtures。本計劃未建立 CLI，唔提供假 runnable 命令。

- 大型實驗先 `df -h /System/Volumes/Data`，少過10GB停；驗證外置碟真係掛載。大型暫存／TMPDIR 用 `/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-research-<run-id>/`；archive約0.8GB亦要計clone／解壓／複本後大小。
- 一份 immutable corpus，arms順序跑、只存細 predictions/artifacts，不複製整庫。一個fold dry run量CPU/RAM/disk；空間不足停，唔轉內置碟。保留 raw/hash/protocol／失敗結果，清可重建大暫存。
- 每批輸出：`protocol.json`＋lock SHA/time、`predictions.parquet`、`paired_metrics.json`、`subgroups.csv`、`calibration.csv`、`roi_by_book.csv`、`artifact_manifest.json`、`docs/experiments/EXP-*.md`。未取得指標明示 N/A／原因。
- 最後 independent replay／leakage review、消融 attribution、全部arms completeness；跑 `./檢查.sh --quick`／`./檢查.sh`。方法／結果文件 exact-scope 保存；未完成／失敗 model code 只保存非main分支，唔release失敗模型。

## 8. 舊結論及完成狀態

EXP-20261009-01 C0/C2 係舊歷史KEEP、forward未完成；layoff decay REJECT。EXP-20261027-06 nudge-off、-07 game-share、-08 rank、-09 opponent-adjusted S/R、EXP-20261026-04 fresh-WTA／90日硬截保持原判決。唔換 book／窗／cutoff 重開失敗候選；新方法寫實質分別及獨立比較。

八項目、**C01–C17 全部有去向**。來源、次序、資料規則、對照、消融、判決、停止及交付已定義。Baseline／row counts／power 係第1–3步產物，唔捏造結果，亦唔將計劃當已跑完。可以開始資料／基準階段，過相應 gate 後先進下一批。
