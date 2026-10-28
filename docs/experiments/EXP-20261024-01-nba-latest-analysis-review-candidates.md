# EXP-20261024-01：NBA 最新分析及只讀 SGM 候選

日期：2026-10-24。baseline commit：23b2e2e40f8a19af860666bf39a1d5ef87de8dbd。

呢份係工程／可觀測性驗證，唔係盈利改善實驗。用戶指出零正式注時主頁只見四個四月舊案例，睇唔到最新逐場分析；正式選腿又喺真實 SGM 報價前已經篩空。

已讀 EXP-20261022-02：選腿規則各 arm 未證明更好；唔可以憑最近五場取消正式 gate。已讀 EXP-20261022-03：現役 C 校準層保留。今次不改正式機率／權重／規則／注碼，唔使用 holdout 調參。

## 固定觀察層

獨立 review-only v1：由已驗證球員候選中排除缺席（既有 builder）、疑似上陣及後備分鐘風險；最多 24 腿、只枚舉 2／3 腳，保留既有同球員／同隊 AST／PTS 結構限制。三個展示價帶 1.5–3／3–6／6–15（單腿乘積只用來找候選）；按既有調整後聯合機率及 EV 確定性排序，每帶最多一次真實 SGM 報價，最多三個請求。實價缺失唔以單腿乘積代替。即使候選 EV 正，仍固定 OBSERVE，唔進正式建議、確認投注或 ROI。

候選記錄喺既有 hash-bound sidecar，原生 immutable snapshot 保存整份側檔。候選失敗會記錄錯誤，唔改正式結果。Dashboard 新增逐場 latest_analysis，顯示正式空缺原因、候選、盤口評估、傷停同完整報告；舊案例改為獨立分頁。

## 同源重播結果

來源：2026-10-25 五場 BKN_CLE／GSW_PHX／HOU_ATL／NOP_DEN／WAS_CHI，305 個球員盤口；原生生產來源資料複製到獨立 worktree，baseline 已先保存。

- 同一份來源重播：305 個 p_final、picked／picked_in 及五場正式 combos 全部相同（五場均零正式組合）。
- 觀察層：五場每場三個，共 15 個真實 Sportsbet SGM 報價成功；實價再驗 request／legs 身分、event、300 秒 quote 合約。此結果只證明接線及展示，唔證明盈利。
- 既有選腿原因：18 個模型正 EV 盤口，17 個 L10 只 0–30%，唯一 ≥50% 盤口唔足以砌兩腳；候選會顯示未達命中率、實價 floor 或非正 EV 嘅具體原因。
- 新版正式 orchestrator 五場通過：完整來源及傷停防火牆仍有效，候選唔繞過任何正式 gate。
- Python：453 passed；前端 Node：86 passed；quick gate 通過。手機 390×844 預覽見最新日期、8 場、5 已分析、15 候選、0 即時正式 SGM，舊案例唔再佔主頁。

## 判決及限制

工程接線可交付；正式模型／策略晉升 **NEEDS MORE TESTING**，今次不晉升。無回測收益、ROI 或命中率改善聲稱。候選僅有 forward 賽前紀錄，未有 settled-day 真實 SGM 研究樣本；唔准憑十五個價或單日結果改正式規則。

可重現命令：`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=Horse_Racing_Dashboard python3 -m pytest .agents/skills/nba/nba_daily_auto/tests Horse_Racing_Dashboard/tests -q`；`node --test Horse_Racing_Dashboard/tests/test_static_template.mjs`；`./檢查.sh --quick`。正式全套 gate、release SHA、公開頁面與來源 hash 證據另由 Central immutable manifest 及本次交付驗證保存。

只讀 latest_analysis 額外容許經完整 firewall＋四檔雜湊驗證嘅 warmup snapshot，正式 analysis_cards／BET 路徑仍拒絕 warmup。手動驗證可保存 warmup 角色，唔會提前滿足／跳過 21:00 production 或翌晨 final_refresh；已加預設拒絕／明確只讀接收回歸測試。
