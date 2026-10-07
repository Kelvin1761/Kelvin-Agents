# EXP-20261005-01 — HKJC 沙田 trainer recency prior

- **日期**：2026-10-05
- **平台**：HKJC
- **狀態**：RETROSPECTIVE COMPLETE / LIVE REJECTED / EARLY-SEASON FORWARD SHADOW
- **上游**：EXP-20260929-03、EXP-20261004-01

## 問題

沙田新季 audit 入面，`trainer_signal` Top3-vs-rest AUC 由0.6852跌至0.5680，
係七個維度最大跌幅（−0.1172）。現行 trainer master rating 將季度 starts 直接累加；
季初少量新賽果會被上一季大量 starts 淹沒。直接接入26/27賽果喺10月4日又出現
Gold增加、Good／Winner-in-Top3倒退嘅 trade-off，所以今輪測試「按日期漸退」而唔係
再加大 current-season multiplier。

## 凍結候選

只改 trainer master rating；jockey master、騎練組合、同程、換騎、7D外層權重、
race-shape 同其他 feature 全部不變。

每個 target meeting 只讀 `Date < target_date` 嘅已完成結果：

```text
row_weight = 0.5 ** (days_before_target / half_life_days)
```

加權 wins／places／starts 之後沿用 production `k=100` empirical-Bayes、負面縮放同
trainer floor。預先登記三個 half-life：90、180、365日；唔加第四個值，唔搜索 k。

適用範圍固定為：

- 沙田草地；
- 非初出馬；
- 跑馬地、沙田AWT、初出馬必須沿用 baseline，排名 bit-identical。

## 固定語料及切分

- **dev**：2026-05-06 至 2026-06-13，現役 schema meeting。
- **terminal**：2026-06-21 至 2026-07-12；只喺 dev 揀完 half-life 後評估。
- **new-season diagnostic**：2026-09-06 至 2026-10-01；已被用作問題診斷，唔係 blind
  holdout，結果只決定值唔值得 forward shadow，唔可直接 promotion。
- legacy sparse-schema meeting 排除；baseline／candidate 同場、同 results、同 PIT rows。

Dev selection：先要求 canonical Gold 同 Good positional 點估計均不倒退；合資格候選
依 `Gold Δ → Good Δ → NDCG@5 Δ → Top3 capture@5 Δ` 排序。完全相同時揀較長
half-life（較保守）。Terminal 唔准反過來改 selection。

## 判決

- canonical Gold＝實際前三全部喺 model Top4；另報 `gold_strict`，兩者唔混用。
- Primary 依 `docs/model-evaluation-contract.md`：Gold／Good dev 或 terminal 任一點估計
  回歸即 REJECT。
- Ranking-only 必須 primary 無回歸，且預先登記 ranking metrics 至少兩項 dev、terminal
  同向改善，其中至少一項 terminal paired CI 下界 >0。
- 即使 retrospective 過閘，2026/27已被睇過，只可建立 immutable forward shadow；
  production ranking、10月4日分析、scheduler live formula全部不直接改。

## 重跑

```bash
PYTHONDONTWRITEBYTECODE=1 python3 \
  docs/experiments/patches/hkjc_trainer_recency_ab.py \
  --out /tmp/hkjc_trainer_recency_ab_20261005.json
```

## 結果

完整PIT corpus：dev 120場（當中71場沙田草地）、terminal 73場（51場沙田草地）、
新季診斷67場（39場沙田草地）。每個 target 嘅最新 prior date 均早過 target date；
errors=0。跑馬地同沙田AWT共三個 partition、三個 arm 全部 metric delta 逐項為0，
no-op contract PASS。

以下係沙田草地 active cohort：

| arm | dev Gold | dev Good | terminal Gold | terminal Good | terminal NDCG@5 | 判決 |
|---|---:|---:|---:|---:|---:|---|
| 90日 | 0.00pp | **−2.82pp** | 0.00pp | **−1.96pp** | −0.07pp | REJECT primary regression |
| 180日 | 0.00pp | 0.00pp | 0.00pp | **−1.96pp** | −0.05pp | REJECT primary regression |
| 365日 | 0.00pp | 0.00pp | 0.00pp | 0.00pp | +0.10pp [0.00,+0.30] | no regression，但證據未過閘 |

365日按預註冊 dev selection 勝出；dev NDCG +0.17pp [0.00,+0.50]、平均實際前三
model rank −0.0047，terminal NDCG +0.10pp [0.00,+0.30]、平均rank −0.0131。
方向一致但CI只貼住0，未達 Stage-4 `RANKING_WIN` 嚴格下界；而新季39場 NDCG／
capture全部0差、平均rank反而+0.0171，所以**365日唔值得升live，亦唔另開長期shadow**。

## 10月4日賽前snapshot診斷

用最後一份真正賽前 immutable snapshot，同 `Date < 2026-10-04` PIT rows；呢度 baseline
係已接 current-season data repair 嘅版本，唔係當日實際未接26/27嗰個原版：

- 90日：canonical Gold +9.09pp；Good／Champion／Winner-in-Top3全部0；NDCG +0.04pp。
- 180／365日：所有上述指標0差。

90日喺今季39場加10月4日方向較好，但佢已喺舊季dev／terminal各蝕Good，唔可以
借單日結果升live。呢個只支持一個**新、明確標成post-hoc**嘅季初假設。

## 跑馬地獨立延伸消融

2026-10-05再用相同PIT cutoff、相同production math同預先存在嘅90／180／365日
half-life，將active cohort改為跑馬地草地非初出馬；沙田、AWT、初出馬一律不改。
呢輪係獨立venue驗證，唔會因為沙田已開shadow就假設跑馬地都有相同regime drift。

- dev：45場（2026-05-13至06-10）；三個arm canonical Gold全部**−2.22pp**。
- terminal：18場（2026-06-24、07-08）；三個arm所有已報metric均0差，冇獨立確認。
- new-season diagnostic：25場（2026-09-09至09-23）；Gold、Good、Champion、
  Winner-in-Top3、Top3 capture全部0差。
- 新季90日只見平均實際前三model rank −0.0133、NDCG@5 +0.11pp
  [0.00,+0.33]；幅度細，而且係已見diagnostic，唔可抵銷dev Gold回歸。

結論：**跑馬地live同forward shadow均不加入trainer recency**。保留現行trainer prior；
如日後跑馬地另有明確data-drift證據，應先建立venue-specific假設再做新一輪blind shadow，
唔可以直接共用沙田候選。

## 最終處理

1. production 7D、trainer rating、10月4日分析全部不改。
2. 新增 `trainer_recency_st_early90` prospective shadow：只限9至12月沙田草地非初出馬；
   90日半衰只取代trainer master base，其他一律不變。
3. pre-race stats builder 產生 `experimental/trainer_recency_90d_stats.csv`；2026-10-05
   本機快照67名練馬師、latest result=2026-10-01。歷史最新檔讀取由 temporal guard 阻擋。
4. immutable snapshot settlement 門檻80 active races；達標仍要重跑 Stage-4 paired CI，
   絕不自動promotion。
5. 呢個 forward candidate 係由已見新季數據形成，故未來證據只可由本實驗完成之後嘅
   immutable pre-race snapshot開始計。
