# EXP-20260902-05 步速圖 + 跑法 + 賽道幾何 夾埋，落唔落到排名？

- **日期**：2026-09-02
- **平台**：AU
- **假設**：起步位 fallback 修好之後（覆蓋 38.8% → 92.5%），預測起步位做連續特徵、
  再同賽道幾何交互，應該落到排名 —— memory `au-settling-position-biggest-lever`
  話起步位係 AU 最大嗰條槓桿（top-3 值 14–20pp），上次試嘅版本 r=0.389、覆蓋只有 37.8%。
- **搜索過嘅舊記錄**：[EXP-20260902-01](EXP-20260902-01-au-track-geometry-and-run-style.md)
  （幾何交互 REJECT）、[-02](EXP-20260902-02-au-run-style-single-source.md)（跑法 bucket REJECT）、
  [-04](EXP-20260902-04-au-settled-position-cascade.md)（覆蓋率修正）、
  memory `au-feature-set-is-saturated`、`leaf-auc-gains-do-not-convert-to-ranking`。

## 數據
- 1,020 場 / 9,727 匹（2026-08-05 起乾淨 point-in-time）
- **有預測起步位 9,002 (92.5%)** —— cascade 之前跑法 bucket 只有 38.8%
- 特徵：近仗起步位加權平均（Settled → 800m → 400m），越細 = 越前
- 三個模式：`plain`、`x_straight`（短直路放大前置價值）、`x_field`（按馬匹數縮放）

## 結果：dev 已經睇到唔使開 terminal

dev 867 場（2026-08-05→08-27），`ability + k·z(feature)`：

| 模式 | k=0.5 | k=1.0 | k=1.5 | k=2.0 | k=3.0 |
|---|---|---|---|---|---|
| plain — **gold** | −0.12 | +0.00 | −0.69 | −0.35 | −1.27 |
| plain — good位 | +0.69 | +0.23 | +0.58 | +1.15 | +0.46 |
| x_straight — **gold** | −0.12 | **+0.12** | −0.58 | −0.35 | −1.38 |
| x_straight — good位 | +0.58 | +0.23 | +0.58 | +1.04 | +0.23 |
| x_field — **gold** | −0.12 | +0.00 | −0.69 | −0.35 | −1.27 |

`gold` 由頭到尾冇改善過：最好嗰格 **+0.12pp（867 場之中 1 場）**，而且 k 一大就跌。
`x_straight` 同 `plain` 幾乎逐格一樣 —— 同 EXP-01「幾何冇交互作用」一致。

**冇開 terminal。** 合約 §6 嘅精神係「判決之前先問把尺分唔分得到」：terminal
gold 嘅 CI 半寬係 **±4.9pp**（見 EXP-04），一個 +0.12pp 嘅 dev 效果喺嗰度分唔到 ——
開咗只會攞返一個跨零嘅區間，同時燒咗一次 terminal 觀察。

## 診斷：唔係特徵差

| | |
|---|---|
| 預測起步位 場內 AUC | **0.5416**（17,682 對） |
| 模型 rank_score 場內 AUC | 0.6640 |
| ρ(預測起步位, 模型分) | **+0.147** |
| 覆蓋率 | **92.5%** |

即係話：一個**準**（0.5416，高過大部分現有 leaf）、**覆蓋闊**（92.5%）、
**幾乎正交**（+0.147，`pace_figure` 呢個「唯一正交 leaf」都只係 ≤0.13）嘅特徵，
硬加落排名分**照樣落唔到分**。

## 檢查
- **leakage-audit**：PASS —— 特徵由賽前 Facts 往績重建；terminal 冇開。
- **golden_scoring**：冇郁（呢個實驗冇改評分 code）。
- **`./檢查.sh`**：五項全綠。

## 結論

**三個訊號夾埋一樣落唔到排名。** 呢次係最強嗰個反例：之前失敗嘅候選可以推說
「太少覆蓋」（跑法 38.8%）或者「唔夠準」，今次兩樣都解決咗 —— 覆蓋 92.5%、
AUC 0.5416、正交 +0.147 —— gold 仍然係零。

呢個係 `au-feature-set-is-saturated` 嘅第三次獨立確認：**差距係資訊，唔係夾法**。
起步位嘅預測力已經被現行維度（尤其 form / performance_quality）由另一條路捉咗，
餘下嗰 +0.147 嘅正交部分唔夠推動場內次序。

⚠️ 一個**未試**嘅方向留返：起步位嘅賽馬學理係經**場面步速壓力**發揮
（領放馬喺得一匹前置嗰陣有利、喺五匹搶前嗰陣蝕）—— 即係場級交互，唔係逐匹加數。
`_pace_bias_adjustment()` 就係咁做，2026 年較早前試過係 wash-to-slightly-negative，
所以預設 OFF（`WC_PACE_BIAS=1` 開）。而家步速圖準咗好多，值得**重測嗰個**，
而唔係再試逐匹加特徵。

**決定**：
- 預測起步位做排名特徵（三個模式）→ **REJECT**（dev gold 從未改善，terminal 冇開）
- 預測起步位做**顯示／分析**（形勢推演表 + dashboard 圖）→ **已上線**（EXP-03）
- 重測 `_pace_bias_adjustment`（場級步速壓力）→ **登記待做**

**commit**：未 commit

## 重跑
```bash
python3 /tmp/.../settle_feature_ab.py
```
