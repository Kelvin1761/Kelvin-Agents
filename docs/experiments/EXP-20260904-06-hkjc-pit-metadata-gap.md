# EXP-20260904-06 HKJC PIT 距離／班次缺口 —— 排位表補返 107 行；race_shape 消融唔再重做

- **日期**：2026-09-04
- **平台**：HKJC
- **緣起**：本來打算 A/B「剷走 `race_shape` 內部嘅 `近仗消耗`（場內 AUC 0.4708）
  同 `走位匹配`（0.5243）」。**搜舊記錄之後停手** —— `EXP-20260902-08` 已經
  預先登記做過同一個實驗（C=fit 中性、D=trip 中性、C+D），判 **唔保留**，
  而且做過功效前置：`race_shape` **全維度中性化**之後 terminal
  capture@5 |Δ| 只有 2.38pp 而 CI 半寬 4.76pp、mean Top3 rank 0.171 < MDE 0.268、
  competitive recall 2.50pp < 3.94pp、NDCG 1.98pp < 4.04pp ——
  **剷走整個 27.4% 維度都細過噪音底**，所以維度內部任何消融喺呢個語料上面
  量唔到。重做只會拿到一個讀唔到嘅數，而見到細細個正數就調參正是嗰份文
  明文禁止嘅（「不以移除後的個別小收益重新調參」）。
- **改為做嗰份文指定嘅前置**：「先修補 PIT raw-results 的日期缺口及距離/班次
  metadata，保留來源、identity、嚴格日期 cutoff，重建 baseline」。

---

## 一：缺口實際係咩

`pit_backtest.load_all_rows()` 21,107 行：

| 欄 | 缺 | 佔比 |
|---|---:|---:|
| Distance | 119 | 0.6% |
| RaceClass | 119 | 0.6% |
| Going | 4,548 | 21.5% |

Distance 缺口**唔係平均散開**：

```
2026-07-15  107 行缺 / 107 行總   ← 整個場次
2026-06-07    4 / 143
2026-06-24    3 / 107
2026-06-03    2 / 107
2026-05-13    1 / 101
2026-05-20    1 / 108
2026-07-12    1 / 152
```

**2026-07-15（跑馬地）整個場次 100% 冇 metadata。** 成因：
`pit_sources.supplement_rows` 只由 `Race_*_Logic.json` 補 metadata，而 07-15
**從來冇評分過**（0 個 Logic）。而賽果 payload 本身冇距離欄 ——
只有 `racedate / race_no / venue / results / sectional_times / cumulative_times /
incident_report`。

另外「2026-04-04 冇賽果」**唔係缺口**：`2026-04-04 Sha Tin (Heison)` 個資料夾
入面全部係 `04-06_*_Analysis.md`，即係**資料夾名同內容唔同日**。
`corpus_paths` 靠日期前綴認場次，所以佢被當成一個場次。同
`au-hkjc-naming-mismatch-scan` 同一個坑：**用前綴砌檔名搵檔本身唔安全**。

## 二：修法 —— 排位表係同一個賽前事實嘅另一個檔

`* Race N 排位表.md` 一直喺硬碟上面，而且有齊：

```
場次: 第1場   地點: 跑馬地   路程: 1650米   班次: 第五班
馬號: 1   馬名: …
```

新 `pit_sources.racecard_contexts()` 用**同一套紀律**砌 `(day, race, horse_no,
name)` → metadata：檔名嘅場次要同 `場次:` 一致、場地要 resolve 得到、
**排位表冇寫嘅欄就留空，唔砌數**。Logic 仍然係權威來源，排位表只補佢冇覆蓋
到嘅 key。

結果：

| | 前 | 後 |
|---|---:|---:|
| 缺 Distance | 119 | **12** |
| 2026-07-15 | 107 / 107 缺 | **0 缺** |
| 排位表 context | — | 469 |
| 填返 Distance / RaceClass | — | 2,262 / 2,262 |

剩低 12 行係**真.冇資料**，唔係配對 bug：7 行連 `RaceNo` 都冇（賽果來源歸不到
場次），另外 5 行係後加／替補馬，逐個核過**唔喺當時抽到嘅排位表上面**
（勁砲王 K543、團長好 K515、嘉應勇將 L094、包裝天王 K570…）。

## 三：對 193 場回測 —— bit-identical，而且係應該嘅

```
193 場   gold 6.74  good 24.87  min 45.08  single 81.87  champion 25.91  top3_champ 56.48
（修前修後完全一樣）
```

**唔係 unwired。** `Distance` 真係入先驗（`_grouped_priors(sub, ["Jockey",
"Distance"])` 同 `["Trainer", "Distance"]`），但補到嗰 107 行係
**2026-07-15**，而回測最後一個場次係 **2026-07-12**。先驗係嚴格 as-of
（`Date < meeting_date`），所以嗰 107 行永遠入不到呢 193 場任何一場嘅先驗。
落喺 as-of<2026-07-12 窗口內嘅 20,848 行本來只缺 11 行，修完仍然係 11 行 ——
窗口內本來就冇嘢好修。

即係：**呢個修正對已公布嘅 HKJC 數字零影響**，但對
（a）將來包含 07-15 之後場次嘅回測、（b）2026-09-06 live meeting 嘅逐距離
騎練先驗，係實質補返資料。

## 四：判決

- **排位表補 metadata —— SHIPPED（資料覆蓋修正，非模型改動）。** 排名指標
  bit-identical，null 結果已解釋到機制層，7 個新測試守住「唔准砌數」同
  「Logic 優先」。
- **`race_shape` 內部消融 —— 唔重做。** `EXP-20260902-08` 已判，而且功效前置
  證明呢個語料判唔到。要重開就要先滿足嗰份文寫嘅條件：`fit` 按樣本量收縮 ／
  同情境比較，`trip` 分開「額外負荷」同「可原諒失利」，**唔係反轉符號或者
  剷走**。
- **`Going` 21.5% 缺口冇動。** 已知 `race_results` 個 Going 欄裝過班次字串
  （`_track_going_score` 因此永久中性 60），所以補佢之前要先證實個欄係咩。

## 五：可重現

```bash
export PYTHONDONTWRITEBYTECODE=1
python3 -m pytest .agents/skills/hkjc_racing/hkjc_reflector/tests/test_pit_sources.py
python3 .agents/skills/hkjc_racing/hkjc_reflector/scripts/pit_backtest.py --json <26 個場次>
```

改到嘅檔案：`hkjc_reflector/scripts/{pit_sources,pit_backtest}.py`、
`hkjc_reflector/tests/test_pit_sources.py`。
