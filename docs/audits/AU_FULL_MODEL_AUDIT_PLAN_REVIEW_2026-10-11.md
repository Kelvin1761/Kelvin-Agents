# AU 全模型審計計劃：執行前覆核

日期：2026-10-11（Australia/Sydney）。結論：**需要修訂後先跑候選實驗**；資料盤點、唯讀診斷同獨立重構準備可以先做。

覆核修訂已整合到 [完整執行版計劃](AU_FULL_MODEL_AUDIT_EXECUTION_PLAN_2026-10-11.md)；後續按執行版嘅 G0–G3 條件與依賴次序開工。本報告保留原覆核證據。

本次只覆核計劃、合約、程式同第一輪文件，沒有跑模型評估、修改引擎、寫 production 資料、commit 或 release。第一輪「全綠／零變化」係原報告嘅聲稱，本次沒有重新驗證。

## 核對範圍同版本

- 原計劃：`/Users/imac/.codex/attachments/3b202f14-8589-425b-a8ce-a7380e34b7b6/貼上的文字.txt`。
- 主 checkout HEAD：`0116c740330db7f02f9d04d2884e211b1d494517`，有大量未提交改動。
- 本機 `origin/main`：`0328f13a9564c787837e3c4aa1cfff19235c9b0c`。本次沒有 fetch；此處不是聲稱已核對遠端最新版本。
- 第一輪 worktree：`/private/tmp/claude-501/-Users-imac-Antigravity-repo/39a67405-0e85-49ba-b4c0-57ec34833411/scratchpad/au-audit`，HEAD `e508754ab9ca40db059eefcbced8fc1986c164f6`，有未提交修正及 B7 候選。
- 採用 `.claude/skills/experiment-review/SKILL.md` 嘅先搜索舊實驗規則；核對 EXP-20260927-02、EXP-20260928-02、第一輪 EXP-20261010-01 同總報告。

## 執行前必修

### 1. 判決版本同乾淨窗口已過時

本機 `origin/main:docs/model-evaluation-contract.md:3–48` 已有 v3，明文要求 2026-10-10 之後新候選用 v3；AU fit 類只用 **2026-08-05 起**嘅乾淨 PIT 段。計劃仍寫「等 HKJC 做好」、一般 fit 由 06-06 起、`au_eval --mode full|walk-forward`。實際已存在嘅選項係 `--stage4-mode v2|fixed_rule|walk_forward_oos`。

修訂：以鎖定 SHA 嘅現行合約為準；Phase V 改成「驗證／補齊現有接口」，不要再平行實作另一套 v3。06-06 起資料可做有清楚標示嘅描述性盤點；不可用它代替現行 fit 評估窗口。舊 v2 判決保留歷史，新候選不再開舊 terminal。主 checkout 同舊 audit worktree 嘅文件落後，不能直接讀它們就認定現行仍然係 v2。

### 2. v3 mode 不會自動令預測變成 OOS

`origin/main` 嘅 `au_eval.compare` 仍以同一個 `cand_scorer` 重評全語料，再將 mode 傳入判決器。`evaluate_full_record` 檢查 mode、長度、leakage flag，沒有核證每筆 fit cutoff、配對 race ID、資料指紋，亦沒有自動執行 Holm／cohort guardrail。`holm_adjust` 存在，但 WIN 路徑沒有呼叫它。

現有 `au_matrix_refit.cmd_walkforward` 按場數切窗，會切開同日；無共識時跳過整個測試窗。它不能直接當成計劃要求嘅逐日 OOS 預測器。

修訂：在 producer／wrapper 強制輸出並驗證 `race_id`、賽日、輸入 hash、profile hash、fit 最後賽日、可用時間、baseline/candidate 排名；全部 fit 日期必須早於預測賽日。所有統計、標準時間、tier、缺失值校準、shrinkage 同參數選擇亦要隨 fold 重建。無候選時輸出預先登記嘅 baseline fallback，不能省略困難窗口；warm-up 排除範圍事先鎖定。配對以 ID join，不能只驗場數。未補齊之前只報診斷，不報可上線 WIN。

### 3. B7 不可混入 §7／Phase A baseline

第一輪 worktree 已將 `WC_AU_JOCKEY_NO_EVIDENCE` 預設設為 **46.86**。呢個值由 dev 擬合，屬 fit 類候選。scoring 註解以「全場 AUC holdout +0.0006」聲稱 `RANKING_WIN`，但 v2 登記列表包含 `top5_pairwise_auc`，不包含全場 AUC，而且 RANKING_WIN 要兩個合資格訊號。

目前 EXP-20261010-01 B7 段只有登記，未附完整結果／Stage 4 JSON。因此現有材料不足以確認該判決；這不等於證明候選無效。其測試亦明言 golden 120 匹沒有這類 runner，故 golden 全綠不能證明 B7 排名不變。

修訂：B7 獨立 patch／profile、預設不啟用；Phase A 對照須明確鎖 `WC_AU_JOCKEY_NO_EVIDENCE=60`，並鎖所有其他開關。補齊舊結果後只作歷史記錄；新研究按 v3 walk-forward 登記，不能把全期寫死 46.86 標成 fixed_rule。

### 4. 禁賠率指示未清理完整

Phase 0 仍有市場 SP 對照／價位段 AUC，Phase 4 有 $21+ 群體，4a 有市場維度，4b E 以市場差距立論，Phase 5 又要求價位段 AUC。開頭雖說刪除，後面執行清單仍會令 agent 跑它們。

修訂：從新執行範圍、候選登記、報告驗收一併移除。保留舊文獻但標歷史。現行 §7 原文仍包含 SP cohort，與本計劃禁賠率要求存在合約層衝突；必須獨立記錄已批准嘅適用範圍／非市場 guardrail，不能靜靜改把尺。Gold／Good 定義維持 canonical。

### 5. Phase A 單一「角色」會改變 safety rail

`origin/main` 嘅 class_score 透過 matrix 0.15 入排名，卻刻意留在 `REPORT_ONLY_FEATURE_KEYS`，避免更改證據厚度計數。因此由「入排名」自動推導 `ABILITY_FEATURE_KEYS`、report-only 同 thin-evidence keys，會破壞現有語義。計劃「9 入分 + 9 報告」亦不能作 registry 驗收真源。

修訂：spec 分開記 `contributes_to_score`、`counts_as_evidence`、`shown_in_report`、missing provenance／fallback、情境 overlay。保持所有既有特殊規則。先以實際資料依赖建立清单，再抽 registry；不要同時改分數、缺失值、gate 門檻。shadow profile 不能改 live coefficient budget／歸一化。按兩個 engine 分開實作。

### 6. 先凍結資料，補 CSV 不等於恢復賽前狀態

copy data-root markers 會令 worktree 指向 production 同一份資料；production `--fill-missing`、重新 calibrate、再 dump 可能改變之後比較嘅輸入。後補賽果欄位可用作標籤／過去賽果統計，但後抓 people stats、speedmap、career summary 不代表當日已知。

修訂：先建立不可變 baseline 資料副本／manifest，記 race/runner ID、日期、來源版本、檔案 hash、捕獲時間、排除原因。CSV 補數先 dry-run、備份、驗唯一鍵及 identity join、欄位覆蓋／衝突，再獨立 apply。每個 PIT lookup 用當時可用版本；沒有捕獲證據就 FLAG。禁止以目前資料覆寫既有賽前快照。

### 7. Forward holdout 日期及揭盲規則未足夠

AU 計劃指定 2026-10-11 起，但合約呢個日期明確例子係 HKJC；本次沒有證據確認 AU 10-11 賽果未被其他 review／monitor 使用。只寫「每個 family 開一次」不足以決定何時可以開。

修訂：候選演算法／參數搜尋範圍／fallback／profile hash 鎖定後，才開始收不可變 prospective predictions。固定最少場數、賽日數、覆蓋、截止日及揭盲點；未達標記 PENDING_FORWARD，不當 REJECT。常規營運可看結果，但候選成效不得被反覆揭盲後繼續調參。不得借歷史重新 dump 假冒 forward prediction。

### 8. 候選 family、多重比較同 §6 要寫成可執行規格

「逐個加，再試最好兩個」仍包含資料選擇；F/R/C 亦未列所有 arm、search budget、交互、缺失指示、fit 程序。上限 12／提醒風險不能代替 Holm。計劃將 budget < MDE 一律判 UNRESOLVABLE，但 §6 原文係限制 **ranking metric**，不能阻止已有 primary 證據。

修訂：每個 family 鎖假設、arm 列表／組合挑選算法、seed、搜尋範圍、費用上限、指標、cohort、p 值計法及 Holm family。單特徵、新權重重 fit、單特徵 + 重 fit 分開量；兩特徵做 ablation。§6 對每個排名指標登記 budget／CI 半寬／資訊性，不能事後救候選或把新資訊「live 權重為 0」誤當預算為 0。Holdout 不參與挑 arm。

## 同時應修正嘅設計細節

1. **Phase R 立論**：HKJC 有高 race_shape 權重，不證明 AU 權重 0 不合理。AU 舊 speedmap／draw 有 REJECT 記錄；重試要逐項列新增 PIT 來源、覆蓋改變或結構假設，不能只憑「更多語料」或跨平台係數。低相關／高單 leaf AUC 只係診斷，不能直接代替增量 A/B 判決。
2. **檔位比例**：原始 barrier ÷ 實際 runner 數在退出馬後可能 >1。保留原抽檔位、有效相對檔位、實際馬數及語義；如用 percentile，從有效起步位排序計 `(rank-1)/(n-1)`，處理 n≤1。切勿只靠密集化重新定義物理起步位。shrinkage 曲線需處理 n≤n0、分母及範圍；n0/c 若 fit 也屬 OOS。
3. **H 顯示校準**：改 missing evidence 計數會觸發 #1/#2 swap，係排名改動，不能聲稱純顯示。Gold／Good 不變不代表 top1／完整排名不變。D1/D2 顯示門檻從結果校準，仍需獨立時間驗證及明確語義；與安全欄另列。
4. **速度 PIT**：`au_unused_field_power._speed_standards` 有掃全 root 建 median 嘅路徑。用它做新 speed 訊號前，確認標準時間、going adjustment、benchmark 也按 cutoff 重建；不是只截斷馬匹往績日期。
5. **性能測量**：extract 含網絡及 cache 波動；cProfile 不能單獨解釋晚間排程延時。用凍結輸入量 Python hot spots，另記 live wall-clock、retry、冷／暖 cache、I/O；多次重測取中位數。performance-only 改動須比較完整輸出及排名。
6. **測試與版本**：Phase A 要 full-corpus ability ≤1e-9、完整排名／tie-break／swap 一致、golden 不改，加缺資料／退出馬／換騎／going 邊界案例。`verify <0.01` 只證 replica 接近，近乎平手仍可能換位。A/A 恒等測試不足以量假陽性，另加預先固定種子嘅 null tests；洩漏案例應靠 provenance gate 拒絕，不能要求統計 KPI 自動辨認洩漏。
7. **Release 範圍**：本次請求係 review，沒有授權執行 plan 內嘅 production backfill／release。計劃「只報告」同 A/§7 release 例外要寫明。未來如明確授權 release，`./保存.sh --path … --expected-result …` 按當時 gate 執行；目前 enabled=true，不能預設流程必然等 `/approve`。混在同一檔嘅 §7／B7 須拆 clean patch，單靠 --path 不能隔離 hunk。
8. **結果狀態**：把「現狀保留」、「候選通過」、「來源不存在」、「不適用」、「等待 forward」分開。矩陣無空格可用 N/A + 原因，毋須硬填 KEEP；舊 KEEP 引用舊 EXP，毋須重開舊 terminal。已結束 shadow 保存 manifest／歷史，僅停用活動項目，不刪審计證據。

## 可直接取代原計劃嘅執行次序

1. **鎖版本／來源**：選定 main SHA；保存第一輪 patch 和舊結果。凍結語料、環境開關及 baseline；B7 預設停用，class_score 等 live 設定明確記錄。
2. **修復評估地基**：核對已存在 v3；修日期邊界、逐日 OOS dump、ID/hash 配對、fallback、Holm、cohort。未完整先只出診斷。
3. **資料修復**：CSV 先在副本補數並驗證，as-of 審計逐欄清 FLAG；production apply 另走已授權流程。補數前後以不同 dataset version 留底。
4. **Phase A 純重構**：registry 抽取同 model 行為變更分開；保留分數貢獻／證據計數／顯示三種語義，full-corpus 等價及整合測試通過。
5. **先預登記，再做 F → R → C**：全部用乾淨 08-05 起資料，按日 fit 所有衍生統計；明確對照 refit-only，執行 family 校正及 ablation。不足功效標 UNRESOLVABLE。
6. **H 分流**：E2E、快照保護、reflector 版本／歸因可先做；顯示校準獨立驗證；任何 safety swap 改動進 ranking 候選流程。
7. **凍結候選，收 forward 證據**：歷史 WIN 與 forward 待確認分開報。達預定樣本點一次揭盲；不因 deadline 未到而無限重跑舊資料。
8. **交付**：九問矩陣、EXP／JSON／manifest、每項檔案與風險、rollback、尚缺資料及重測條件。改 code 後跑 `./檢查.sh --quick`，交付前跑 `./檢查.sh`。本輪審計有界終點係「每項有證據狀態」，不是無法證明嘅「完全優化」。

## 重現本次覆核

```bash
git rev-parse HEAD origin/main
git worktree list --porcelain
git show origin/main:docs/model-evaluation-contract.md
git show origin/main:.agents/skills/au_racing/au_wong_choi_auto/scripts/au_eval.py
git show origin/main:.agents/skills/shared_racing/model_evaluation_decision.py
git show origin/main:.agents/skills/au_racing/au_wong_choi_auto/scripts/au_matrix_refit.py
```

第一輪 B7 對照資料：audit worktree 嘅 `scoring.py` 未提交 diff、`tests/test_jockey_no_evidence.py`、`docs/experiments/EXP-20261010-01-au-full-model-audit-preregistration.md:163`。本報告沒有將未知嘅 B7 結果補成已驗證判決。
