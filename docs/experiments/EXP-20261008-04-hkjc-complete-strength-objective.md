# EXP-20261008-04 — HKJC complete-strength objective

Status: **PROMOTE — Stage-4 `RANKING_WIN`**.

## 問題

舊 `overall-strength 60/40` 只係重新分配 core/context 權重，development Gold
跌 2.47pp；佢冇真正改變「模型學緊乜」。今次測試將 horse-level core 由入位
二元訊號改為全場連續名次強度：第一至包尾都有資訊，避免只問有冇入前三。

## Locked design

- baseline：EXP-20261008-03 的全場 `shape_winsor10`；
- target：`1 - (finish_position - 1) / (field_size - 1)`，只作訓練 label；
- learner：positive Ridge，固定 `alpha=4`；
- inputs：只用賽前 horse-level evidence，包括 speed、class、form、consistency、
  form-line、distance、official rating、近六仗、上仗負距、總勝率、同程及同場同程
  強度；不使用 draw、race-shape、trainer、odds 或賽後文字；
- 所有 input 在同場轉 percentile，缺值先以同場中位處理；
- 5 個 expanding-time development folds；validation 日期的結果不得進入 fit；
- 全場同一排序公式，不鎖 Top 2、不只修第 3–8 位；
- terminal 只可在 development 有候選過閘後打開。

## Locked arms

1. `strength_global15`：global strength 佔 15%；
2. `strength_global25`：global strength 佔 25%；
3. `strength_venue15`：沙田／跑馬地分開 fit，strength 佔 15%。

## Selection gate

Development 必須 Gold、Good 非負，5 folds 至少 3 folds 兩項 primary 同時非負，
三個 smooth ranking 指標至少兩個改善，tail errors 不惡化，meeting-level Top-5
hits 波幅不得增加。合資格候選按 smooth ranking 改善總和選一個，terminal 及
Stage-4 仍按既有 evaluation contract 判決。失敗候選只保留研究記錄，不入 live。

## Leakage declaration

所有 input 來自 archived pre-race card/form/engine fields；賽果只用作過去 fold 的
訓練 label 及 scoring 後 evaluation。沒有 odds、同日較後結果、未來結果或 incident
text。

## Result

Development 280 場用預先鎖定規則選中 `strength_global15`：

| 指標 | Delta vs shape_winsor10 |
|---|---:|
| Gold | +0.71pp（多 2 場） |
| Good | +0.36pp（多 1 場） |
| Champion | 0.00pp |
| Top-3 Capture@5 | +0.12pp |
| Competitive Recall@5 | +0.04pp |
| NDCG@5 | +0.00124 |
| Meeting Top-5 hits SD | 0.2781 → 0.2666（−4.1%） |

5/5 development folds 的 Gold、Good 都同時非負。25% arm 雖然波幅更低，但只有
2/5 folds primary 同時非負；場地分開 15% arm 合資格但 objective 較低，所以兩者
都冇被選。即係完整戰力層暫時毋須分開沙田／跑馬地；底層 draw、race-shape、
surface evidence 仍然各自分場地。

Locked terminal 60 場：Gold 0.00pp、Good +1.67pp、Capture +2.22pp、Recall
+2.00pp、NDCG +0.01207。沙田 terminal 43 場 Good/Capture 各 +2.33pp、Recall
+2.21pp；跑馬地 17 場 primary 全部持平而 Capture +1.96pp。Stage-4 判
`RANKING_WIN / primary_neutral_ranking_supported_gain`。

全 340 場相對 winsor10：Gold +0.59pp、Good +0.59pp、Champion 0、Capture
+0.49pp、Recall +0.39pp、NDCG +0.00315；meeting Top-5 hits SD 0.2896 →
0.2697（−6.9%）。兩步合計相對原 live：Gold +0.59pp、Good +0.59pp、Champion
+0.59pp、Capture +1.47pp、Recall +0.71pp、NDCG +0.00960；逐日 SD 約
0.3006 → 0.2697（−10.3%）。

相對最初 live 的合併候選仍承接 EXP-03 terminal 少 1 場 Gold，因此按原 Stage-4
硬閘仍會標 `primary_regression`；今次 `RANKING_WIN` 係完整戰力層相對已由用戶接受
的 winsor10 baseline 的獨立判決。呢個紀律保留喺記錄，唔會將一場 trade-off 隱藏。

## Frozen production formula

正式排名用：

`85% × robust-7D 同場百分位 + 15% × complete-strength 同場百分位`

完整戰力係 development-only positive Ridge frozen coefficients；最高邊際係近六仗
平均名次，其次上仗負距、form、form-line、distance、speed、class、rating change。
同程／同場同程率在控制其他證據後係數收縮到 0，故今次唔重複加分；佢哋仍留在
既有 distance/surface path。所有馬用同一公式，冇 rank lock 或 named-horse swap。

Production 同時保存 `complete_strength_legacy_ability_only` immutable rollback
shadow；至少 80 個 forward active races 後，舊式如多至少 2 場 Gold 或 Good、而
另一 primary 非負，monitor 才建議 rollback，永不自動啟用。env emergency rollback：
`WC_HKJC_COMPLETE_STRENGTH=legacy_ability_only`。
