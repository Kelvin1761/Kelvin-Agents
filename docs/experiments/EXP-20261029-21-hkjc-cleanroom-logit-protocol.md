# EXP-20261029-21 — HKJC clean-room 簡單模型 vs 現行模型（預先登記）

- **日期**：2026-10-29；平台：HKJC；mode：`walk_forward_oos`
- **問題**：「砍掉重練」值唔值得做？如果一個只用賽果庫、零人手規則嘅簡單模型
  喺同一批場次打和或者贏現行 9D 引擎，就代表現行嘅複雜度冇貢獻；輸就代表重寫會蝕。
- **假設（可證偽）**：clean-room conditional logit 喺 v3 全紀錄判決下唔差過現行模型
  （Gold／Good 點估計 ≥ 0）。
- **搜索過嘅舊記錄**：EXP-20261010-02（同一語料、同類 logit，只做訊號篩選，
  OOS AUC 0.7143，**從未同現行模型喺同一批場次比較**）、EXP-20260928-01（ML 診斷，
  base-6 matrix 上加 component，唔係獨立模型）、EXP-20261014-10（市場基準）、
  EXP-20261019-02（外層權重 refit）。冇記錄做過「獨立簡單模型取代成個引擎」。

## 鎖定配置（睇任何對比結果之前寫低）

- **Baseline**：`hkjc_eval_harness.py run`（production `score_race` + PIT priors），
  worktree HEAD `fadb6ed1`。
- **Candidate**：`docs/experiments/patches/hkjc_cleanroom_logit.py`
  - 資料：`HKJC_Race_Results_Database` 全部 `full_day_results.json`（2024-09 起）。
    退出馬（`W*` 或者空白名次）**唔當出賽**：唔入歷史、唔計騎練出賽數
    （`hkjc_expanded_corpus.py` 會將佢哋當成冇名次嘅出賽，呢度唔跟）。
  - 特徵（12 個，全部只用賽日之前嘅賽事，同日賽事互相睇唔到）：
    近三仗名次百分位、近三仗輸距、上仗名次百分位、歷史上名率（EB k=3 向 0.25 收縮）、
    騎師 as-of 上名率（EB k=20）、練馬師 as-of 上名率（EB k=20）、檔位百分位、
    檔位百分位 × 跑馬地、負磅 − 頂磅、同程上名率、近三仗首段位置百分位、
    log(休賽日數)、log(1+出賽次數)、班次變動。
    每場內 z-score，缺值 = 0 + 缺值旗。
  - 模型：同場 softmax conditional logit，目標 = 頭三（三匹各 1/3），L2 = 1.0，L-BFGS。
  - Walk-forward：每個評估賽日 D，只用 `day < D` 而且 `day ≥ 2024-12-01`
    （三個月 warmup）嘅賽事 fit，再預測 D 全部場次。
  - 排名對象：同一場 baseline `picks` 入面嘅馬（同一個候選集），按 candidate 分數排。
- **判決**：`hkjc_eval_harness.py compare base cand --stage4 walk_forward_oos`，
  預設剔走 `speed_score` 死咗嘅賽日。單一 arm，冇 family、冇 Holm。
- **唔做**：唔調特徵、唔調 L2、唔換目標去救結果。睇完結果之後嘅任何變動都係新實驗。

## 預先講明嘅解讀

- 打和或者贏 → 現行複雜度冇證據有貢獻，砍掉重練有理據（但仍然要 forward 確認）。
- 輸（primary_regression）→ 現行引擎入面賽果庫冇嘅資訊（段速、晨操、賽績線、
  評分、配備）或者規則有貢獻，重寫唔應該由呢個起點出發。
