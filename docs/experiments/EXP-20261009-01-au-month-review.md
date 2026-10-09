# EXP-20261009-01 AU 一個月表現檢討（儲存咗嘅賽前排名 vs 市場）

- **日期**：2026-10-09
- **平台**：AU
- **假設**：模型表現喺某啲馬場／賽事類型顯著差過（或好過）按馬匹數預期同整體市場差距；
  呢啲差嘅格可以追溯到可修嘅原因。
- **搜索過嘅舊記錄**：EXP-20260905-02（全 miss 場日）、EXP-20260927-02（馬場 override
  REJECT）、EXP-20260928-02/07（Matrix refit／ML hybrid REJECT）、EXP-20260831-15（市場差距
  係正交資訊）、記憶 `au-layoff-signal-discarded`（休息日數懲罰失敗）、
  `au-trial-score-is-accurate-but-unheard`
- **改到嘅檔案／組件**：新 harness `au_window_review.py` + 測試；冇改評分 code

## 配置
- **baseline**：production 當日賽前快照嘅排名（`AU_AUTO_SCORE_V3`，窗口內引擎零 commit）
- **candidate**：冇 —— 呢個係診斷，唔係候選。對照組係收市 SP 排序。

## 數據
- **語料**：`AU_Racing/Archive/` 161 個場次嘅 `_prediction_snapshots/`（逐場揀開跑前最後一個；
  冇開跑時間先退返悉尼 11:00 規則）+ `Race_Results_Reflector.md` + canonical CSV
- **窗口**：2026-09-09 → 2026-10-08；方向驗證：2026-08-10 → 2026-09-08（只有 364 場有快照）
- **樣本**：1,200 場（剔走 37 場賽果唔齊、5 場開跑前冇快照）；快照 = 該場開跑前最後一個（開跑時間由 Sportsbet 賽事頁 cache `data-utime`）

## 結果
| 指標 | 模型 | 市場 SP | 差 [95% CI] |
|---|---|---|---|
| 頭5位AUC | 0.6908 | 0.7773 | |
| Gold | 19.1% | 31.9% | −12.7 [−15.3, −10.1] |
| Good位 | 26.1% | 37.3% | −11.2 [−14.2, −8.2] |
| Pass | 49.2% | 65.7% | −16.6 [−19.5, −13.5] |

### 分層（只列有訊號嘅；全表見 audits 附件）
| Cohort | n | Gold（預期） | 相對市場差距 | 判斷 | 8 月重現？ |
|---|---|---|---|---|---|
| Stakes/Plate/Open | 77 | 11.7%（16.8%） | Gold −10.7 [−21.1,−0.3]、Good −10.9 [−21.3,−1.8] | 特別差 | 冇（n=22） |
| Metro | 208 | 12.5%（18.7%） | −3.8 [−10.0,+2.0] | 邊緣差 | — |
| Maiden | 358 | 22.1%（18.2%） | +0.8 [−4.2,+5.6] | 邊緣好 | — |
| 模型頭四揀：休後 ≥180 日 | 244 匹 | 上名 33.6% vs 其他 46.6% | −13.0 [−19.3,−6.6] | 差 | 冇（n=27，CI 跨零） |
| 初出馬排名 − 市場排名 | 599 匹 | +0.63 名次 | | 被低估 | 方向一致（+0.41） |

州、路程、場地狀況、信心級別、分差、場地預測準唔準、快照後退出：全部同預期冇顯著分別。

## 檢查
- **leakage-audit**：唔適用（冇新特徵）。快照時間已核實喺賽前；`late` 規則場次表現同
  `pre_cutoff` 一樣，冇洩漏跡象。
- **golden_scoring**：冇郁
- **data_contract**：PASS（`stale-baseline` 警告係舊有）
- **退步**：冇（冇改模型）

## 結論
差距平均分佈喺所有 cohort，唔係馬場或者路程問題 —— 同「市場差距係正交資訊」一致。
唯一顯著嘅差格（春季 Stakes 賽）同兩個個體訊號（休後長休馬被高估、初出馬被低估）
都同「模型太信舊績／評分、市場用試閘同休後資訊」呢個機制吻合，但前兩個 8 月冇重現，
**唔可以用今個月調參**。搵到嘅 bug（class_move 錯位一場、今場獎金死咗、「極慢」= 冇證據、
Synthetic 當草地、早更後唔再刷新）詳見 audit。

另外：快照資料夾名 2026-09 中由 UTC 改做本地時間（`+1000`），任何用快照時間做賽前篩選
嘅工具都要讀 offset，唔可以當 UTC。

**決定**：NEEDS MORE TESTING → 跟進：H1／H2 預先登記後 REJECT（EXP-20261009-03）；
class_move 錯位已作 §7 修正（EXP-20261009-02）
**commit**：未 commit

## 重跑
```bash
export PYTHONDONTWRITEBYTECODE=1
python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_window_review.py \
  --since 2026-09-09 --until 2026-10-08 \
  --mapping /Users/imac/wongchoi-scheduler/.agents/skills/au_racing/data/sb_archive_meeting_ids.json \
  --sb-cache /Users/imac/Antigravity-repo/.agents/skills/au_racing/.sportsbet_cache \
  --out-json ds.json --out-md report.md
```
- dataset fingerprint：`b5c73cda32effd0cbb82552bdc70a57268733c426d35c1990e56538fa0e760c3`
- worktree base：`1c77d21f`（origin/main 2026-10-09）
