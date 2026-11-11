# EXP-20261111-21 協議：「潘頓上仗騎、今仗同場揀咗另一匹」—— 舊季確認＋forward 登記

- **日期**：2026-11-11（寫喺睇任何舊季結果之前；舊季賽果喺寫呢份嘅同時下載緊，未做任何分析）
- **平台**：HKJC
- **提出**：Kelvin 2026-11-11：「上仗潘頓騎，今仗潘頓唔騎，最主要係潘頓」
- **搜索過嘅舊記錄**：EXP-20261027-12（P2「上仗頂級、今仗換落非頂級」，Holm 唔過）、EXP-20261027-13（頂級騎師 overlay 全部 REJECT）、
  EXP-20261018-03（換騎 −1.5）、EXP-20261110-06（上仗弱騎師，REJECT）

## 定義（凍結）

`.agents/skills/hkjc_racing/hkjc_daily_auto/hkjc_purton_rival.py`：一匹馬係 case，當且僅當

1. 佢上仗（賽日之前最近一次香港出賽，同日唔計）由潘頓策騎；
2. 今仗由另一個騎師策騎；
3. 潘頓今仗喺同一場騎緊另一匹馬。

只計有名次嘅出賽（退出／未完成唔計）。資料只係賽果（騎師、名次、最終獨贏賠率），賽前排位表已經知道邊個騎邊匹，冇洩漏。

## 已經睇過嘅數據（揀出呢個分法嘅數據，唔再用嚟判）

賽果庫 2024-09-15 → 2026-11-08，579 匹（定義檔重算 574 匹，差 5 匹係退出馬處理唔同）：

| 量度 | 結果 |
|---|---|
| 上名率 | 23.7%（潘頓揀嗰匹 48.7%） |
| 控制賠率（對全場） | −3.0pp [−6.6, +1.0] |
| 勝出 A/E | 0.767 [0.537, 1.005] |
| 控制模型排名（440 場回放，149 匹） | −4.8pp [−11.4, +2.3] |
| 推廣到頭五騎師（2,276 匹） | 控制賠率 −0.4pp、控制模型 −0.2pp |
| 回放扣 0.25–1.0 原始分（同一批，診斷） | Gold +0.7～+1.1pp、Good −0.2～−0.5pp |

「同場揀咗另一匹」同「只限潘頓」兩個切法係睇完數據先揀，所以上面全部唔算證據。

## 測試一：舊季確認（retro，一次過）

- **數據**：2019-09-01 → 2024-07-31 五季 HKJC 公開賽果頁，`docs/experiments/patches/hkjc_backfill_old_season_results.py`
  存入 `<HK root>/_research_old_season_results/`，**唔寫入賽果庫**（引擎 PIT priors 讀賽果庫，加舊季 = 改 live 輸入）。
  取消／不設投注嘅賽日當冇賽事。
- **只有市場鏡頭**：舊季冇賽前 Logic 可以回放模型。
- **統計量**：case vs 全場其他馬，上名率分層加權差，按最終獨贏賠率分 ≤3／3–6／6–12／12–25／>25；
  另報勝出 A/E。以賽日做單位 bootstrap 2000 次，seed 0。
- **判決**：CI 上界 < 0 → `CONFIRMED_NEGATIVE`（市場系統性高估被潘頓放棄嘅馬）；CI 下界 > 0 → `REVERSED`；
  其他 → `NOT_CONFIRMED`。
- **命令**：`python3 docs/experiments/patches/hkjc_screen_purton_rival.py retro`
- **意思**：CONFIRMED 只答「市場有冇低估呢件事」，**唔等於**模型要扣分 —— 模型冇睇賠率，要另外睇模型鏡頭。

## 測試二：forward（模型鏡頭）

- **窗口**：2026-11-11 起（之前嘅賽日用咗嚟揀分法）。
- **登記**：`hkjc_forward_tracker.FORWARD_TESTS["purton_rival"]`，kind `purton_rival`，**400 匹** case 第一次夠數 Telegram 一次
  （而家每季約 260 匹，預計約 2028 年 3 月）。
- **統計量**：同上，但按現行模型排名每兩名一段分層（`hkjc_eval_harness.py run --since 2026-11-11` 嘅排名）。
- **判決**：模型鏡頭 CI 上界 < 0 → `PASS_SCREEN`；其他 → `REJECT`。
- **命令**：
  ```bash
  H=.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py
  PYTHONDONTWRITEBYTECODE=1 python3 $H run --since 2026-11-11 --out <scratch>/fwd.jsonl
  python3 docs/experiments/patches/hkjc_screen_purton_rival.py forward --model-run <scratch>/fwd.jsonl
  ```
- **PASS_SCREEN 之後**：唯一准開嘅排名 arm 係 case 馬原始分 **−0.5**（而家寫死，唔准事後揀幅度），
  行 `model-regression-gate`（Stage 4 v3 `fixed_rule`，只用 forward 賽日）。上唔上線由 Kelvin 決定。
- **功效**：400 匹只夠捉到約 −5pp 或更大嘅效應；之前見到嘅 −3～−5pp 落喺邊緣。結果係 REJECT 都只係「400 匹判唔到」。

## 唔准做

- 改定義（例如加返「潘頓唔喺呢場」、改做頭三騎師）、改分層、改窗口去救結果。
- 用 2024-09 → 2026-11-10 嗰批數據證明任何嘢。
- 因為 retro CONFIRMED 就直接幫模型加扣分。
