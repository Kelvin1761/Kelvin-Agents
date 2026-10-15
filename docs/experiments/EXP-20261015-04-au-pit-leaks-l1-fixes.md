# EXP-20261015-04 AU 四個 point-in-time 洩漏（L1 不變性測試發現）—— §7 正確性修正

- **日期**：2026-10-15
- **平台**：AU
- **假設**：唔係改善假設，係正確性修正（評估合約 §7）。四個來源喺**歷史**場次（回放／重抽）會食到 D 之後嘅資訊；修完之後：(a) live（D ≥ 今日）輸出逐位元不變；(b) 歷史場次只用 D 之前已知嘅資訊。
- **搜索過嘅舊記錄**：memory「騎練率有前視」「檔位矩陣洩漏入回測」「Sportsbet form pages leak the race being predicted」「派生嘅 as-of 表唔係 as-of」；L1 測試 `test_au_future_append_invariance.py`（commit 6779d3a3 cherry-pick）。
- **改到嘅檔案／組件**：
  - `au_racing_engine/pit.py`（新）—— 「歷史 = D < 今日（悉尼）」唯一定義；`WC_AU_PIT_TODAY` 只供證明 live 不變用
  - `claw_sportsbet_form.py` —— `pit_runner_stats()`、`write_meeting(pit_mode=)`
  - `sb_people_stats.py` —— `load_as_of(D)`
  - `au_racing_engine/au_draw_bias_calculator.py` —— `collect_races()` / `build_matrix()` / sidecar `au_draw_bias_races.json`（`--index-only`）
  - `au_racing_engine/engine_core.py` —— `_race_date()`、`_rating_known_at_race()`、`_load_draw_bias_matrix_as_of()`
  - `resources/AU_{Jockey,Trainer}_Ratings.csv` 加 `as_of` 欄；`au_build_jt_ratings.py` 重建時蓋今日日期

## 四個修正

| # | 來源 | 原本 | 修法 | live |
|---|---|---|---|---|
| 4 | 表格頁累積統計（Career / Last 10 / Track / Distance / 場地 / 1st-3rd Up / 12 months / J/H / Win% / Place% / Days / Prize / Ave $） | 原封抄入 Formguide／Racecard；只有往績**行**有 `run_date >= D` 閘 | 歷史場次（D < 今日，**或者**頁面已經有 D 當日往績行 = 同日賽後重跑）由已過閘嘅往績行重計；Prize／Ave $ 計唔到寫 `-` | 照用頁面數 |
| 5 | 騎練 `(LY:)` | 用 cache 最新 `ly`，唔理 `fetched_at` | 歷史場次用**嚴格早過 D（悉尼 00:00）**最後一個快照（snapshots JSONL + cache 本身）；冇就 `-`（中性），唔准跌返 current cache | 照用 cache |
| 6 | 檔位矩陣 | 由全份結果 CSV 砌，冇 as-of | calculator 另寫逐場 sidecar；歷史場次由 `Date < D` 嘅場次用**同一個** `build_matrix()` 重砌；冇 sidecar = 空矩陣 | 照用靜態 `au_draw_bias_matrix.json`（**冇重建**，用 `--index-only`） |
| 7 | 騎練 tier 表（`(LY: -)` fallback、`_is_top_*`、`_jockey_rank_value`） | 冇日期 | 加 `as_of` 欄（兩個 CSV 2026-05-16 入 repo，git 記錄；`Paul Snowden` 別名行 2026-09-05 先加，但佢只係 `Peter & Paul Snowden` T1 判斷嘅名字對應，判斷本身 05-16 已存在，所以同樣標 05-16）；歷史場次只用 `as_of < D`，冇日期 = 中性 | 照用 |

calculator 重構驗證：舊 `main()` 同新 `build_matrix(collect_races())` 喺真 CSV 輸出**完全相等**。現行 committed 矩陣（2026-09-01 建）同而家 CSV 重建唔相等 —— 所以今次刻意**唔**重建 live 矩陣，避免順手改 live。

## Live divergence（修正 4 嘅代價）

歷史模式由往績行重計，但 Sportsbet 頁面每匹馬最多 10 行（含試閘），所以累積數係**下限**。對照 live 語料（2026-08-23 起、賽前抽取、261 場次、20,071 匹；頁面數 vs 同一份 Formguide 可見往績行重計）：

| 欄位 | 完全一致 | 平均少計場數 |
|---|---|---|
| Career | 34.7% | 10.63 |
| Track | 68.3% | 1.25 |
| Distance | 40.6% | 3.19 |
| Trk/Dist | 78.6% | 0.51 |
| Good / Soft / Heavy / Synth | 38.7% / 42.9% / 63.8% / 88.0% | 6.06 / 3.27 / 0.94 / 0.31 |
| 1st / 2nd / 3rd Up | 37.6% / 39.6% / 42.7% | 1.74 / 1.57 / 1.37 |
| 12 Month | 59.1% | 1.48 |
| J/H | 83.2% | 0.63 |
| Days（只計正式賽） | 48.8%（99.8% 喺 0 或 −1 日：頁面係 D−1 晚抓，重計以 D 計反而更準） | — |
| Last 10（解碼後名次） | 92.9% | — |

73.4% 匹馬頂住 10 行上限。spell 門檻 63 日係喺同一批 live 頁擬合（Last 10 原字串一致率 49→91 日掃描：63 日最高 86.3%）。**呢啲數唔影響 live**（live 照用頁面數），只描述「重抽歷史場次」同 live 有幾唔同。

## 數據
- **語料**：`corpus_paths.meeting_dirs(AU_RACING)`（唔係 rglob）；乾淨 PIT = 2026-08-05 起
- **樣本**：全語料 3,299 場 / 32,584 匹；乾淨 2,496 場 / 24,085 匹
- **方法**：`au_dump_engine_leaves.py` 三次 —— baseline（fb001d47 = origin/main 33705b78 + L1 測試）、candidate 預設（歷史模式）、candidate `WC_AU_PIT_TODAY=2000-01-01`（強制 live）；全部 `PYTHONDONTWRITEBYTECODE=1`

## 結果

### Live 不變
baseline vs candidate（強制 live）：**3,299 場、32,584 匹，每個 leaf、綜合分、排名逐位元一樣**。

### 引擎重評分（修正 6、7）

| 範圍 | 指標 | baseline | candidate | 差 |
|---|---|---|---|---|
| 乾淨 ≥08-05（2,496 場） | Gold（capture-at-4） | 20.59% | 20.59% | 0 |
| | Good位 | 26.04% | 26.04% | 0 |
| | 頭兩揀任一上名 | 49.56% | 49.56% | 0 |
| | 頭馬 | 25.44% | 25.44% | 0 |
| 舊 <05-17（477 場，非 PIT） | Gold | 16.14% | 16.14% | 0 |
| | 頭兩揀任一上名 | 46.54% | 46.96% | +0.42pp |
| | 頭馬 | 26.21% | 25.79% | −0.42pp |

- 乾淨語料只有 `pace_map_score` 郁（20,067 匹，最大 7.78 分）—— race_shape 權重 0，綜合分 0 匹郁、頭四 0 場郁。
- tier 表喺乾淨語料 0 影響（as_of 05-16 早過全部場次）。05-16 之前嘅舊語料：`preparation_score` 921 匹（±1，練馬師 tier 微調）、`jockey_score` 3 匹、綜合分 924 匹、頭四 37 場變 —— 正正係「用今日 tier 評舊場次」嗰部分。

### 重抽（修正 4、5）
乾淨語料 365 個場次之中 **358 個係賽前抽**（`Meeting_Summary` 丟棄 0 行）—— 本身冇洩漏。**7 個係同日賽後抽**（2026-08-12 ×5、09-09 Randwick-Kensington、10-11 Seymour，共丟棄 308 行），即係 stored Logic 有頁面累積統計洩漏。用 cache 頁重抽其中 5 個（41 場；Devonport／Randwick-Kensington 頁名對唔到）：

| 41 場 | leak（舊行為：頁面數 + current cache） | fixed（新預設） | stored（當日原檔，現行引擎重評） |
|---|---|---|---|
| Gold | 21.95% | 24.39% | 17.07% |
| Good位 | 21.95% | 26.83% | 26.83% |
| 頭兩揀任一上名 | 56.10% | 51.22% | 51.22% |
| 頭馬 | 31.71% | 26.83% | 34.15% |

leak vs fixed 頭四唔同：**32 / 41 場**。41 場冇功效，方向混雜，**唔係**表現證據 —— 只證明呢兩條路喺重抽時真係大幅改變排名。

## 檢查
- **leakage-audit**：修正 4 個 LEAK；L1 測試 4 個 `expectedFailure` 已拆，全部 PASS。新增 `PointInTimeModeTests`：live 照用頁面數／current cache、歷史重計＋D 前快照、冇快照 → `-`、同日賽後頁 → 歷史、tier `as_of` 規則、冇 sidecar → 空矩陣。people case 而家有寫快照檔，baseline LY 係真值（唔係兩邊都中性嘅假綠）。
- **golden_scoring**：冇郁（120 匹）—— 預期：改動全部喺 feature 上游。live 不變由上面全語料強制 live dump 證明。
- **data_contract**：引擎指紋變，已 `--calibrate --since 2026-08-05 --limit 2000` 重建（窗口推前一日，數值只係語料漂移）。
- **模型說明**：已重新生成 AU（差異只係語料窗口漂移）；HKJC 同步漂移唔屬今次範圍，冇 commit。
- **退步**：live 冇。歷史重抽嘅累積統計係下限（見 live divergence 表）—— 呢個係刻意取捨：寧可少計，唔可以計埋未來。

## 結論
四個洩漏都係「live 啱、回放錯」嘅形狀，修法一律用同一個「D < 今日（悉尼）」定義分 live／歷史，live 逐位元不變。乾淨語料嘅回測數字零變化，因為 358/365 個場次本身就係賽前抽、tier 表早過語料、檔位矩陣權重 0。真正受影響嘅係：(1) 7 個同日賽後抽嘅場次（stored 檔仍然有洩漏，未重抽）；(2) 任何將來嘅 backfill／重抽；(3) 任何重新啟用 pace_map 嘅候選。

**決定**：KEEP（§7 正確性修正）
**commit**：見 git log（本分支）

**跟進（未做）**：7 個同日賽後抽場次嘅 stored Formguide／Logic 要用新預設重抽，或者喺語料排除；未做之前，佢哋喺回測入面帶住頁面累積統計洩漏。

## 重跑
```bash
export PYTHONDONTWRITEBYTECODE=1
python3 -m pytest -q .agents/skills/au_racing/au_wong_choi_auto/tests/test_au_future_append_invariance.py
python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_dump_engine_leaves.py --out dump_cand.json
WC_AU_PIT_TODAY=2000-01-01 python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_dump_engine_leaves.py --out dump_live.json
# baseline：git archive fb001d47 解壓到 scratch，同一命令 --out dump_base.json
python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_racing_engine/au_draw_bias_calculator.py --index-only
```
