# EXP-20261009-01 — Tennis：Elo 骨幹（遲一場修正 + 大語料重新擬合）

- **日期**：2026-10-09（預先登記喺跑任何比較之前寫）
- **平台**：Tennis（tennis-wong-choi，match-winner）
- **Base commit**：origin/main `1c77d21f`
- **Harness**：`tennis-wong-choi/scripts/tune_elo_backbone.py`（唯讀；語料先 `extract` 去 scratchpad）
- **語料**：`player_match_history`，`ELO_PROVIDERS`，`won = 1`，2008-01 → 2026-10
- **判決尺**：`.agents/skills/shared_wong_choi/resources/evaluation_rulers/tennis-v1.json`
  （bootstrap by match，4,000 次，seed 20260826）

## 背景

2026-10-09 乾淨賽前量度：match-winner 模型對去水市場 ΔLL **+0.117**（最近 30 日，n=1,147），
比 8 月 +0.082 更差。管線審計搵到：

1. **Elo 遲一場（真 bug）。** `elo_builder` 喺 `player_elo_history` 記**賽前** rating
   並以比賽日期做 stamp；`rating_as_of` 讀「嚴格早過今日」最新嗰行 = **上一場之前**
   嘅 rating。今日 R1 贏咗，聽日 R2 定價睇唔到；只得一場往績嘅球員永遠 1500。
   實例：player 47 打完 10-07 係 1768.4，10-09 嘅預測讀 1765.2。
2. `player_elo_history` 用 `INSERT OR IGNORE`，重建永遠唔覆蓋舊行 —— 表入面係
   幾次 build 嘅混合（player 47：09-02 `matches_played` 294 > 09-03 嘅 293）。
3. 模型分辨力弱而唔係太平：elo-ok 預測 outcome~model logit 斜率 0.781（<1）。
   溫度校準救唔到（同 8 月 Platt REJECT 一致）。

## 已 REJECT／唔重做

clay nudge 全關（洩漏 harness）、Platt、shrink k=0.65、ITF Elo、跨盤套利、
交易所價、fitted hold、surface one-hot。

## 預先登記

**Fold（按年，walk-forward，Elo 只用嗰日之前嘅賽果）：**
dev = 2019–2021、2022–2023；dev 確認 = 2024–2025；2026 獨立報；
live 賽前預測（2026-08-28 起，對市場）= holdout，**只做最後確認，唔准用嚟揀參數**。

**評分群體：** 兩位球員都有之前日期嘅往績（= 生產會定價嘅群體），所有候選同一批場。

**判決（logloss，Brier 做 guardrail）：**
- KEEP 候選：兩個 dev fold **同** dev 確認 fold 嘅 ΔLL 95% CI 全部 < 0，Brier 唔變差，
  而且 level 分層（tour／challenger／itf）冇一層顯著變差
- 任何一個 fold CI 跨零 → NEEDS MORE TESTING；任何一個 fold 顯著變差 → REJECT
- 唔准換指標、換 fold、換群體去救候選

**候選（逐個獨立量，baseline = 上一個已 KEEP 嘅版本）：**

| # | 候選 | 性質 |
|---|---|---|
| C0 | `fixed`：讀當日開賽前 rating（修遲一場） | 正確性修正，但一樣要量 |
| C1 | K 曲線 base／offset／exponent 重新擬合（只喺 dev fold 搜） | 參數 |
| C2 | 場地混合權重 `w_surface`（全局） | 參數 |
| C3 | 長休回歸均值（`layoff_decay_per_30d`） | 新機制 |

C1–C3 只喺 dev fold 揀值，揀完一次過喺 dev 確認 fold 驗；組合要做 ablation。
勝負幅度（MoV）冇 games 欄位，今次唔做；新球員排名播種留待之後。

**上線方式（如果有 KEEP）：** 先 shadow，唔覆蓋 `player_elo_history`；
live holdout 對市場量到之前唔改生產定價。

**誠實預期：** 最可能嘅結果係同市場差距收窄，而唔係贏過 7.9% 抽水。

## 結果

**一句：** 修遲一場（C0）同場地權重 0.35（C2）喺 2019–2025 歷史上過晒預先登記嘅閘，
合共 ΔLL −0.0052；但模型對市場嘅差距係 +0.09 至 +0.12，**骨幹最多收窄大約 5%，
唔會令網球變成有利可圖**。K 曲線（C1）NEEDS MORE TESTING，長休回歸（C3）REJECT。

### Harness 驗證

`verify`：生產參數重行一次，19,416 個球員最終 rating **100% 同 `players.overall_elo`
一致**（< 0.01）。評分群體 172,690 場（兩位球員都有之前日期）。

### 各候選（ΔLL = 候選 − baseline，負數 = 好咗；bootstrap 4,000 次，seed 20260826）

| 候選 | dev 2019–21 | dev 2022–23 | 確認 2024–25 | 判決 |
|---|---|---|---|---|
| C0 `fixed`（修遲一場） vs lag | −0.0078 [−0.0095, −0.0061] | −0.0044 [−0.0053, −0.0035] | −0.0035 [−0.0043, −0.0027] | **KEEP** |
| D1 去跨來源重複 vs lag | +0.0000 | −0.0000 | +0.0000 | 2019–25 冇重複；只得 2026 可判 → NEEDS MORE TESTING |
| C1 K（160/10/0.4，dev 揀）vs fixed | −0.0008 [−0.0013, −0.0002] | −0.0005 [−0.0010, −0.0000] | −0.0000 [−0.0005, +0.0004] | **NEEDS MORE TESTING**（確認 fold 跨零；2026 tour 顯著差 +0.0014） |
| C2 `w_surface` 0.35（dev 揀）vs fixed | −0.0007 [−0.0014, −0.0000] | −0.0019 [−0.0026, −0.0013] | −0.0017 [−0.0023, −0.0010] | **KEEP** |
| C3 長休回歸（12 個設定） | 全部 +0.0001 至 +0.0031 | | | **REJECT** |

C2 喺 dev 嘅掃描：w=0.00 −0.0001、0.20 −0.0013、**0.35 −0.0015**、0.50 −0.0010、
0.65 0、0.80 +0.0017、1.00 +0.0048。草地改善最大（確認 fold −0.0079）。

### Ablation（確認 fold 2024–25，vs 生產 lag）

| | ΔLL |
|---|---|
| 只 C0 | −0.0035 |
| 只 C2 | −0.0019 [−0.0025, −0.0012] |
| C0 + C2 | **−0.0052 [−0.0062, −0.0042]** |

兩樣各自有邊際貢獻，大致可加。tour 層三個 fold 都係同方向但確認 fold CI 跨零
（n=3,113）。

### Live holdout（2026-08-28 起賽前預測，對市場）

- **C0 做唔到忠實 replay。** 用今日語料重建生產當時嘅 overall-Elo component，
  只有 **47.9%** 對得返（< 0.01）。生產嘅 as-of Elo 唔可以由今日數據重現：
  (a) TennisMyLife／Sackmann 用**賽事開始日**做日期而且遲到入庫，會改寫過去嘅 as-of 值；
  (b) `player_elo_history` 用 `INSERT OR IGNORE`，舊 build 嘅行永遠唔會被覆蓋。
  所以 C0 嘅 live 確認只能靠 shadow 向前量。
- **C2 用存咗嘅 component 機率重新混合（忠實）：**

| 群體 | n | 存咗 LL | C2 LL | 市場 LL | Δ | 95% CI |
|---|---|---|---|---|---|---|
| 全部 | 1,086 | 0.6857 | 0.6855 | 0.5674 | −0.0003 | [−0.0022, +0.0017] |
| 可落注 | 459 | 0.6511 | 0.6504 | 0.5653 | −0.0006 | [−0.0051, +0.0039] |
| tour | 307 | 0.6466 | 0.6456 | 0.5497 | −0.0009 | [−0.0079, +0.0056] |

Challenger／ITF 完全唔郁：場地缺失時場地 component 等於整體 component，重新混合係 no-op。
**live 量唔到分別（冇 power），唔係反證。**

### 2026 fold 唔可信（記低，唔好用）

2026 混咗「賽事開始日」（Sackmann／TML）同「實際比賽日」（TennisExplorer）兩種日期。
`fixed` 喺星期四讀數會讀到同賽事星期五、六嘅 TML 結果（都打咗星期一日期）—— 前視。
所以 2026 fold 入面 C0 嘅數字、ITF +0.0026 嘅反常，都唔可以當證據。dev／確認 fold
只有 Sackmann／TML 一種日期，冇呢個問題。

### 另外搵到、未修嘅缺陷

1. **跨來源重複**：2026 年 7,078 對同一場比賽俾兩個來源各記一次（同一贏家 99%），
   生產 Elo 更新兩次。實測影響細（2026 整體 −0.0007 至 −0.0010）。
2. **ITF 模型差過擲毫**：live ITF／UTR logloss 0.707 > 0.693。唔落注（tier 閘擋住），
   但佢佔每日分析大半。
3. **Challenger 場地 100% 缺失**（9 月起 207 場有 177 場所有來源都冇場地）。

### 結論同下一步

- 歷史上 C0 + C2 係真改善，值得以 **shadow** 方式上線（唔覆蓋 `player_elo_history`），
  同時要先修 as-of 表可重現性（stamp 用賽後 rating、重建前清表），否則 live 永遠
  replay 唔到。
- **但佢唔會改變落注結論。** 可落注群體模型 LL 0.651 vs 市場 0.565；骨幹改善 0.005
  只係差距嘅大約 5%。要追到市場，單靠歷史賽果嘅 Elo 做唔到。
- 唯一實際可行、而且歷史上有人用嚟打贏軟莊嘅方法係「銳價參考」（交易所／Pinnacle
  價做公平機率），但嗰個需要新數據源同方法論改動，要 Kelvin 決定。

### Shadow 上線（2026-10-09，第二個 release）

- `player_elo_history_v2`：記**賽後** rating（同日最後一場為準），每次重建先清表；
  `elo_history.start_of_day_rating()` 讀「嚴格早過今日」= 當日開賽前。生產表一個字都唔郁。
- 寫入包喺 savepoint 入面：v2 出錯只會跳過 shadow，唔會令生產 Elo 唔更新（有測試）。
- `feature_builder` 加 `snapshot["shadow_backbone"]`（純數字，唔係 datapoint，唔郁
  data quality／warning／閘）；`probability_model` 輸出 `model["shadow"]`
  = v2 rating + `w_surface` 0.35 + **同一個** nudge，版本 `elo-v2-start-of-day.surface-0.35`。
  生產機率有冇 shadow 都一模一樣（有測試）。
- 生產 DB 副本端到端：重建寫 539,604 行 v2；10-09 嘅 40 場入面 28 場有 shadow
  （其餘球員未有往績，同生產一樣唔夠資格）。重建時間 17s → 22–27s。
- **量度：** `tune_elo_backbone.py shadow-report --since <上線日>` —— 同一刻、同一份輸入
  計出嘅生產 vs shadow vs 市場，冇 replay 問題。跟 tennis-v1：每個 family ≥600 場
  加 power，CI 唔准跨零先講得改善。

### 重現

```bash
cd tennis-wong-choi
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python scripts/tune_elo_backbone.py extract --out /tmp/elo_corpus.db
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python scripts/tune_elo_backbone.py verify  --cache /tmp/elo_corpus.db
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python scripts/tune_elo_backbone.py compare --cache /tmp/elo_corpus.db --baseline lag --candidate "fixed,w_surface=0.35" --by level
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python scripts/tune_elo_backbone.py holdout --cache /tmp/elo_corpus.db --candidate "lag,w_surface=0.35" --stored-components
```

語料 extract 時間：2026-10-09 18:30 AEDT（190,833 winner rows，24,103 players）。
