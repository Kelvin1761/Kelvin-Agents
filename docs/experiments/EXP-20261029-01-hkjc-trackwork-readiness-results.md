# EXP-20261029-01 — HKJC 晨操讀法深度審查 + 重建候選（結果）

- 預先登記：`EXP-20261029-01-hkjc-trackwork-readiness-protocol.md`（commit `be5c16a5`，喺跑任何數之前）
- baseline = main `dd824007`；harness 411 場（2026-04-12 至 10-28）；晨操 JSON 只有 2026-05-03 起 36 個賽日、369 場

## 1. 而家點讀

| 層 | 做咩 |
|---|---|
| 抽取 `extract_trackwork.py` | 21 日窗，每匹馬逐行：快操／試閘／踱步／游水／水中步行機／跑步機；計數、首尾快操時間比趨勢（差 ≥0.5 秒加強、≥0.8 秒放緩）、`race_jockey_involved`、維持分／備戰分／復刻分（全部係手寫加減分） |
| Logic `create_hkjc_logic_skeleton.py` | 將 digest 寫成一句中文（`trackwork_digest`），分類（狀態延續／翻案復刻／初出備戰） |
| 引擎 `_trackwork_trend_score` | 用 regex 由嗰句中文讀返分類同趨勢 → 底分（翻案 66／加強 70／放緩 46.24／其他 60）＋活躍度（快操 ×0.5、試閘 ×1、踱步 ×0.1、游水 ×0.05，上限 8）。外層權重 0.98% |
| 引擎 `_prep_score` | 由句子讀「備戰分」→ 初出馬穩定性分（×0.35） |
| 顯示 | `_trackwork_pattern`、`_trackwork_interpretation`、`_trackwork_timeline`（唔入分） |

完全冇用到：快操**段速本身**（只用首尾總時間）、場地（從化／全天候／草地）、距今日數、上仗之後先開始嘅備戰、
呢匹馬平時嘅操練習慣、試閘嘅組別／對手、配備。

## 2. 數據審查 —— 搵到嘅問題

| # | 問題 | 規模 | 類型 |
|---|---|---|---|
| D1 | 晨操表入面有**「出賽」行**（`1650M (霍宏聲) (5/12)`），抽取層當咗普通記錄 | 3,286 行；1,720 匹馬窗口內有上仗 | §7 |
| D2 | 因 D1，「賽日騎師有參與操練」會因為騎師**喺比賽**策騎過而觸發 | 1,591 個旗標入面 **562 個（35%）**淨係靠出賽行 | §7 |
| D3 | **賽後先抽**嘅檔案包埋**今仗本身**（出賽行連名次）同當朝踱步 → 回放同 live 睇到唔同嘢；今仗出賽行令旗標必中 → 備戰分 +15、復刻分 +12 | 18 個賽日、1,476 行今仗出賽；Logic 入面 1,407／4,401 匹 | §7（point-in-time） |
| D4 | 「馬匹跑步機」行 details 寫「快操／踱步」就被當咗快操／踱步 | 135 課假快操、1,434 課假踱步 | §7 |
| D5 | 2026-05 舊格式：`gallop_times` 係段速同總時間撈埋一齊（`[31.1, 27.0, 58.1, …]`），趨勢比較嘅係第一段段速 vs 最後一課總時間 | 1,676 課快操 | 已由 EXP-20261018-11 嘅 >4 秒守衛擋咗大部分；只影響存檔 |
| D6 | `trial_sectional_signal` 有試閘就係 `strong` —— 常數，唔睇段速，「試閘段速訊號強」永遠係假 | 每匹有試閘嘅馬 | 顯示 |
| D7 | `body_weight_delta_lbs` 永遠 `None`；抽取層 `career_category` 永遠 `status_continuity`（Logic 先改） | 全部 | 死欄位（冇入分） |
| D8 | 2026-05-03 沙田：138 匹有晨操記錄但 Logic 冇 digest 句 → 晨操分當中性 | 1 個賽日 | 存檔 |

D1–D4 喺抽取層修好（`extract_trackwork.py`：只留賽日之前嘅行；`make_digest`／`summarize_trackwork`
唔計出賽行；跑步機按 `type_raw` 判；`create_hkjc_logic_skeleton.hydrate_trackwork_jockey_involvement`
同樣唔睇出賽行）。測試：`hkjc_race_extractor/tests/test_trackwork_race_rows.py`。

## 3. A — §7 修正回放（`fixed_rule`）

Arm `docs/experiments/patches/hkjc_arm_trackwork_pit_clean.py`（同抽取層修正同一規則；另外將 05 月舊格式行由
details 重新 parse，只影響存檔）。原本冇 digest 句嘅馬唔郁（唔好喺呢個 arm 憑空加資訊）。

改咗咩（4,261 匹有 digest 嘅馬）：備戰分 1,762 匹、「賽日騎師有參與操練」921 匹、趨勢 215 匹、快操課數 97 匹、分類 55 匹。

Stage 4 v3 `fixed_rule`（345 場，剔 speed_score 死日）：**33 場排名有郁**。

| 指標 | Δ | 95% CI |
|---|---:|---|
| Gold | 0.00 | [0.00, 0.00] |
| Good | −0.29pp | [−0.88, 0.00]（**一場**：2026-05-09 沙田 R3，第 2／3 選 8↔6 對調） |
| top3_capture@5 | −0.19pp | [−0.48, 0.00] |
| NDCG@5 | +0.0003 | [−0.0013, +0.0020] |
| competitive_recall@5 | −0.12pp | [−0.29, 0.00] |
| 前三平均名次 | 0.0000 | [−0.0078, +0.0069] |

判決器：`REJECT / primary_regression`（Good 點估計負一場）。

§7 預先聲明 cohort（`hkjc_sec7_strata.py`，賽日 bootstrap）：馬群 ×4、首選 SP ×5 —— **冇一個 CI 全負**。
最差兩格：13–14 匹 Good −0.66 [−2.19, 0.00]、首選 SP 4–7 Good −0.80 [−2.70, 0.00]（都係同一場）。

§7 檢查：
1. 錯處獨立可證：「騎師喺比賽策騎過」唔係「騎師有參與操練」；賽後先有嘅行唔係賽前資訊；跑步機唔係快操。✅
   績效數字相反方向我哋都會改。
2. 零顯著退步：primary 冇 CI 全負、九個 cohort 冇 CI 全負。✅
3. Leakage：只係剔走資訊（賽日當日同之後嘅行、比賽行），冇加任何新欄位。✅
4. **呢個冇通過表現閘，唔係一個已證實嘅改善。** 同 EXP-20261018-11 一樣：晨操權重 1%，修正影響細過噪音。

上線位置係**抽取層**（之後抽嘅晨操檔），存檔 Logic 唔重建；評分引擎冇改，golden 不變。

## 4. B — 新訊號篩選（預先登記六個，Holm）

`docs/experiments/patches/hkjc_screen_trackwork_readiness.py tw_base.jsonl`；344 場（35 個賽日），
fit < 2026-09-09（209 場）、測 135 場；剔初出馬。

| 訊號 | 覆蓋 | OOS ΔLL | 95% CI | Holm p | 場內 AUC |
|---|---:|---:|---|---:|---:|
| `trial_any` 近 21 日有試閘 | 100% | −0.0005 | [−0.0060, +0.0048] | 1.000 | 0.5012 |
| `days_since_work` 距最後一課快操／試閘 | 100% | −0.0039 | [−0.0083, +0.0002] | 1.000 | 0.4972 |
| `post_race_load` 上仗後每 7 日負荷 | 100% | −0.0043 | [−0.0107, +0.0023] | 1.000 | 0.5091 |
| `work_speed_z` 最近快操末段 vs 同日同場地 | 95% | +0.0004 | [−0.0005, +0.0012] | 1.000 | 0.4983 |
| `habit_dev` 課數 − 呢匹馬平時 | 100% | −0.0025 | [−0.0109, +0.0056] | 1.000 | 0.4989 |
| `jockey_work` 騎師真係有操（剔出賽） | 100% | −0.0005 | [−0.0014, +0.0005] | 1.000 | 0.5133 |

Cohort（實際上名 vs 模型預期）：有試閘 +1.0pp（n 1,597）；最近快操 z ≤ −1（操得慢）**+2.1pp**、z ≥ +1（操得快）
**−0.9pp**；課數低過平時 ≤ −2 **−4.3pp**（n 307）；騎師真係有操 +0.5pp。

**判決：B 全部 `UNRESOLVABLE（功效不足）`。** 冇一個 CI 下界 > 0，Holm 後全部 1.0；場內 AUC 全部 0.497–0.513，
即係單獨睇都同擲毫差唔多。預先登記規定冇一個過就唔寫 arm、唔改模型。

讀法（唔係結論）：
- 「操得快嘅馬跑輸預期、操得慢嘅跑贏」同 EXP-20261010-11「轉快 −1.2pp、轉慢 +1.4pp」方向一致 ——
  兩次獨立量度都見到，但兩次都過唔到 CI。如果係真，意思係現行「加強 +10／放緩 −13.76」方向可能反咗；
  但 EXP-11 將佢中性化已經 REJECT（Good −0.70pp）。冇足夠證據郁。
- 「課數低過平時」−4.3pp 係最大嘅 cohort 差距，但 OOS ΔLL 係負 —— cohort 差距唔等於可落分收益。

## 5. 結論

1. **而家嘅晨操讀法基本上冇讀到「準備度」。** 佢讀嘅係首尾兩課快操總時間（唔同路程都比）同課數，
   加一堆手寫加減分。場內 AUC 0.4984（EXP-11）；剷走成個 leaf 零變化（EXP-20261019-04）。
2. **有四個 §7 錯（D1–D4）**，最大嗰個係比賽行冒充操練：35% 「賽日騎師有參與操練」係假、
   18 個賽日嘅存檔包埋今仗本身。已喺抽取層修正，作為正確性修正上線，**唔係已證實改善**。
3. **六個新讀法（Kelvin 提嘅 hidden gems 方向：試閘、距最後一課、上仗後負荷、按場地調整嘅快操速度、
   同馬匹平時習慣比、騎師真係有操）全部 `UNRESOLVABLE`。** 36 個賽日唔夠功效；場內 AUC 全部 0.50 左右，
   即係就算有訊號都好細。冇改模型。
4. Forward：`trackwork_rescreen` 改為指向本實驗，夠 60 個賽日原封重跑 `hkjc_screen_trackwork_readiness.py`
   （唔准加特徵、換窗口）。
5. 方向一致但未過 CI 嘅觀察：兩次獨立篩選都見到「操得快／轉快 → 跑輸預期」。如果 60 個賽日之後仍然係咁，
   值得預先登記一個「加強唔加分」arm；而家唔做。

**唔建議做嘅**：重寫維持分／備戰分／復刻分嘅手寫加減分 —— 呢啲只入初出馬穩定性同顯示，
冇證據顯示任何一個組件有料，重寫等於喺噪音上調參。

## 重跑

```bash
S=<scratch>
PYTHONDONTWRITEBYTECODE=1 python3 .agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py run --dump-matrix --out $S/tw_base.jsonl
PYTHONDONTWRITEBYTECODE=1 python3 .agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py run --dump-matrix \
  --arm docs/experiments/patches/hkjc_arm_trackwork_pit_clean.py --out $S/tw_clean.jsonl
python3 .agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py compare $S/tw_base.jsonl $S/tw_clean.jsonl \
  --stage4 fixed_rule --leakage-audit-passed
python3 docs/experiments/patches/hkjc_sec7_strata.py $S/tw_base.jsonl $S/tw_clean.jsonl
PYTHONDONTWRITEBYTECODE=1 python3 docs/experiments/patches/hkjc_screen_trackwork_readiness.py $S/tw_base.jsonl
```
