# EXP-20261116-02 預先登記：AU 外層權重 walk-forward refit（HKJC EXP-20261114-03 S 版嘅 AU 版）（睇判決結果之前寫）

觸發：Kelvin 2026-11-16：「after we test the last race odds, let's also move on to 大樣本回放 + 外層權重 refit」。
HKJC S 版（6,047 場回放 fit）回放 holdout Gold +1.93、Good +2.16，Kelvin 上線。

## 同 HKJC 唔同嘅地方（照實寫）

- **AU 冇大樣本忠實回放。** 乾淨 point-in-time 語料只有 2026-08-05 起（3,736 場）；之前嘅場次係賽後重評（洩漏，見 EXP-20260903-02、
  檔位矩陣洩漏記錄），唔用嚟 fit。所以呢個係「現有乾淨語料嘅 walk-forward refit」，唔係 HKJC 嗰種大回放。
- 以前 AU refit：EXP-20260928-02（2,853 場共識 REJECT）、EXP-20261101-39（3,246 場診斷：適當 fit 冇多預測力）。今次語料大少少、
  方法改做 HKJC 嗰套（場內置中 logistic、縮放到現行總和、逐段 walk-forward），預期效果細。

## 方法

六個維度分 m_k（`map_features_to_matrix_scores`），場內置中。A/A：重算 `compose_matrix_score + overlay` 同 dump ability 最大差 < 1e-3 先繼續。
由第 21 個賽日開始，每 7 個賽日用之前所有賽日（2026-08-05 起）嘅賽果 fit 一次：
logistic 入位 ~ a + Σ c_k·m_k + c_r·rest（rest = overlay（濕地／全程速度／檔位）＋冇 fit 嘅維度×現行權重）。
w_k = max(c_k, 0) × S，S 令 fit 維度權重總和 = 現行總和。頭 20 個賽日用現行權重。逐日用嘅權重都冇睇過當日賽果。

| arm | fit 邊啲維度 |
|---|---|
| **R**（主 arm，HKJC S 版做法） | stability、jockey_trainer、class_weight、track、preparation；**pace_perf 固定 0.0879**（Kelvin「段速係核心」，唔用代理數據調低段速） |
| RF（診斷，HKJC F 版） | 六維全部 |
| RP（有條件） | **只有 EXP-20261116-01 P 過上線條件先跑**：R 權重 + P 上仗賠率（兩樣同一個 logistic 一齊 fit） |

## 判決

BASE = `FINAL.json`（同 EXP-20261116-01），2026-08-05 起 3,736 場，v3 `evaluate_full_record` `walk_forward_oos`，
ranking metric = top3 capture@5、NDCG@5、top5 AUC，賽日 bootstrap 2000；分層同 EXP-20261116-01（加首選距上仗日數）。

- **上線條件**：PRIMARY_WIN 或 RANKING_WIN，跑咗嘅 arm 做一個 family **Holm** 後 p < 0.05，冇分層 CI 全負。
- 「冇代價」：Gold、Good 點估計都 ≥ 0、冇分層 CI 全負 → 交 Kelvin 決定。
- 其餘 REJECT。數值（warm-up 20、每 7 日、負係數夾 0、縮放到現行總和）喺睇結果之前定死。冇過嘅 arm 唔會 commit model code。
- 上線要用**全語料最後一次 fit 嘅權重**，再喺 forward 監察；呢個實驗只判 walk-forward 版本。

## 命令

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scratch/au_outer_refit_20261116.py \
  "/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/au-noise-20261113/FINAL.json" \
  "/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/au-outer-refit-20261116"
```

結果：`EXP-20261116-02-au-outer-refit-results.md`；判決 JSON：`EXP-20261116-02-evidence/`。
