# EXP-20261110-01 協議：NBA 大細盤精選（紙上盤）—— forward 預先登記

- **日期**：2026-11-10（喺任何 forward 數據存在之前 commit）
- **平台**：NBA
- **決定人**：Kelvin（2026-11-10：「happy with it and also make sure dashboard is updated」—— 精選 + 紙上 card + dashboard）
- **取代**：同日較早嗰個「大細盤 under ＋ 模型 edge ≥5pp，全部線」嘅草稿（冇 commit 過）。改為網球式精選：每場一注。
- **凍結**：揀注規則 `.agents/skills/nba/nba_engine/featured.py`（`RULE = nba-featured-ou-v1`）；判決腳本
  `docs/experiments/patches/nba_featured/evaluate.py`。兩樣都同本文件同一個 commit。
- **永遠唔會自動落注、唔會改 B2／SGM／p_final。** 唔落真錢，直到 F1000 PASS 而且 Kelvin 決定。

## 點解（dev 觀察，2026-10-21…11-10，129 場）
- milestone 盤（我哋一直買嘅「N+」）每腿抽水約 8–10%；大細盤（O/U .5，兩邊有價）兩邊加埋 6.5–7.4%。
- 16 日 5,535 條大細盤線：全部 over −10.8% [−14.2, −7.3]，全部 under −1.7% [−5.0, +1.5]。
- 網球式精選模擬（每場 edge 最高 1 注、每日最多 10 注）：大細盤 104 注 **+6.1% [−12, +25]**；milestone 49 注 −9.9% [−35, +15]。
- 警告：(1) 模型對 under 嘅 logloss 0.6936，差過大細盤去水價 0.6887 —— 模型絕對機率唔準，排序可能有啲用；
  (2) 試咗幾個切法先揀呢個；(3) 104 注 CI ±18pp。**呢啲唔係證據。** 分析時亦犯過一次錯（將 ledger `line`＝ceil 當真線，
  做出假嘅 under +23.6%），所以一定要 forward。

## 規則（全部凍結）
- **母體**：target_date ≥ 2026-11-11；每場第一個通過防火牆嘅 21:00 publication（同 SGM tracking 同一個）。
- **候選**：該場 Sportsbet 球員大細盤每條 .5 線、每一邊（PTS／REB／AST／3PM）。
  - P(over X.5) = 同一球員同一 stat milestone 腿「ceil(X.5)+」嘅 `p_final`；P(under) = 1 − 佢。冇對應 milestone 腿就唔計。
  - 球員 availability 要係 `ok`（Day-To-Day 等唔計）。
  - 去水：p_fair(side) = (1/價) ÷ (1/over價 + 1/under價)；edge = P(side) − p_fair(side)。
- **每場一注**：edge ≥ 0.05、價 ≤ 3.0 嘅候選入面揀 edge 最大（打和按球員、market、低線、side 固定排序）。
- **每日上限**：同日超過 10 注就按 edge 取頭 10（`daily_top`，card、dashboard、判決三處共用）。
- **價**：21:00 publication 嗰陣嘅大細盤價（sidecar 凍結），之後唔改價。
- **結算**：球員實際數字對 O/U 線；冇上場（ledger settlement `void`）= 作廢，唔計注。平注 1 單位。
- **顯示**：Dashboard NBA「⭐ 大細盤精選（紙上盤）」（`featured_records`，同 SGM `records` 分開，唔入 ROI 板、唔入穩膽停損）；
  每晚 21:00 Telegram 紙上 card（content）；覆盤訊息只列中／唔中，**唔報 ROI**（AGENTS.md：ROI 只經統一板）。

## 判決
- **F250（中期）**：頭 250 注已結算。ROI 95% CI 上限 < 0 → **STOP**（建議停 card）；否則繼續。中期**唔會 PASS**。
- **F1000（終判）**：頭 1,000 注已結算。平注 ROI 95% CI **下限 > 0** → PASS。
- CI：按日 cluster bootstrap（同一晚嘅注共用新聞、步速同一次模型運算），2,000 次，seed 20261110。
- 兩個判決都只用「頭 N 注」，結果凍結，唔會因為之後數據多咗而重判。
- 夠數由 `nba_forward_tracker`（postgame）自動判一次，Telegram primary 推一次。

## 功效（預先講明）
- 每日大約 3–8 注（大細盤唔係每場 21:00 都已開盤；11-08 七場得三場有候選）。1,000 注大約要 4–6 個月。
- 1,000 注嘅 ROI CI 大約 ±6pp：真 edge 要 ≥ +6% 左右先有機會 PASS。細過呢個大概判「未過」—— 寧願漏，唔好信錯。
- F250 嘅 STOP 只會喺明顯蝕（大約 −12% 或更差）先觸發。

## 唔通過
記低點樣失敗，唔准喺同一批數據改門檻／改 market／改 side 再判。要再試就重新登記一個新版本（新 `RULE`）。

## 重跑
```bash
python3 docs/experiments/patches/nba_featured/evaluate.py status     # 只顯示已結算注數
python3 docs/experiments/patches/nba_featured/evaluate.py evaluate   # 未夠數會拒絕；已凍結就讀返
```

## 附錄（2026-11-10，產品決定，唔改上面任何揀注或判決規則）
Kelvin：「大細盤精選 我覺得要做 可以取代左現有sgm」，揀 A。由 target date 2026-11-11 起：
- 唔再發 SGM card；精選 card 係 NBA 主 card。覆盤只報精選（中／唔中）。
- ROI 板 NBA 嗰行改計精選紙上盤（`featured_records`，2026-11-11 起），唔再混 SGM。
- 穩膽停損（EXP-20261027-21）唔再檢查，因為 SGM 唔再發佈。
- 引擎照計 B2／SGM、dashboard 照追蹤，只作對照。
- **仍然係紙上盤**：F1000 PASS 之前唔落真錢。

## 附錄 2（2026-11-10 較後，產品決定，唔改任何揀注或判決規則）
Kelvin 撤回上面附錄嘅「停發 SGM」：(1) SGM 每日照發；(2) 大細盤精選 card 排喺 SGM 後面；(3) forward 測試照跑，
ROI 板 SGM 同大細盤精選各一行（`nba`、`nba_featured`）。穩膽停損（EXP-20261027-21）照舊檢查。
撤回發生喺第一個 forward target date（2026-11-11）嘅 21:00 card 之前，所以冇任何一張 card 或者 ROI 紀錄受過舊決定影響。
**仍然係紙上盤**：F1000 PASS 之前唔落真錢。
