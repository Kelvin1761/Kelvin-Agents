# EXP-20261013-10 速度重建：頭段步速＋位置修正末段速度

- **日期**：2026-10-13
- **平台**：AU
- **狀態**：**REJECT（三個都係）**｜預先登記喺量度之前寫，以下規則冇改過
- **假設**：Sportsbet 往績行已經有、但引擎冇用嘅 `WinningTime`、`800m／400m 位置`，
  可以砌出 `pace_figure`（「速度考驗背景」）冇嘅兩樣資訊：
  - **B1 頭段步速**：頭馬時間 − 場級 L600 = 去到 600m 標記嘅時間。引擎所有
    early pace 欄位都係 Racenet 死 code（0%），呢個方向從來冇測過。
  - **B2 位置修正末段速度**：現行 own-L600 = 場級 L600 + 終點負距×0.17，假設匹馬
    喺 600m 同領放馬齊頭。改為減去 600m 標記時估計落後距離（由 800m／400m 位置
    內插 × 每位馬位數），分得開「後上」同「前置頂唔住」。
- **搜索過嘅舊記錄**：EXP-20260831-03（pace_figure 拆解：early pace 欄位全 0%）、
  EXP-20260831-05（個體化 own-L600 上線）、EXP-20260831-07 / EXP-20260927-01
  （WinningTime 速度指數 REJECT —— 同 own-L600 重疊 ρ 0.418）、EXP-20260822-02
  （末段跌位 REJECT —— 位置變化本身同 form 重複）、EXP-20260902-02/-05（跑法、
  起步位 REJECT）。**唔重做**：純 WinningTime 速度指數、純位置變化、純跑法。

## 預先登記嘅特徵（只用賽日之前嘅非試閘往績，最近 4 仗有數據嘅平均）

| 名 | 定義 | 方向 |
|---|---|---|
| `early_pace_faced` | 場頭段速度 z：(距離−600)/(WT − L600raw)，對 (100m 距離格, 地況族) 標準 | 大 = 經歷過快步速 |
| `early_speed_own` | 本駒頭段速度 z：頭段時間 + 600m 標記估計落後 × 0.17 秒 | 大 = 自己快 |
| `late_speed_pos` | 位置修正末段：−(L600raw + 0.17×(終點負距 − 600m 估計落後) − 標準) | 大 = 末段快 |

- `L600raw` = PF token `L600 Delta` + `_lookup_standard_l600(場地, 距離)`（現行表）。
- 600m 估計落後 = ((800m 位 + 400m 位)/2 − 1) × G；G = 終點「每名次負距」嘅語料中位數。
- 標準格只用 **2026-06-01 之前**嘅往績建（as-of）。
- 單場 z 截 ±3。

## 判決（照 `docs/model-evaluation-contract.md` Stage 4 v2，唔改尺）

- 語料：`au_dump_engine_leaves.py` baseline dump（3,461 場），同一份做 baseline 同 candidate。
- 候選 = `default_scorer + k × 場內z(特徵)`，冇值 = 0。
- k 網格 {0.5, 1, 1.5, 2, 3}（ability 場內 SD 中位 7.43）。**只用 dev** 揀：
  dev Gold、Good 都唔負、dev 頭5 AUC > 0 嘅 k 取**中位數**（唔取 argmax）。
- 揀定 k 先跑一次 `au_eval.compare` → Stage 4 v2 判決。
- 每個特徵獨立判；過閘多過一個先做組合 + ablation（`feature-ablation`）。
- 先報單獨判別力（場內 AUC）同正交性（ρ vs pace_figure / form / performance_quality），
  呢兩個只係診斷，唔係判決。

## 配置
- **baseline**：HEAD `0116c740` + working tree（另有其他 session 未 commit 改動；`./檢查.sh --quick` 全綠、golden 120/120），
  leaves dump `au_dump_engine_leaves.py`（3,461 場，2025-08-02 → 2026-10-13；dev 2,666 場）
- **candidate**：`default_scorer + k × 場內z(特徵)`，零 engine 改動

## 數據
- 去重往績 159,510 條；每名次負距 G = **0.877** 馬位；標準格 race_early 58 / own_early 57 / late 4（只用 < 2026-06-01）
- 特徵 35,235 匹馬

## 結果

### 診斷（唔係判決）
| 特徵 | 覆蓋 | 場內上名 AUC | ρ pace_figure | ρ form | ρ PQ | ρ ability |
|---|---:|---:|---:|---:|---:|---:|
| early_pace_faced | 64.2% | **0.5001** | −0.096 | −0.012 | −0.032 | −0.029 |
| early_speed_own | 63.7% | 0.5266 | −0.029 | +0.069 | +0.041 | +0.062 |
| late_speed_pos | 79.7% | 0.5787 | **+0.601** | +0.182 | +0.315 | +0.390 |

同一批馬：現行 `pace_figure_score` AUC **0.5981** > `late_speed_pos` 0.5787。

### 判決（Stage 4 v2）
| 特徵 | dev 合格 k | terminal 頭5 AUC | Stage 4 v2 |
|---|---|---|---|
| early_speed_own | {0.5} | +0.0019 [−0.0014, +0.0053] | **REJECT** `primary_regression`（good_positional） |
| early_pace_faced | {0.5} | +0.0014 [−0.0018, +0.0046] | **REJECT** `primary_regression`（good_positional） |
| late_speed_pos | 冇（k=0.5 dev gold −0.26pp 起步就負） | 未碰 terminal | **REJECT** |

dev 掃描（gold / good / 頭5 AUC）：
- early_speed_own：k0.5 +0.15/+0.34/+0.0004；k1 +0.04/0.00/−0.0005；k≥1.5 全負
- late_speed_pos：k0.5 −0.26/0.00/−0.0000；k1 −0.38/+0.34/−0.0001；k3 −1.01/−0.30/−0.0047
- early_pace_faced：k0.5 +0.04/+0.23/+0.0000；k≥1 漸負

## 檢查
- **leakage-audit**：PASS —— 只用 `date < 賽日` 嘅非試閘往績；標準格只用 < 2026-06-01；
  Formguide 係賽前快照（`Days:`／往績行），冇用 `J/H`、`WinRange`、`Ave $` 等總結欄
- **golden_scoring**：冇郁（零 engine 改動）
- **data_contract**：N/A
- **退步**：early_* 兩個喺 terminal good_positional 點估計回歸

## 結論

**點失敗：**
1. **頭段步速（場）係零訊號**（AUC 0.5001）—— 「經歷過幾快嘅頭段」對今仗上唔上名冇資訊。
2. **本駒頭段速度真係正交**（ρ ≤ 0.07），但太弱（0.5266），加落去 dev 只喺最細 k 打和偏正，
   terminal Good位回歸。佢嘅用處可能喺**步速圖／起步位預測**（顯示層），唔喺排名層 —— 未測。
3. **位置修正末段速度反而差過現行**（0.5787 vs 0.5981）。用「名次 × 0.877 馬位」估 600m 落後
   帶入嘅誤差大過佢修正嘅偏差：名次唔係馬位，頭幾匹可以擠埋一齊亦可以拉開。即係
   EXP-20260831-05 嘅「600m 齊頭」簡化**經驗上係較好嘅近似**。

**整體：** Sportsbet 往績行上面嘅速度代理（WinningTime、位置、場級 L600）已經用盡 ——
同 `au-feature-set-is-saturated` 一致。下一步要真·逐駒計時（例如 Racing Queensland
GPS 段速，昆州 >90% 場次、2024 起）先可以答「段速有冇用」，唔可以再由代理推。

**決定**：REJECT（三個）
**commit**：未 commit（零 model code；只有呢份記錄）

## 重跑
```bash
cd /Users/imac/Antigravity-repo/.agents/skills/au_racing/au_wong_choi_auto/scripts
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 au_dump_engine_leaves.py --out $S/leaves_baseline.json
# $S = 任何 scratch 目錄（leaves dump ~21MB）
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 au_speed_rebuild_probe.py build $S/leaves_baseline.json $S/feats_v1.json
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 au_speed_rebuild_probe.py diag  $S/leaves_baseline.json $S/feats_v1.json
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 au_speed_rebuild_probe.py judge $S/leaves_baseline.json $S/feats_v1.json early_speed_own
```
