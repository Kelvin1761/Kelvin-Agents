# EXP-20261021-08 NBA live 最終機率 E 嘅單調重校準（全覆蓋、唔依賴同季場數）

- **日期**：2026-10-21
- **平台**：NBA
- **假設**：live 最終機率 E（base＋7 個可重現調整項，即係今日排腿同計 EV 用嘅機率）slope ≈0.45，高機率區高估 10–14pp（EXP-05／06）。**假設：一個只喺 dev 擬合、套用喺 E 輸出上嘅單調重校準（isotonic 或 Platt）可以移除過度自信，而且唔需要任何額外輸入（所以對賽季初每條腿都有效）。** 同時預先講明：單調映射**改唔到排序（discrimination）**——E 嘅 Brier 比 plain L10 base 差，排序質素先係限制。可證偽：若 K1／K2 唔過下面條件（包括否決同賽季初階層水平條件），結論就係「E 嘅重校準唔足以修好校準，或者賽季初要另一個 map／policy」。
- **搜索過嘅舊記錄**：EXP-20261021-02～07（E 嘅 slope 同高機率區高估、ablation 發現可重現項令 base 變差、layer A、賽季初 carryover 同分鐘校正）。冇 E 重校準記錄。
- **改到嘅檔案／組件**：**冇改 production code，冇改 frozen artefact `nba_fit_layer_A_v1.json`。** 新增 `docs/experiments/patches/nba_calibration_exp20261021_02/nba_recal_e.py`（重用 `nba_calib`、`nba_pregame`、`nba_early`、`nba_early_minutes`、`nba_refit`、`nba_fit_layer`）。
- **狀態**：🔵 協議已寫（未跑結果）。

> 限制同 EXP-02～07：線係「L10 平均附近 3 個整數」，唔係莊家開價母體 —— **只量機率引擎校準度，冇講利潤／EV**；E 只含 7 個可重現 live 項（冇 spread、對手 pace／防守、USG／傷兵、ML），所以**唔等於完整 live 機率**；只常規賽。傳聞：Day-1 真實定價腿（3 場、893 條、一日）顯示 `p_final∈[0.9,1.0)` 預測 0.923 實現 0.746——**只係傳聞，不入判決**。

## 1. Population 同切分（凍結）
- **P1（全覆蓋主 population，同季）**＝EXP-05 primary（賽前可知、同季 ≥10 場 prior、prior-10 平均 MIN ≥20、冇賽後過濾）；輸入 `out5/rows.csv`（sha256 `e8b25930…`）。dev＝2025-26 `<2026-01-01`；gap＝1 月；**H1**＝2025-26 `≥2026-02-01`；**H2**＝2024-25。階層：全部係「第 ≥11 場」（`n_cur≥10`＋本場）。
- **P2（賽季初，另行評估）**＝EXP-06 early population（同季第 1–10 場，上季 ≥40 場且平均 ≥20 分鐘）；輸入 `out6/rows.csv`（sha256 `a96b350a…`）。dev＝2025-26 early（<2026-01-01）、**H2**＝2024-25 early、**H3**＝2023-24 early。E 用 live 實際會算嘅方式（L10 跨季，已喺 rows 內嘅 `e`）。階層：第 1 場（`n_cur=0`）／第 2–5 場（1–4）／第 6–10 場（5–9）。
- **映射只喺 P1 dev 擬合**（唔用 early 數據），然後套用喺 P1 H1／H2 同 P2 全部窗口——咁先真係測「同一個映射可否用喺賽季初」。H1、H2、H3 各評估一次，唔用嚟調參。
- 線／stat／clip／bootstrap 同 EXP-05：3 條最近整數線，PTS／REB／AST／3PM，機率 clip `[0.01,0.99]`，paired GAME_ID cluster bootstrap 2000 次 seed 20261021。

## 2. Arm（固定）
E 嘅輸出取 rows 內嘅 `e`（live clamp／cap 後，精度 0.1pp；值落喺 0.05–0.98）。

| Arm | 定義 |
|---|---|
| **K0（reference）** | E 原樣 |
| **K1** | **per-stat isotonic**：喺 P1 dev，每個 stat 用 `y` 對 `E` 做 pool-adjacent-violators。**Ties／flat 規則**：先按相同 `E` 值合併（權重＝行數，值＝平均 y），再喺唯一 `E` 值上做 PAV（單調非遞減，允許 flat 段）；預測用 `np.interp` 喺唯一 `E` 值嘅擬合值之間線性內插，範圍外 clip 到兩端；最後 clip `[0.01,0.99]`。 |
| **K2** | **per-stat Platt**：`sigmoid(a_s + b_s·logit(clip(E)))`，dev 擬合。 |
| **L（benchmark）** | P1：frozen layer A（`nba_fit_layer_A_v1.json` 係數，唯讀）；P2：EXP-06 的 A1（frozen A 套用喺 EB 混合 count，`n_cur<10` 時 L 本身未定義，只作排序／校準對照）。 |
| **base** | plain L10 hit rate（live base，EXP-02 (a)） |
| 探索 K1p／K2p | stat 池化版：K1p＝全 stat 一個 isotonic；K2p＝Platt `a + b·logit(E) + stat dummies`（共用斜率）。**判決用 per-stat（K1、K2）**，池化係探索，預先唔改。 |
| 探索 K1e／K2e | 同 K1／K2，但喺 P2 dev early 擬合（只評估 P2 窗口）；用嚟答「賽季初需唔需要另一個 map」。 |
- **判決 candidate：K1、K2**。其他全部係描述性／探索。比較：每個 arm 對 K0 同對 L 做 paired GAME_ID cluster bootstrap（`d_brier_vs_a`＝vs K0、`d_brier_vs_c`＝vs L）。Holm 只作資訊。

## 3. 預先登記判決規則（K1、K2；全部成立先叫 `passes`）
**每個 population 各自判決**；「**全覆蓋 passes**」＝ P1 同 P2 兩個都 passes（因為目標係每條腿都有校準機率）。
**P1（窗口 dev／H1／H2）**
1. H1 pooled `ΔBrier vs K0` 95% CI 全部 <0；
2. dev pooled `ΔBrier vs K0` 點估計 <0（in-sample）；
3. H2 pooled `ΔBrier vs K0` 95% CI 全部 <0；
4. calibration slope ∈ [0.85,1.15]，**H1 同 H2 都要**（點估計）；
5. H1 pooled 10 桶 reliability：所有 n≥500 嘅桶 `|mean p − mean y| ≤0.05`；
6. **否決**：喺 dev，用 candidate 自己嘅最終機率，按 prior-10 平均 MIN 桶（20–25 以 `t_sip_n01=−3` 代表；≥25 以 `=0` 代表，同 EXP-05）計 `mean(y−p)` 同 cluster bootstrap 95% CI；任何桶 `|殘差|>0.03` 且 CI 排除 0 → 否決。
**P2（窗口 dev／H2／H3，用 P1-dev 映射）**
1. H2 pooled `ΔBrier vs K0` CI 全部 <0；2. dev 點估計 <0；3. H3 CI 全部 <0；4. slope 入 [0.85,1.15]，H2 同 H3 都要；5. H2 pooled 冇 n≥500 且 `|p−y|>0.05` 嘅桶；
6. **階層水平**：第 1 場、第 2–5 場、第 6–10 場三個 stratum，喺 H2 同 H3，`|citl|≤0.03` 且 CI 包 0（同 EXP-07 條件 7，但三層都要）；
7. **否決**：dev，candidate 自己嘅最終機率，按上季平均 MIN 桶（20–25／25–30／≥30）同 `n_cur` 階層（第 1 場／2–5／6–10）；任何桶 `|殘差|>0.03` 且 CI 排除 0 → 否決。
- 不准用 H1／H2／H3 重擬合、換 map 類型、換階層或桶、換指標去救候選；想換設計就開新實驗。
- **範圍聲明**：`passes` 只代表「E 嘅校準被修正」，**唔代表排序變好**，亦唔代表 K 同 L 一樣好；vs L 嘅結果只作描述（E 重校準唔可能超越排序）。

## 4. 其他報告（描述性）
- **排序／rank（單調映射改唔到嘅部分）**：AUC（pooled 同 per-stat；pooled AUC 加 GAME_ID cluster bootstrap 95% CI，200 次）：E、base、L、K1、K2；E−base、L−E 差值 CI。逐 stratum（第 1 場／2–5／6–10／≥11）報 Brier、slope、citl、AUC。明確寫「重校準 E 可以／唔可以修咩」。
- **選注視角（`p≥0.70`／`p≥0.80`，描述性，唔係利潤）**：K0、K1、K2、L：n、佔比、平均預測、實際命中；以及 **K0→K1／K2 嘅跨門檻移動**：原本 `E≥0.70`（／0.80）嘅腿有幾多比例重校準後仍 ≥ 門檻；原本低於門檻而升上去幾多；平均預測／實現。
- **映射穩定性（描述性，只作描述，不用嚟選模型）**：per-stat Platt `(a,b)` 分別喺 P1 dev／H1／H2 同 P2 dev／H2／H3 重擬合並列表；isotonic 映射值喺 `E∈{0.30,0.50,0.70,0.80,0.90,0.95}` 嘅 dev 擬合 vs H2 擬合。若賽季初（P2）映射同 P1 差好遠，寫明「賽季初需要另一個 map 或者另一個 policy」。
- **洩漏檢查**：point-in-time 單元測試（重用 EXP-02～07；新增 isotonic／Platt 單調性、tie 處理、映射只用 dev 嘅測試）；shuffle test（dev：置換 `y`，重擬合 K2 per-stat，斜率 `|b|<0.10` PASS；K1 檢查擬合後 in-sample Brier 改善 <0.0005）。
- **若有 candidate 全覆蓋 passes**：寫 shadow deployment design（`shadow_cal_prob_E` 欄位放喺 `shadow_fit_prob_A` 旁，預設計算、冇 consumer、versioned frozen map 檔＋sha256、loader fail-closed、同 fit layer 同一套隔離規則）。若冇：直接寫原因。
- 「what could still be wrong」一節。

## 5. 重跑
（跑完後填）

## 6. 結果
（跑完後填）
