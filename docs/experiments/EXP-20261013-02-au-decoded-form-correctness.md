# EXP-20261013-02 — 已解碼第十名被誤讀成一冠一敗

- **日期／平台**：2026-10-13／AU
- **觸發**：用戶核對 10-12 Tamworth R4 第二揀 Platinum Card，只有一次大敗往績。
- **假設**：Facts decoded 單一名次 `10` 被 legacy compact parser 拆成 `[1,10]`，
  虛構前三獎勵，經 PQ fallback 推高 stability。格式分源可獨立修正呢個錯誤，
  唔需要增加大敗扣分。
- **舊記錄搜索**：`debut|one.start|single.start|一場|thin.evidence`、parser 名稱。
  已讀 EXP-20260822-01/04、EXP-20260902-08/09 同 EXP-20261013-01；未見修正
  decoded 單一 `10` 同 compact `10` 格式混淆嘅記錄。

## Baseline／修正

Baseline commit `0116c740330db7f02f9d04d2884e211b1d494517` 加當時未 commit 工作。
`engine_core.py` 原有其他 session 修改保留，今次只增加來源格式處理。

修正前 scoring SHA256：`8394e7f427ff5b62a0dc3f4ce29c908fc2ab17f4ef6ba198d192b49422fb1082`。
修正前 engine_core SHA256：`0228145fb0a802a43586a2240aa3ed94dfb1b874ae9ffc787cff70e27e27bfed`。
修正後 scoring SHA256：`76fb67313c3d0117ee4ee96f45a6a46cfa077c7bb421b9ca928b14616e04720c`。
修正後 engine_core SHA256：`707baddb70074ea0ba493244dc3823fef4c08bebe71e452884dfcf84926e5dd7`。

`parse_recent_finishes(..., source_format=...)` 區分 decoded positions 同 compact；
Facts enrichment 標記 positions，舊 Logic 對匹配 Facts 同值採用 positions，
legacy `2134` 行為保留。無 weights、常數、扣分幅度或 odds proxy 改動。

## 資料／切法

用 EXP-01 固定 eligible dev，1,762 場、2026-08-05 至 09-21；兩個 arm 以相同
prepared raw inputs 重播。Baseline 對原凍結 snapshot 零 drift。五個 whole-date
dev folds，四個 field-size cohort。

Dev 正確性 guardrail 通過後 terminal 確認一次。原日期 split 不變；811 場中
排除已曝光 Tamworth meeting 8 場、21 incomplete／tied results、11 runner
alignment 不完整，771 場、09-22 至 10-12；四個 field-size 同五個 baseline
首選 SP cohort。SP 評分後 join，只作 guardrail。

被修正：dev 72 匹、terminal 47 匹；另外 Platinum Card 係獨立機制個案，唔入
validation。Tamworth 原始 published 64.8516／rank2，同現行重播64.9013區分。
修正後完整8匹賽前field重播63.7364／rank3，不能用7匹賽後對齊排序冒充賽前排名。

凍結原輸入 SHA256：`db0ffe220069c1c8e3b40275a5e497355c95ed977b3505d2e578a541c12f9519`。
凍結 paired leaves SHA256：`6e2f9d6a700d40de723f2d202851b7d50e4ef36f5b9d0b5a9d58a6d695f0beee`。
每個 fresh prepared input hash 記入逐場 JSON；修正前 code／golden／contract 另備份。

## 結果及判決

| 指標 | Dev Δ | Terminal Δ | Terminal paired 95% CI |
|---|---:|---:|---:|
| Gold | +0.0568pp（+1 場） | 0pp | [0, 0] |
| Good | 0pp | 0pp | [0, 0] |
| Pass | 0pp | +0.1297pp（+1 場） | [−0.2594, +0.6485] |
| 前三平均模型 rank（低為佳） | −0.00151 | −0.00216 | [−0.00520, +0.00086] |

配對 race bootstrap 2,000 次，seed 7。Dev folds Gold／Good 無點估計回歸；
terminal 所有指定 cohorts Gold／Good 逐場零變。

**決定：KEEP CORRECTNESS FIX，唔係已證實表現改善，冇 PRIMARY_WIN／RANKING_WIN。**
就算績效方向相反，decoded 第十名也不應虛構一場冠軍；若有顯著回歸應隔離及
查其他錯誤，唔應保留錯誤格式。符合評估合約 §7 嘅獨立可證錯誤及無顯著回歸。

## Leakage／資料限制

- **修正本身 PASS**：只用賽前 Facts 已有格式及近績；target 賽果完全唔入評分；
  無 odds 入分；Tamworth exposed case 全 meeting 排除 validation。
- **歷史整體證據 FLAG**：current runtime reconstruction，非逐場 immutable
  published 全語料；原模型 mutable 歷史統計 PIT 尚未逐欄認證。不能用呢輪
  小變化宣稱 predictive improvement 或選新權重。
- 個案完整正式表缺失，只能從摘要證明大敗，不能猜確切距離／輸距／班次。
- PF 單一 source dated run 對應舊試閘，需獨立做來源可靠性研究，今輪無改 PF。

## 檢查／產物

- 七項新 parser 回歸測試通過；近績／輸出／PQ 三組 targeted tests 22 項通過；
  發佈閘＋parser 12 項通過。
- 已 record AU golden（舊 snapshot 保留）、data-contract 重校 2,000 場／19,781
  匹、官方生成器更新模型說明。冇手改生成說明。
- 必要 full gate 暴露原 test 依賴 mutable baseline：現在負磅本來中性率86.24%、
  SD0.756，唔應必然 dead-field。測試改用記憶體固定 populated baseline；保留
  live CLI gate，以及 warning／唔攔發佈嘅原本契約。
- 本地 `.venv` 補回既有 parser 所需 lxml；完整 gate 用正常 repo 權限跑，消除
  HKJC logger sandbox 假失敗。最後結果見同目錄驗證記錄。
- **commit**：未 commit，無 push／deploy。

[完整個案、stability 分類及下一步假設](../audits/au-race-weight-oracle-20261013/STABILITY_TAMWORTH_R4.md)。
原始 JSON、paired leaves、舊 code／baseline 留 `scratch/au_stability_format_20261013/`。

## 重跑

```bash
PYTHONDONTWRITEBYTECODE=1 .venv-au-ml/bin/python \
  docs/experiments/patches/au_stability_format_audit.py \
  --data scratch/au_race_weight_oracle_20261013/runtime.json \
  --diagnostic scratch/au_race_weight_oracle_20261013/diagnostics.json \
  --out scratch/au_stability_format_20261013 \
  --case '/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/AU_Racing/Archive/2026-10-12 Tamworth Race 1-8/Race_4_Logic.json' \
  --phase dev

# 僅喺 dev 正確性 guardrail 通過後執行一次：
PYTHONDONTWRITEBYTECODE=1 .venv-au-ml/bin/python \
  docs/experiments/patches/au_stability_format_audit.py \
  --data scratch/au_race_weight_oracle_20261013/runtime.json \
  --diagnostic scratch/au_race_weight_oracle_20261013/diagnostics.json \
  --out scratch/au_stability_format_20261013 \
  --case '/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/AU_Racing/Archive/2026-10-12 Tamworth Race 1-8/Race_4_Logic.json' \
  --phase terminal \
  --results-csv '/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/AU_Racing/AU_Historical_Raw_Race_Results.csv'

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  .agents/skills/au_racing/au_wong_choi_auto/tests/test_recent_form_format.py \
  .agents/skills/au_racing/au_wong_choi_auto/tests/test_publish_gate_blocks_dead_fields.py \
  -q -p no:cacheprovider
./檢查.sh --quick
./檢查.sh
```

驗證結果：`./檢查.sh --quick`、`./檢查.sh` 全部通過；凍結 paired leaves 重算 2,533 場，逐場指標全部同報告一致。完整 log：`scratch/au_stability_format_20261013/full-check.log`。
