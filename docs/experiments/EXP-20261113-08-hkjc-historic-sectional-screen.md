# EXP-20261113-08 HKJC 歷史逐匹分段（2019 起 6,036 場）重新判段速概念

- **日期**：2026-11-13 ｜ **平台**：HKJC
- **觸發**：Kelvin：「唔好用同一批場次試，用晒資料庫所有歷史場次」「前段有冇對標準時間同路程調整？」
- **假設**：真逐匹分段（對標準、扣當日快慢）喺近績、評分、負磅、騎師、輸頭馬等級、表現數字之上仲有獨立訊號，而且唔會令 Gold／Good 跌
- **搜索過嘅舊記錄**：EXP-20261113-02／-03／-04／-05／-07、EXP-20261112-11
- **改到嘅檔案／組件**：冇 live 改動；`backfill_history.py`（抓取，f66c26b3）、`hkjc_hist_sectional_features.py`、`hkjc_hist_sectional_screen.py`

## 數據
- HKJC「分段時間及位置」頁 2019-09 → 2026-11 **6,036／6,036 場**，解析失敗 0；同我哋 formguide 重疊 **10,047 匹次逐段完全一樣、0 差異**。
  段數唔一致嘅 660 匹全部係冇跑完嘅馬。原始頁同解析檔喺外置碟 `WongChoi-Archive/hkjc-history/`。
- 全天候 612 場、草地 5,424 場。2022/23 季起有尾段每 200 米細分（呢度未用）。

## 配置（跑之前寫喺兩個腳本 docstring）
- **標準**：每季用之前所有季、同跑道（沙田草地／跑馬地草地／沙田全天候）× 路程 × 班次 × 段、入頭三馬中位數（n ≥ 20，否則唔分班次）；比較用今仗班次標準
- **當日快慢**（`_v`）：每賽日 × 跑道 × 段類，全場馬匹對標準偏差中位數；只扣喺往績
- **每匹**：近 6 仗、1/k 加權、最少 2 仗；first（第一段，每 400 米）、mid（中段，≥4 段先有）、pen（倒數第二段）、l400、total；style = 第一段走位百分位
- **模型**：場內置中 logistic，逐季 walk-forward；測試 2021/22 → 2026/27（**5,206 場**，指標計 4,337 場有頭三嘅）
- **基礎**：B0 = 近績、日數、出賽數、檔位、負磅相對、騎師 PIT 勝率；B = B0 ＋ 輸頭馬等級 ＋ 表現數字（EXP-20261112-11）
- **判準**：模型之上係數 Holm < 0.05 而且 Gold、Good 點估計 ≥ 0（Kelvin 規則）；概念層，入引擎要另外 A/B

## 結果（候選 − 基礎，pp，場次 bootstrap 1,000；係數場次 bootstrap 300）
基礎 B0：Gold 11.51%｜Good 19.78%｜capture@5 63.25%｜頭二 75.65%
基礎 B：Gold 11.97%｜Good 20.57%｜capture@5 64.25%｜頭二 76.32%

| 候選 | 基礎 | 係數／SD | Holm | Gold | Good | capture@5 | 頭二選有中 |
|---|---|---|---|---|---|---|---|
| **SECT 整組** | B0 | +0.301 [+0.272,+0.335] | 0.013 ✅ | +0.39 [−0.23,+0.97] | +0.14 [−0.62,+0.92] | **+0.72 [+0.30,+1.17]** | **+0.78 [+0.05,+1.54]** |
| **SECT 整組** | B | +0.145 [+0.118,+0.170] | 0.023 ✅ | +0.21 [−0.30,+0.76] | +0.02 [−0.55,+0.62] | +0.04 | **+0.74 [+0.14,+1.34]** |
| first_v（前段對標準扣當日） | B | +0.089 [+0.067,+0.110] | 0.033 ✅ | +0.05 | +0.35 [−0.14,+0.88] | −0.19 | +0.35 |
| total_v（全程對標準扣當日） | B | +0.125 [+0.095,+0.159] | 0.030 ✅ | +0.09 | +0.21 | +0.14 | −0.07 |
| style（前段走位） | B | +0.081 [+0.057,+0.103] | 0.027 ✅ | +0.07 | +0.28 | −0.24 | +0.23 |
| first（唔扣當日） | B | +0.089 | 0.040 ✅ | 0.00 | +0.14 | −0.26 | +0.25 |
| l400 | B | **−0.032** [−0.057,−0.005] | 0.040 | −0.02 | +0.14 | −0.08 | +0.05 |
| l400_v | B | −0.019 | 0.560 | 0.00 | −0.07 | +0.02 | 0.00 |
| mid_v | B | +0.020 | 0.300 | +0.35 [+0.09,+0.62] | +0.02 | −0.02 | +0.32 |
| pen／pen_v | B | ≈0 | >0.38 | ≈0 | ≈0 | ≈0 | ≈0 |

B0 之上 l400 有 +0.108／SD，但加咗輸頭馬等級＋表現數字之後變 −0.032 —— L400 已經俾完成時間類資訊食晒。

## 結論
1. **段速概念成立**：喺 5,206 場，真逐匹分段整組喺近績＋評分＋負磅＋騎師＋輸頭馬＋表現數字之上仲有獨立訊號（+0.145／SD，CI 遠離零），頭二選有中 +0.74pp CI 全正。
2. **Gold／Good 冇跌**：同 449 場引擎語料「每加資訊 Gold 就跌」相反 —— 嗰度係細樣本（Gold 由 ~17 場決定）加 baseline 喺同批場次調過（EXP-05）。
3. **有用嘅係前段同全程對標準，唔係 L400**：first_v、total_v、style 各自過；L400 喺表現數字之上冇剩餘（同 EXP-02 一致，而家用 6 季數據確認）。中段弱。
4. **扣當日快慢有幫助**：total_v 係數 +0.125 vs total +0.077；first_v Good +0.35 vs first +0.14。
5. **但 Gold／Good 效果細**：全部點估計 ≥ 0 但冇一個 CI 下界 > 0（CI 半闊 ~0.5pp）。過嘅係按預先登記嘅概念判準，唔係引擎 Stage 4。

**決定**：概念 PASS（MEASUREMENT）；live 冇改。下一步：用 6 季標準＋當日快慢喺引擎計前段／全程對標準，做引擎 A/B（`model-regression-gate`）。
**leakage-audit**：PASS —— 標準只用之前季；當日快慢只扣喺往績（賽後先知，但只用喺賽日之前嘅仗）；往績只取賽日之前；冇用賠率。
**commit**：冇 model code

## 重跑
```bash
# 數據（外置碟要掛載；約 13 小時，斷點續抓）
python3 .agents/skills/hkjc_racing/hkjc_race_extractor/scripts/backfill_history.py run --kinds sectional
python3 .agents/skills/hkjc_racing/hkjc_race_extractor/scripts/backfill_history.py parse
PYTHONDONTWRITEBYTECODE=1 python3 docs/experiments/patches/hkjc_hist_sectional_features.py <out>/sect_features.pkl
PYTHONDONTWRITEBYTECODE=1 python3 docs/experiments/patches/hkjc_hist_sectional_screen.py <concept_features.pkl> <out>/sect_features.pkl
```
`concept_features.pkl` 由 `hkjc_figure_concept_walkforward.py`（EXP-20261112-11）生成。
