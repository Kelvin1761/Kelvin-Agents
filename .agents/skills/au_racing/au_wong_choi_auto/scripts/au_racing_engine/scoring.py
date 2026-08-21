#!/usr/bin/env python3
"""AU Wong Choi Auto scoring primitives."""
from __future__ import annotations
import re

FEATURE_KEYS = (
    "form_score", "trial_score", "sectional_score", "pace_map_score",
    "jockey_score", "trainer_score", "jockey_horse_fit_score", "class_score",
    "rating_score", "weight_score", "distance_score", "track_score",
    "formline_score", "consistency_score", "performance_quality_score",
    "health_score", "confidence_score", "pace_figure_score",
)
ABILITY_FEATURE_KEYS = (
    "form_score", "performance_quality_score", "pace_figure_score",
    "trial_score", "pace_map_score", "jockey_score", "trainer_score",
    "jockey_horse_fit_score", "rating_score", "track_score",
)
REPORT_ONLY_FEATURE_KEYS = (
    "sectional_score", "class_score", "weight_score", "distance_score",
    "formline_score", "consistency_score", "health_score", "confidence_score",
)

# Legacy archive recovery only.  Old Logic files predate the complete
# Sportsbet margin/prize/starter transport and therefore copied consistency
# into Performance Quality.  A strictly pre-race Sportsbet sidecar can recover
# that evidence, but it is a secondary reconstruction rather than the original
# captured Facts.  The 10% reliability blend was positive in 4/5 development
# date folds and the untouched terminal Top-5 AUC (+0.00480, CI wholly > 0),
# while improving both audited failure cohorts.  Primary/live PQ is untouched.
SPORTSBET_PQ_RECOVERY_ALPHA = 0.10

# pace_figure = legacy key for field-relative L600-vs-benchmark context. Racenet
# can contain runner timing; Sportsbet `Sectionals 600m` is race-level and must
# not be described as an individual split. Neutral 60 where PF
# data absent → rank-neutral on no-PF races.
# 2026-07-03 段速 restructure ("swap"): the MEASURED pace figure is now the primary
# 段速 signal (0.143) and the old text-PI sectional dimension is demoted to 0.045 —
# it is near-noise (AUC 0.528 ceiling) but its "has timing data" floor still carries
# a mild winner signal, so it keeps a small weight rather than zero. Validated on
# TWO independent PF windows (05-22→06-13: GGP 89→91; 06-19→07-01 OOS: GGP 29→38)
# AND the full 687-race archive (gold 33→37, pass 285→297, champ +0.9pp, winT3
# +2.0pp, box4 +0.2pp; good −1 within noise). Direct stability-weight cuts were
# tested the same day and LOSE window A — the gain is from the 段速 restructure,
# not from de-weighting stability. Weights sum to exactly 1.0 (normalised from the
# tested 1.0475-sum config; ranking-identical, keeps grade thresholds honest).
# Rollback: pace_figure 0.05 config {"stability":0.3135,"sectional":0.09975,
# "race_shape":0.2223,"jockey_trainer":0.2033,"class_weight":0.0475,
# "track":0.06365,"form_line":0.000,"pace_figure":0.050}.
# 2026-07-10: sectional(0.04535)+pace_figure(0.14296) 合併為 pace_perf(0.18831)，
# 內部 leaf 權重精確折算 → 排名逐匹一致（見 matrix_mapper 註釋）。
# 2026-07-11: track_score 去重 —— 原本 race_shape 內含 30% track_score（有效
# track 影響 0.06367 + track 維度 0.06076 = 0.12443；draw 影響 0.21222×0.70=0.14855）。
# 拆乾淨：race_shape 變純 draw @0.14855、track 收晒全部 @0.12443。兩者相加同舊
# (0.21222+0.06076) 一樣 → 逐匹 rank-identical。其餘維度不變。
# 2026-08-01 維度尺正規化配套權重（見 matrix_mapper.MATRIX_DISPLAY_GAINS）。
# 排名只食 weight × gain × deviation，所以維度顯示尺一 stretch，權重就必須同步
# 除返個 gain，否則等於偷偷 re-weight。呢組數 = 舊權重 ÷ gain，再歸一化到總和 1。
# 每個維度嘅有效影響力比率都係同一個常數 1.4225（唔係「差唔多」，係逐個一模一樣）
# → 場內排名基本相同（710 場實測 625 場逐匹一致，餘下 85 場係 gain>1 撞 0/100
# clip 造成，指標影響淨計輕微正面：gold ＝、pass ＝、champ +0.56、mrr +0.38、
# ndcg +0.18、good_pos +0.28、winT3 −0.14、t3prec −0.09），ability spread 放大 1.4225 倍。
# 舊值（gain 全部 = 1 時使用）：
#   stability 0.29928 / pace_perf 0.18831 / race_shape 0.14855
#   jockey_trainer 0.19408 / class_weight 0.04535 / track 0.12443 / form_line 0.0
# 順帶好處：正規化之後七個維度 spread 拉平，所以呢組權重第一次真正等於「影響力
# 佔比」。舊組唔係 —— 實測 race_shape 名義佔 15.1% 權重但只出 4.9% 影響力
# （ratio 0.32），stability 名義 29.9% 卻出 48%。
#
# ── 2026-08-01（較後）：真正嘅重新配權 ────────────────────────────────────────
# ⚠️ 上面嗰次正規化係**刻意 rank-neutral** 嘅（weight × gain 保持常數 1.4225×）。
# 呢一次唔係 —— 呢次係一次經 A/B 驗證、**刻意改變排名**嘅重新配權。
#
# 點解而家先做：0.43664 嗰組係喺 jockey/trainer 兩個 leaf 被重寫**之前** fit 嘅。
# 統一上名率 + 人馬配搭「無紀錄」點位落地之後，jockey_trainer 維度嘅原生 SD
# 由 3.20 闊到 4.09（+28%），舊權重係 fit 落一個已經唔存在嘅分佈。
#
# 做法（`au_matrix_refit.py`，配 `au_dump_engine_leaves.py` 出 dataset）：ability 對 leaf 分係線性嘅，所以一份評好分嘅
# dataset 就可以離線評估任何權重組合 —— 先用 `verify` 證明 replica 同真引擎逐匹
# 一致（7,547 匹 max|Δ| 0.0082，純 2dp 捨入），先至信搜索結果。3,000 條隨機權重
# 向量，dev 606 場揀，dev 內部 5 個時間 fold 做閘（要過 4/5），未碰過嘅 107 場
# holdout 完全唔參與揀參數。
#
# **取閘後候選嘅逐維度中位數（共識），唔取 argmax。** argmax 係教科書級 overfit：
# 實測 argmax 喺 dev 靚好多（good_pos +3.80、winT3 +4.13）但喺 holdout 爆炸
# （pass_any1 −5.61、good_any2 −4.67、t3prec −3.74）。共識就冇呢個問題。
#
# 呢組數係四個 random seed 各自共識之後再取中位數。收斂度極高 —— 四個 seed、
# 三個唔同目標函數（均衡／只計上名／只計贏馬）、PF on 同 off 兩個 footing，
# 加上另一條工作線一套完全獨立嘅實作，**八次搜索冇一次例外**都指向同一個方向：
# stability ↓、pace_perf ↓、jockey_trainer ↑、class_weight ↑、race_shape ↑、track 持平。
#
# 實測（713 場全樣本，vs 舊權重）：**11 個指標全部改善** —— gold +0.42、
# good_pos +1.54、good_any2 +0.14、pass_any1 +1.68、champ +0.98、winT3 +2.52、
# t3prec +0.75、mrr +1.22、blowout −1.40、compet +1.82、ndcg5 +1.32。
# 未碰過嘅 holdout：winT3 +2.80、ndcg5 +1.85、champ +1.87、mrr +1.81、compet +0.93、
# good_any2 +0.93，倒退淨係 pass_any1 −0.93 同 blowout +0.93（各自 = 1 場）。
# 舊值（2026-08-01 正規化配套，rank-neutral 嗰組）：
#   stability 0.43664 / pace_perf 0.26149 / race_shape 0.05136
#   jockey_trainer 0.11055 / class_weight 0.02347 / track 0.11650 / form_line 0.0
# 2026-08-03：Sportsbet 語料重新配權（604 場 / 6,228 匹，2026-01-24→08-01）。
# 換源之後 leaf 分佈真係變咗（`pace_figure` 覆蓋 50%→96%、`sectional` 98%→34%），
# 舊權重係喺舊分佈上 fit 嘅。直接證據：補完騎練 LY token 之後 `jockey_score`
# 場內 AUC 0.565→0.589，但排名反而跌（首選=頭馬 141→134）—— leaf 好咗，配權冇跟住。
# 取 975 條過閘候選嘅逐維度中位數（共識），**唔取 argmax**：argmax 喺 holdout
# gold −3.30 / champ −5.49，又一次重現教科書 overfit。
# walkforward 5/5 窗口全勝；全樣本 604 場 11/11 指標改善（winT3 +3.97、
# any2 +2.81、t3prec +1.55、gold +1.32）。
# 2026-08-05：段速分退出 pace_perf，pace_perf gain 1.0244 → 0.9909，所以權重要
# 除返個 gain 比例，令排名影響力保持不變（等價換算，唔係偷偷 re-weight）。
# ⚠️ 呢組係「等價權重」而唔係重 fit 出嚟嘅最優 —— 重 fit 係獨立議題（對照組
# 顯示 re-fit 本身就贏 10/1，同移除段速分無關），要自己過 walk-forward。
# Rollback: {"stability":0.38232,"pace_perf":0.14407,"race_shape":0.11502,
#            "jockey_trainer":0.19149,"class_weight":0.07337,"track":0.09373,"form_line":0.000}
# 2026-08-08：修正 runtime audit 漏讀 scheduler `Archive/` 之後，用完整 805 場／
# 8,249 匹 current-runtime 語料重新 fit。目標以 Gold、Good位、新 Pass（Top 3
# 任兩匹上名）為核心，但仍守 champion / winner@3 / NDCG。每個 expanding
# walk-forward window 只用之前日期 fit，5/5 未見未來窗口 objective 全勝；跨窗口
# 共識喺完整日期 terminal holdout 嘅頭 5 配對 AUC +0.0134，95% paired-bootstrap
# CI [+0.0025,+0.0244]。全樣本 Gold +1.49pp、Good +3.23pp、Pass +2.61pp。
#
# 方向喺每個訓練窗一致：stability / pace / track 減少，jockey-trainer / class /
# race-shape 增加。採用五個 expanding-window 共識嘅逐維度中位數，唔用任何一次
# dev argmax。Rollback：
#   {"stability":0.37398,"pace_perf":0.14569,"race_shape":0.11280,
#    "jockey_trainer":0.20414,"class_weight":0.07170,"track":0.09169}
# Ranking registry contains ranking dimensions only. ``form_line`` remains a
# useful report matrix in ``matrix_mapper`` but its long-retired 0.000 entry no
# longer pretends to be a seventh vote in the model.
MATRIX_WEIGHTS = {"stability":0.32920,"pace_perf":0.10559,"race_shape":0.13485,"jockey_trainer":0.22957,"class_weight":0.12042,"track":0.08037}

# ── Wet-form 7D feature (gated to Soft/Heavy races) ──
# A horse's career wet-going place record IS predictive of box-trifecta on wet
# tracks, where the dry 7D score under-rates proven wet performers. This is a
# per-horse going-suitability feature folded into the single ability_score
# (綜合戰力分) on wet races — NOT a post-hoc ranking bolt-on and NOT one of the
# retired report-only micro-modifiers. On dry races it is exactly 0, so the dry
# score is unchanged and stays == pure 7D.
# Walk-forward validated (held-out, expanding window): Soft box-trifecta
# 14.4% → 16.6% at scale 12 (robust plateau 6–12; Heavy unaffected). The going
# record is densely populated (92.7% of runners have ≥1 wet start).
# 2026-08-01：scale/clamp 一齊 ×1.4225 —— 呢個 overlay 係**直接加落 ability 分**，
# 唔經維度矩陣，所以維度尺正規化令 ability 嘅 spread 放大 1.4225 倍之後，如果 overlay
# 唔跟住放大，佢喺濕地賽嘅相對影響力就會靜靜雞縮水 1.4225 倍。
# 實測（710 場，只 toggle 正規化）：唔跟 scale → 71 場排名有變，其中 **70 場係濕地**；
# 跟住 ×1.4225 → 709/710 逐匹一致（剩低 1 場係 matrix_scores 2dp 四捨五入）。
# 即係濕地 overlay 嘅原始校準（Soft box-trifecta 14.4%→16.6% @ scale 12）完整保留。
# 2026-08-01（較後）：矩陣重新配權令場內 pure_7d SD 由 5.1211 收窄到 4.7702，
# 所以 overlay 要再 ×0.9315 先至維持返同一個相對影響力。呢個係**推導出嚟嘅**
# 係數（SD 比例），唔係搵返嚟嘅參數 —— 唔跟就等於靜靜雞畀濕地 overlay 加咗 7.4%
# 話事權。累積係數 1.4225 × 0.9315 = 1.3251。
# 2026-08-03：Sportsbet 重配權令場內 pure_7d SD 由 4.4085 收窄到 3.7344，
# 所以 overlay 再乘 ×0.8471（= 3.7344/4.4085）。**呢個係量出嚟嘅比例，唔係
# fit 出嚟嘅參數** —— overlay 直接加落 ability，唔跟住收窄就會靜靜咁放大
# 佢喺濕地賽嘅相對話事權。
# 實測確認佢冇害：holdout champ 由 +0.00 變 +1.87、mrr +0.73 → +1.81、
# t3prec −0.31 → 0.00，dev 完全一樣。
# Rollback: 12.0 / 5.0（配 gain 全部 = 1）。
# 2026-08-04 lockstep：`jockey_trainer` 內部重配之後 ability 散佈 ×1.0329，
# 所以濕地 overlay 要跟住郁同一個比例，否則佢喺新散佈之下嘅相對影響力會靜靜咁縮。
# 呢個係 derived ratio，唔係 fit 出嚟嘅值 —— 唔可以獨立調。
# 2026-08-08：完整 805 場矩陣重配後 pure-ability 場內 RMS SD 係舊配置
# 0.94790 倍，wet overlay 同步乘 0.94790，保持原本相對影響力。候選用呢個
# lockstep 比例重驗後頭 5 holdout AUC CI 仍全正。
# 舊值 13.91 / 5.79。
WET_FORM_FEATURE_SCALE = 13.19  # 13.91 ×0.94790；points of ability per (shrunk_wet_place_rate − prior)
WET_FORM_SHRINK_A = 4.0         # pseudo-count for place-rate shrinkage toward prior
WET_FORM_PRIOR = 0.5            # global career wet place-rate (~0.496 measured)
WET_FORM_MAX_ABS = 5.49         # 5.79 ×0.94790；clamp the feature to a sane ±range


def _parse_wet_record(going_stats_line):
    """Career (soft+heavy) starts & places from the 軟地/重地 segments of going_stats_line."""
    starts = places = 0
    for label in ("軟地", "重地"):
        match = re.search(rf"{label}:\s*([^|]+)", going_stats_line or "")
        if not match:
            continue
        nums = [int(n) for n in re.findall(r"\d+", match.group(1))]
        if len(nums) >= 4:
            starts += nums[0]
            places += nums[1] + nums[2] + nums[3]
        elif nums:
            starts += nums[0]
    return starts, places


def wet_form_feature(going, going_stats_line):
    """Per-horse wet-going-suitability contribution to ability_score (綜合戰力分).

    Returns 0.0 on dry (Good/Firm) going so the score stays == pure 7D. On Soft/Heavy
    going, returns scale·(shrunk_wet_place_rate − prior), clamped to ±WET_FORM_MAX_ABS.
    A horse with no wet starts shrinks to the prior → 0 (neutral)."""
    g = str(going or "").lower()
    if "soft" not in g and "heavy" not in g:
        return 0.0
    starts, places = _parse_wet_record(going_stats_line)
    rate = (places + WET_FORM_SHRINK_A * WET_FORM_PRIOR) / (starts + WET_FORM_SHRINK_A)
    value = WET_FORM_FEATURE_SCALE * (rate - WET_FORM_PRIOR)
    return round(max(-WET_FORM_MAX_ABS, min(WET_FORM_MAX_ABS, value)), 4)

# 2026-07-11 修：career5_unplaced_pen 由 +0.82（語義反轉——變數叫「懲罰」卻加分，
# ML 殘骸）改為 −0.82 對稱。
# 2026-07-30 runtime micro audit：class-up 0 權重同 RT 高低加減均冇改過
# 7,530 匹最終分；RT 已喺 sectional/rating 層表達，移除重疊死參數。
CLASS_MICRO_WEIGHTS = {
    "career0_base": 57.7,
    "career0_2yo_bonus": 0.84,
    "career5_placed_bonus": 2.31,
    "career5_unplaced_pen": -0.82,
    "career15_maiden_pen": -6.79,
    "career15_unplaced_pen": -1.4,
    "career15_placed_bonus": 5.42,
    "class_drop_bonus": 2.1,
    "metro_prov_pen": -5.48,
}

CONSISTENCY_MICRO_WEIGHTS = {
    "career0_base": 52.4,
    "base": 64.6,
    "recent_place_bonus": 7.86,
    "recent_poor_pen": -2.7,
    # forgiveness_bonus (1.49) 2026-07-10 退出計分：A/B 移除對排名零影響（box4 微升），
    # 寬恕背景改為報告純顯示解讀，唔再入分。
    # margin_trend_bonus 2026-07-10 新增（用戶提出，HK 亦有用）：近2仗平均輸距 vs 之前
    # 改善/惡化 ≥2L → ±3。A/B：全檔 GGP +1、A窗 +1、winT3 +0.6pp，無指標倒退。
    # 2026-08-04 拆成兩邊。原本一個 `margin_trend_bonus` 同時做 +改善 / −惡化，
    # 即係强制對稱。718 場實測兩邊完全唔對稱：
    #     輸距趨勢惡化  n=1,165  超額 **−6.2pp**   ← 真訊號
    #     輸距趨勢改善  n=  956  超額 **−0.1pp**   ← 冇訊號
    # 「跑得越嚟越差」預測得到，「跑得越嚟越好」預測唔到。一個共用數字冇得
    # 表達呢件事，所以拆開。改善側嘅實際數值由 A/B 決定，唔係由對稱決定。
    "margin_trend_up_bonus": 3.0,
    "margin_trend_down_pen": -3.0,
    "run_style_bonus": 5.2,
    "pi_stable_bonus": 5.71,
    "repeat_bonus": 2.7,
    "no_repeat_pen": -2.0
}

# 2026-07-10 噪音剪裁（702場 A/B，PF backfill 之後）：
# - trial_extreme/excellent/pass 補償 REMOVED — 原本非單調（最快試閘 +0、較慢反而 +3.97，
#   ML search 殘骸）；三個修法測齊，「完全移除」最好（GGP +2）兼 timing 上游斷供後本身已啞。
# - peak_pi_bonus / trend_up / trend_down REMOVED — ablation 全指標零變化（純惰性）。
# - realization / forgiveness / pi tiers / l600 峰值 KEPT — 移除有實測損失。
#
# 2026-08-01 中性化（710 場 A/B）：base 由 35.8 改 60.0，其餘每項 ×0.753864
# （= 40 / (28.1+15.07+9.89)，令最高路徑仍然剛好 100 分）。
# 原因：呢個 leaf 係純加分累加器 —— 冇任何負項，「冇 PI 數據」同「PI 顯示冇後勁」
# 都係 add(0.0)，於是 38.1% 嘅馬停留喺 base 35.8，喺 60 為中性嘅顯示尺上讀成
# ❌❌「段速偏弱」。實際上「冇 PI 數據」嗰 1,391 匹 top-3 率 30.1%，*高過* 全樣本
# 平均 —— 拿最差嘅分數去表達「查唔到」係錯嘅。用戶亦直接踩到呢個矛盾：
# 段速實速分顯示「近3場快過基準 1.54 秒」而 段速分 只有 39。PF 有數據嘅馬當中
# 16.7% 中招（PF≥70 但 段速分 ≤45）。
# A/B（710 場，dev 575 / holdout 135）：gold 37→39、t3prec +0.23、mrr +0.13，
# dev t3prec +0.29、holdout champ +0.74 / mrr +0.26 / ndcg +0.14，無指標實質倒退。
# 同日測過「PI 有紀錄但零增益」額外扣分（−4/−8 兩檔）：dev 升但 holdout
# ndcg −0.34/−0.46、crec −0.58/−0.73 → 兩檔都 REJECT，只採用中性化。
# Rollback: base 35.8 + 上述每項 ÷0.753864（即回復下面註釋嘅原值）。
# 每項取兩位小數（同其他 micro family 一致）：最高路徑 60 + 21.18 + 11.36 + 7.46
# = 100.00，剛好用盡 0-100 尺而唔會撞 clip（撞 clip 會製造假平手）。
SECTIONAL_MICRO_WEIGHTS = {
    "base": 60.0,                    # 原 35.8
    "pi_extreme_bonus": 21.18,       # 原 28.1
    "pi_excellent_bonus": 15.08,     # 原 20.0
    "pi_pass_bonus": 2.74,           # 原 3.64
    "l600_extreme_bonus": 11.36,     # 原 15.07
    "l600_excellent_bonus": 2.74,    # 原 3.64
    "realization_bonus": 5.01,       # 原 6.64
    "forgiveness_bonus": 7.46        # 原 9.89
}

TRACK_MICRO_WEIGHTS = {
    "base": 62.9,
    "same_track_place_bonus": 5.0,
    "same_track_win_bonus": 2.4,
    "same_track_poor_pen1": -8.81,
    "same_track_poor_pen2": -0.81,
    "going_place_bonus": 0.8,
    "going_win_bonus": 3.77,
    "going_poor_pen1_wet": -4.75,
    "going_poor_pen1_dry": -3.46,
    "going_poor_pen2_wet": -4.14,
    # 2026-07-11 修：乾地「1 戰零上名」原本 −7.08，罰得重過「2 戰零上名」(−3.46)，
    # 非單調（樣本越少罰越重，不合理，ML 殘骸）。改 −3.0，令 1 戰 ≤ 2 戰。A/B rank-neutral。
    "going_poor_pen2_dry": -3.0,
    "wet_unverified_pen": -6.4,
    "heavy_win_bonus": 3.87,
    # 2026-07-11 修：heavy_place_bonus 原本 −2.88（符號反轉——重地曾上名嘅馬反被扣分，
    # 而 note 竟寫「具備重地作戰能力」；同 best_formal_mult 同款 ML 殘骸）。改 +2.0，
    # 令重地階梯單調：曾贏 +3.87 > 曾上名 +2.0 > 零上名 −5.94。A/B rank-neutral（Heavy good↔pass 互抵）。
    "heavy_place_bonus": 2.0,
    "heavy_poor_pen": -5.94
}

# 2026-08-01 中性化（710 場 A/B）：base 由 55.7 改 60.0。
# 「檔位形勢」＝ pace_map_score ×1.0，所以 leaf 嘅尺就係維度嘅尺。舊 base 55.7 加上
# 修正上限 +4.05 → 全庫最高只得 59.75，即係**60 係天花板而唔係中性**：14.4% 嘅馬
# 卡喺 59.75，0.0% 曾經高過 60，32.3% 落喺 ❌ 帶。一個永遠只會講「中性或差」、
# 但拿住第二大權重（0.14855）嘅維度，用戶讀落自然覺得「一直 60、純噪音」。
# base 移到 60 之後範圍變 50.6–64.05，好檔位終於讀得出「有利」。
# 純常數平移 → 場內排名逐匹不變（710 場 11 個指標、dev/holdout/5 folds 全部完全相同）。
# 同日測過對稱化 cap（±5/±6/±7/±9.43）：dev 同 holdout 方向互相矛盾、無一個持續贏
# → 全部 REJECT，保留實測擬合出嚟嘅不對稱 cap。
#
# 2026-08-02：**呢個不對稱唔係缺陷，係佢啱。** 713 場場內量度（已修正馬群大細，
# 數字＝相對該批期望前三率嘅超額）：
#     <54      n= 154   **−8.3**        恰好 60   n=  87   +1.4
#     54–57    n= 616   −3.2            60–62    n=1806   +0.9
#     57–60    n=2503   −1.6            62–63.9  n=1259   +1.5
#                                       撞頂 64.0 n=1122   **+3.1**
# 修正場數之後階梯完全單調（未修正嘅 pooled 數字係反嘅 —— 差檔位集中喺大場，
# 大場前三率天然低，唔修正就會得出「差檔位跑得好」嘅假結論）。
# 重點：分數範圍係 −9.43/+4.05，結果範圍係 −8.3/+3.1 —— **兩者幾乎一比一**。
# 壞檔位嘅傷害本來就大過好檔位嘅幫助，個 cap 只係忠實反映咗呢件事。拉對稱
# ＝ 用一個現實冇嘅對稱去覆蓋一個量到嘅不對稱，所以之前果次會輸。
# 同日再試過**只放寬上限**（4.05 → 6 / 8 / 12，保留下限）：一樣唔過關。
# holdout good_pos +0.93 但 good_any2 −0.93、t3prec −0.31（cap 12 更差：
# any2 −1.87、winT3 −0.93），dev 三個都係 champ 負、blowout 負。全部 REJECT。
# 代價係 14.9% 嘅馬撞頂平手（34.9% 場次至少一匹、16.0% 場次剛好四匹），
# 呢個平手係已知而且**接受**嘅 —— 解開佢嘅每一個做法都蝕得多過賺。
# Rollback: base 55.7。
PACE_MICRO_WEIGHTS = {
    "base": 60.0,               # 原 55.7
    "modifier_cap_max": 4.05,
    "modifier_cap_min": -9.43,
    "modifier_multiplier": 1.1
}
# ── micro adjustment 家族審查（2026-08-04，718 場 runtime ablation）──────
#
# 目標係「剷走唔會蝕嘅就全部剷」。逐個家族 ablate 之後，**八個家族只有兩個
# 符合條件**，所以呢度只剷咗兩個：
#
#   ✅ form_line        改動場次 0（所屬維度 MATRIX_WEIGHTS = 0.000）→ 已剷，常數內聯
#   ✅ trainer          改動場次 0（門檻從未觸發）           → 已剷
#   ❌ track            hold Good位 −0.68，3/5 fold
#   ❌ class            hold Good位 −2.04，3/5 fold
#   ❌ consistency      dev Good位 −0.70，3/5 fold
#   ❌ sectional        hold Good位 −2.72，3/5 fold
#   ❌ jockey_horse_fit dev Good位 −1.05、hold winT3 −4.08，2/5 fold
#   ❌ pace             dev Gold −1.05 / Good位 −0.88 / winT3 −2.28，1/5 fold
#
# ⚠️ **「全部一齊剷」實測係輸嘅** —— dev Gold −0.35 / Good位 −0.88 / winT3 −1.75，
# holdout Gold −1.36 / Good位 −2.72 / winT3 −5.44，2/5 fold。所以剩返嗰六族
# 唔可以當「手調噪音」剷。佢哋睇落似手調，但量度話佢哋喺出力。
#
# 重跑：au_runtime_micro_ablation.py --archive-root <scored> --results-csv <sb_results.csv>
# 2026-07-11 大剪裁（702場 A/B）：
# - 「歷來最佳配搭」family REMOVED — best_formal_mult 被 ML 推成負數（沿用最佳配搭
#   反而扣分，語義反轉 bug）；成族移除 GGP +2／A窗 +1／B窗平。
# - combo（同場館騎練組合）＋ misc（減磅/週期/首仗二出/-5未知馬房）兩族 REMOVED —
#   逐項 ablation 全指標零變化（惰性），改為 display-only notes。
# - 0 權重死支（debut_top_trainer/young_top_jt/latest_upgrade/jockey_downgrade_vs_best）刪除。
# - KEPT（有實測損失）：trial（−11 GGP if removed）、current（−6）、signal（−5）、latest pens。
# 2026-08-04 新增。`_trial_score` 之前**完全冇** named weight dict —— 全部係
# 函數入面嘅 inline literal（`add(2, …)`、`add(4, …)`、`add(good * 9, …)`）。
# 後果係佢從來冇入過 `au_runtime_micro_ablation.py` 嘅 MICRO_FAMILIES，
# 即係試閘呢個 leaf 七個手調數字從來冇被 ablate 過。
#
# 718 場逐項審計（`au_adjustment_audit.py`）：
#     試閘前三獎勵      n=4,801  +1.5   一致
#     最近試閘頭馬      n=1,977  +4.6   一致，最強
#     試閘密度高兼交代穩  n=  939  +1.3   一致
#     最近試閘前三      n=2,824  −0.7   方向相反但幅度細
#     初出馬備戰        n=  360  −1.4   方向相反但幅度細
TRIAL_MICRO_WEIGHTS = {
    "no_trial_debut_base": 58.0,
    "no_trial_base": 60.0,
    "base": 56.0,
    "top3_mult": 9.0,
    "debut_prep_bonus": 4.0,
    "debut_maiden_bonus": 2.0,
    "latest_win_bonus": 4.0,
    "latest_win_maiden_bonus": 2.0,
    "latest_top3_bonus": 2.0,
    "latest_top3_maiden_bonus": 1.0,
    "density_bonus": 2.0,
    "density_maiden_bonus": 3.0,
    "fast_trial_bonus": 4.0,
    "mid_trial_bonus": 2.0,
}

FIT_MICRO_WEIGHTS = {
    "trial_ok_bonus": 3.38,
    "trial_ok_top_jt_bonus": 1.0,
    "current_formal_cap": 4.05,
    "current_formal_mult": 0.31,
    "current_basic_fit_bonus": 0.65,
    "current_high_fit_bonus": 1.47,
    "current_trial_cap": 2.57,
    "current_trial_mult": 3.8,
    "latest_downgrade_pen": -4.11,
    "leave_proven_jockey_pen": -2.98,
    # 2026-08-04 新增：上仗騎師同呢匹馬嘅往績，做**連續分級項**。
    #
    # 點解要新加一項而唔係改上面兩個。上面兩個係**單邊門檻**：
    # 「上仗騎師上名率 ≥50% 而今場換人」扣 2.98。但 718 場條件化量度顯示，
    # 同一個分岔點之下低嗰半邊（<50%）跑 **−6.8pp**、高嗰半邊跑 **+4.8pp**，
    # 而現行 code **淨係碰高嗰半邊**，低嗰半邊乜都冇畀。所以反符號都救唔到
    # ——實測反符號八個 AUC 區間全部跨 0。要兩邊都出力先得。
    #
    # 逐段實測（6,812 匹、92.4% 覆蓋、已修正馬群大細）：
    #     lo_rate 0.00       n=2,899   **−6.4pp**
    #             0.20–0.34  n=  311   −4.7
    #             0.50–0.67  n=1,149   +3.1
    #             0.67–1.00  n=2,411   **+8.0**
    # 完全單調，跨度 14.4pp。
    #
    # ⚠️⚠️ **實測落唔到分，所以係 0.0（關閉）。** 呢條路徑留住係因為佢係
    # 目前為止最乾淨嘅一個「量到但用唔到」嘅訊號，而唔係因為佢有用。
    #
    # 測過嘅：mult 4 / 8 / 12、加埋反 SAME、再把佢抽做獨立維度掃
    # w = .03/.05/.08/.12/.16。**全部 ability AUC 區間跨 0**（點估計一致係正，
    # Good位 一致係負）。連同反符號、歸零，一共 13 個變體、4 種設計，
    # 冇一個改善排名。
    #
    # 點解一個 14.4pp 單調嘅變數會冇用：佢喺 `form_score` 分層之內仲保住
    # +11.8 / +4.9 / +8.8 / +4.1pp，即係**唔係**近績代理 —— 但好可能係
    # 現有 leaf **組合**嘅代理（我只分層咗 form_score 一個）。
    #
    # 對一個亂咗嘅 leaf，正確反應係**少信佢**而唔係修佢個公式 ——
    # 而嗰個已經做咗（jockey_horse_fit 內部權重 .52 → .381）。
    "latest_jockey_record_mult": 0.0,
    "latest_jockey_record_cap": 5.0,
    "signal_best_jockey_bonus": 3.85,
    # 2026-08-04：以下三項本來係函數入面硬寫嘅 `add(2, …)`。提升成有名參數，
    # 因為一個 ablation 掃唔到嘅魔術數字比一個調得太多嘅參數更難升級。
    "signal_same_jockey_bonus": 2.0,
    "signal_trial_rider_bonus": 2.0,
    "signal_reunite_bonus": 2.0,
}

# 2026-08-01（較後）矩陣重新配權之後嘅實測分佈（7,547 匹）：
#   之前  max 88.0  mean 64.59   A+ 11 / A 45 / A− 157 / B+ 584
#   之後  max 84.5  mean 64.03   A+  2 / A 20 / A− 101 / B+ 429
# 頂端**刻意**變窄咗：新權重攤得更平均，所以「每個維度都出色」自然更罕見。
# 呢個係想要嘅行為 —— 整場重新配權嘅起因就係 Benbulben 嗰類「一兩個維度谷高、
# 其餘平平」嘅馬被評得太高。唔好見到 A+ 少咗就落手調呢組門檻：一調就等於把
# 舊模型嘅過度自信搬返出嚟。真係要調，先重新量度分佈，再改埋呢段註釋。
# 評級純粹係報告用字，冇任何選馬／落注邏輯讀佢（只有 validation.py 做一致性檢查）。
GRADE_THRESHOLDS = ((96,"S+"),(92,"S"),(88,"S-"),(84,"A+"),(80,"A"),(76,"A-"),(72,"B+"),(68,"B"),(64,"B-"),(60,"C+"),(56,"C"),(52,"C-"),(48,"D"),(0,"E"))

def clip_score(value, default=60.0):
    try: score = float(value)
    except (TypeError, ValueError): score = default
    return max(0.0, min(100.0, score))

def compute_grade(ability_score):
    score = clip_score(ability_score,0)
    for threshold, grade in GRADE_THRESHOLDS:
        if score >= threshold: return grade
    return "E"

def score_band(score):
    score = clip_score(score)
    if score >= 85: return "✅✅"
    if score >= 70: return "✅"
    if score >= 55: return "➖"
    if score >= 40: return "❌"
    return "❌❌"

def parse_float(value):
    if isinstance(value,(int,float)): return float(value)
    if not value: return None
    match = re.search(r"-?\d+(?:\.\d+)?",str(value))
    return float(match.group(0)) if match else None

def parse_numbers(text):
    if not text: return []
    return [int(m.group(0)) for m in re.finditer(r"\d+",str(text))]

def parse_record_line(line):
    if not line: return {"starts":0,"wins":0,"seconds":0,"thirds":0,"places":0}
    nums = parse_numbers(str(line))
    if len(nums) >= 4:
        wins = nums[1]
        seconds = nums[2]
        thirds = nums[3]
        return {
            "starts": nums[0],
            "wins": wins,
            "seconds": seconds,
            "thirds": thirds,
            "places": wins + seconds + thirds,
        }
    if len(nums) >= 3:
        wins = nums[1]
        places = nums[1] + nums[2]
        return {"starts":nums[0],"wins":wins,"seconds":nums[2],"thirds":0,"places":places}
    return {"starts":0,"wins":0,"seconds":0,"thirds":0,"places":0}

def parse_recent_finishes(text):
    """Finish positions from a recent-form string, newest conventions honoured.

    Handles both separated ("8-9-7-6") and compact ("2134") formats — the compact
    form previously parsed as one giant number and silently returned nothing,
    zeroing the consistency place/poor components for those horses. In compact
    form each digit is one run and "0" is the AU code for 10th-or-worse.
    """
    if not text: return None
    raw = str(text).strip()
    if re.fullmatch(r"\d{2,}", raw):
        return [int(ch) if ch != "0" else 10 for ch in raw]
    nums = parse_numbers(raw)
    if nums: return [n if n != 0 else 10 for n in nums if 0 <= n <= 24]
    return None

def safe_ratio(numerator, denominator):
    if not denominator: return 0.0
    return min(1.0, max(0.0, numerator / denominator))
