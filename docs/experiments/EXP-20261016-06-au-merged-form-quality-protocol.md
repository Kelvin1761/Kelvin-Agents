# EXP-20261016-06 預先登記：近績分 + 表現質素分合併（賽事質素判近績）

> 喺計任何候選數字之前寫。結果另寫 `EXP-20261016-06-au-merged-form-quality-results.md`。

- **日期**：2026-10-16；**平台**：AU
- **用戶要求**：「performance_quality should be combined together with form_score… use the quality
  of the race to judge the scoring in the form score」；之後再問「shall we look at 6 races instead of just 4」。
  設計由 Claude 提出、用戶 2026-10-16 同意：賽事質素用**獎金**，每場一條式，先量 leaf 再跑 §8。
- **baseline**：`claude-au-stability-20261016` @ `e684d05a`（F6a + 班次 parser 修正）。
- **舊記錄**：EXP-20260903-01（死班次乘數，剷走 K1 會蝕）、EXP-20261016-04（stability 量度）、
  memory `au-reallocating-dimension-shares-fails`、`leaf-auc-gains-do-not-convert-to-ranking`。

## 而家點計（對照）

`stability = 60 + 0.6(近績分 − 60) + 0.4(表現質素分 − 60)`：近績分睇名次（4 級階梯）＋死班次乘數
＋獎金場內調整＋−4 規則；表現質素分睇負距＋獎金。班次計咗兩次，名次同負距分開兩個 leaf。

## 候選（4 個，全部固定，冇 fit）

每場往績 i（用 production 嘅 `_performance_quality_digest` 揀出嚟嘅完整正式賽：有負距、獎金、
出賽數，目標日之前）：

| 成分 | 定義 |
|---|---|
| 名次 | `z_place = (0.5 − pct) / σ_pct`，`pct = (名次 − 1)/(出賽數 − 1)`；名次唔合法就成場唔計 |
| 負距 | `z_margin = −(min(20, |負距|) − μ_m) / σ_m` |
| 賽事質素 | `z_class = (log10 獎金 − μ_p) / σ_p` |

- **eq3**：每場值 = 三個成分平均（名次 + 負距 + 賽事質素）。
- **eq2**：每場值 = 名次同賽事質素平均（用戶原意：用賽事質素判名次；冇負距）。
- **N4**：最近 4 場，權重 1.0／0.8／0.6／0.4（同而家一樣）。
- **N6**：最近 6 場，權重 1.0／0.8／0.6／0.4／0.3／0.2。
- 候選 = {eq3, eq2} × {N4, N6}。最少 2 場先計；場內 ≥ 3 匹有值先標準化：
  `合併 leaf = clip(60 + 20 × 場內 z(加權平均))`。
- **冇值嘅馬**：用返而家嘅 `stability` 合成分，排名同而家一樣。
- 實作：`form_score` 同 `performance_quality_score` 都設成合併 leaf → `stability` 維度 = 合併 leaf
  （0.6 + 0.4 = 1）。維度係數 0.371 唔變（fixed arm）；refit arm 由 refit 程序自己配。
- **μ、σ**：只用 `run_date < 2026-08-05` 嘅歷史往績（按（馬名、日期）去重）計，**冇用任何賽果標籤**；
  評估窗前定死。

## 閘

1. **leaf（診斷）**：乾淨窗場內配對 AUC，合併 `stability` vs 而家 `stability` 合成（同一批馬），
   賽日 bootstrap 2000、seed 7；Holm 跨 4 個候選。只報告，唔攔。
2. **§8 四 arm（判決）**：4 個候選全部跑（`au_walkforward_refit.py`，同一 procedure hash），
   `evaluate_with_refit_arms`。候選要 WIN，而且佢嘅 arm-Holm p 再做**跨 4 候選 Holm** 後 < 0.05。
3. 來源 availability FLAG：正式判決 `leakage_audit_failed`；研究診斷用 True，**唔准當 WIN**。
   即係今次最好結果都只係 NEEDS MORE TESTING，要 forward 確認。
4. **ablation**：eq3 − eq2 = 負距嘅邊際；N6 − N4 = 多兩場嘅邊際。照報，唔揀子集。

## 唔准做

- 改成分權重、遞減權重、20 上限、z 尺度、fallback。
- 睇完結果再加候選（例如 N5、班次標籤版）喺同一個 family 入面。
- 用班次標籤：而家只有 9 月起先有，另開實驗。
