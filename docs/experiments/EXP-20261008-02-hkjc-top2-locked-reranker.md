# EXP-20261008-02 — HKJC Top-2 locked boundary reranker

- **日期**：2026-10-08
- **平台**：HKJC
- **狀態**：REJECT／USER-DIRECTED ARCHITECTURE WITHDRAWAL — 弱正向但 Stage 4 不足，且鎖名次會人為保護指標
- **假設**：現役 Top-5 通常已包含大部分實際好馬，但第 3–8 位有一兩匹被排高／排低；
  鎖死首兩名，只用賽前 point-in-time 訊號重排第 3–8 位，可改善 Top-5 邊界並直接
  保護 Good／Champion。
- **前置實驗**：EXP-20261008-01 證明極端 core/context 小修方向正面但力度不足；
  EXP-20260928-06/07-HK/08 證明 wholesale 7D refit 會傷 primary，因此今次不改全場權重。

## Baseline and leakage contract

- baseline commit：`c89a2f09e79c559de512845a22608073ac06c705`；
- 同一 340 場／4,239 runner point-in-time dataset；最後 15% 日期封作 terminal；
- baseline 必須用 `current_live_recomputed_ability`；
- 只用今場賽前已存在、正式 engine 可取得的 current score、7D matrix、feature scores、
  venue／surface／distance／class／field size；
- 所有 runner 特徵先轉為同場 percentile rank；不使用 odds、市場 rank、賽果、賽後
  incident、未來 trainer／horse statistics；
- `finish_pos` 只供 label 與最後 evaluation join。

## Locked learner

- regularized logistic regression，target = 實際前三；L2，`C=0.20`，不設 class weight；
- development 用五個 chronological blocks 做 expanding-window OOF：每 fold 只可用較早
  日期；第一 fold 沒有更早資料，候選保持 baseline；
- terminal 只在 development 揀定一個 arm 後開一次，模型用全 development fit；
- 初出馬可以參與，但沒有專屬 fallback 或人手規則。

## Locked rerank

1. 現役第 1、2 名完全鎖死；第 9 名或以後完全不動。
2. 只重排現役第 3–8 名。
3. 分數為 current-rank percentile 與 ML-rank percentile 的 Borda blend。
4. 固定三個 ablation arms：ML share `15%`、`30%`、`45%`。

Development selection rule：Gold／Good 不得回歸、至少 3/5 folds primary 非負、三個
ranking metric 至少兩個正向、tail guardrail 不得明顯惡化。合資格時先選 ranking 改善
最大者；相同則選較低 ML share。參數及 selection rule 在 terminal 前鎖定。

## Locked evaluation

- Stage 4 Gold／Good no-regression；Champion 應因 Top-2 lock bit-identical；
- Top-3 Capture@5、Competitive Recall@5、NDCG@5；
- 實際前三跌出 Top-5、實際前三最差模型 rank、模型 Top-5 跑第 8+；
- meeting-level Top-5 hits／完整 capture SD；
- 沙田／跑馬地在 development、terminal 分開報；
- terminal 任一 Gold／Good 回歸、ranking 全無改善、或 volatility／tail 明顯惡化即 REJECT。

## Production gate

只有 Stage 4 通過先會產生 frozen coefficient artifact、接入 deterministic engine、更新
golden／data contract／生成模型說明並跑完整測試。否則只保留 experiment record。

## 結果與決定

Development 揀到 `top2_lock_ml30`：Gold／Good／Champion 全部 0.00pp，Capture@5
+0.71pp、Recall +0.23pp、NDCG +0.00347；terminal 亦分別 +1.11pp、+1.17pp、
+0.00523，三個 primary 仍 0.00pp。34 meeting 的 Top-5 hits SD 由 0.3006 降至
0.2880（−4.2%）。

不過三個 ranking CI 都未獲 Stage 4 支持，判 `ranking_evidence_too_weak`。更重要係
Top-2 lock 令 Good／Champion 結構上不能回歸，容易將「避開評估風險」誤當「整體
模型變準」。用戶提出此設計過度針對現有排名，決定合理。

**REJECT，不接 main、亦不作 prospective candidate。** 後續只接受對全場每匹馬用
同一規則的 holistic candidate。
