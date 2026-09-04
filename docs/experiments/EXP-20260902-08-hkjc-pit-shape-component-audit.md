# EXP-20260902-08 HKJC PIT 修復與 Race Shape 組件審核

- 日期：2026-09-02；平台：HKJC。
- 問題：Race Shape 27.37% 是否過重？先確認時間安全，再量現有組件，而非盲目加段速。
- 已查：EXP-20260902-03、04_walk_forward_calibration.md、pit_backtest.py、評估合約。
- 起點：`926eac54`，shared worktree 有其他 AU/dashboard 工作；不包含、不覆蓋。
- 狀態：已完成權重研究；沒有 production 模型候選改動；不 commit/push/activate。

## 固定設計（結果揭示前）

1. 修復現有 PIT harness 的 package imports、missing meeting cutoff；驗證同日及未來結果不可進入先驗。
2. 語料沿用 264 場（2026-04-12 至 2026-07-12），不因資料稀疏刪走舊場次。
3. 保留 EXP-03 時間界線：dev < 2026-06-13，terminal >= 2026-06-13。terminal 已曾查看，不再稱 untouched holdout；今次不據此反覆調參。
4. 使用 production `rescore_logic`（含 headers、post-matrix adjustments、debut weights、SIP），canonical `eval_metrics.race_metrics`。Gold = 實際前三全部落 model Top4；`gold_strict` 另報，不混用。
5. 預先限定：A=Race Shape 轉 5pp 至 stability；B=轉 5pp 至 sectional；C=沙田 fit 設中性（不轉移其內權）；D=沙田 trip 設中性；C+D 為有解釋嘅消融組合。全部固定，唔以 terminal 揀方案。
6. 七維 joint refit：dev meeting bootstrap 200 次 PL 非負 fit 中位數，5 個 dev expanding-time folds；debut 權重鎖定。拆單維變化（其餘比例縮放）只喺 dev 做 ablation。
7. 先量 neutralised Race Shape 在各 ranking metric 的部件預算及 terminal paired CI 半寬（seed 7、2000 resamples），不事後以功效規則挽救候選。
8. 分層：venue、field size、sparse/rich schema；going provenance 不清不得冒充賽前已知分層。Odds 不進評分／fit。
9. PIT 修復只處理 aggregate J/T 資料；所有 archived text/derived signals 的賽前 provenance 未逐一證實前，leakage status = FLAG，禁止宣稱可 promote 或「最好模型」。

## 結果

### 正確性修復（不是已證實的模型改善）

- `pit_backtest.py` 原先 `import live_priors / engine_core` 已不能啟動；改為正確 HKJC package，確保注入的 global 就是 production 真正使用的物件。
- `rescore_backtest.py` 回放時由 meeting folder 注入日期，與已存在的日期矛盾則拒絕；補回缺失 venue。
- PIT cutoff／來源日期缺失會拒絕；移除永久覆寫 `RacingEngine._jockey_trainer_prior` 的副作用（現役 rescore 已會清除 embedded aggregate combo prior）。
- 6 個新增測試：package identity、嚴格 `< meeting_date`、未来結果擾動不變、缺日期拒絕、archive 不改寫、PIT rating 與 production rating 數學一致（12 decimal places）。
- 264 場 / 3,318 匹的研究排名重算 **逐匹 ability 與完整 production rescore 一致**（包含初出馬例外及 SIP）。
- 評分 code、權重、golden、data-contract baseline 未改；只修診斷工具。

### 資料限制（不能當成全量 pre-race replay）

- 264 份 Logic 全部缺 `race_date`；879 / 3,318 runners 屬 sparse schema，71 / 264 場為 sparse-majority。
- 原始先驗來源 20,454 行，2024-09-08 至 2026-07-15；但缺 archive 的 **2026-05-20、06-21、07-01、07-08、07-12** 五個賽日。
- 有距離的 raw rows 只去到 **2026-05-09**；往後同程先驗不完整。呢個係缺資料，不是未來洩漏，但會令回放不能等同當日完整資料。
- draw_position_fit / position_window 非空 2,439；position_pi 非空 2,183。檢查可見 ISO 日期未見當日／未來日期，**但不等於** 所有文字信號已證實賽前可得。
- dev 180 場混有 sparse/rich，而 terminal 84 場全 rich；因此時間 split 同時係資料覆蓋 regime split。
- terminal 曾用於 EXP-03；本輪不靠其結果再揀參數。所有成效只作有明示限制的診斷，leakage audit **FLAG**。

### 權重方向（只由 dev 擬合）

| 維度 | baseline | 200 次賽日 bootstrap 中位數 |
|---|---:|---:|
| sectional | 12.85% | 7.14% |
| trainer_signal | 23.62% | 23.17% |
| stability | 9.83% | 14.53% |
| race_shape | 27.37% | 14.45% |
| class_advantage | 14.28% | 14.89% |
| horse_health | 4.04% | 14.24% |
| form_line | 8.01% | 11.58% |

Race Shape bootstrap 90% interval 10.79%–18.07%。但該區間係 **PL likelihood** 的權重穩定性，唔係「改用呢個權重就提升 Gold/Good」的證明。health 的單獨 dev AUC 只有 0.4942，仍被 joint fit 大幅加權，亦提醒不能照抄係數。

### 後段 84 場（相同語料／時間窗）

| 配置 | Gold@4 | Top2雙上名 | Top3至少兩中 | 0 hit | 1 hit | Top3 capture@5 |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 13.10% | 19.05% | 44.05% | 19.05% | 36.90% | 60.32% |
| joint refit | 13.10% | 17.86% | 39.29% | 16.67% | 44.05% | 64.68% |
| Shape→stability 5pp | 10.71% | 17.86% | 44.05% | 19.05% | 36.90% | 62.30% |
| Shape→sectional 5pp | 11.90% | 11.90% | 41.67% | 21.43% | 36.90% | 59.52% |

joint refit：

- dev Top2雙上名 **27.22%→22.22%（-5.00pp）**；terminal -1.19pp，95% paired CI [-9.52,+7.14]pp。
- dev capture@5 **66.48%→65.00%**；terminal +4.37pp，95% CI [+0.79,+7.94]pp。terminal 有量到捕捉改善，但方向在 dev 相反，primary 又退步，不能只揀呢個好數字。
- terminal 0 hit 減 2 場，但 1 hit 增 6 場；頭三至少兩中減 4 場。Winner Top3 55.95%→47.62%。
- 補充描述指標（不拿來另改判決）：dev Top2 合共位置捕捉 **183→177 / 360揀**；terminal **76→77 / 168揀**；12 匹 baseline Rank3 位置馬升入 Top2，但15匹 baseline Top2位置馬被調走（另有4匹較後排名位置馬升入），淨增只1匹。改善「第三選提升」尚未穩定保住原有好選擇。
- 5 個 expanding-time folds，Gold+Good 同時不退步只有 **3/5**；兩個 fold 雙退步。
- terminal 沙田草地 60 場：Good 不變，Pass -5.00pp；泥地 6 場：Pass -16.67pp；跑馬地 18 場：Good -5.56pp。小 cohort 不過度解讀，但不能聲稱一致改善。

**joint refit 不保留**：primary 在 dev/terminal 都退步，且來源證據 FLAG。呢次唔係「因一場輸而拒絕」，係整體目標取捨與輸入證據不足。其餘固定權重轉移同樣無清晰全面優勢。

### Race Shape 部件審核

dev 非中性 rows 的場內 pairwise AUC（僅診斷，非因果或邊際收益）：

| 組件 | AUC | dev 中性60比例 |
|---|---:|---:|
| stability | 0.6137 | 5.43% |
| sectional | 0.5675 | 42.09% |
| race_shape | 0.5603 | 0.18% |
| draw | 0.5609 | 0.00% |
| fit | 0.5347 | 51.00% |
| trip | 0.4885 | 46.06% |

- 沙田 55% draw + 25% fit + 20% trip；跑馬地是 draw + capped delta。相同 27.37% 外權，不代表兩場地內部相同。
- 普通彎途檔位先驗：1–4檔75分／9+檔50分。單靠此差值，跑馬地 ability 差 **6.84** 分、沙田約 **3.76** 分（不計其他情境）。顯示影響力大，但不證明錯。
- `compute_draw_position_fit` 以內／外疊的平均絕對名次判「偏好」；即使各只有一仗亦可下結論，未按樣本量收縮，未控制 field size／班次／路程。去重 key 只有 barrier+finish+XW，並非 race identity；不同真賽事可能被誤合併。
- trip 由 XW 疊數轉消耗標籤；上仗走外疊可能代表額外負荷，亦可能係可原諒的失利。現有固定扣分不能區分，亦無按距今日數衰減。
- sectional 是多項 heuristic 加減分，不是純標準化段速；現有 dev 大量中性，加外權不會修復覆蓋或校準。
- fit/trip 弱的單獨 AUC **不代表可直接刪除**：預先登記 neutralisation 顯示 Top2/Pass 並無一致受益（完整結果見 evidence.json）。不以移除後的個別小收益重新調參。
- 前置 power audit：Shape 全中性對 capture@5 的 terminal |Δ|=2.38pp，CI 半寬4.76pp；mean Top3 rank 0.171<0.268；competitive recall 2.50pp<3.94pp；NDCG 1.98pp<4.04pp。四個 ranking metric 對此次部件預算均非資訊性；但此規則不會豁免 primary 退步或來源 FLAG。

## 下一個獨立階段

先修補 **PIT raw-results 的5個日期缺口及距離/班次 metadata**，保留來源、identity、嚴格日期 cutoff，重建 baseline；再針對 fit 的樣本收縮／同情境比較與 trip 的「額外負荷 vs 可原諒失利」分開設計候選。不要直接反轉 trip 符號或把本輪係數當最佳模型；也不要求先等30場未來賽事，應先用現有可核實資料補齊證據。

## 可重現

- Commit 起點：`926eac54de7f67f78a8f6f7a5c3632a7d95b0cce` + 本輪 PIT 修復 diff。
- Sample hash：`dc8a79318d558286c3f65e3aa6baab2cb33723cd0cc17e78ead656e6dbe708a9`。
- Raw snapshot hash：`eb42d7bbd52179e11f640c7aaa45f4c662835ed915b41d16b910492864a7f0ed`。
- `/private/tmp/hkjc-pit-shape-20260902/pit_scored.json`：engine/script source hashes + 每場來源 hash + 分數 dump。
- `/private/tmp/hkjc-pit-shape-20260902/evidence.json`：完整指標、CI、分層、消融、folds、權重區間；不進 git。

```bash
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python3 scratch/hkjc_pit_shape_refit_20260902.py \
  --out /private/tmp/hkjc-pit-shape-20260902
# Source hash 相同時可加 --reuse-dump，不再重跑慢速 narrative/render。
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest \
  .agents/skills/hkjc_racing/hkjc_reflector/tests -q -p no:cacheprovider
./檢查.sh --quick
./檢查.sh
```

**測試**：`./檢查.sh --quick` 通過；`./檢查.sh` 全部10組通過（9組Python + Dashboard node）；HKJC Wong Choi 56 passed；另行執行 Reflector tests **21 passed**（含6個新增 PIT tests）；指定檔案 py_compile、`git diff --check` 通過。重跑 quick 時 concurrent AU 工作造成 AU data-contract stale-baseline 警告，未改動對方基準；HKJC data-contract/golden 均一致。

**決定**：工具正確性修復已實作；權重與組件候選不 promote。Model/production 未變，未 commit/push。
