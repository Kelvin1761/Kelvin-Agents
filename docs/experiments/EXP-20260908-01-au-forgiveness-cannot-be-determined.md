# EXP-20260908-01 「寬恕認定」判唔到 —— 推導出嚟嘅標籤方向全部相反

- **日期**：2026-09-08
- **平台**：AU
- **假設**：`寬恕認定` 欄可以由走位軌跡確定性推導，取代硬寫死嘅 `[需判定]`。
  **證伪。** 三個推導規則對下仗表現嘅方向**全部同「寬恕」相反**。
- **搜索過嘅舊記錄**：EXP-20260907-02/03/04、memory
  `au-facts-columns-constant-or-empty`、`au-late-fade-is-redundant-with-form`、
  `au-run-style-single-source-and-rejected`、`au-settle-position-accurate-covered-orthogonal-still-fails`
- **改到嘅檔案**：`.agents/scripts/inject_fact_anchors.py`（placeholder）、
  `au_racing_engine/engine_core.py`（剷 `unresolved_forgiveness`）、
  `tests/test_gear_change_display.py`
- **harness**：`docs/experiments/patches/au_forgiveness_derivation_test.py`

## 背景：一個講咗成年都冇人判嘅「待判定」
`寬恕認定` 喺 **73,452 行入面 100% 都係 `[需判定]`** —— 因為 writer 個 f-string
硬寫死。呢個係 LLM 年代嘅 placeholder（`generate_skeleton.py` 仲留住
`[FILL: 基準/寬恕/不可饒恕/-]`），AU 轉全 Python 之後冇人接手。

後果：`_confidence_score` 嗰個「條件式」`-1` **每匹馬都中**，變咗常數。

## 試過真係判
`跑位軌跡` 覆蓋得（正式賽 53,213 行）：完整 `S→8th→4th→F` **80.0%**、
部分 15.4%、只有完成名次 2.8%。所以推導係做得到嘅。三條規則：

| 標籤 | 條件 |
|---|---|
| 尾段執位 | 完成 ≥4 名，但尾 400m 執位 ≥3 個位 |
| 全程守後 | ≥8 匹、落飛喺尾四分一、完成 ≥4 名、全程冇改善 |
| 搶前消耗 | 落飛頭兩位，尾 400m 失位 ≥4 個 |

**驗證**：被寬恕嘅馬，下仗應該跑贏佢上仗名次所暗示嘅水平。
7,658 個「上仗大敗（名次 ≥4）」樣本，今仗入位率按當場派彩位數／馬匹數校正：

| 上仗標籤 | n | 今仗超額 |
|---|---:|---:|
| （無寬恕） | 7,233 | +0.4pp ±1.1 |
| 尾段執位 | 176 | −2.3pp ±6.4 |
| **全程守後** | 126 | **−11.1pp ±6.9** |
| 搶前消耗 | 122 | −6.8pp ±7.3 |

**三個都係負。** 「全程守後」顯著。即係我標「可寬恕」嗰批下仗跑得**更差** ——
走位形態量緊嘅係**能力**唔係**運氣**，而能力 `form_score` 已經捉咗
（同 `au-late-fade-is-redundant-with-form` 一致）。

## 點解判唔到
真正嘅寬恕證據（受阻、被夾、大外無遮擋、慢步速）住喺 **stewards / notes**，
而嗰三個欄實測 **21,127 行 0.0% 有內容**（EXP-20260907-02）。
**唔係我哋唔判，係冇嘢可判。**

## 改咗啲咩
1. Writer：`[需判定]` → **`[-]`**（＝「冇寬恕」，唔再假裝有嘢待判）。
   ⚠️ 一定要 `[-]` 唔可以 `-`：`_forgiveness_count()` 嘅排除集係
   `{"[-]", "[需判定]"}`，寫裸 `-` 會令**每一場**都算有寬恕，反手㨂着
   `sectional_score` 嗰個 **7.46 分** bonus。已加 test 釘死。
2. `_confidence_score` 剷走 `unresolved_forgiveness -1`（而家永遠 0）。
   **每個顯示嘅信心分 +1** —— 常數偏移，唔改相對次序。

## 順帶：`走位消耗` 又一條常數欄
73,452 行 **100% 都係 `中低`**。今日／琴日累計五條常數或空欄：
`早段步速`(0%)、`L600/RT`(0%)、`備註`(常數)、`寬恕認定`(常數)、`走位消耗`(常數)。

## 量度陷阱（我今次又中一次）
第一次掃 Facts 表撈埋咗**賽績線表**嘅行（出現 `✅ 強組`、`對手後續成績`），
行數 101,336 vs 真正 73,452。**表頭比對唔夠 —— 要同時校驗欄數，而且遇到
非表格行就重設 header。** 同 `grouping-key-collisions-fake-signal` 同一族。

## 檢查
- **leakage-audit**：PASS —— 驗證用「上仗 → 今仗」，方向正確，冇用今仗資料造標籤
- **golden_scoring**：AU **120/120 一致**
- **run_tests**：15 個 suite 全綠（新增 3 個測試）
- **退步**：冇

## 結論
1. **寬恕判唔到，唔係差個公式，係差個來源。** 唯一有覆蓋嘅走位證據量緊能力，
   而且方向同寬恕相反。
2. 已經停止寫一個永遠唔會被判嘅 `[需判定]`，同埋剷走佢造成嘅常數罰分。
3. 如果將來真係要做寬恕：**前提係攞到 stewards report**（Racing Australia
   有公開 stewards report，但唔喺 Sportsbet 頁）。冇嗰個來源就唔好再試推導。
