# EXP-20261016-18 預先登記：AU `class_weight`（官方評分對位）六項審計

> 量度之前寫。結果另寫 `EXP-20261016-18-au-class-weight-audit-results.md`。

- **日期**：2026-10-16；**平台**：AU；**baseline**：main `05dd1b20`。
- **用戶指示**：「go ahead and test 1-6 and fix if needed」。
- 維度 = 0.70 rating_score + 0.15 class_score，係數 0.3826。
- **語料**：`scratch/au_class_audit_dump_20261016.py`（同 production 一樣評分路徑，另記 rating／class 嘅輸入），乾淨窗 08-05 起。
  離線 replica 重算 rating_score、class_score、ability 要同引擎差 < 1e-3，否則停。
- 超額入位 = 入位 − 派彩位數／馬匹數（8 匹以上 3 位，否則 2 位）；bootstrap 一律按場次／賽日 2000、seed 7。

## 寫登記前已知（code 審查，冇睇任何結果）

- `_venue_tier`：唔含都會字眼嘅場地一律當 provincial；`METRO_VENUE_TOKENS` 只有悉尼、墨爾本、布里斯本，
  **冇 Morphettville（阿德萊德）、Ascot、Belmont（珀斯）**。

## 六項同候選

**R1 同場兩把尺。** rating fallback 係逐匹決定：一場有 ≥ 2 匹有評分，冇評分嗰啲仍然行「0.5 級數 + 0.5 負磅」代理。
描述：混合場次（有評分同冇評分都有）入面，代理馬 vs 評分馬喺同一 rating_score 區間嘅超額入位率。
候選 **R1x**：混合場次嘅冇評分馬，有負磅代理就**只用負磅代理**（同評分一樣 z×6、±12 嘅尺），冇先用級數代理。

**R2 級數分對代理馬計兩次。** 代理馬嘅 class_score 經 rating 佔 0.35，再自己佔 0.15。
候選 **R2x**：rating_score 嚟自代理嘅馬，維度入面 class_score 當 60（只經代理計一次）。

**R3 降班 +2.1。** 描述：觸發率按月（08、09、10 月）同 live 最近 14 日（10-02 → 10-16）；觸發 vs 冇觸發超額入位。
如果 live 14 日觸發率 < 乾淨窗平均嘅 1/5 → 記為「live／回測唔一致」，候選 **R3x** = 剷走呢項。否則只報告方向。

**R4 上仗名次用絕對名次。** 候選 **R4x**：有上仗馬匹數就改用場內百分位 pct = (名次 − 1)/(馬匹數 − 1)：
「上名」= pct ≤ 0.25、「冇表現」= pct > 0.5；冇馬匹數照舊用絕對 ≤3／≥6（同 `_form_score` 07-31 修正同一做法）。

**R5 人手係數。** 候選 **R5a**：剷走 BM ×0.9／處女 ×0.8；**R5b**：剷走前三門檻 +1.5／−1.0。

**R6 場地分級。** 描述：上仗／今場場地認成 metro 嘅比例同最常見 provincial 場地名。
候選 **R6x**（正確性）：都會 = 悉尼（Randwick、Rosehill、Warwick Farm、Canterbury）、墨爾本（Flemington、Caulfield、Sandown、
Moonee Valley／The Valley）、布里斯本（Eagle Farm、Doomben）、**阿德萊德（Morphettville）、珀斯（Ascot、Belmont）**。

## 判決（每個候選對 baseline，v3 `fixed_rule` 全紀錄 2,485 場 + 預先聲明分層）

- **R6x、R4x**（同已證錯處／已修過嘅同類錯處）：§7 —— 冇 primary CI 全 < 0、冇分層 primary CI 全 < 0 → 上線。
- **R1x、R2x**（改 leaf 資訊）：fixed arm Gold、Good 點估計都 ≥ 0 而冇 ranking CI 全 < 0 → 上線；否則跑 §8，refit arm WIN 而 live guard 過 → 上線；其他 REJECT。
- **R3x**：只喺「live／回測唔一致」成立先測；§7 規則。
- **R5a、R5b**（簡化）：Gold、Good 點估計都 ≥ 0 而冇 ranking CI 全 < 0 → 剷走；否則保留。
- 多個採用 → 合併版再跑 v3，冇 primary CI 全負先上線；另報 §8 同跑包尾（頭兩名 $15+ 跑尾三分一）。

## 多重比較（宣告）

最多 7 個候選（R1x、R2x、R3x、R4x、R5a、R5b、R6x），同一 41 日 OOS 窗已經用過多次。採用規則都係「冇代價嘅修正／簡化」，唔係改善聲稱；
任何「改善」講法要 Holm 跨所有跑咗嘅候選。

## 唔准做

改門檻（0.25、0.5、1/5）、改都會名單（除咗上面寫明嗰批）、睇完結果加候選。
