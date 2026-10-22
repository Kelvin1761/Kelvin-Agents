# EXP-20261022-02 NBA 穩膽揀腿規則 ablation（協議，喺計任何結果前 commit）

- **日期**：2026-10-22
- **平台**：NBA
- **假設**：Phase 2 嘅四條揀腿規則（stat 白名單、神經刀禁止 `cov ≤ 0.35`、賠率區間、取消 2.0–3.5x 目標）中，至少一條令穩膽式揀腿喺莊家價之上嘅 holdout flat ROI 優於現行式 gate（A0）。**可證偽**：若無任何 arm 嘅 holdout ΔROI 95% CI 下限 > 0，結論＝「未證明更好」。
- **搜索過嘅舊記錄**：EXP-20261022-01（本實驗嘅 baseline 同語料）、EXP-20261021-02～05（機率引擎校準，無賠率）。冇其他 NBA 揀腿規則實驗。
- **改到嘅檔案**：**冇改 production code。** 只加 `docs/experiments/patches/nba_banker_phase1/phase2_ablation.py`。
- **語料**：EXP-20261022-01 嘅 `corpus_2025_26.csv`（`build_corpus.py`，已加 `cov`、`l3_avg`、`min_avg`、`game` 欄；原有欄位不變）。剔走 2026-04-09（可能入場後抽取）。**只有季後賽／附加賽，冇轉隊球員。**

## 1. 切分（凍結）
- 31 個比賽日按日期排序：**dev＝首 19 日（04-12…05-06）**、**gap＝05-07**、**holdout＝最後 11 日（05-08…06-10）**。holdout 只評估一次，唔准用嚟揀參數或改切法。
- 注意 EXP-20261022-01 嘅 baseline 用咗全部日子（包括 holdout）做描述；**所以本實驗唔直接沿用 baseline 揀出嘅賠率區間**，區間由 dev 重新選（§2 P）。

## 2. Arm（固定，唔准加）
共同 pool 基礎＝**A0（現行式 gate，由 `select_combo_1` 寫法搬過嚟）**：`L10 命中 ≥ 0.8`、`L5 命中 ≥ 0.8`、`price ≥ 1.20`、`cov ≤ 0.65`、`(avg_l10 − line)/line ≥ 0.15`、`l3_avg ≥ line`、milestone over。唔含 `edge ≥ 0`（冇引擎機率）。

| Arm | 相對 A0 嘅改動 |
|---|---|
| A0 | 無 |
| S | stat ∈ {PTS, REB} |
| C | `cov ≤ 0.35` |
| P | 賠率區間：喺固定候選 {[1.20,1.30), [1.30,1.45), [1.20,1.45), [1.30,1.60), [1.45,1.80)} 入面**只用 dev** 揀單腿 flat ROI 最高（要求 n ≥ 100），然後凍結 |
| N | 組合唔設 2.0–3.5x 目標（取 pool 頭兩條腿） |
| ALL | S＋C＋P＋N |

## 3. 組合構造（所有 arm 一樣，確定性）
每場一個組合：pool 按 `(−hit_l10, −hit_l5, price)` 排序（live 排序少咗 `edge`）；同球員唔重複；同隊 PTS ≤2、同隊 ≤3；最多 3 腿。有目標嘅 arm（A0、S、C、P）：逐腿加到組合賠率 ≥2.0，要 ≤3.5，否則該場冇組合（至少 2 腿）。N／ALL：頭兩條腿。組合賠率＝腿賠率相乘（**實際 SGM 價較低**，所以 ROI 係上限，只可比較 arm 之間）。

## 4. 度量同判決（預先登記）
- **Primary**：holdout **單腿 flat ROI**（arm pool 入面所有腿）嘅 ΔROI＝arm − A0，**按比賽日 cluster bootstrap（2,000 次，resample 日；兩個 arm 用同一批 resample 日）**。
- **Secondary（唔參與判決）**：每場組合命中率、組合 ROI（上限）、n 組合、平均組合賠率。
- **判決**：
  - `improves`：holdout ΔROI 下限 > 0 **且** dev ΔROI > 0。
  - `regresses`：holdout ΔROI 上限 < 0。
  - 其他＝`not shown`。
- **功效聲明（先登記）**：A0 holdout 預計 ≈ 300 條腿；若 SD 單腿回報≈0.5，SE ≈ 3pp，MDE（80% 功效）≈ 9pp ROI。**細過 ~9pp 嘅改善喺呢個語料度量唔到**；`not shown` ≠ `冇用`。
- 只記一次結果；唔准因結果加 arm、換指標、換窗、換 K。

## 5. 狀態
協議已凍結，**未跑**。結果見 §6（跑完先加）。
