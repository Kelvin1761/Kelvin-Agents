# NBA Wong Choi 全面模型及工程審核

日期：2026-10-23（悉尼）｜基準：`8f09e341`｜分支：`codex-nba-full-audit-20261023`

## 判斷

現役管線已有唔少正確防線，但**未有足夠證據證明現役模型喺今季有正期望值，亦唔應以「穩膽」名稱代替風險驗證**。
本次確認並修正 3 項工程缺陷；另列 9 項待處理問題／限制。冇調參、重訓或更換模型，亦冇聲稱命中率／ROI 改善。

最優先後續係資料新鮮度同實際 SGM 報價核對，其次先做季初校準驗證及 ML 重建。繼續改手工加減分，未必能解決呢幾個根本問題。

## 範圍、方法及限制

- 審查現役 orchestrator、Sportsbet／NBA extractor、季節／身份處理、報告生成、10-Factor、校準層、ML predictor／訓練 builder、MC、SGM、排程、snapshot、reflector、market ledger、reliability、ROI 及 dashboard 匯出嘅主要路徑。
- 對照 NBA 最近實驗及已合併修正，避免將舊缺陷再報一次。舊 analyst／backtester／report generator 係旁支，唔當成現役主引擎。
- 全部 NBA 專項測試；先量基準，再建立失敗重現，最後跑完整 repo 檢查。合成測試只證明程式行為，唔證明投注表現。
- 唯讀抽查本機 2026-10-21／22／23 market ledger，以及當日兩份 extractor JSON；來源路徑、SHA-256、行數及摘要見同名 `.json` 證據檔。
- **唔係完整歷史回測**：未掃齊 HOT／catalog-verified WARM 語料，未重建每場歷史版本、未查遠端帳簿、未重新抓 live API／Sportsbet，也未核實每個已安裝 launchd job 嘅運作。唔將本次 code scan 當成完整營運健康認證。
- 本機資料會繼續增長，證據檔係審核時點嘅讀數；append-only ledger 可按證據檔嘅 `source_bytes` 讀取前綴，核對 `source_sha256`。以下「未發現」只限已讀取範圍。

## 現役模型係乜

1. 先計 L10、10-Factor、usage guard、ML 及 MC。
2. `nba_prob_layer.json` 預設啟用 C 層：`logit(p) = a_stat + 0.755×logit(1/price) + 0.140×logit(L10)`，最終球員機率被呢層取代。**市場賠率係已明文登記嘅模型輸入**，唔係隱藏 proxy。
3. Hybrid ML 調整預設關閉；ML 仍計算及記錄。fit-layer A 只係 shadow，同季至少 10 場／平均分鐘門檻不足就 null。
4. SGM 選腿仍受 L10／L5、波動、MC guard、賠率目標及組合 EV 閘影響。C 層唔代表其他選擇規則已獲驗證。
5. 組合 live 機率仍係邊際機率相乘再扣手工懲罰。共享比賽劇本 joint MC 只係 shadow。

## 已修正（本次）

### F01 · P1 · 模型開關改咗，cache 仍可能重用舊模式報告

位置：`nba_orchestrator.py:337`，`report_inputs`。

原本 cache hash 包含盤口、extractor、renderer、模型檔及 Git revision，但冇包含 `NBA_WC_ENGINE`、`NBA_WC_PROB_LAYER`、`NBA_HYBRID_ML_ADJUST_ENABLED`、`NBA_FIT_LAYER_SHADOW_ENABLED`。
同一 commit 下關閉校準層／改引擎／改 shadow 開關，仍可以回傳之前嘅報告；有關 rollback 或實驗對照會行錯模式。

修正：cache schema 升到 2，將四個 runtime 開關寫入輸入指紋。舊 cache 會重建一次；模型公式不變。
驗證：四個開關各有一個「原先可重用，切換後必須失效」回歸測試。舊 code 四項全失敗。

### F02 · P1 · 暫時未配對賽果會永久佔用結算 key

位置：`nba_daily_auto/nba_market_ledger.py`，`settle`。

原本球員未搵到等情況會 append `outcome=unresolved` 嘅 `settlement`。Ledger 係首次寫入為準；下一次即使 box score 已完整，都唔會再處理嗰條腿。

修正：只 append `hit`／`miss`／`void`；未解決項目保留為待結算，下次重試。已完成結算仍然首次寫入為準。
驗證：同一 Final brief 先用空球員表，應寫 0 行；補回球員後寫 3 行，再跑寫 0 行。舊 code 第一輪錯寫 3 行。
實際影響：本次三日 ledger 冇見到已寫入嘅 `unresolved`，所以**冇聲稱已修復任何歷史結算**，亦冇改 live ledger。其他未抽查位置若已有舊 unresolved，仍須獨立設計 append-only 修復。

### F03 · P1 · Ledger 嘅完場檢查接受缺失或否定狀態

位置：同上，`settle`。

原本空 status 會直接放行；只要包含 `final` 字眼亦放行，包括 `Not Final` 同 `Final pending`。配合首次寫入規則，可以永久凍結未完場結果。

修正：只接受 Results Brief 已使用嘅 `Final`、`Final/OT`／`Final/2OT`、`Final (<source>)` 格式。
驗證：缺失、空字串、進行中、否定及 pending 狀態全部唔結算；五種合法 Final 格式照常結算。舊 code 嘅缺失、空字串、否定同 pending 四項失敗。
邊界：呢個只係 ledger 嘅最後一道防線；最終比分／box score 真實性仍依靠上游 finality 判斷。

## 待處理／模型風險

### F04 · P1 · 傷停／陣容 cache 冇時間新鮮度保證（新確認）

`extractor_cache_current` 主要核對結構、空資料同 preseason contract，冇核對 `extracted_at` 年齡。`process_single_game` 遇到結構完整嘅 extractor 就重用；排程 refresh 明確重抓盤口，但唔保證重抓傷停。
因此 warmup 嘅傷停可以一路用到 production／final refresh；傷停配對邏輯修好，亦唔等於資料係最新。

證據：當日 CLE_PHI 抽查檔標示 `2026-10-22T19:00:29`，仍存在於翌日分析目錄。呢個時間本身唔證明球員狀態錯，但 code 冇防止過期。
建議：將慢變歷史數據同快變傷停／陣容分開，對快變來源設新鮮度要求；測試 warmup→final refresh、來源失敗、已開賽保護及當時時間。先驗證舊／新實際資料差異，再處理選腿影響。

### F05 · P1 · SGM +EV／Kelly 依賴單腿乘價，未以實際組合價作閘（已知限制仍存在）

`compute_combo_ev` 用單腿價相乘計 EV；`gen_combo_section` 用同一價顯示回報同 Half-Kelly。真實 Sportsbet SGM quote 係 snapshot 後記入評估 ledger，冇回流到發佈 EV gate。
如果組合價低過乘價，可能出現乘價 +EV、真價非 +EV；報告尾註只提醒價格可能不同，未解決 gate 同注碼嘅基礎。

本次唔聲稱已實際出現呢個反轉：三日抽查成功賽前 quote 觀察分別 18／69／24 筆，當中冇量到「乘價正而實際價非正」。呢啲有重複快照，唔係獨立注數，亦唔證明將來安全。
建議：發佈前綁定同一組腿嘅真實報價，重新計 EV／注碼；缺報價就清楚標示無法驗證組合 EV。呢個會影響選擇，須獨立基準及行為驗證。

### F06 · P2 · ML 訓練證據無效，仍未到可採納階段（已知、shadow 防線在）

`build_nba_ml_dataset.py:347` 把己隊當對手；`train_nba_xgboost.py` 用隨機逐行 train/test 同 shuffled CV，同一 player-game 多條線可跨界；部分缺值中位數亦喺切分前由全資料計。
所以舊高 AUC 唔能夠證明實盤泛化。現役有 27 個數值特徵，metadata 列嘅 categorical 欄位冇列入模型特徵，唔應誤報成「live 漏傳 categorical」bug。

Hybrid ML 預設 shadow，降低即時風險；但 `--engine ml` 配合關閉 C 層，仍可令未驗證 ML 主導機率。
建議：下次重訓一併修 builder，按日期／場次切分，fit imputer 只用 train，只評估可投注盤口並與市場比較。唔應只改 live 對手值就宣稱模型已修好。

### F07 · P2 · SGM 大勝風險懲罰冇接到候選腿（新確認）

`_has_blowout_risk` 讀 `leg.adj_breakdown.minutes_floor`；但 `build_leg_candidates` 冇傳遞 `adj_breakdown`。正常產生嘅候選腿永遠缺呢個欄位，該段額外 5% 相對機率扣減唔觸發。
最小重現：spread=15 嘅 player card 有 `minutes_floor=-3`，轉成 candidate 後欄位消失、偵測結果 False。

只修資料傳遞都會改組合 EV／選擇，所以本次未直接採用。先固定規則、同語料 A/B，記錄組合變化；若績效證據不足，仍要坦白講係設計一致性修正而非已證明改善。

### F08 · P2 · 使用率及 pace 有名義上存在但未完整接通嘅路徑（新確認）

- `compute_usage_redistribution` 依據有冇 game log 判缺陣，冇使用已抽到嘅傷停狀態。正常有歷史紀錄嘅 Out 球員未必觸發重分配；資料失敗反而可以被當成缺陣。合成 Active＋Out、兩者均有十場紀錄時回傳空 dict。
- `build_player_card` 傳 `team_pace=None` 去 10-Factor，故 matchup pace 呢個調整冇完整接線。
- MC 從 `card.usg_bonus` 讀使用率 bonus，但 player card 冇存呢個傳入值，MC 因而多數讀到 0。

C 層會取代 10-Factor 最終機率，所以唔應將每個死調整當成現役機率必然受損；MC guard／顯示及 fallback 仍可能受影響。
建議：逐條先量真實非空覆蓋及使用量，再決定保留／接通／移除；每個行為改動分開 ablation。

### F09 · P2 · 防守者欄位死值，門檻單位可疑（新確認，原因待來源驗證）

`fetch_defender_impact` 要求 `PerGame`；選 key defender 時要求 `D_FGA >= 20`。抽查 CLE、PHI、DEN、OKC 四隊嘅 key_defenders 全空。
已證明呢批資料冇防守者訊號；**未獨立核實上游實際單位及全聯盟分佈，唔直接斷言改成另一個數就正確**。
建議：保留原始返回值、按隊統計 D_FGA 分佈，核對來源單位、閾值及縮寫；加欄位覆蓋警報，再評估門檻候選。唔好只靠 JSON key 存在就當健康。

### F10 · P2 · 校準監察按日期代替按模型身份篩選（新確認）

`nba_reliability` 以 `CALIBRATION_EPOCH=2026-10-23` 排除舊日子，但冇按 `engine`／模型設定版本篩選。
實際當日被 evaluator 選中嘅 582 條腿：579 條 `calibrated(hybrid)`、3 條舊 `hybrid`，同日已混有兩代引擎。當日未結算，暫時冇造成校準警報，但之後會污染「校準層上線後」統計。
建議：以每條實際選中 observation 嘅模型身份／設定 hash 分組；先選正確賽前 snapshot，再分代統計，唔准用篩選先後將舊 snapshot 冒充最新發佈。

### F11 · P2 · 報告描述同實際選擇／機率來源不一致（部分已知仍存在）

Banker 文案話 2–3 legs、L10/L5≥80%、神經刀禁止；code 允許 4 legs、fallback≥70%、CoV 至 0.75。
校準後腿機率仍喺 combo 推理段描述成由「8-Factor」推到 Final Adjusted；最終其實係 C 層。調整注碼等文案亦有部分仍根據未扣相關性乘積。
呢啲會令讀者誤解安全程度同模型來源。
建議：先修描述，逐項由現役規則生成，並披露 fallback；是否收緊 Banker 規則，要沿用 EXP-20261022-02 嘅 forward shadow 證據，唔可將兩日失手當成採納依據。

### F12 · P2 · 校準設定讀取失敗會靜默退回舊機率（新確認）

`nba_prob_layer.load_config` 對讀檔／JSON 錯誤回 None，`calibrated_prob` 隨即無值，caller 自動用 legacy_prob；冇獨立「設定壞咗」狀態。刻意關閉同意外損壞走同一 fallback。
正常 tracked config 已存在，今次未見 live 設定損壞；風險係部署或設定故障時，會回到已知校準較差嘅舊路徑而未清楚報警。
建議：區分 disabled、invalid、unreadable；加模型設定身份同狀態，遇到 unexpected invalid 決定阻擋／降級並明示。呢個係獨立行為決定，唔應喺本次順手更改。

## 實際表現證據點樣解讀

以下係現存 ledger 同 evaluator 嘅描述性讀數，Brier 越低越好；唔係同一個模型跨日比較，亦冇以兩日數據判輸贏。

| 悉尼分析日 | 可用賽前腿／已結算 | player-game-market clusters | 所選模型 Brier／raw market | 入選腿 Brier／raw market |
|---|---:|---:|---:|---:|
| 2026-10-21 | 603／603 | 102 | 0.13120／0.11962 | 0.37128／0.18864（14 腿） |
| 2026-10-22 | 2,736／2,728 | 504 | 0.12687／0.11020 | 0.31985／0.20501（66 腿） |
| 2026-10-23 | 582／0 | 0 已結算 | 未有結算 | 未有結算 |

21／22 日係舊 hybrid／10F 世代，**唔可以用佢哋判 C 層好壞**。23 日已混代，見 F10。兩日及少量比賽不足以聲稱策略持續優於／劣於市場。
raw market 含抽水，唔係 fair probability；去水比較只覆蓋有配對兩邊價嘅子集。梯級線高度相關，腿數唔等於獨立樣本數。上述差距只係值得優先追查選腿及校準嘅診斷。

C 層既有 EXP-20261022-03：季後賽 holdout 11 日／3,647 行，Brier 0.1896、對 live-like E 0.2145、raw market 0.1920。對舊引擎有離線證據；對市場嘅改善 CI 跨零。擬合樣本唔代表季初／轉隊環境。Shuffle 檢查準則曾修訂，原實驗已披露；唔把 shuffle 通過當作完整 point-in-time 證明。

## 可保留嘅防線

- L10 以 parsed game date 排序，排除美國當日及未來資料，標明跨季來源；空 API 同無賽事有分開處理。
- 傷停身份配對、Doubtful／Suspended 排除、DNP void、明確 `NO BET` 及 preseason shadow 規則有測試。
- Snapshot append-only、報告 SHA sidecar、賽後／遲寫觀察排除、no_prediction 唔補造賽前紀錄。
- ML 與 fit A shadow 冇直接取代預設 live 機率；反向輸入污染尚未由本次檢查發現。
- Banker 匯出係 combo 1 其中最高 EV **單腿**，唔等同整個 combo 1；呢個係現役產品語義，統計時必須分開。

## 後續執行順序

| 優先 | 工作 | 驗證／採納條件 |
|---|---|---|
| 1 | 本次三個工程修正 | 最小重現、回歸測試、完整 gate；冇模型改善聲稱 |
| 2 | 傷停／陣容新鮮度＋模型身份監察 | 模擬分階段 refresh／來源失敗／跨開賽；按 engine 分代統計 |
| 3 | 真實 SGM quote 同 EV／注碼綁定 | 同一腿集合／同一賽前時間驗價，測試 quote 令 EV 反轉及無報價情況 |
| 4 | 死欄位＋描述修正 | 先量上游覆蓋與接線，逐項決定；改選擇／分數要獨立 A/B |
| 5 | 季初／轉隊校準研究 | 先核對完整 HOT＋WARM、賽前時間、固定評估協議；同窗 baseline／candidate、時間 OOS、按日 bootstrap、逐 stat／角色／跨季 cohort |
| 6 | ML 重訓及 joint MC 採納研究 | 修訓練 builder／split／imputer；校準同市場比較；新季前瞻資料足夠先採納 |

唔建議一次過改晒以上模型部件。SGM 共享風險 MC、Banker 收緊規則及 fit A 應繼續 shadow，未有足夠獨立結算證據唔升級成 live。

## 驗證紀錄

- 基準 `./檢查.sh --quick`：通過。AU 稀疏 trial／新欄位及 HKJC stale baseline 警告屬起步已有，冇喺本次重寫校準基準。
- 基準 NBA 專項：336 passed。最初沙盒執行係 332 passed／4 個 `ps` PermissionError；允許 process inspection 後全部通過，唔係 NBA code regression。
- 新測試喺未修 code：9 failed／31 passed，對應 cache 四項、unresolved 一項、finality 四項。另有進行中狀態等原先已正確案例。
- 新增 15 個參數化測試案例；合法 Final 變體、DNP、首次結算 idempotency、cache 正常重用全部保留。
- 修正後 NBA 專項：**351 passed**；`./檢查.sh --quick` 同完整 `./檢查.sh` 均通過，16 個 suite 全綠。完整測試約 736 秒，其中 Shared Wong Choi 1,728 個測試約 653 秒；現存 expected failures／skips 並非本次新增。
- `git diff --check` 通過。冇修改任何 live ledger／模型檔／歷史 snapshot。

重跑命令（喺呢個分支根目錄）：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q \
  .agents/skills/nba/nba_wong_choi/tests \
  .agents/skills/nba/nba_daily_auto/tests \
  .agents/skills/nba/nba_reflector/tests
./檢查.sh --quick
./檢查.sh
python3 .agents/skills/nba/nba_daily_auto/nba_market_ledger.py evaluate \
  --since 2026-10-21 --until 2026-10-23
```

最後一條只讀 ledger；唔加 `--write`。未收集完整歷史、模型分代及足夠前瞻樣本之前，判決係 **工程修正已驗證／模型表現仍待證據**。
