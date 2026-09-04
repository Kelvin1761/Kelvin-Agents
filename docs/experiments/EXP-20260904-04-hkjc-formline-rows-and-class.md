# EXP-20260904-04 HKJC 賽績線 —— 60.9% 對手行由來冇入引擎；班次入分 REJECT

- **日期**：2026-09-04
- **平台**：HKJC
- **提出人**：Kelvin —— 「由嘉應高昇個案我見到一樣嘢：賽績線，group 1–3 本身就係
  好競爭嘅班次，佢賽績線只得 60 分完全講唔通。」
- **前置更正**：嘉應高昇個 `賽績線` 係 **94.0**（全場第二高，而場內 6 匹範圍
  81–95），唔係 60。全場 120 匹只有一匹讀到 60，係第 10 場，而嗰個 60 係
  `FL2_zero_cap`（「面對強陣但每仗都大敗」封頂，pit 驗證過 good +0.7 / champ +0.6）。
  **但個機制批評本身係啱嘅**，而且沿住佢挖到一個更大嘅缺陣 —— 見下。
- **搜索過嘅舊記錄**：`EXP-20260904-04`（同日，顯示尺 + 級數優勢）、
  `EXP-20260902-03`。memory `au-formline-mapping-not-data`、
  `au-cohort-gap-is-not-a-gain`、`ab-identical-means-unwired`、
  `au-only-half-the-leaves-score`。
- **Baseline**：`pit_backtest.py` 26 個場次 / 193 場
  `gold 6.74 good 24.87 min 45.08 single 81.87 champion 25.91 top3_champ 56.48`

---

## 一：機制批評成立

`hkjc_profile_scraper.compute_form_lines` 個「強度評估」欄**只答一條問題：
對手其後有冇再贏**。對手其後參賽嘅班次（`class_str`）計咗、印咗，然後
**除非佢又贏，否則完全丟掉** —— `has_class_upgrade` 只用嚟做 `超強組` 嘅
tiebreak（`future_wins >= 1 and has_class_upgrade`）。

所以一隻其後去跑一級賽而贏唔到嘅對手，同一隻跑第五班贏唔到嘅對手，得到同一個
`❌ 弱組`。實測 6,815 條已標籤對手行：

| 標籤 | n | 佔比 |
|---|---:|---:|
| ❌ 弱組 | 3,239 | 47.5% |
| ✅✅ 超強組 | 1,551 | 22.8% |
| ⚠️ 中組 | 1,411 | 20.7% |
| ✅ 強組 | 614 | 9.0% |

當中「對手其後跑過分級賽／第一班」嘅 494 條：**59.7%（295 條）被評弱組／中組**，
48.4% 直接 `❌ 弱組`。而呢 494 條有 **127 條只有一仗後續**（0/1 = 擲毫）。

2026-09-06 R3：嘉應高昇喺**二級賽**贏驕陽明駒，驕陽明駒其後跑一次一級賽冇贏
→ `❌ 弱組`。班次越高，對手越難再贏，所以個指標系統性地罰最高班。

## 二：沿住呢條線挖到嘅真缺陷 —— 60.9% 對手行由來冇入引擎

個表係「一場一對手一行」：每場第一個對手嗰行帶 `#`／日期／賽事／我嘅名次，
亞軍／季軍嘅**續行**呢四欄空白。而
`create_hkjc_logic_skeleton.parse_formline_table` 用 `int(cols[1])` 做「係唔係
數據行」嘅測試：

```
Facts 賽績線 blocks : 3,249
對手行（Facts）      : 37,265
入到 Logic           : 14,580  (39.1%)
丟掉                 : 22,685  (60.9%)
```

而 `engine_core._formline_summary()` 個 docstring 寫住
「**EVERY** notable past opponent」—— 佢驅動 FL2 60 分封頂同整段賽績線敘述。

丟掉嘅係**非第一個對手**，即亞軍／季軍。2026-09-06 R3 嘉應高昇 11 條剩 5 條，
而丟掉嗰批正正係兩隻 `✅✅ 超強組`（金鑽貴人、舉步生風），留低嘅係睇落最弱
嘅亞軍。所以報告一路寫「未有賽果背書（0/5仗對手再贏）」。

修完（承繼賽事欄位）之後同一匹馬：**兌現度 0/5 → 3/10「已受賽果驗證（franked）」**，
敘述由 `➖ 賽績線` 變 `✅ 賽績線` 並且點名兩隻升班再贏嘅對手。

## 三：A/B（193 場，同一 harness／先驗）

⚠️ **第一次跑四個 arm 六個指標一模一樣。** 唔係「冇效果」——
`engine_core._value()` 係先睇 horse top-level 再睇 `_data`，而
`formline_strength` **兩邊都有**，所以只寫 `_data` 會被遮住。兩邊都寫之後
arm 才分開。（`ab-identical-means-unwired` 再中一次。）

| arm | gold | good | min | single | champ | top3_champ |
|---|---:|---:|---:|---:|---:|---:|
| FL0 baseline | **6.74** | 24.87 | 45.08 | 81.87 | 25.91 | 56.48 |
| **FL1 行數修正** | **6.74** | **24.87** | **45.08** | **81.87** | **25.91** | **56.48** |
| FL2a 班次 floor | 6.74 | 23.32 | 43.52 | 81.87 | 25.91 | 56.48 |
| FL2b 薄證據（後續<3仗唔算弱） | 6.74 | 24.87 | 45.08 | 81.87 | 25.91 | 56.48 |
| FL3 行數＋班次 | 6.74 | **25.39** | 45.08 | 81.87 | 25.91 | 56.48 |
| FL4 行數＋薄證據 | 6.22 | 24.35 | 44.04 | 81.35 | 24.87 | 55.44 |
| FL5 三個一齊 | 6.22 | 23.32 | 44.04 | 81.35 | 24.87 | 55.44 |

Ablation 揭到一個真交互：**班次 floor 單獨落係差嘅（good −1.55），但配合行數
修正就變 +0.52**。機制講得通 —— 只有 39% 對手（而且偏向亞軍，即係贏得最少嗰批）
嘅時候，落一個 floor 係喺一個有偏樣本上放大偏差。

配對 bootstrap（場內 AUC，4,000 次）：

```
FL0            場內 AUC = 0.6991
FL1 行數修正    ΔAUC +0.0024  CI [-0.0013, +0.0060]  (22/193 場有變)
FL3 行數＋班次  ΔAUC +0.0026  CI [-0.0010, +0.0063]  (27/193 場有變)
```

**班次 floor 喺行數修正之上只加 +0.0002 AUC。** 兩個 CI 都跨零。

## 四：判決

- **FL1 行數修正 —— SHIPPED（正確性）。** 六個指標 bit-identical、ΔAUC 點估計
  正、wiring 已核實（46/193 場至少一匹 ability 有變）。修嘅係「引擎睇唔到六成
  證據」同一個講大話嘅 docstring，唔係調參，所以按 §7 正確性修正上線。
- **班次 floor —— REJECT。** 單獨落傷 good 1.55pp；配合行數修正只值 +0.0002 AUC。
- **薄證據規則（後續<3仗唔算弱）—— 單獨落 bit-identical**（AU 版本已經係咁做，
  HKJC 呢邊唔做都冇分別）。
- **報告層修正 —— SHIPPED。** `❌ 弱組` 而對手其後跑過分級賽嘅行，加註
  「此欄只計對手其後有冇再贏；佢其後係跑一級賽」。個標籤讀落似「當日陣容淺」，
  但佢量嘅唔係呢樣。

### 順手記低：`formline_strength_score` 有兩個分支係死 code

3,438 匹實測 signal 分佈：`strong` 56.4%、`elite` 24.5%、`unknown` 19.1% ——
**`weak`(54 分) 同 `neutral`(64 分) 一次都冇出現過**。5 個 rating × 5 個分數
壓縮成 3 個可達值。同 `au-dimension-scale-weight-lockstep` 同形，未修。

## 五：可重現

```bash
export PYTHONDONTWRITEBYTECODE=1
scratch/hkjc_formline_ab_20260904.py      # 七個 arm
scratch/hkjc_formline_auc_20260904.py     # 配對 bootstrap + wiring 核實
```

改到嘅檔案：`create_hkjc_logic_skeleton.py`（`parse_formline_table`）、
`hkjc_racing_engine/{engine_core,renderer}.py`、
新增 `tests/test_formline_table.py`。
