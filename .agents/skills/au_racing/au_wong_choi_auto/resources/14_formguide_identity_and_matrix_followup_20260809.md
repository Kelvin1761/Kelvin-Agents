# AU Formguide identity + matrix follow-up — 2026-08-09

## Direction

今輪按用戶方向只研究 horse-ability scoring matrix，冇做 Top-2 lock、slot 3/4 rerank、
賠率或 post-race feature。Gold／Good 優先，Pass 定義維持「模型 Top 3 任兩匹上名」。

## Data alignment fixes

### 1. PF refresh

舊 Logic 已有 PF payload 時，`enrich_logic_from_facts()` 原本用 fill-if-missing，令新版
Formguide parser 無法更新舊 schema。修正為 matching Formguide／point-in-time backfill
存在時原子替換 PF payload。

- 無 source PF：3,572 → 431 匹；
- `racenet_formguide_cfb`：1,233 → 4,374 匹；
- 修正後 ranking byte-equivalent：Gold／Good／Pass／AUC 全部不變。

PF 語意亦重新核實：Racenet `Last600` 係跑到剩 600m 時嘅累積時間，真正末段 600
係 `Runner Time - Last600`；Sportsbet `l600` 就係真正末段 600。兩者都唔係
`L600 Delta`，文件註釋已修正，避免未來混合單位。

### 2. Cross-horse Formguide digest

Freshness audit 比較 1,034 個 Logic 同 matching Formguide，發現大量舊 Logic 保留另一場／
另一匹馬嘅 digest。實例：正確馬名 `Casino Seventeen` 下面，舊 Logic sire 係
`Zoustar`、上仗騎師係 `Tom Sherry`；matching Formguide／Facts 證明正確值係
`Casino Prince`、`Luke Cartwright`。

根因係歷史 multi-race scraper identity bug 已修，但 enrichment 一直只補空缺，令錯 payload
永遠唔會被正確 source 覆蓋。常見 mismatch：

- current jockey history：5,153 匹；
- timing entry count：3,307 匹；
- sire：3,027 匹；
- recent / best 600m speed：約 2,840 匹；
- best／latest jockey、running-position digest：普遍 2,000–2,700 匹。

修正為：matching horse-number Formguide section 存在時，整個 digest 原子更新，包括有意義
嘅 `0`／`False`／空值；冇 matching section 先保留舊 payload。並刪走 50 多行逐欄
fill-if-missing 重複碼。更新前亦新增 horse-number + normalized-name identity guard；
全 archive 預檢係 0 name mismatch、0 Logic runner missing（4 個額外 Formguide runner 可容許）。

## Corrected production baseline

完整 1,034 Logic discovery／805 aligned races／8,249 runners 真引擎重跑：

| Metric | Before identity refresh | After | Delta |
|---|---:|---:|---:|
| Gold | 16.15% | **16.15%** | 0.00pp |
| Good | 24.35% | **24.84%** | **+0.49pp** |
| Pass | 45.71% | **45.84%** | +0.13pp |
| Champion | 24.84% | **25.47%** | **+0.63pp** |
| Winner@3 | 55.53% | 55.28% | -0.25pp |
| Winner@5 | 74.16% | **74.53%** | +0.37pp |
| Top-3 precision | 46.75% | **46.92%** | +0.17pp |
| Top-5 AUC | 0.6842 | **0.6864** | +0.0022 |

1,982 / 8,249 匹 ability 改變，1,972 匹涉及 jockey-trainer matrix。最新 211-race
holdout 完全冇改，因為新 meeting 本身已由正確 scraper 建立；修復只清理舊錯配。
Development Top-5 AUC +0.0029；五個時間 fold delta：+0.0151 / -0.0012 /
+0.0048 / +0.0034 / 0.0000。

## Structural scoring candidates

以下全部用修正後 805 場 snapshot、場內 pre-race normalization、完整日期 dev／terminal
holdout、paired race bootstrap；冇候選加入 production。

### True final-600 figure

`Runner Time - Last600` 單獨 AUC 0.588；dev 0.593、holdout 0.564。10% 混入現役
pace leaf 嘅 holdout Top-5 AUC +0.0037，CI [+0.0008,+0.0069]，但 Gold -0.25pp、
Good 0、Pass +0.12pp。Gold／Good 優先之下只留 shadow，唔 ship。

### Whole-race speed figure

10–100% sweep：30% 版本 Gold +0.50pp、Pass +1.61pp，但 Good -0.25pp，holdout CI
[-0.0042,+0.0100]；40% 起 dev AUC 轉負。未證明穩定改善。

### Historical handicap-rating movement

`current rating - latest historical HC` 單獨 AUC 約 0.592，但混入現役 rating matrix
冇 incremental value。10% 已令 dev Top-5 AUC -0.0013；100% holdout CI 全負，
Good -1.24pp、Pass -1.74pp。現役 official rating 已吸收同一訊息。

### Class strength / distance aptitude

- `class_score` 單獨 AUC 0.568、五個 dev folds 全正，但 5–20% 加入／取代 rating
  全部未通過，Good／Pass普遍下降。
- `distance_score` 單獨 AUC 0.556；10–100% 取代 track signal 未能守住 Gold／Pass，
  所有 holdout CI 跨 0。
- opponent `formline_score` 改善覆蓋後仍只得 AUC 0.508，早期 folds 低過 0.5，
  維持 report-only 係正確簡化。

## Conclusion

> 後續更新：本文寫完後再發現 archived meeting cache 漏讀 `Archive/`，修正後取得
> 現役 Sportsbet 完整 margin＋prize＋starters evidence，並完成一個通過 gate 嘅
> performance-quality matrix upgrade。最新結論及 production 數字以
> `15_performance_quality_matrix_upgrade_20260809.md` 為準。

今輪有實際 performance 改善，但來源係修正跨馬資料 identity，而唔係微調 ranking。
現有 PF／rating／class／distance 已高度重疊；再調現有比例主要係交換 Gold、Good、Pass，
冇穩定全面提升。下一個有機會提高 Gold 嘅研究應新增獨立 point-in-time evidence：
完整 running-position-adjusted sectionals、歷史 race-strength normalization、可重播 trip／
excuse evidence。Production matrix 權重維持不變。

## Verification

- full runtime materialization：1,034 Logic files／805 aligned races／8,249 runners；
- AU auto + shared + daily tests：**414 passed**；
- 新 regression tests 封住 stale PF、cross-horse Formguide digest 同 identity mismatch。
