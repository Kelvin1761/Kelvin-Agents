# EXP-20260824-01 長休後復出未上名，短期內再跑應否扣分

- **日期**：2026-08-24
- **平台**：AU
- **起因**：用戶覆盤 2026-08-22 Randwick R1；Gunroom 舊輸出排第一，實際跑
  9/11。用戶提出佢長休後復出表現唔好，模型可能漏咗呢層狀態週期。
- **假設**：一匹馬上一仗係長休後復出、復出未上名，而今仗 30 日內再跑，應該喺
  ranking score 扣分。
- **搜索過嘅舊記錄**：EXP-20260822-01/02/03/04、EXP-20260823-02/03；
  `REFIT_PLAN.md` 已記 `days` 單獨 AUC 0.483（反向 0.517），但未測「長休 ×
  復出未上名 × 二出」交互。
- **改到嘅 production model code**：無
- **重跑腳本**：`scratch/au_gunroom_20260824/post_spell_experiment.py`

## 先核對個案

Gunroom 唔係 2026-08-22 直接久休復出：

1. 2025-12-12 Canterbury 跑第三；
2. 約 **239 日**後，2026-08-08 Kembla Grange 復出，跑 4/8、輸 1.5L；
3. 13 日後跑 2026-08-22 Randwick R1，所以今場係休後第二仗。

舊引擎只見到「距上仗 13/14 日屬正常間隔」，`status_cycle` 又係空值，確實冇
表達「上一仗係長休後復出」呢層 context。呢個係資料／敘事缺口；但要落 ranking
分，仍然要過模型評估合約。

## 數據同洩漏檢查

- runtime point-in-time dataset：1,411 場、14,109 匹；dev 899 場、holdout 512 場。
- 候選只由 `raw_pre_race.facts_section` 入面**早過目標賽日**嘅正式賽日期同名次重建：
  - `prior_spell_days = 最近一仗日期 − 再上一仗日期`
  - `days_since_return = 今仗日期 − 最近一仗日期`
  - 最近一仗未入前三
- **冇用市場、SP、賽後 career overview 或目標賽果做特徵。** `actual_pos` 只作 label。
- 舊 Facts 嘅名次格 `- (-1.5L)` 按 EXP-20260822-01 已證語義處理為「未上名」，
  唔會把輸距當名次。

## Development 搜索

只喺 dev 搜：長休門檻 60/90/120/180 日、再跑窗口 21/30/45 日、扣分
0.5–3.0。要求五個時間 fold 至少 4 個非負，再按 dev 頭五位 AUC 揀。

鎖定候選：**長休 ≥180 日、復出未上名、30 日內再跑 → ability −3.0**。

- dev 頭五位 AUC：**+0.000723**
- 5 個 dev 時間 fold：4/5 非負
- dev cohort：全部 178 匹，上名 31（17.42%）
- 當模型本身排 Top 3：35 匹，上名 13（37.14%）
- 當模型本身排第一：9 匹，上名 3（33.33%）

即係全池方向同用戶觀察一致，但條件於模型排名之後，效應已收窄好多。

## 一次過 Holdout 判決

候選鎖定後先睇 holdout：

| 指標 | 結果 |
|---|---:|
| dev 頭五位 AUC | +0.0007 |
| holdout 頭五位 AUC | **+0.0011** |
| holdout 95% CI | **[-0.0012, +0.0036]** |
| 全場 holdout AUC（參考） | +0.0020 [+0.0001, +0.0039] |
| Gold / Pass / winner@5（全樣本參考） | +0.21 / +0.14 / +0.43pp |
| winT3 / t3prec（全樣本參考） | -0.07 / -0.02pp |

**主裁判區間跨零，按 `docs/model-evaluation-contract.md` 唔可以 ship。**

Holdout cohort 更顯示點解唔應該硬扣：

- 全部 124 匹，上名 27（21.77%）
- 模型 Top 3：25 匹，上名 12（48.00%）
- 模型首選：4 匹，上名 **3（75.00%）**

全池「長休後復出未上名」係弱群，但模型已經睇高嗰批唔係同一回事；硬扣會有
Simpson's-paradox／錯殺風險。

## 個案重跑更正：唔可以用 archived Logic 聲稱新排名

最初用 commit `18035ada` 現行 engine 直接食 08-22 archived Logic 重跑，曾得到
Twinkling Star 第 1、Clear Proof 第 2、Let's Go Again 第 3、Gunroom 第 4、Isawyou
第 5。**呢個重跑現已判定無效並撤回。**

原因係舊 Logic / Facts 對未上名往績仍然保留 `- (-1.46L)` 呢類缺失 finish token；
現行 engine 重算時會把部份壞仗排除，令 Twinkling Star 等馬嘅 `form_score` 不合理升到
100。佢唔係修正後嘅 point-in-time input，所以唔可以用嚟比較新舊排序，亦唔可以講
Gunroom 已由第 1 跌到第 4。

可核實嘅唯一賽前 source of truth 係 08-22 10:11 生成嘅原始
`Meeting_Auto_Scoring.csv`：

| 原始模型排名 | 馬 | 分數 | 實際名次 |
|---:|---|---:|---:|
| 1 | Gunroom | 71.0453 | 9 |
| 2 | Clear Proof | 70.5134 | 1 |
| 3 | Isawyou | 70.2017 | 2 |
| 4 | Let's Go Again | 69.2070 | 4 |
| 5 | Twinkling Star | 68.4200 | 8 |
| 7 | Call Me Sassy | 62.4169 | 3 |

因此今次只可以判定長休候選 **REJECT**；未有一份資料完整、可重現嘅「修正後 R1
新排名」。未上名 finish-token 修正嘅排序效果，要等新 point-in-time race 向前量。

## 額外發現：Reflector 曾經改寫原始排名

`Race_Results_Reflector.md` 只列每場頭六名；舊 reflector 卻將「冇出現喺賽果檔」
當成退賽，刪走 Gunroom 等尾段馬再重新排名，所以舊報告錯誤顯示 Clear Proof 第 1、
Isawyou 第 2，並把 R1 評為 Gold。

2026-08-24 修正後，預測快照保持不可變；只會剔除賽果明確標示 `is_scratched` 嘅馬。
R1 正確覆盤係：模型 Top 3 = Gunroom / Clear Proof / Isawyou，實際 Top 3 = Clear
Proof / Isawyou / Call Me Sassy，評級 **Pass**、Top 5 覆蓋 2/3。

## REF-DA01 五角度覆盤

### 1. 結果偏差

| 舊模型排名 | 馬 | 實際排名 | 偏差 | 判讀 |
|---:|---|---:|---:|---|
| 1 | Gunroom | 9 | +8 | 最嚴重高估；兩個平均有效訊號（PF、濕地）同場失手 |
| 2 | Clear Proof | 1 | +1 | 前列判斷正確 |
| 3 | Isawyou | 2 | +1 | 前列判斷正確 |
| 7 | Call Me Sassy | 3 | +4 | 實際第三仍被低估 |

Isawyou 原始賽前排名一直係第 3；「現行重跑第 5」來自不完整 archived Logic，已撤回。
Gunroom 仍然係原始模型首選，呢個高估個案未被一個經驗證嘅新 R1 排名解決。

### 2. 過程偏差

- 舊 health context 只睇到距上仗 13/14 日，寫成正常間隔，冇表達上一仗係長休後復出。
- Gunroom 嘅 PF 係往績**賽事環境**而非個體段速；本場 PF 頭三匹全部落榜，見
  EXP-20260823-02。
- Soft/Heavy 往績舊版 1:1 溝埋，會錯誤壓低 Clear Proof、抬高 Gunroom；已由
  EXP-20260823-02 通用修正。
- 市場 $26 只作模型分歧診斷，冇偷偷落排名分。

### 3. SIP-DA01 自我審計

多角度審計今次有實際改變決定：如果只睇本場，`-3` 可以把 Gunroom 再推後；但分開
全池、模型 Top 3、模型首選三層後，符號／幅度明顯收窄，holdout 主閘亦跨零。
所以最終由「準備加長休懲罰」改成 **REJECT**。SIP-DA01 今次有效，冇同基礎模型
衝突；佢阻止咗用市場同單一賽果救候選。

### 4. 泛化性審計

- 🟡 **條件性資料問題**：引擎缺少「上一仗係休後復出」狀態週期，會令報告 context
  不完整，值得補顯示／風險提示。
- ⚪ **未證實排名問題**：長休後復出未上名唔可以一律扣分；holdout 模型首選 4 匹中
  3 匹仍上名，未有足夠泛化證據。

### 5. Design Pattern Proposal

- **Issue ID:** REF-20260824-01
- **分類:** 🟡條件性
- **問題描述:** 只睇距上仗日數會把休後第二仗誤寫成普通 14 日間隔，遺失 prep context。
- **受影響嘅 Protocol:** 基礎邏輯／報告風險層
- **建議修改:** 由賽前正式賽日期衍生 `prep_stage`、`prior_spell_days` 同
  `return_run_placed`，先作報告／風險提示；排名分保持 0，等 forward sample 令 holdout
  頭五 AUC CI 排除零先再審。
- **預期效果:** 改善報告可解釋性；**唔聲稱命中率改善**。
- **SIP-DA01 評價:** 有效 — 成功分開個案合理性同可泛化排名證據。

## 結論

**REJECT ranking penalty。** 用戶指出嘅狀態週期 context 缺口係真，但今次候選未過
holdout 主閘，唔准講成改善，亦唔改 production scoring。

覆盤器嘅「部分賽果改寫預測排名」bug 已修正，但呢個係評估正確性修正，**唔係模型
命中率改善**。R1 原始模型仍然係 Gunroom 第 1、Clear Proof 第 2、Isawyou 第 3；
未有可信證據支持硬改成 Clear Proof / Isawyou 頭二。後續可以把「休後第二仗」補入
報告／風險提示，但除非新 point-in-time 數據令 holdout CI 排除零，唔應該直接入分。

## 重跑

```bash
PYTHONDONTWRITEBYTECODE=1 python3 \
  scratch/au_gunroom_20260824/post_spell_experiment.py \
  /private/tmp/au_reopt_20260821/work/au_ml_runtime_dataset.json
```
