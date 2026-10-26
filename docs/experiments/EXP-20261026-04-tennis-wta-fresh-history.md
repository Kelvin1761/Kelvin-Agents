# EXP-20261026-04 — WTA 官方新歷史：固定來源更新，同窗消融

狀態：預先登記，未睇 candidate 結果。日期：2026-10-26。

- 授權：全面審計後用戶要求繼續改善及 refine 模型。
- Baseline：main `3dc209bf4561eee6890c0a0ce35dd59865efbb7f`；production scoring unchanged。
- 先搜尋：EXP-20261026-03、EXP-20261009-01、EXP-20261015-05，8-21 professional conversion。
- 舊失敗 Platt／layoff／arbitrary weight search 唔重試。今次新增嘅係已存在官方 WTA source。
- 語料：live DB 一致 SQLite backup，唯一研究副本位於外置碟 scratch。
- 保留原模型／原 history；唔清 live tracker、唔重新標記舊 prediction 為 PIT。

## 固定假設

WTA serve profiles 用 2026-05-18 之後已完賽嘅官方 serve statistics，
可以修復「五個月舊資料仍算 usable」嘅缺口，並改善 raw prop probability。
唔改 hold coefficients、simulator dispersion、selection 或 stake thresholds。

## 預定 arms（唔按結果加 arm）

- A0：現役 player_match_history，現役 hold／ace／prop formulas。
- A1：只喺 WTA serve profiles 追加 official WTA rows，match_date 嚴格早過預測日；
  table／event id 去重；官方 rows 同現有舊 WTA serve corpus 日期冇重疊。
- A2：獨立診斷：A1 加固定 90 日 serve-history age bound；唔由結果揀 age threshold。

每個 arm 同場、同 line、同 odds、同 outcome 配對；先報全部 matched sample 同 coverage，
再以 tour／surface／family 報分層。新增覆蓋單獨報，唔當配對績效增益。
多條 line／雙邊唔當獨立比賽，bootstrap 用 match clustering，4,000 次 seed 20260826。
單樣本比較：raw Brier、log loss 對 A0 同市場；ROI 只係 secondary，保持既有 flat-unit profile。
Secondary ROI 使用固定 raw P−market P ≥0.04、1u 平注，只係定價診斷；
唔等於正式混合權重／family eligibility／Kelly selector 嘅實際注單。
盤口 baseline 用目前各 family 實際 estimator：games／game handicap／first-set game handicap
用 fitted holds、sigma 0.06；first-set winner 用 hand-set holds、sigma 0。
其餘只由 match P 定價嘅 families 唔聲稱會因 serve source 更新而改變。

建 dataset 之前補明次要診斷（仍未讀任何候選績效）：
- 全部官方已完賽 matches 做下一場 service-game hold forecast；用真實 service-game counts
  算 binomial Brier／log loss，量新來源嘅基本預測資訊；唔用佢取代 prop promotion 指標。
- D0 只替換 server hold-rate，其他 return／opponent-Elo 保留 A0；純 attribution control，
  唔用 D0 去救 A1。原因：官方資料無 opponent Elo，直接 overlay 可能同時移除舊 strength adjustment。
- Fetch window 提前至 05-18，只為包含 05 月開始、06 月才完嘅跨月賽事；
  model overlay 仍固定 06-01 起，唔讀 05 月 official rows，避免同 legacy serve corpus 重疊。

## 時間／資料紀律

- 官方 backfill：2026-06-01..2026-10-25，先只寫研究副本。
- match date 要由官方 match timestamp，唔接受 tournament start-date fallback 作 PIT 論據。
- 同時要求官方 actual match timestamp 早過 fixture UTC start，防止本地日期同 UTC 差一日
  導致讀入同場／之後嘅 observation；歷史 backfill 開關唔會繞過呢個限制。
- Props 使用 MIN(id) 開盤報價，兩邊須有同一 fetched_at 嘅開盤證據；
  profiles 截止時間亦係呢個報價時刻，唔係更遲嘅 fixture start，避免用新 feature 對舊價格。
- 任何錯 winner／退賽／資料衝突／不可能值／身份歧義要記錄同排除。
- 未查看候選績效前，獨立 source 檢查再發現「全場比分 6-3,6-2，但 service games 只記 5」
  等 exposure 不一致。增加全場兩邊 exposure 對比分嘅一致性檢查：只接受完整 BO3 set scores，
  總 service games 要喺總 games 扣 tie-break 至總 games 範圍，兩邊數量差不超過 tie-break 數+1。
  修正前嘅重播中止，唔用嗰輪數字擇參；四個 arms、split、指標及價格政策完全不變。
- 固定既有 chronological split（如用 serve pricing harness：2026-07-15），
  唔改切法去救候選。之後已開過嘅歷史窗只標研究／診斷，唔冒充 untouched holdout。
- 新 backfill 嘅 fetched_at 係今日；資料當時確切可用性未有保存 snapshot 證明，
  即使 predictive metrics 升都唔將 counterfactual replay 當實盤 PIT record。
  正式 promotion 仍需 frozen tennis-v1 嘅市場相對／power／coverage／calibration／CLV／ROI 證據。

## 安全／工程修正

已審閱嘅離線 reader／SQL fail-closed 修正先恢復；backtester ledger 係獨立 evaluation scope。
另外以獨立 fixture 驗證 winner-conflict settlement guard 同 BO5 unsupported format gate，
呢啲係正確性修正，唔聲稱提高預測準確率。

## 結果

**決定：REJECT 直接接線及 90 日硬截。新 source 留研究副本，唔改正式 pricing。**

候選 SHA：`5900435a531bbb34b35e85fb98d66b1ede84e2de`（查看結果前已 push 非 main 分支）。

完整官方擷取：63 tournaments；3,390 matches；3,045 新有 stats／16 無 stats／329 已有；errors 0。

6,780 個 player-sides 經品質／日期／身份篩選後 2,950 可用。排除項：{"missing_or_inconsistent_actual_match_timestamp": 2076, "non_completed_match": 112, "invalid_serve_rates_or_exposure": 285, "inconsistent_service_exposure_with_score": 699, "unresolved_or_ambiguous_player_pair": 28}。

同窗、同開盤、同 line、同 outcome 配對：**114 matches／300 props**，全部落喺既有 07-15 split 之後；之前窗無可用 PIT props。

| 版本 | Brier ↓ | Log loss ↓ | ΔBrier vs A0 95% match CI | Secondary 平注 P/L / n |

|---|---:|---:|---|---|

| A0 | 0.264495 | 0.740483 | baseline | -9.513u / 97 |

| A1 | 0.276047 | 0.768007 | [-0.0019205848888888893, 0.02536502188121625] | -28.492u / 122 |

| A2 | 0.275479 | 0.764894 | [-0.03303733195734434, 0.05403653981106612] | -32.552u / 117 |

| D0 | 0.269309 | 0.750536 | [-0.0015752902998236366, 0.011148625937834947] | -19.813u / 94 |

| 市場 | 0.246078 | 0.691638 | — | — |



分層（同一份 paired cohort；全部 family 遠低於 600 個 match 嘅正式門檻）：

| Family | matches / props | A0 Brier | A1 Brier | 市場 Brier |

|---|---|---:|---:|---:|

| player_games | 19 / 38 | 0.266274 | 0.280904 | 0.256875 |

| player_game_margin | 25 / 134 | 0.273660 | 0.284665 | 0.244829 |

| player_first_set_game_margin | 20 / 20 | 0.270226 | 0.288114 | 0.247734 |

| player_first_set | 108 / 108 | 0.251438 | 0.261410 | 0.243522 |



Coverage（共同 quote／canonical 檢查之後各 arm 可定價 rows）：A0 572，A1 636，A2 323；新增覆蓋唔作配對增益。

Primary A1 vs A0 ΔBrier +0.011551，CI 跨零，未證明改善；A1 vs 市場 ΔBrier 95% CI [0.002186, 0.058574]、ΔLL [0.002976, 0.153414]，呢份 matched cohort 明確落後市場。

Player-games A1 vs A0 ΔBrier CI [0.003574, 0.026499]，但只有 19 場，屬細樣本退步警號，唔擴大解讀。

次要 hold 診斷：280 matches／560 player-sides／6,068 service games；hand A0 0.226457 → A1 0.225341，Δ CI [−0.002318,−0.000035]；fitted 0.223375 →0.223068，CI 跨零。基礎 hold 有訊號，未能傳到 props。

D0 只換 server hold-rate 亦未改善 props，唔能夠將失敗簡化為「只係缺 opponent Elo」；唔按結果加權救候選。

90 日硬截失去大量 coverage，prop Brier／LL 未改善，拒絕。

Bootstrap 未作多重假設校正，無任何 promotion claim；backfill availability 仍屬 FLAG，無真正 untouched holdout；CLV 未估，不能宣稱有交易 edge。

四個版本用同一現役 simulator kernel；之後獨立發現嘅 service-order bug 另開 EXP-20261026-05，唔將 source failure 改寫成成功。

原始完整結果：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-refine-20261026/wta_history_evaluation.json`。

## 工程驗證

- 原審計 reader 恢復後 729 tests；加入 safety／research fixtures 後第一次完整 gate：
  16/16 suites，Tennis 753、Shared 1,751、NBA 624；記錄 `/private/tmp/tennis-refine-full.log`。
- 最後新增 UTC cutoff case，以及修正 research fixture import lint 後再次跑 quick／full；
  quick／16-suite full 已過，full 記錄 `/private/tmp/tennis-refine-research-full-final.log`。
  最後 exposure 一致性檢查新增後，Tennis 全套再跑：756 passed（17.43s），
  `/private/tmp/tennis-refine-final-tennis-tests.log`；final quick 亦全綠。
- Native 正確性修正獨立 immutable release gate，唔包含研究 overlay／harness／profile refactor。
- 正確性修正 `007fbc628ec4ca157da68f1d9a439291901d68bf` 已合併／啟用；
  scheduler runtime HEAD 同 SHA，BO5／qualifying smoke passed，六場 winner conflict 可見；
  runtime 無研究 overlay。報告：[correctness fixes](../audits/tennis-correctness-fixes-20261026.md)。
- DB 一致 backup 僅一份，原 live DB 只讀。外置碟已確認真掛載，開始及中途內置碟均 >10GB。
- Corpus bytes：1,838,747,648；SHA256 `a45fd7062caa31ac4afa9a4e6d5f8901044d1e3d7eb5529f883b1cc872c9cac0`。
  matches 9,681／predictions 15,632／history 418,233／props 25,454／market snapshots 232,100／
  WTA sides 6,780。最後研究規則喺查看績效前保存研究分支；唔自動發佈模型。

## 重跑

```bash
cd tennis-wong-choi
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  /Users/imac/Antigravity-repo/tennis-wong-choi/.venv/bin/python \
  scripts/evaluate_wta_history.py \
  --db '/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-refine-20261026/tennis_research.db' \
  --output '/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-refine-20261026/wta_history_evaluation.json'
```

完整結果只寫外置碟；本記錄保留濃縮判決，唔搬原始逐盤資料入 git。
