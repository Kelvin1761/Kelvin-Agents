# EXP-20261023-07 NBA context 接線及防守單位修正

**判決：工程／資料正確性修正；冇證明預測或盈利改善。** 對應審核 F07、F08、F09。C 係數、選取門檻及既有 correlation 權重均未改；未將 MC／10-Factor／新 RF 晉升成最終機率。

相關前案：EXP-20261023-01（B2B 接線）、EXP-20261023-02（傷停分類，當時尚未處理 usage）、EXP-20261023-04（開季補缺）、EXP-20261021-02～05（缺 context 嘅舊機率研究，唔可以外推完整輸入）。呢次修正既有通道，唔以舊缺值研究判定新特徵有功效。

## 根因及修正

1. **Blowout**：`_has_blowout_risk` 讀 `adj_breakdown.minutes_floor`，但候選 flatten 時冇傳。依家 copy 原本 breakdown；原有 spread≥12／minutes_floor≤−2 嘅 joint probability 5% 扣減可以生效，冇改幅度。真實 card→candidate→correlation integration test 覆蓋。
2. **Usage**：冇 gamelog 唔等於受傷；有完整歷史嘅 Out 球員亦唔代表健康。使用同一狀態分類器，只有已確認缺陣者提供紅利；DTD／Questionable 唔提供亦唔接收。刷新傷停時重新計算，復出會清走舊紅利；報告唔信舊 serialized allocation。名稱用全名規範身份。
3. **Pace**：10-Factor 第 10 項原本硬傳 None，依家傳真正己隊 PACE。MC 本來已收到己隊 pace，呢部分唔改 MC 公式。
4. **MC usage 單位**：來源係 USG 百分點，MC 參數係 stat count。依家 card 帶明確欄位；固定效率情境下 PTS／3PM bonus = L10 AVG × bonus_USG / original_USG。25% 加 5pp → 相對 +20%，唔係加 5 個 stat。USG 唔直接定義籃板／助攻，呢兩項冇直接換算。唔擬合新權重，唔根據 terminal 揀比例。marginal 同 joint simulator 兩條實際呼叫均有 integration test。MC 記錄版本 2.1／joint v1.1，ledger 保留版本。
5. **防守來源**：官方 NBA API 同一 cutoff（2025-26／截至 2026-04-08）576 位球員，PerGame `D_FGA≥20` = **0**；Totals = **523**。同一批 576 人 `PCT_PLUSMINUS` 完全一致；錯嘅係樣本單位。改用 Totals，保留原 20 total attempts floor，記錄 unit／GP／覆蓋，規範隊名；統計 cache contract 升為 2，舊模式／來源失敗 cache 唔會永久重用。官方 endpoint 定義：[nba_api LeagueDashPtDefend](https://github.com/swar/nba_api/blob/master/docs/nba_api/stats/endpoints/leaguedashptdefend.md)。實際查詢及分佈證據另存 JSON，唔回填今日資料落舊賽前輸入。

## 預先固定消融

Base：`0bffbeb674d32ef9cc79722c931751c35250315a`（完整 real renderer，原始 64 例重播）。本次採已鎖定 50 個 pre-tip priced captures，實際 49 場／24 個 US 日期。code-only arm 約 2 MB，一份原始語料；所有輸出留已掛載外置碟。

九個 arm：injury_status、mc_usage、team_pace、blowout 各自單獨；full；full 分別移除以上四項。所有來源 input hash、v3 model hash、10,000 draws、game／leg seed 固定，冇 fit、search、刪失敗案例。共 450 次 renderer，全部成功。

SGM 報價修正刻意喺實驗外：呢啲係**正式報價之前嘅候選軟件重播**，唔係可以落注嘅產品。舊例全部冇正式組合，所以零變化只證明呢份語料冇 selection regression，唔證明新情境一定更好。

按同一份 dataset 已採用嘅最早合法來源逐列去重後，8,286 個有 label 嘅盤口全部對得返 renderer，冇失配。軟件重播總共 8,606 個 capture×leg（保留兩個快照）。原先直接 game_group→capture 一對一 mapping 會錯配同場兩快照，已改按 source_game_path；原初摘要保留，正式用 `paired_summary_deduplicated.json`，唔改資料或日期。

## 結果

- 九個 arm 嘅 **p_final 差異 0**（全部 8,606 個 capture×leg）；C 仍只食同一個市場價及 L10。組合全部 0，membership 差異 0。
- 只有 MC usage 有單獨 MC 變化；傷停分配同 MC 接線有 interaction，故亦跑 full-minus 項，冇只報 combined。
- full：2,645 個 MC 機率改變；配對 Brier Δ **−0.000688**，日期 cluster 95% CI **[−0.002223, +0.000652]**，跨零，**唔係改善證據**。
- MC usage 單獨：232 個變化，Δ −0.000048，CI [−0.000279, +0.000126]，亦跨零。
- 10-Factor 診斷值嘅變化及每項 full-minus 結果全部保存，唔以 shadow 值取代 C。

呢個 USG→scoring-volume 換算係固定效率情境，未包括教練輪換、傷缺已經反映喺 L10、角色轉變等效應，唔係因果功效證明。尾段歷史曾被研究檢視，唔當新盲測；呢份結果只支持修正既有資料通道及冇觀察到現役 C 輸出 regression。未驗證 forward 命中／ROI，亦冇歷史真實 SGM quote 可以證明盈利。

## 證據及重現

- `docs/experiments/patches/nba_audit_20261023/context_ablation.py`（從 immutable base 建 arm，禁止通知／部署，固定語料）
- `docs/experiments/patches/nba_audit_20261023/analyze_context_ablation.py`（逐來源對齊、按日配對 bootstrap，2,000 次／seed 20261023）
- `docs/experiments/evidence/EXP-20261023-07/`：完整 arm protocol／來源 code hash、逐項數字、防守 API 單位／樣本及時間資料覆蓋
- 外置根：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/codex-nba-remediation-20261023`

正式發佈另須 NBA 專項、quick、完整 immutable gate，並以 release manifest 驗證 merge／activate；唔用本文件當部署成功證據。
