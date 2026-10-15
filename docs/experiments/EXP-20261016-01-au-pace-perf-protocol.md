# EXP-20261016-01 預先登記：AU `pace_perf` 診斷（1–3）同修正（4–6）

> 呢份喺**睇任何結果之前**寫。之後唔准為咗救候選而改指標、窗、門檻或者變體。
> 結果另寫：`EXP-20261016-01-au-pace-perf-results.md`。

- **日期**：2026-10-16
- **平台**：AU
- **起因**：用戶同 Claude 逐個維度覆核公式，第一個係 `pace_perf`。用戶要求診斷 1–3、
  修正 4–6，試閘分完全剷走（三條路、所有馬，用戶 2026-10-16 揀定）。
- **舊記錄**：EXP-20261015-02（試閘門檻 2/4/6 + refit）、EXP-20261012-31（剔走試閘 PF
  Gold −0.37pp）、EXP-20260831-03（個體化 L600）、Codex EXP-20261015-08/09/10/12/14
  （全程／頭段速度，研究分支）、memory `au-pace-figure-is-the-only-orthogonal-leaf`、
  `au-race-level-l600-outweighs-own-sectional`、`au-trial-score-is-accurate-but-unheard`。
- **把尺**：合約 v3 + §8（兩邊都 refit，EXP-20261015-20）。

## 現行公式（`engine_core._pace_figure_score`、`_pf_aggregates`）

```
own_i = L600Δ_race,i + margin_i × 0.17            （只計 Sportsbet）
x     = mean(own_i)，Formguide 上面全部 PF 往績，每場一樣重
z     = (x − 場均) / 場內標準差                  （同場 ≥3 匹有數據）
PF    = clip(60 − 20z)
pace_perf = 60 + 0.941744 (PF − 60) + 0.058256 (trial − 60)，係數 0.12094
```

## 語料

- 研究 dump：`scratch/au_paceperf_dump_20261016.py`，同 production dump 同一評分路徑，
  另外輸出引擎實際食嘅 PF 往績（`pf_run_list`）。
- **判決窗**：2026-08-05 起乾淨 point-in-time 段（v3 fit 類候選只准用呢段）。
- **揀形狀窗**：2026-08-05 之前（賽後重評，有前視 FLAG）。只用嚟為 4、5 揀固定值，
  **唔參與任何判決**。
- 排除：前三不足 3 匹、冇頭馬嘅場次（同 canonical）。

## 診斷（只量度，唔改模型）

指標：**leaf 層面**場內配對 AUC（同場上名 vs 落第，只計 PF 有值嘅馬），
按賽日 bootstrap 2000 次，seed 7，配對 Δ 對現行 leaf。leaf 準咗唔等於排名會好
（memory `leaf-auc-gains-do-not-convert-to-ranking`），所以診斷贏咗嘅變體
只係**入圍**第二階段，要過 §8 先算數。

### D1 後上馬偏差

- 每匹馬嘅跑法 = PF 往績入面 `(pos_settled − 1)/(starters − 1)` 嘅平均
  （正式賽、兩個欄都有、starters ≥ 2）。三等份：前置 < 1/3、守中、後上 > 2/3。
- 場內按 PF 分排名切五等份；每格計「實際入前三率 − 3/馬匹數」（超額）。
- **主統計**：後上超額 − 前置超額，五格平均（按格內樣本加權），賽日 bootstrap CI。
  CI > 0 = PF 低估後上馬；CI 跨零 = 量唔到偏差。
- 副統計：用今仗 `running_style_line` 標籤再做一次。
- **唔准**用「位置 × 固定馬位」砌落後距離（Codex EXP-14 已講明位置係序數）。
  D1 只做診斷；如果見到偏差，修法要另外登記。

### D2 大敗場極端值

變體（逐場 own_i 唔變，只改聚合）：
- D2a：margin 封頂 6L
- D2b：margin 封頂 10L
- D2c：中位數代替平均
- D2d：剔走最差一場再平均（≥3 場先剔）

另報：margin > 10L 嘅往績佔幾多。

### D3 近仗權重

- D3a：最近 3 場平均
- D3b：最近 5 場平均
- D3c：指數衰減，權重 0.8^k（k = 0 係最近一場）

D2 + D3 共 7 個變體當一個 family，Holm 調整。

## 修正（候選，過 §8 先上線）

### F4 秒／馬位隨速度變

`s/L_i = 0.17 × v_ref / v_i`，`v_i = distance_i / winning_time_i`。
`v_ref` = 揀形狀窗內全部 PF 往績 `v_i` 嘅中位數（喺判決窗之前定死）。
冇頭馬時間就用 0.17。固定規則，冇 fit。

### F5 高分飽和

喺揀形狀窗量「PF 分（5 分一格）→ 超額入位率」曲線。
候選形狀：`z` 截喺 `[−z*, +z*]`，`z*` = 曲線停止上升嗰格對應嘅 z（揀形狀窗定）。
如果揀形狀窗見唔到飽和，**冇 F5 候選**，照記。

### F6 剷走試閘表現（用戶決定）

- `trial_performance_applies` 對所有馬返 False：試閘 PF 往績唔再入 L600、
  初出馬試閘時間代理停用、`trial_score` 一律 60。
- `pace_perf` 只剩 `pace_figure_score`（leaf 權重 1.0），係數 = 0.12094 × 0.941744，
  PF 嘅傳導量完全不變。
- `trial_score` 改為 report-only，唔再當證據計（安全欄唔會因為佢 = 60 而觸發）。
- 試閘備戰（preparation）同體能照留。
- 性質：**用戶接受嘅簡化**，唔係已證實改善。照報證據。
- Ablation（累加，三份 dump）：F6a 只剷 leaf + 證據計數；F6b 再剔 PF 試閘行；
  F6c 再停初出馬時間代理（= F6 全部）。

### 判決

每個 F 候選：§8 四 arm（`au_walkforward_refit.py`，同一 procedure hash）
→ `evaluate_with_refit_arms`。歷史來源 availability 仍係 FLAG，所以正式 v3
會係 `leakage_audit_failed`；另報 `leakage_audit_passed=True` 嘅研究診斷，
**唔會當成 WIN**。F 候選之間（F4、F5、F6）各自對同一 baseline，Holm 跨候選。
多個 F 一齊上線之前要再做合併 + ablation。

## 未包括（下一階段）

Codex Sportsbet-only 全程速度／頭段（EXP-20261015-14 規格）：用戶要求納入，
但要先建 par 標準，另開登記，唔喺呢份入面偷偷加。
