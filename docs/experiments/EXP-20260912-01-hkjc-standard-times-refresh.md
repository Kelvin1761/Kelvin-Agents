# EXP-20260912-01 — HKJC 官方標準時間表刷新

- **日期**：2026-09-12
- **平台**：HKJC
- **假設**：將已過期嘅 HKJC 標準時間／參考段速表更新至官方 2026-08-25 版本，作正確性修正時唔會令 primary KPI 顯著退步。
- **搜索過嘅舊記錄**：冇相關 HKJC 標準時間刷新實驗；另參考 `EXP-20260823-03`（AU L600 標準表，唔同平台／唔共用模型）。
- **改到嘅檔案／組件**：`.agents/scripts/hkjc_standard_times.json`、`.agents/scripts/hkjc_reference_sectionals.json`

## 配置

- **baseline**：`cf98f9580d58e841cc509c46ba5ce5a1f2146171`；官方表生效日 `2025-08-26`，本地抓取日 `2026-04-20`
- **candidate**：HKJC 官方頁於 2026-09-12 抓取；官方表生效日 `2026-08-25`
- **差異**：71 個標準時間鍵；59 個共同鍵改值、加 `沙田_1000_C1`、刪 `沙田_2000_C1`；參考段速同步刷新

## 數據

- **語料**：本地 HKJC archive，有完整 Facts、Logic 同全日賽果嘅 meeting
- **dev 窗**：2026-05-03 至 2026-07-04，162 場
- **terminal 窗**：2026-07-08、2026-07-12、2026-09-06、2026-09-09，38 場（尾 15% 唯一日期，鎖定）
- **樣本**：21 meeting／200 場／2,269 匹；baseline/candidate 同場同馬；sample hash `655b59043c6c9ecddddfaea6468400d267c4671e38873845d60231a45c80827f`
- **重播方法**：由已存 Facts 嘅近仗場地／路程／班次／完成時間，分別用 old/new table 重建 `finish_time_block`，再由同一個 production engine 評分；舊表重建同已存 block 逐匹驗證，0 skip／0 mismatch

## 結果

| 指標 | baseline all | candidate all | dev Δ | terminal Δ / 95% CI |
|---|---:|---:|---:|---:|
| Gold | 13.000% | 13.000% | 0.000pp | 0.000pp [0, 0] |
| Good positional | 22.500% | 22.500% | 0.000pp | 0.000pp [0, 0] |
| Top-3 capture@5 | 62.167% | 62.167% | 0.000pp | 0.000pp [0, 0] |
| NDCG@5 | 52.595% | 52.568% | −0.034pp | 0.000pp [0, 0] |
| Competitive recall@5 | 57.775% | 57.775% | 0.000pp | 0.000pp [0, 0] |

- 200 場中 3 場 top-5 次序／邊界有變；Gold、Good、capture 同 recall 逐場全部不變。
- Stage 4 表現候選判決係 `REJECT / ranking_evidence_too_weak`：呢次冇證實改善，亦唔以表現候選名義上線。
- §7 cohort guardrail：field-size ×4 同 baseline 首選 SP ×5 嘅兩個 primary 都逐場零差，所以冇 cohort 可能出現全負 CI。

## 檢查

- **獨立正確性證據**：官方頁標示新表生效日 `2026-08-25`；舊本地表仍係 `2025-08-26`，即本地資料確實落後一個版本。
- **leakage-audit**：production 使用 PASS——新表喺下一次預測前已公開。歷史 replay 本身有時間穿越（2026-08-25 表回套較早賽事），所以只可用作敏感度／退步檢查，**唔可以用作改善證據**。
- **golden_scoring**：PASS；已鎖 Logic fixture 120/120 一致。表檔只影響下一次 Facts 生成，所以冇重錄 snapshot。
- **data_contract**：PASS；現有 HKJC baseline 對最近 60 場全部欄位合格。表檔唔會改已生成 Logic，故保留原有 150 場 calibration，避免用未出賽嘅 2026-09-13 meeting 無意改窗。
- **退步**：primary 全部零差；dev NDCG@5 −0.034pp，terminal 零差，冇顯著退步。
- **已知限制**：現行 `get_standard_time()` 對 Facts 內中文班次會跌落 C4 fallback；今次只做 table refresh，冇混入班次正規化修正。該修正會另開獨立實驗／ablation。

## 結論

官方標準表已落後一個版本，屬可獨立證明嘅資料正確性問題。200 場敏感度 replay 冇任何 primary 變化，但亦冇表現改善證據；因此按合約 §7 **KEEP 作正確性修正**，唔宣稱預測改善。

**決定**：KEEP（§7 正確性修正；非表現改善）
**commit**：待 release approval

## 重跑

```bash
PYTHONDONTWRITEBYTECODE=1 python3 .agents/scripts/scrape_standard_times.py
PYTHONDONTWRITEBYTECODE=1 WC_DISABLE_HKJC_PROFILE_ENRICH=1 python3 /private/tmp/hkjc_standard_time_gate.py
```
