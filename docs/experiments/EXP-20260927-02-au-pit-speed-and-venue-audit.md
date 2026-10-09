# EXP-20260927-02 — AU point-in-time 速度評分與低表現場地審計

**狀態：PROMISING／PROSPECTIVE SHADOW ONLY／NOT SHIPPED**
**日期：** 2026-09-27 ・ **平台：** AU

## 問題

新語料已經過 2,000 場。今次問兩樣：

1. `WinningTime` 速度訊號喺嚴格 point-in-time 標準之下，仲可唔可以改善排名？
2. 低 Gold 場地係真場地弱點、日期組成，定係資料覆蓋缺口？可唔可以靠速度修？

開始前搜尋過：`EXP-20260826-04`、`EXP-20260831-05/07`、
`EXP-20260831-02`、`EXP-20260905-02` 同 `EXP-20260927-01`。舊結果一再顯示：

- `WinningTime` 有單獨判別力，但舊構造同個體化 `pace_figure` 重疊；
- 全局重配權重多次失敗；
- 場地／星期層未搵到穩定 all-miss predictor；
- 低表現日仍有 93% 真上名馬落喺 model Top 5，較似邊界排序問題。

## 先修量度：速度標準唔准睇未來

舊 research harness 一次過用完整語料 fit 速度標準，早期 target 會借到後來賽事嘅
`WinningTime`。今次另寫 research-only audit：

- 每個 target date `D` 嘅 `(場地, 距離)` 中位時間只用 `< D` 往績；
- cell 最少 10 場；地況修正最少 40 場；
- runner 本身只用 `< D` 往績，最少三條有效速度；
- 同一場 WinningTime 先按 `(場地, 日期, 場次, 距離)` 去重；
- 結果只喺排名完成後 join，冇餵入 feature。

呢個係**語義 point-in-time**：用嘅全部係 target 前已完成賽事事實。archive 檔案可能係
之後 backfill，冇 ingestion timestamp 可以證明當日已成功存檔；因此唔會將本次結果冒充
immutable live replay。

## 鎖定候選

- `global_add`：`final_rank_score + 0.5 × 場內 z(speed_best3)`
- `boundary_all`：速度較高時只交換 model rank 4／5
- `boundary_close`：同上，但原分差必須 `≤ 0.5`

三個候選都係一次過固定；冇按場地揀 k。今次係 discovery audit，所有現有日期已經睇過，
所以無論結果幾靚都**唔可以直接 promotion**。

## 語料與資料質素

- target：**2,081 場**，2026-06-06 至 2026-09-26，70 個完整賽日
- 速度參考：**23,297 場**；重複內容衝突 135 條
- runner 平均速度覆蓋：**57.50%**
- speed 場內上名 AUC：**0.5555**
- speed vs 現役 `pace_figure`：**ρ +0.2455**，有重疊但比舊構造低

覆蓋係主要 regime change：

| 日期段 | 場次 | runner 覆蓋 | 完全零覆蓋場次 |
|---|---:|---:|---:|
| 06-06 至 07-25 | 197 | 0.0% | 197 |
| 07-31 至 08-16 | 476 | 34.8% | 243 |
| 08-17 至 08-29 | 406 | 68.9% | 17 |
| 08-30 至 09-12 | 482 | 74.6% | 12 |
| 09-13 至 09-26 | 520 | 75.3% | 8 |

所以 pooled 全期會將「舊 Formguide 冇 WinningTime」同模型效果混埋。Rosehill Gardens
0% 覆蓋已核實唔係場名 alias：07-18、08-01 兩個 meeting 共 20 份 Formguide 都係
**0 份有 `WinningTime`**。

## 整體結果

| 候選 | Gold Δ | Gold 95% CI | Good Δ | Pass Δ | Champion Δ | Winner@3 Δ |
|---|---:|---:|---:|---:|---:|---:|
| `global_add` | **+0.43pp** | **[+0.05,+0.86]** | **+0.48pp** | +0.34pp | −0.10pp | +0.29pp |
| `boundary_all` | −0.14pp | [−1.06,+0.72] | 0 | 0 | 0 | 0 |
| `boundary_close` | +0.14pp | [−0.19,+0.48] | 0 | 0 | 0 | 0 |

`global_add` 五個完整日期段 Gold：`0.00, -0.21, +0.99, +1.04, +0.19pp`。
早期一段全部零覆蓋；有訊號之後三段正、一段微負。

### 覆蓋分層（描述性，唔係新調參）

| race 速度覆蓋 | 場次 | 平均覆蓋 | Gold Δ | Good Δ | Pass Δ | Champion Δ | Winner@3 Δ |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0 | 477 | 0.0% | 0 | 0 | 0 | 0 | 0 |
| 0–50% | 313 | 29.2% | +0.64 | +0.32 | +1.28 | −0.32 | +0.64 |
| 50–80% | 368 | 64.4% | 0.00 | 0.00 | −0.27 | +0.54 | −0.54 |
| ≥80% | 923 | 94.0% | **+0.76** | **+0.98** | +0.43 | −0.33 | +0.65 |

由覆蓋穩定嘅 2026-08-17 起計，1,408 場 `global_add`：Gold **+0.71pp**
95% CI **[+0.14,+1.35]**、Good +0.50、Pass +0.14、Champion 0.00、Winner@3 +0.28。
呢個切段係事後資料質素診斷，只可支持方向，唔可以當 terminal。

## 低表現場地

場地 Gold 先減走相同賽日全體 Gold，避免某場地剛好集中喺難日。CI 按日期 cluster
bootstrap；最低而 CI 全負嘅四個場地：

| 場地 | 場次／賽日 | raw Gold | 同日調整 Gold | 95% CI | speed AUC | `global_add` Gold Δ |
|---|---:|---:|---:|---:|---:|---:|
| Kalgoorlie | 31／4 | 6.5% | **−11.4pp** | [−19.7,−0.8] | 0.618 | 0.0 |
| Ballarat Synthetic | 54／7 | 16.7% | **−8.1pp** | [−13.1,−3.2] | 0.648 | 0.0 |
| Randwick | 70／7 | 7.1% | **−7.0pp** | [−14.1,−1.2] | 0.490 | **+2.9pp** |
| Caulfield | 47／5 | 4.3% | **−7.0pp** | [−12.3,−2.6] | 0.509 | 0.0 |

結論唔係「四個場地要另加權」：每個只得 **4–7 個賽日**，而且 speed 只喺
Randwick 改善 Gold，該場地 speed AUC 反而低過 0.5。呢個組合唔支持 causal
venue-specific speed rule。四個場地只列入 prospective cohort guardrail。

## 判決

1. **`boundary_all`／`boundary_close` REJECT**：冇穩定收益。
2. **場地專屬權重 REJECT FOR NOW**：場地差異存在，但日數太少，speed 修復亦唔一致。
3. **`global_add` PROMISING／SHADOW ONLY**：PIT 後全期 Gold CI 下界大過 0，Good／Pass／
   Winner@3 同時正；但候選係睇完現有語料後先正式定義，而且 pooled Champion −0.10pp，
   未符合 promotion 所需嘅 untouched terminal 證據。
4. **最值得做嘅 operational 改善係 WinningTime 覆蓋**：高覆蓋組結果較好；舊 meeting
   冇原始欄位，唔應用中性值冒充速度。

冇改 live scoring、權重、golden 或 data-contract。

## 預先登記：下一個 prospective terminal

- 起點：**2026-09-27** 之後新完成、乾淨、可配對賽果嘅 meeting；舊賽事不得補入。
- 候選固定：只測 `global_add k=0.5`；標準、min-cell、三仗門檻全部鎖死。
- 樣本：最少 **2,000 場**；到門檻嗰日要收完整賽日，唔准切日。
- 中途只報資料健康，**唔准睇結果後改 k／覆蓋門檻／場地名單**。
- Stage 4：terminal Gold、Good 點估計都不得負；至少一項 paired race bootstrap
  95% CI 下界 >0；field-size cohort 同上述四個場地冇實質 regression。
- 場地樣本不足時只報 `UNRESOLVABLE`，唔因細樣本加 venue override。

### 已落實盲測收集（2026-09-27）

- `au_speed_shadow_monitor.py` 已駁入 AU evening scheduler，喺 reflector／results ingest 後行。
- 未夠 2,000 場，runtime status **唔包含任何 outcome metric**，只公開場數、賽日、
  WinningTime 覆蓋同場地資料健康。
- 第一次過門檻會包含當日完整賽事，鎖死 exact race keys、terminal 截止日同 sample
  SHA-256；之後重跑唔會吸入新賽事。
- 達標會標記 `ready_for_manual_stage4_review` 並跑下文預註冊嘅 machine Stage 4；即使
  通過亦只產生候選 gate，唔會自動 merge／改 live ranking。
- 初始狀態：`collecting`，**0／2,000 場**，`outcomes_visible=false`。

### 2026-09-28 樣本量修正（收集前、0 場 outcome）

原先 1,000 場係整數式最低門檻，唔係 power calculation。喺 shadow status 仍然係
0 場、`outcomes_visible=false` 時，用 discovery period 嘅 paired race delta 估 nuisance
variance，並按賽日 cluster：

- 2026-08-17 後高覆蓋期 Gold：+0.690pp，14 場由失敗變成功、4 場由成功變失敗；
- 預期令兩側 95% CI 下界大過 0：50% power 約 799 場、80% 約 1,631 場、
  90% 約 2,184 場；
- 全期效果較細（+0.424pp）時，80% power 約 3,488 場，顯示任何固定數字都唔保證過閘。

因此門檻喺未有 prospective outcome 前一次過改成 **2,000 場**：高覆蓋 regime 下有
約 80–90% power，同時仍保留完整賽日。之後唔再按中途結果加減樣本；2,000 場只係
揭盲點，最終仍按 Stage 4 CI 同 no-regression 規則判決。

### 2026-09-29 自動 Stage 4／release gate（71 場、outcome 仍封存）

用戶要求達標後唔使等人手計數。喺 `outcomes_visible=false`、只收咗 71／2,000 場時，
預先鎖定以下 automation；**候選公式、k、樣本門檻同 watch venues 全部冇改**：

- development evidence 固定引用本實驗已公布嘅 2,081 場：Gold +0.43pp、Good +0.48pp；
  唔會因新 terminal 再 fit 或改參數。
- prospective terminal 兩個 primary 點估計都不得負，並至少一個 paired 95% CI 下界 >0。
- 全 terminal runner coverage 最少 70%；低過就自動攔截 candidate release。
- field-size 同四個 watch venues 只喺最少 100 場／5 個賽日時作 automatic regression
  verdict；不足列 `UNRESOLVABLE`。夠數 cohort 若 Gold 或 Good 點估計負且 paired CI
  上界仍 <0，判 `cohort_regression`。
- 通過後自動產生 immutable candidate gate，內含 sample／config／proposal／gate SHA、
  固定 activation formula 同 rollback 邊界；重跑只接受完全相同 gate。
- **唔自動 merge 或 activate live model。** Scoring/model release 仍要全測試、candidate
  commit 同 owner `/approve SHA`；呢條係 release policy，唔係統計判決留白。

## 重現

```bash
PYTHONDONTWRITEBYTECODE=1 python3 \
  .agents/skills/au_racing/au_wong_choi_auto/scripts/au_speed_venue_audit.py \
  --data-root "<AU_Racing>" --clean-from 2026-06-06 \
  --min-venue-races 30 --json-out /private/tmp/au_speed_venue_audit_20260927.json
```

測試：`test_au_speed_venue_audit.py`（6 passed）。
