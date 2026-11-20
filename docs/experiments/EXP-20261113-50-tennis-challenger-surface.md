# EXP-20261113-50 — Tennis：Challenger 補返場地（硬地／紅土）入勝負模型

- 日期：2026-11-13；平台：Tennis；類型：**數據補缺候選 → REJECT**（冇上線）。
- 起因：Kelvin 問點解每注都係「數據完整度 65/100（入選門檻 65）」。
- 已搜舊記錄：memory「場地才係真瓶頸」（2026-08-29）、EXP-20261105 card component blockers、EXP-20261110-03 盈利掃描。
- Baseline：main `2d8f5df4`；候選 code 只喺分支 `claude-tennis-surface-20261113`（`d48ae706`），**冇入 main**。

## 1. 「數據完整度 65」係量度設計問題，唔係數據

`model/features/data_quality.py`：100 起扣，錯誤每項 −20，警告加總但**上限 −35**。
重算 250 場近期定價賽事（唯讀 DB 複本）：每場都有約 17 個「樣本少」警告（對手 Elo／排名分組、大賽、對賽，各 −5），
一開始就扣滿 35 → 冇錯誤嘅場次一律 **65 = 入選門檻**；有錯誤嘅 0 或 25。2026-11-01..13 定價 2,364 行：65 分 2,216、0 分 102。
即係個門檻實際只問「有冇錯誤」。**分數同門檻冇改**：改佢會改揀注，而精選規則係預先登記（EXP-20261105-10）。

真缺口：2026-11-06 起定價 539 場，場地已知 50 場（9%），Challenger **0/123**（08-20 起 0/215）；Sportsbet 賽事輪次 0%（682 場 UNKNOWN，來源本身冇）。
頭 70 注精選 57 注係 Challenger，冇一注有場地 → `surface_elo` 靜靜等於 `overall_elo`。

## 2. 場地來源（已建，冇上線）

- ATP 官方賽程 JSON（atptour.com）有齊場地，但第二次請求被擋；**冇用偽裝繞過**，棄用。
- 改用維基百科「2026 ATP Challenger Tour」（MediaWiki API）：每週列「城市, 國家 — Hard (i) — Challenger 100」。賽程係賽前公佈，冇前視。
- 配對：城市字詞要喺 Sportsbet 名入面（或 Sportsbet 縮寫嘅地名喺城市入面）、Sydney 日期喺該週（週六資格賽起、Sydney 快一日）、級數一致、所有候選場地一致；否則留空。
- 覆蓋：08-20 起 232 個 Challenger 賽事日配到 218 個（94%）。
- 準確：同 TennisMyLife 已完賽記錄獨立核對 **295/295 場地一致，0 錯**。

## 3. A/B：勝負模型 logloss（主裁判）

語料：唯讀 DB 複本（2026-11-13 備份，外置碟），Challenger 單打、2026-08-20..11-11、場地有配到、賽果單一一致、
有開賽前賠率（`MIN(id)`，`fetched_at < start_time_utc`）。同一場同一 as-of 特徵，只差 `match_context.surface`。
配對 bootstrap 4,000 次，seed 20260826，95% CI（按場，一場一行）。

結果（449／459 場；餘下 10 場跑緊，唔會改結論）：機率有變 371 場，平均 |Δp| 0.069。

| 範圍 | n | LL 而家 | LL 補場地 | ΔLL（負＝好） | 95% CI | ΔBrier | 市場 LL |
|---|---:|---:|---:|---:|---|---:|---:|
| 全部 | 449 | 0.6787 | 0.6970 | **+0.0182** | [−0.0002, +0.0375] | +0.0083 [−0.0002, +0.0173] | 0.5996 |
| 硬地 | 366 | 0.6680 | 0.6844 | +0.0163 | [−0.0047, +0.0371] | +0.0076 | 0.5937 |
| 紅土 | 83 | 0.7259 | 0.7526 | +0.0267 | [−0.0191, +0.0714] | +0.0110 | 0.6255 |
| 前半 | 224 | 0.6544 | 0.6655 | +0.0111 | [−0.0151, +0.0379] | +0.0049 | 0.5816 |
| 後半 | 225 | 0.7030 | 0.7283 | +0.0253 | [−0.0009, +0.0525] | +0.0116 | 0.6176 |

每一格點估計都係變差；同市場差距由 +0.079 擴大到 +0.097。

## 判決：REJECT（唔駁入定價）

正確嘅場地令模型更差，即係 Challenger 球員嘅**分場地 Elo 本身唔準**（樣本少），而「冇場地」時 surface 組件等於整體 Elo，
實際上係加重咗較穩陣嘅整體 Elo。唔准用呢個結果收窄範圍（例如淨用紅土）去救。

可以另外預先登記嘅新候選（未做）：分場地 Elo 按該場地場數向整體 Elo 收縮；要獨立 A/B，唔可以喺呢批數據上揀收縮參數。

## 有上線嘅部分（純顯示）

Dashboard 精選理由剷走永遠係 65 嘅「數據完整度」句；場地未知就寫「場地未知，場地 Elo 用緊整體 Elo 代替」。
揀注、定價、前向測試不變（`tennis_reasons.py`、`tennis_tracking.py`）。

## 重現

```bash
P=docs/experiments/patches/tennis_challenger_surface_20261113
# DB 複本：sqlite3 .backup 去 /Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-dq-20261113/copy.db
# wiki.json：MediaWiki API action=parse page="2026 ATP Challenger Tour" prop=wikitext（放同一目錄）
# surface_ab.py 要 import 分支 d48ae706 嘅 challenger_calendar；分 4 shard 跑：
for k in 0 1 2 3; do PYTHONDONTWRITEBYTECODE=1 tennis-wong-choi/.venv/bin/python $P/surface_ab.py $k 4 & done; wait
tennis-wong-choi/.venv/bin/python $P/surface_ab_eval.py
tennis-wong-choi/.venv/bin/python $P/dq2.py     # 第 1 節嘅警告統計
```
