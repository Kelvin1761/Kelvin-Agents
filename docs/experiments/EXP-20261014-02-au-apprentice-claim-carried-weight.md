# EXP-20261014-02 AU：見習減磅／超磅喺抽取層保存，實負磅入 Racecard（§7 正確性修正）

- **日期**：2026-10-14
- **平台**：AU
- **假設**：唔係績效假設。係一個可以獨立證明嘅抽取錯誤：Sportsbet `J` 行嘅 `(a-1.5)` 被剝走，
  見習騎師嘅馬被記錄成多揹 1.5–4kg。
- **搜索過嘅舊記錄**：EXP-20261012-34（減磅殘差 UNRESOLVABLE，冇接入）、
  EXP-20261014-01（`claim_kg` 做特徵 REJECT，AUC 0.4833；記錄指出抽取層要另開一單修）。
- **改到嘅檔案／組件**：
  - `.agents/skills/au_racing/claw_sportsbet_form.py`：`parse_jockey_allowance`、`carried_weight`、
    `format_weight_field`；`parse_runner_blocks` 讀 `J` 行；`write_meeting` 寫 Racecard `Weight:` 欄
  - `au_racing_engine/source_alignment.py`：`RACECARD_META_RE` 加 `allowance_label`／`allowance_kg`
  - `au_racing_engine/engine_core.py`：Racecard profile 帶 `jockey_allowance_kg`；horse 加
    `jockey_allowance_kg`、`carried_weight`；報告 note／負磅顯示；`_handicap_weight_proxy` 加註
  - `build_au_logic.py`：死 code `_load_racecard_profiles` 改用 named group（之前 `group(1)` 係練馬師名）
  - 新測試 `au_wong_choi_auto/tests/test_jockey_allowance.py`（16 項）

## 錯處（獨立證明，唔靠績效）

8,854 個 cache 賽事頁、44,096 個 runner `J` 行：

| `J` 行後綴 | 數目 | 值 | 解讀 |
|---|---:|---|---|
| 冇 | 33,998 | — | 冇調整 |
| `(a-N)` | 9,010 | 1.5 / 2 / 3 / 4 | 見習減磅 |
| `(aN)`（冇減號） | 1,081 | 0.5 / 1 / 0 / 2 / 3 / 3.5 | **超磅**（推斷，見下） |

- **`W` 係分配負磅**：3,696 場入面，見習馬嘅 `W` 有 6,704 匹（96%）跟住號碼次序單調；
  如果 `W` 係實負磅，`W − 減磅` 應該單調，但呢個只得 449 匹（6%）。用戶例子 Rosehill R8
  60.0／59.5／59.5（Anna Roper a-1.5）／59.0／59.0（Jacob Stiff a-3）重抽後逐字對得上。
- **`(aN)` 係超磅**係由數據推斷，Sportsbet 冇寫明：出現喺 James McDonald、Tommy Berry、
  Nash Rawiller 呢類資深騎師（唔會有減磅）；呢批馬 51.6% 喺全場最低磅，冇調整嘅基準係 24.0%。
  即係「騎師壓唔到最低磅」。如果將來發現唔係，只要改 `parse_jockey_allowance` 嘅正號分支。
- 總覽表個騎師格只得 `( )`，所以舊 `parse_overview` 剝唔剝都冇分別 —— 減磅只喺 runner 區塊 `J` 行。

## 揀邊個負磅入引擎：**分配負磅**（唔轉）

`weight` 喺引擎有三個用途，逐個判：

| 用途 | 位置 | 揀 | 原因 |
|---|---|---|---|
| 讓磅代理（冇官方 rating 時 `rating_score` 嘅 fallback） | `_handicap_weight_proxy` | **分配** | 代理量嘅係「讓磅官點評呢匹馬嘅能力」。讓磅官先派磅，減磅係之後因騎師而減，同馬嘅能力無關。用實負磅會把「見習騎師」誤讀成「讓磅官睇低呢匹馬」。 |
| 場內負磅統計（場均／SD／頂磅） | `_field_summary` | **分配** | 代理嘅分母，同上 |
| `weight_score` | `_weight_score` | **分配** | 已退出排名；而且註釋已證明讓磅賽負磅係能力訊號唔係體能負擔 |
| 報告「負 X kg」、人馬配搭 note | 顯示 | **兩樣都顯示** | 分配負磅照舊，加後綴「（見習減 3kg，實負 54.0kg）」 |

轉做實負磅喺代理入面**等於從後門加入減磅特徵** —— 見習馬實負較輕 → 代理分較低 → 排名降，
而呢個正正係 EXP-20261012-34（UNRESOLVABLE）同 EXP-20261014-01（REJECT）已經測過嘅訊號。
所以唔轉，亦唔用 §7 去偷渡一個候選。

## 配置
- **baseline**：`775b98a6`（開工時 HEAD），保存前喺 `267e0d5b`（origin/main）重驗；生產 Racecard（冇減磅）
- **candidate**：工作樹改動 + cache-only 重抽嘅 Racecard（只換 `Weight:` 欄，RA rating 等其他欄原封不動）

## 數據／A/B

2026-10-14 Rosehill 八場（`WC_SB_CACHE_ONLY=1` 重抽，零網絡請求），98 匹，21 匹有調整。
三方比較，全部用 `au_auto_orchestrator.py`：

| 對比 | Scoring CSV（8 場 + Meeting） |
|---|---|
| 舊 code + 舊 Racecard（`git archive HEAD`） vs 新 code + 新 Racecard | **9/9 逐 byte 一樣** |
| 新 code + 舊 Racecard vs 新 code + 新 Racecard | 9/9 逐 byte 一樣 |

**保存前喺新 base `267e0d5b`（main 期間多咗 4 個 commit，包括 `93a0a193` 改引擎）重做**：
生產場次 10:19 被排程重抽過，所以用新鮮副本（15 匹有調整）再比三方 —— 舊 code、新 code + 舊 Racecard、
新 code + 新 Racecard —— **9/9 逐 byte 一樣**。⚠️ 中途試過一次「DIFF 全部」，原因係 cand 副本係
07:42 抽嘅舊版、old 副本係 10:19 新版，即係兩份輸入唔同，唔係改動造成。A/B 一定要兩邊同一刻抄。

Logic.json 差異只有：`jockey_allowance_kg` 21、`carried_weight` 21、`class_weight` 判讀文字 21、
人馬配搭 note 18（減磅 note；3 匹超磅冇 note，只有負磅後綴）。即係**有接通**，而唔係 A/B 冇駁線。

`golden_scoring --platform au`：120 匹全部一致（fixture 係舊格式 Racecard，證明冇減磅時零變化）。

**au_eval 冇跑**：預測逐 byte 一樣，冇嘢可以比；跑出嚟只會係 `identical_predictions`。

## 檢查
- **leakage-audit**：PASS —— 減磅喺排位表公佈（賽前），賽前賽後頁同一值（EXP-20261014-01 已核）；
  而且唔入分。
- **golden_scoring**：冇郁（120／120）；冇 `--record`。
- **data_contract**：唔涉及（冇新評分欄位）
- **退步**：冇（排名輸出逐 byte 一樣）

## 已知限制
- **2026-10-14 之前抽嘅 Racecard 冇括號**，引擎讀成 `jockey_allowance_kg = 0.0`。對舊檔嚟講 0 係
  **未知**，唔係「證實冇減磅」。要補舊檔就用 cache 重抽 `Weight:` 欄（cache 有 9,010 個減磅）。
- Formguide 冇改：佢冇今仗負磅欄，`J:` 行有 `extract_formguide_data` 嘅 regex 同 LY 查冊食緊。
- 順手發現：`au_ml_matrix_diagnostics.RACECARD_META_RE` 喺 418 行真 Racecard 入面 0 行配到
  （唔容許 `kg`），同今次無關，另開 task。

## 結論
抽取層而家保存見習減磅同超磅，Racecard `Weight:` 欄寫成 `59.5kg (Claim 1.5kg, Carried 58kg)`，
第一個數字仍然係分配負磅，所以下游四個 parser 唔使改。引擎刻意繼續用分配負磅計分，實負磅只入報告。

**呢個冇通過表現閘，唔係一個已證實嘅改善。** 佢係 §7 正確性修正：錯處獨立可證，排名零變化。

**決定**：KEEP（§7 correctness，display + data only）
**commit**：未 commit

## 重跑
```bash
export PYTHONDONTWRITEBYTECODE=1 WC_DISABLE_POST_SUCCESS_DEPLOY=1
# 重抽（cache only）
cd .agents/skills/au_racing
WC_SB_CACHE=/Users/imac/Antigravity-repo/.agents/skills/au_racing/.sportsbet_cache WC_SB_CACHE_ONLY=1 \
  python3 claw_sportsbet_form.py --meeting-url https://www.sportsbetform.com.au/452913/3447848/ \
  --races 3447848,3447849,3447850,3447851,3447855,3447858,3447861,3447863 \
  --out-dir $S/claw_out --date 2026-10-14 --venue Rosehill
# 兩份 meeting 副本，cand 只換 Weight: 欄，然後各跑
python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_auto_orchestrator.py "<meeting copy>"
python3 .agents/skills/shared_racing/scripts/golden_scoring.py --platform au
python3 -m pytest .agents/skills/au_racing/au_wong_choi_auto/tests/test_jockey_allowance.py
```
⚠️ 喺 worktree 跑 claw 會寫 worktree 自己嘅 `.sb_horse_index.json`（gitignored），跑完刪走。
