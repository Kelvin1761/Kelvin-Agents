# EXP-20261030-02 — Tennis 球員 tour 標籤修正（資料正確性修正，唔係模型改善）

- 日期／平台：2026-10-30／Tennis 資料層。
- 問題：`rankings_wta` 每日 hold 19 行（"canonical player identity changed"），`history_lowtier`
  每日喺 KE64 中斷；根源係 `players.tour` 大面積錯標。
- 搜尋舊記錄：EXP-20260826-09（語料／tier 閘）、`player_identity.derived_tour` 註解（2026-08-09／08-27
  兩次因 tour 錯標而收窄 merge guard）、記憶「tennis-identity-merge-had-no-caller」。前兩次修嘅係 merge
  guard，**冇人修寫入路徑**，所以錯標一路累積。
- Baseline code：`c97d4cb6134cb8349cc9bf3c96325a5e106d3dee`。資料：live DB 2026-10-30 10:55 一致
  `.backup`（外置碟）＋ 11:20 唯讀抽出嘅 slim 副本（剔走 `feature_snapshots`／`predictions`／
  `market_predictions` 同非 ranking 嘅 raw body）。**live DB 冇寫過。**

## 成因（三個寫入點）

1. **ESPN**：按 scoreboard 標 tour。合辦賽事嘅女子賽亦出現喺 `atp` scoreboard（一次 history pull 有 20 場重複），
   Swiatek／Zheng 等被標 ATP。每場 competition 自己有 `type.slug`（`womens-singles`）。
2. **TennisExplorer 語料**：`_tour_of` 預設 ATP，名冇 "WTA" 就當男子。男女 ITF 同名（"Bastad ITF"），所以
   **全部女子 ITF** 都標咗 ATP：tennisexplorer 240,146 行歷史有 234,151 行係 ATP。頁面 header 其實有
   `/atp-men/`／`/wta-women/` 連結同 `type-men2`／`type-women2` icon，parser 一直掉咗。
3. `get_or_create_player`：UNKNOWN 標籤會抹走已知 tour；`_ensure_player` 冇 tour 時預設 ATP。

連帶：`_resolve_by_similarity` 用 tour 過濾候選，女子被標 ATP 後，"Stakusic M." 等女子賽果被掛咗去男子
（Marko Stakusic、Lucas Gomez、Cheong-Eui Kim 等 6 個 ranked 男子記錄大部分對手係女子）。

## 修正

- 寫入點：ESPN 用 `type.slug`；TennisExplorer parser 讀 header 標記，冇標記就 UNKNOWN（唔繼承上一個 tournament、
  唔預設 ATP）；`get_or_create_player` 已知 tour 唔再被行標籤覆蓋；`_ensure_player` 預設 UNKNOWN；
  `_identity_agrees` 接受只差空格／連字號嘅名（Ye Xin Ma／Yexin Ma／Ye-Xin Ma）。
- `history_lowtier`：一行 identity conflict 改為 hold 該行、匯入其餘、最後拋 `HistoryIdentityHoldError`
  報 partial。之前 KE64 一行由 2026-10-28 起每日中斷成個 TML 檔，TML 低級別歷史凍結喺 10-27。
- `ingest_wta_stats._resolve_player`：按「唯一真人」（terminal canonical）而唔係「唯一一行」。
- 修復：`tennis_wc.identity.player_tour` + `scripts/repair_player_tours.py`。證據次序：
  authoritative（ranking 行 ≥90% 一致；`wta:`／`uts:`／TML id）→ 對手圖傳播（單打唔會男女對打；
  ≥3 場、≥90% 一致，逐輪同步）。authoritative 內部矛盾只報告唔投票。dry-run 預設、連線唯讀；
  `--apply` 一個 transaction、每個舊值寫入 `player_tour_repairs`；`--revert RUN_ID` 可逆。
- 「錯 merge」重新判斷：brief 列嘅 Hyojoo Jeong→Sunam Jeong、Pankratova→Kalyakina **唔係錯 merge**——
  WTA 官方 id `wta:323403` 喺 2026-09-14 由 "Sunam Jeong" 改名 "Hyojoo Jeong"，`wta:331329` 喺 10-18 由
  "Maria Kalyakina" 改 "Maria Pankratova"。修復將 merge target 改新名、舊名留 alias。只限數字 WTA 官方 id；
  UTS id 見過喺兩個男子之間轉手（uts:45169 Krumich→Rosenkranz），所以唔當改名。de Minaur 嘅 WTA child
  係 Sportsbet "Alex De Minaur" 錯標，唔係錯 merge。KE64 Toby Samuel→Stefan Kozlov 維持 hold。

## Dry run（live DB 唯讀，2026-10-30）

23,486 個 terminal 球員：authoritative 決定 4,880、對手圖 11,173、未能決定 7,433（stored ATP 5,824／
UNKNOWN 1,210／WTA 399，留原值）。authoritative 矛盾 0。改動 6,932 行：ATP→WTA 4,696（authoritative 106、
對手 4,590）、UNKNOWN→ATP／WTA 2,227、WTA→ATP 9（de Minaur Sportsbet 行、Shang Juncheng、Krumich 等，
全部男子）。改名 2。抽樣 30 個 ATP→WTA（對手）全部係女子名或女子雙打組合。
已有 tour 證據嘅球員，對手票與 authoritative 一致 3,585／3,622。

## 量度（同一份資料，只差 code／修復）

| 量度 | 舊 code＋舊資料 | 新 code＋舊資料 | 新 code＋修復後 |
|---|---:|---:|---:|
| WTA ranking holds（重放最新 payload） | 19 | 18 | **0** |
| ATP ranking holds | 7 | 7 | 7 |
| WTA 排名名單連到 serve stats（1,542 名） | 1,431（其中 334 連去 merged 行） | 1,535（0） | **1,540（0）** |
| 舊 code＋修復後資料嘅 serve stats 連結 | — | — | 583 ⚠️ |

勝負模型重放：2026-10-01..29 已結算 Sportsbet 賽事 1,116 場（`assemble_match_feature_snapshot` +
`price_match_snapshot`，配對）：**snapshot 改變 0 場、概率移動 0 場**，LL 0.693171／Brier 0.249000 前後完全一樣。
Snapshot 唔讀 `players.tour`；Elo builder 唔讀 tour，修復亦冇搬動任何歷史行，所以 Elo 不變。
**呢個係正確性修正，唔係模型改善，冇聲稱任何預測增益。**

剩低 7 個 ATP holds 全部係名／id 問題，唔關 tour：Aleksandr／Alexander Shevchenko、Adrian／Gabi Adrian Boitan、
Lalami／Lalami Laaroussi（同一人改寫法）、Krumich→Rosenkranz、Toby Samuel→Kozlov（id 重用，hold 啱）、
Joao Silva 兩個 id 撞同一 canonical。

## 未做／限制

- 已入庫嘅錯標行：`player_match_history.tour` 未改（`canonical_history` 去重鍵含 tour，要另外評估）。
- 6 個 mixed record 男子身上嘅女子賽果未搬走：要逐行判斷身份，會改 Elo，需要預先登記嘅 A/B。
- TennisExplorer 新寫入點對未來 identity 解析嘅效果無法回溯量度（原始 HTML 冇存）；要 forward 觀察
  `mixed_records` 數有冇再增加。
- ⚠️ **次序**：修復一定要喺新 code 上線之後先跑；舊 `_resolve_player` 遇上修復後資料會由 1,431 跌到 583。

## 決定

寫入點修正＋修復工具：**KEEP（正確性修正，§7）**。live DB 修復**未執行**，等用戶批准，並排喺 release 之後。

## 重跑

```bash
PY=/Users/imac/Antigravity-repo/tennis-wong-choi/.venv/bin/python
export PYTHONDONTWRITEBYTECODE=1
cd tennis-wong-choi && PYTHONPATH=src $PY scripts/repair_player_tours.py --report plan.json   # dry run（唯讀）
cd .. && $PY docs/audits/tennis-tour-repair-20261030-measure.py --db before.db --out before.json [--src <舊 code src>]
$PY docs/audits/tennis-tour-repair-20261030-measure.py --compare before.json after.json
```

Artifacts（plan、三份量度、比較）：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-tour-repair-20261030/`。
