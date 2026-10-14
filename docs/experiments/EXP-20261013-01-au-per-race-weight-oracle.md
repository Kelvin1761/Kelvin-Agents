# EXP-20261013-01 — AU 逐場賽後權重反推

- **日期／平台**：2026-10-13／AU
- **假設**：失手場嘅權重解集會顯示重複方向；若主要係共通權重失衡，之前時段
  失手場嘅共識應能保住下一段 dev 嘅 Gold／Good。
- **舊記錄搜索**：搜尋 `oracle|inverse|per.race|逐場|反推`；未見同類逐場三層
  oracle。相關：EXP-20260826-02、EXP-20260826-03、EXP-20260928-02。舊全局
  refit 同 argmax 已有 overfit／primary 回歸記錄，今次唔重跑全局擇優 refit。
- **組件**：新增 `docs/experiments/patches/au_race_weight_oracle.py` 同九項 tests；
  冇修改 AU engine。

## 凍結配置

Baseline commit `0116c740330db7f02f9d04d2884e211b1d494517`，包括當時工作區未 commit
嘅 current runtime；完整 dirty status 記入 diagnostics JSON。

Engine SHA256：`5e644ed3b23827f6c43d0e8b49c2e90ee1cf05449ef0378e30d4a0cac80a7f86`。
Dataset SHA256：`db0ffe220069c1c8e3b40275a5e497355c95ed977b3505d2e578a541c12f9519`。
Results SHA256：`917726c762a141f1866ac91617c64e044e72438a9c81ccd90ee9438153a6945e`。

六維係數總量 1.9307986129541292；local 每維 ±25%；positive 非負；signed 每維
±總量。全部總量固定、全部 runtime residual overlays 凍結。每層固定 2,048 組
搜索、seed 20261013；加 baseline、positive 軸端點、LP witnesses。唔係無上限搜索。

Primary 目標沿用 place 四項等權：Gold、Good、Pass、top3 precision；先保留
同樣最好 primary 嘅解集，再以實際前三平均 rank、全場配對 concordance、距離
揀展示例子。展示例子係 hindsight oracle，**唔係可部署 argmax 候選**。
共識使用解集逐維中位數；不足 20 個解唔記「全部加／減」方向。

LP 枚舉同達 Gold＋Good 嘅所有 top2 podium 配對及 Top4 可容許嘅一匹 outsider；
未有 sampled witness 先做 exhaustive feasibility。全場次序另做 exact LP。
margin 0.001，最近已搵到權重距離只係上界，唔係全域最小距離。

## 數據

Canonical 語料共讀 3,618 檔，runtime scoring 同賽果分離後輸出 3,446 場。
完整語料先照 `au_eval.date_partitions` 切分，再選 dev 2026-08-05 起：
1,762 場、1,176 失手、586 成功；日期 2026-08-05 至 2026-09-21。
terminal 811 場、2026-09-22 至 2026-10-12 冇做診斷、冇用 outcome 擇參。
同馬群、最近日期嘅 unique success 對照共 533 組。

801 場太早、45 場 incomplete／tied results、27 場 runner alignment incomplete
排除。輸入連同日邊界、排除理由、係數／模型／工具 hashes 保存在 scratch JSON。

## 結果

| 診斷層 | Gold（全 dev） | Good（全 dev） | Pass（全 dev） | 失手場可同達 Gold＋Good |
|---|---:|---:|---:|---:|
| baseline | 21.51% | 25.65% | 49.72% | — |
| local oracle | 27.92% | 34.68% | 59.02% | 19 / 1,176 |
| positive oracle | 65.61% | 72.64% | 93.47% | 455 / 1,176 |
| signed oracle | 91.37% | 93.81% | 99.72% | 969 / 1,176 |

全部 oracle 數字用咗同場賽果，唔報 prediction CI、唔作 improvement／promotion。
失手場完整結果排序 LP 可行：0／25／198 場；signed 仍 207 場無法同達。
正權重解集反覆降 stability 195 場、jockey_trainer 183 場；456 場有 podium
被非上名馬全維度及 overlay 支配。方向有 outcome-conditioning 同 search-density
偏差，只係候選假設。

固定四段 forward dev sanity check：Gold Δ −2.49、−4.12、+0.27、+0.29pp；
Good Δ +0.50、−2.75、−0.53、−0.59pp；實際前三平均模型 rank 四段全變差。
**失手共識無法穩定轉移，唔用佢取代全局權重。**

## 檢查／決定

- **leakage-audit**：FLAG。current runtime reconstruction，非 immutable 當日
  published predictions；mutable 歷史 features 嘅 PIT 未逐欄證明。SP 唔入特徵。
- **golden_scoring／data_contract**：冇改；quick 全通過。
- **九項工具測試**：PASS，包含 terminal 毒化 outcome 不被診斷讀取、LP 可行／
  不可行、反向解、完整次序、係數預算、Gold 定義、replica fail-closed。
- **完整 repo gate**：已跑，兩個 suite 因環境未過：AU 缺 lxml，HKJC daily
  寫 log sandbox permission；其餘通過，完整 log 留 scratch。
- **決定**：KEEP DIAGNOSTIC TOOL／NEEDS MORE TESTING；共識直接取代全局權重方向
  不採用。冇 model candidate promotion，冇 bootstrap 正式判決。
- **commit**：未 commit；冇 push／deploy。

## 產物

[發現及假設](../audits/au-race-weight-oracle-20261013/FINDINGS.md)；
[完整報告](../audits/au-race-weight-oracle-20261013/REPORT.md)。

原始輸入／逐場 JSON／逐場 CSV 留 `scratch/au_race_weight_oracle_20261013/`，總量
約 90MB，未達外置碟暫存門檻；開工前內置 Data volume 可用 25GiB。

## 重跑

使用已凍結 snapshot（最可重現）：

```bash
PYTHONDONTWRITEBYTECODE=1 .venv-au-ml/bin/python \
  docs/experiments/patches/au_race_weight_oracle.py \
  --data scratch/au_race_weight_oracle_20261013/runtime.json \
  --out scratch/au_race_weight_oracle_20261013 \
  --results-csv '/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/AU_Racing/AU_Historical_Raw_Race_Results.csv' \
  --samples 2048 --seed 20261013 --since 2026-08-05

PYTHONDONTWRITEBYTECODE=1 .venv-au-ml/bin/python -m unittest discover \
  -s docs/experiments/patches -p test_au_race_weight_oracle.py -v
```

重新由 current archive 建快照會反映最新原始資料／引擎，唔保證同凍結 snapshot
相同；寫去新 experiment 目錄，唔覆蓋本輪證據：

```bash
PYTHONDONTWRITEBYTECODE=1 .venv-au-ml/bin/python \
  docs/experiments/patches/au_race_weight_oracle.py \
  --build-runtime \
  --archive-root '/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/AU_Racing' \
  --results-csv '/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/AU_Racing/AU_Historical_Raw_Race_Results.csv' \
  --data scratch/au_race_weight_oracle_new/runtime.json \
  --out scratch/au_race_weight_oracle_new
```
