# EXP-20261113-43 結果：前置馬加分按直路長度（V1）／逐場地收縮（V2）—— 兩個都 REJECT

- **預先登記**：[protocol](EXP-20261113-43-au-front-by-straight-length-protocol.md)（分支 `claude-au-straight-venue-20261113` `65ecfa4f`，量度之前 push）。
- **baseline**：`FINAL.json`（main `1c33b058` 評分），3,736 場、99 個賽日；幾何 120／133 場地（EXP-20261113-42 補齊後）。
- **碼**：`scratch/au_front_straight_venue_20261113.py`；判決器 `scratch/au_short_straight_wf_judge_20261113.py`（`JUDGE_MODE=walk_forward_oos`）。
  證據：`EXP-20261113-43-evidence/`。
- **接線**：兩個 arm 各郁 2,245 場、5,042 匹（有幾何場地嘅前置馬）。
- **決定**：V1、V2 **REJECT / primary_regression**。family（L1–L3、W1、V1、V2）冇一個 WIN，Holm 唔使調。

## v3 walk_forward_oos

| arm | Gold | Good | top3@5 | ndcg@5 | top5 AUC | 分層 CI 全負 |
|---|---|---|---|---|---|---|
| V1 直路線性 | −0.21 [−0.47, +0.03]（3/6 塊） | +0.03 | +0.12 | −0.01 | +0.06 | ≤8 匹 Gold、1201–1600m Gold |
| V2 逐場地收縮 | −0.08 [−0.28, +0.13] | −0.03 | +0.04 | +0.01 | +0.04 | 首選前置 Gold |
| （對照 W1，<375m 單一門檻） | +0.08 | −0.05 | +0.11 | +0.10 | **+0.11 CI 全正** | — |

## 描述（唔做判決）

- **V1 直路斜率會散**：c1（每多 100m 直路嘅前置效應）由 08-26 −0.257 跌到 11-12 −0.067 —— 數據越多，「直路越短越利前置」越弱。
  最後 β：Kilcoy（143m）+3.2、Mornington（210m）+2.6 … Flemington +0.4、Rockhampton −1.0。
- **V2 逐場地同直路長度唔一致**：最後 β 最高 Kalgoorlie +3.2、Alice Springs +3.1、Tamworth +2.9、**Rockhampton +2.9**（直路 600m）；
  最低 Canberra −2.9、Randwick −2.5、Dubbo −2.2、Flemington −1.5。即係逐場地估出嚟嘅係噪音，唔係直路機制。
- 頭三選命中：V1 0 hit 9.02% → 8.83%、平均命中 +0.0021；V2 9.02% → 8.97%、+0.0037（78／52 場命中數有變）。

## 解讀

- 用齊 93% 場次之後，「直路越短越利前置」唔單止過唔到閘，連方向都喺擬合入面慢慢消失。
  EXP-20261113-41 嘅描述層剩餘超額（直路 < 400m +2.8～+4.2pp）同 W1 嘅 AUC 改善，係集中喺少數短直路場地，
  唔係一個可以按直路長度推廣嘅規律。
- 逐場地收縮（k = 200）都抵唔住每場地一百幾匹嘅噪音 —— 估出嚟嘅場地排名同直路長度冇關係。
- 呢個係「直路 × 前置」第四次唔過閘（EXP-20260902-01、20261113-23 L、-41 W1、今次）。

## 唔再試

- 冇新資訊來源（例如真逐駒起步位／步速）之前，唔好再開「直路 × 前置」family。
- 唔准改 k、z 中心、或者揀場地名單再試。

## 重跑

```bash
export PYTHONDONTWRITEBYTECODE=1
D="/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/au-front-straight-venue"
python3 scratch/au_front_straight_venue_20261113.py "/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/au-noise-20261113/FINAL.json" "$D"
```
