# EXP-20260928-04 — HKJC 同日逐場場地偏差

- **日期**：2026-09-28
- **平台**：HKJC
- **狀態**：**REJECT / SHADOW ONLY**；正式候選 terminal primary 回歸，冇改 live formula
- **假設**：同日、同表面、已完成場次嘅頭三名早段位置，能識別當日偏前／偏後，
  並改善與每匹馬歷史實際早段位置相符嘅排序。
- **搜索過嘅舊記錄**：EXP-20260902-08/10、EXP-20260904-07、
  EXP-20260927-03/04、EXP-20260928-01/03；未見同日逐場 PIT replay。
- **Harness**：`docs/experiments/patches/hkjc_same_day_bias_ab.py`

## 資料安全

- target Rn 只可讀同一 meeting、race number `< n` 嘅賽果；嚴禁使用 Rn 或之後場次。
- 只比較相同表面（沙田草／沙田 AWT／跑馬地草）；混合表面不共用 bias。
- 頭三名使用官方 `running_positions` 第一個沿途位；按該場 field size 正規化。
- 每匹馬 typical position 只用 target date 之前正式賽果，最多近 5 場；target race 不入。
- 不讀賠率、當場名次、事後 incident 或全日最終 aggregate。
- 官方結果冇 XW／實際幾疊，所以今輪只測「早段位置」；唔會假裝 draw 等於走疊。
- 至少 2 場同表面已完成賽事先啟用；之前全部中性、排名不變。

## 預先鎖定 arms

所有 feature 先於場內標準化；缺值 z=0。只改 race-shape，外權維持現役
standard 27.37%／debut 20%。

| Arm | race-shape adjustment | 身份 |
|---|---:|---|
| current_live | 0 | baseline |
| same_day_position | `clip(4 × z(position_match), -5,+5)` | 唯一 eligible candidate |
| same_day_draw | `clip(4 × z(draw_match), -5,+5)` | diagnostic；draw 只係檔位 proxy |
| both | 各 `2 × z`，合計 clip ±5 | interaction diagnostic |

`position_match = (0.5 − horse_typical_position) × (0.5 − day_top3_position) × reliability`。
兩邊都偏前或都偏後為正；一前一後為負。`draw_match` 同樣用 current draw percentile
對當日頭三 draw percentile 嘅距離，場內中心化後使用。

## 判決

- 唯一 eligible arm 為 `same_day_position`。diagnostic arms 不可因結果最好而晉級。
- 唯一日期尾 15% 為 terminal；Stage-4 v2 Gold／Good 任何 dev 或 terminal 負數即 REJECT。
- ranking metrics 預先登記 `top3_capture_at5`、`competitive_recall_at5`、`ndcg_at5`。
- venue、surface、race-number 1–4／5+ 為 guardrail。
- current pipeline 尚未 intra-day rerun；即使過閘，先做 shadow CLI／排程驗證，唔直接改
  朝早全日 snapshot。

## 結果

32 meeting／320 場／3,972 匹，當中 228 場（71.25%）喺開跑前已有至少兩場
同表面完成賽事，可以啟用同日偏差；95.69% runner 有 target date 之前嘅個體早段位置。

唯一 eligible `same_day_position` 相對 current live：

| 指標 | all 320 | dev 274 | terminal 46 |
|---|---:|---:|---:|
| Gold | 0.00pp | +0.36pp | **−2.17pp** |
| Good | **+1.88pp** | +1.82pp | +2.17pp |
| Champion | −0.31pp | 0.00pp | **−2.17pp** |
| Top3 capture@5 | +0.73pp | +0.97pp | **−0.72pp** |
| Competitive recall@5 | +0.35pp | +0.55pp | **−0.83pp** |
| NDCG@5 | +0.36pp | +0.52pp | **−0.59pp** |

全樣本 Good 改善有配對 CI 支持（+1.88pp，95% CI +0.31 至 +3.44），但 terminal
Gold／Champion 各少一場，而且三個排序指標全部轉負。Stage-4 按預先鎖定規則判
**REJECT — `primary_regression: gold`**。呢個係有方向但未能跨時間保持嘅訊號，唔可以
用 all-sample Good 升幅掩蓋 terminal 倒退。

兩個 diagnostic arm 亦冇晉級：

- `same_day_draw`：全樣本 Gold +0.94pp、Good +1.25pp，但冇 ranking metric CI 支持，
  Stage-4 `ranking_evidence_too_weak`；而 draw 亦唔等於實際走疊。
- `both`：all-sample ranking 小升，但 terminal Gold −2.17pp，`primary_regression`。

所以相中方法會保留成研究／prospective shadow 概念，但目前既冇穩定績效證據，日常
pipeline 又未有逐場 rerun，今輪不接入 live 7D。官方結果冇 XW，仍然只可以量早段位置，
唔會聲稱已量到「走幾多疊」。

## 2026-10-06 regime fragility follow-up

用戶觀察旺財喺偏前／利內日表現較好、偏後／利外日明顯較差。今輪唔重搜公式，
只用 archived pre-race `current_live_rank` 做事後分層診斷：

- 最新 research dataset 34 meetings／342 races；同 rail-position result dataset 成功配對
  3,833 runners／309 races。
- 為免 target race 自己決定自己嘅 regime，每場只用**同日其他場次**計 position edge
  同 draw edge（leave-one-race-out）；298 races／30 meetings 有足夠兩邊資料。
- `front_inner` 定義為前置同內檔 residual edge 都大於0；`closer_outer` 兩者都小於0。
  draw 只係檔位 proxy，唔係實際走幾疊。

| Regime | Races / meetings | Gold | Good | NDCG@5 | 實際前三平均模型排名 |
|---|---:|---:|---:|---:|---:|
| front + inner | 232 / 27 | 13.36% | 22.41% | 65.51% | 4.97 |
| closer + outer | 11 / 2 | **0.00%** | 27.27% | **75.24%** | 5.09 |

Gold 差13.36pp（meeting-cluster bootstrap 95% CI +9.67至+16.77pp）支持「完整Top4
覆蓋喺反向regime崩落」；但 Good 同 winner-in-Top3 冇同方向跌，NDCG反而較高。
因此唔應描述成整體排序全面失效，更準確係：**反向regime令一至兩匹上名馬跌到Top4
以外，令Gold呢個all-or-nothing指標歸零。** closer+outer 只有兩個meeting，仍屬強烈但
小樣本診斷，唔可單獨改formula。

兩個完整反向日為2026-09-09及2026-09-23跑馬地，共17場，Gold 0/17。當日實際前三：

- 外檔9+：18匹，Top4 capture **0/18**，平均模型排名9.44；
- 內檔1–4：15匹，Top4 capture **14/15**，平均模型排名2.20；
- 實際早段後置9+：17匹，Top4 capture 5/17，平均模型排名6.65。

呢個確認現行 draw-heavy race-shape 對常態內檔優勢有效，但遇到反向賽道時有非對稱
尾部風險。正確下一步唔係預賽日無條件加外檔／後追，而係另測 causal、逐場先後有序嘅
`reverse-bias risk / shortlist diversification`：至少兩場同表面賽果後先啟用，先降低
信心或提供反向情境替補，唔直接大幅重排。原 `same_day_position` 候選已因 terminal
Gold／Champion各−2.17pp被拒，唔可因今次兩日個案翻案。

## 2026-10-06 prospective implementation

已落地 `HKJC_REVERSE_BIAS_SHADOW_V1`，但身份仍然係 **SHADOW ONLY**：

- intraday 排程每15分鐘醒一次，但只會喺已分析賽日同場地時間窗內抓 partial results；
- target Rn 只讀同表面、已完成而且 race number `< n` 嘅連續賽果；至少兩場先有決策；
- position 同 draw 訊號各自以4場達 full reliability，向中性0.5 shrink；兩者都至少0.55
  先標記 reverse bias；
- official Top3 固定，只喺 shadow Top4 用最高正式排名、但未入Top4嘅外檔情境馬替換第4；
- draw 明文標示只係 lane proxy，實際走幾疊仍然未觀測；唔讀 odds；
- snapshot 以 source hash + completed prefix + decision 產生 immutable id，亦保存已消毒嘅
  position／draw percentile observations（不保存 odds），重跑只會 reuse；
- 賽後 baseline／shadow 分開結算 Gold 同 Top3 capture@4，寫入獨立 ledger；至少80個
  active races 先可做 locked review，`auto_promotion=false`；
- 正式 ability、rank、Logic、Top4 同 morning prediction snapshot 全部不變。

實作與測試：

- `.agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts/hkjc_reverse_bias_shadow.py`
- `.agents/skills/hkjc_racing/hkjc_wong_choi_auto/tests/test_reverse_bias_shadow.py`
- `.agents/skills/hkjc_racing/hkjc_daily_auto/tests/test_hkjc_intraday_shadow.py`

## Reproduction

```bash
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 \
  docs/experiments/patches/hkjc_same_day_bias_ab.py \
  --dataset /tmp/hkjc_ranking_dataset_20260928_v2.csv \
  --output /tmp/hkjc_same_day_bias_ab_20260928.json
```
