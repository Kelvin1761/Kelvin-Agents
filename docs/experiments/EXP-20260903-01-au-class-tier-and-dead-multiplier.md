# EXP-20260903-01 — AU 班次水平：死咗嘅近績班次乘數，同場地層級折算

- **日期**：2026-09-03；**平台**：AU
- **baseline**：`8b1a71499a3a8cbc0360d0c0a278f78604965868`（= 當時 origin/main = production）
- **baseline dump**：`/private/tmp/au-class-baseline.json`（現行引擎重算全語料）
- **搜索過嘅舊記錄**：EXP-20260825-02／03／04（exact class、proven_class overlay）、
  EXP-20260826-06（class_score revival）、EXP-20260831-06（讓磅負磅）、
  EXP-20260902-06 候選 A、EXP-20260902-07 候選 L（兩個獎金 proxy，都 dev 回歸）。
  **場地層級（metro／country）折算從來冇做過候選** —— 只喺 EXP-06／07 寫低係缺口。

## 先確立嘅缺陷（唔係候選，係量度）

`_form_score` 第 1017 行：`entry_tier = self._get_class_tier(entry.get("class", ""))`。
但 `_record_entries()` **由來冇寫過 `class` 呢個 key**（佢寫嘅係 `kind`、
`class_move`、`source_race_class`）。所以 `entry_tier` 永遠係 `_get_class_tier("")`
嘅 fallback 值 7，而 `delta = today_tier - 7` 只係今仗班次標籤嘅函數。

語料實測（`scratch/au_class_field_audit_20260903.py`，唯讀，冇跑引擎）：

| 量度 | 值 |
|---|---:|
| 場次／馬匹／計分近績行 | 1,985 ／ 20,843 ／ 71,751 |
| 有 `class` key 嘅近績行 | **0** |
| **全場 `class_mult` 只得一個值嘅場次** | **1,980 / 1,980** |
| `class_mult` 分佈 | 0.7 ×20,100；0.85 ×5,334；1.0 ×38,078；1.1 ×8,239 |
| 有 `source_race_class` 嘅近績行 | 10,558（14.7%），其中 8,886 解析到 level |
| 近績行場地層級 | country 49,050 ／ metro 22,701 |
| 同一標籤嘅平均 exact level | metro 71.15（n=1,322）／ country 60.70（n=7,564） |

即係話呢個乘數**唔係**「今仗班次 vs 本駒往績班次」，而係一個**場級常數**，
按今仗班次標籤 0.7／0.85／1.0／1.1 咁縮放全場嘅近績分離散度。
⚠️ 最後一行嗰個 10.45 分差係**標籤分佈差**，唔係轉移折扣：metro 本身就辦高班賽事。
唔可以當成「country BM79 = metro BM68.6」。

## 預先登記（喺睇任何候選績效之前寫）

沿用 `au_eval` whole-date 尾 15% 日期 terminal、dev 五個時間 fold、canonical
Gold／Good位 primary 同既定 ranking metrics（`docs/model-evaluation-contract.md`
Stage 4 v2）。**唔調參、唔搜索組合。** 先 dev；任何 primary dev 回歸即停該候選，
唔開佢嘅 terminal。通過 dev 嘅固定候選先做一次 terminal 確認。

四個**獨立**候選（唔准只測合併版）：

1. **K1 — 中和死乘數**：`class_mult = 1.0` 恆定。呢個係消融：問句「呢個意外嘅
   場級離散度增益係幫緊定係害緊」。唔加任何新資訊。
2. **K2 — 駁返真嘅逐仗班次**：`entry_tier = _get_class_tier(entry["source_race_class"])`，
   缺標籤就當 `delta = 0`（→ mult 1.0，「冇證據」係中性，唔係扣分）。
   覆蓋率已量：71,751 行有 10,558 行（14.7%）有 raw 標籤。
3. **K3 — K2 加場地層級降級**：同 K2，但該仗喺非 metro 場地時，佢個 tier 降一級
   （country BM79 唔等於 metro BM79）。單一固定步，冇調參。
4. **K4 — `proven_class` 場地折算**：`exact_race_class_level()` 出嚟嘅 level，
   如果該仗喺非 metro 場地就減 **Δ = 5.0**（約一個澳洲班次階）。
   **Δ 係編碼假設，唔係 fit 出嚟嘅值**；只測呢一個值。方向啱但幅度唔啱屬後續實驗，
   唔准喺同一輪重新揀 Δ。

**功效前置條件**（terminal 開之前要量）：`proven_class` 係**場內**標準化，所以
一個恆定 Δ 喺「全場都嚟自同類場地」嘅場次會互相抵銷。要先數清楚有幾多場次嘅
近四仗場地層級係**混合**嘅 —— K4 只可能喺嗰啲場次郁得到。混合場次太少 =
呢個候選冇 power，唔准用 terminal 嘅 CI 去扮結論。

**唔准做**：賠率只作評估分層，唔入候選；唔重新抓取；歷史日期一定早過賽日；
唔改評估合約；唔用單一個案（Sunburnt Country）代替語料驗證。

## 結果

### 語料、基準及可重現性

- baseline dump：1,861 場／18,579 匹。`au_matrix_refit verify` 對真引擎
  max|Δ| **0.003900**、mean|Δ| 0.00000842、**冇一匹 >0.01** —— dump 重現得到 live 引擎。
- dev 1,338 場（2025-08-02 → 2026-08-18）；terminal 523 場（2026-08-19 → 2026-09-02）。
- 同場同馬逐行配對；sample hash `35b97b508584a5e89079149cc25dd48926d34c34c7b6f4541a3d313d62e00b8a`。
- **功效前置條件（K4）已量**：1,410 / 1,861 場（**75.8%**）嘅場內近四仗場地層級係混合，
  所以場內標準化唔會把一個恆定 Δ 完全抵銷。呢個前置條件係**過咗**嘅 —— 佢唔係後面失敗嘅原因。

### K1 — 中和死乘數（唯一真正量到嘅候選）

dev 6,968 / 13,599 匹有變（51.2%），全語料 8,103 匹（43.6%），ability max|Δ| 6.678。

| dev 指標 | baseline | K1 | Δ |
|---|---:|---:|---:|
| gold | 17.36527% | 17.14072% | **−0.22455pp** |
| good_positional | 22.08084% | 21.10778% | **−0.97305pp** |
| pass | 44.61078% | 44.31138% | −0.29940pp |
| champion | 23.42814% | 23.57784% | +0.14970pp |
| top-3 precision | 46.58184% | 46.58184% | 0.00000pp |

**兩個 primary 都回歸 → REJECT，terminal 冇開。**

結論唔係「呢個 bug 冇所謂」。而係：呢個場級常數乘數雖然**唔係**原本設計嘅
「今仗班次 vs 本駒往績班次」，但佢實際上做緊一件有用嘅嘢 ——
按今仗班次標籤縮放全場近績分嘅離散度（高班賽 ×0.7 壓縮、初出／未知班次 ×1.1 放大）。
剷走佢會蝕。**呢個意外行為要保留，但要喺 code 講清楚佢實際係咩**，
唔可以繼續扮佢係逐匹馬嘅班次證據。

### K2／K3／K4 — 唔係 REJECT，係**測唔到**

三個都靠 `source_race_class`（Facts 第 20 欄）。呢個欄位 2026-08-25 先加入抽取層，
**backfill 唔到**（頁面歷史已經拎唔返）。逐月覆蓋：

| 月份 | 近績行 | 有班次標籤 | 覆蓋 |
|---|---:|---:|---:|
| 2025-08 → 2026-07（12 個月） | 30,105 | **0** | **0.0%** |
| 2026-08 | 38,540 | 7,452 | 19.3% |
| 2026-09 | 3,106 | 3,106 | 100.0% |

**按評估切法分：dev 51,474 行有 0 行（0.0%）有標籤；terminal 18,731 行有 9,533 行（50.9%）。**

後果，逐個核實過：

| 變體 | dev 有變 / 13,599 | terminal 有變 / 4,980 | 判決 |
|---|---:|---:|---|
| K1 | 6,968 | 1,135 | REJECT（見上） |
| K2 | **6,968**（同 K1 逐匹一樣） | 1,186 | **測唔到** |
| K3 | **6,968**（同 K1 逐匹一樣） | 2,582 | **測唔到** |
| K4 | **0** | 2,314 | **測唔到** |

K2／K3 喺 dev 每一行都行返「冇標籤 → 中性」條 fallback，所以佢哋喺 dev **就係 K1**；
K4 喺 dev 完全隱形。三個第一次跑出嚟嘅 dev 數字**逐位等於 K1**
（−0.22455／−0.97305／−0.29940／+0.14970／0.00000）—— 呢個唔係巧合，
係「候選冇接通」嘅徵狀，唔可以當「候選冇效果」。

**唔准開佢哋嘅 terminal。** terminal 係唯一有呢個欄位嘅窗口；
用佢嚟揀候選 = 用 holdout 調參，係 `AGENTS.md` 明文禁止嘅。

### 幾時先測得到

現時語料 96 個賽日，terminal 係尾 15 個（由 2026-08-19 起）；有標籤嘅賽日得 9 個
（2026-08-25 → 2026-09-02），全部喺 terminal 入面。

| 目標：dev 有幾多個有標籤賽日 | 仲要等幾多個賽日 |
|---|---:|
| 1（技術上入到 dev，冇 power） | ~8 |
| 10 | ~19 |
| **30（先叫做有得測）** | **~42** |
| 50 | ~66 |

即係話大約 **2026-11 中**先有一個講得出嘢嘅 dev 窗。呢個同
`au-people-stats-have-lookahead` 嘅等待期形狀一樣。

### 順帶量到（唔係候選證據）

同一個 exact class 標籤，metro 平均 level 71.15（n=1,322）vs country 60.70（n=7,564）。
⚠️ 呢個係**標籤分佈差**（metro 本身辦高班賽事），**唔係**轉移折扣。
唔可以用嚟推「country BM79 = metro BM68.6」，亦唔可以攞嚟當 Δ 嘅根據。

## 檢查

- **leakage-audit**：候選只讀存檔賽前 Facts；歷史日期一定早過賽日；
  賠率只作分層冇入候選；賽果只作評估 label。**冇新洩漏**。
  但發現一個**評估結構問題**：候選所依賴嘅欄位只存在於 holdout 窗，
  等於「只可以喺 holdout 度睇到效果」，所以停手。
- **golden_scoring**：冇郁（研究程式只喺自己 process 內 patch，冇改 live 引擎）。
- **data_contract**：未跑（冇 live 改動）。
- **退步**：K1 dev 兩個 primary 回歸，已記錄。

## 結論

1. **確立咗一個真缺陷**：`_form_score` 個班次乘數由來冇讀到逐匹馬嘅班次
   （`entry["class"]` 呢個 key 唔存在），1,980/1,980 場全場同一個值。
2. **但唔可以照剷**：K1 消融 dev 兩個 primary 都跌，所以呢個意外嘅場級離散度縮放
   要保留。要做嘅係**改註釋同命名去講真話**，唔係改行為。
3. **班次水平調整本身仍然係未答嘅問題。** 三個真正加班次資訊嘅候選
   （K2／K3／K4）**喺現有語料上結構性咁測唔到**，因為原料欄位 2026-08-25 先存在，
   而評估切法把佢全部推入 holdout。呢個係**語料建構問題，唔係想法被否定**。
4. Sunburnt Country 嗰類 country→metro 高估，喺呢一輪**冇解決，亦冇被否定**。

**決定**：K1 **REJECT**；K2／K3／K4 **NEEDS MORE TESTING（等語料，約 2026-11 中）**。
**commit**：未 commit 任何 model code（符合「失敗實驗嘅 model code 唔准 commit」）。
只 commit 實驗記錄同兩個唯讀研究腳本。

## 重跑

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scratch/au_class_field_audit_20260903.py
PYTHONDONTWRITEBYTECODE=1 python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_dump_engine_leaves.py --out /private/tmp/au-class-baseline.json
PYTHONDONTWRITEBYTECODE=1 python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_matrix_refit.py verify --data /private/tmp/au-class-baseline.json
for v in k1 k2 k3 k4; do
  PYTHONDONTWRITEBYTECODE=1 python3 scratch/au_class_tier_20260903.py --variant $v --out /private/tmp/au-class-$v.json
  PYTHONDONTWRITEBYTECODE=1 python3 scratch/au_class_eval_20260903.py \
    --baseline /private/tmp/au-class-baseline.json --candidate /private/tmp/au-class-$v.json \
    --label $v --phase dev
done
```

⚠️ 研究腳本用 `inspect.getsource` + **逐字 anchor** 改寫 live method 嘅副本；
anchor 唔見咗會即刻 assert 失敗，唔會靜靜咁評緊未 patch 嘅版本。
原始 dump 全部留喺 `/private/tmp/au-class-*.json`（每個約 11 MB），冇入 repo。

## 重跑

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scratch/au_class_field_audit_20260903.py
PYTHONDONTWRITEBYTECODE=1 python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_dump_engine_leaves.py --out /private/tmp/au-class-baseline.json
PYTHONDONTWRITEBYTECODE=1 python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_matrix_refit.py verify --data /private/tmp/au-class-baseline.json
```
