from __future__ import annotations

from .scoring import clip_score, score_band


MATRIX_FORMULAS = {
    "stability": (
        ("form_score", 0.60),
        ("performance_quality_score", 0.40),
    ),
    # 段速表現 (2026-07-10): 段速與引擎 (sectional 0.04535 = 0.805 sec + 0.195 trial)
    # 同 L600 速度考驗背景 (pace_figure 0.14296) 合併為一個維度，總權重 0.18831。內部權重
    # 係舊有效 leaf 權重嘅精確折算（0.14296/0.0365/0.0088 ÷ 0.18831）→ 排名逐匹
    # 完全一致（702場 A/B 驗證 GGP/champ/box4 全部相同）。內部權重 sweep（p.85/.90/
    # 1.0、s.25）全部兩窗唔贏 → 呢個折算比例就係局部最優。
    # Rollback: 拆返 "sectional":(sec .805, trial .195) w=0.04535 + "pace_figure" w=0.14296。
    # 2026-08-05 `sectional_score` 退出排名。實測（725 場，剔走中性 60）：
    #   段速分場內 AUC **0.525** —— 接近噪音（0.500 = 冇資訊）
    #   **即使有 L400 PI 數據都只有 0.532**（696 場 / 12,151 對）
    # 即係佢弱唔係因為缺數據（21.0% 缺 PI），係個 leaf 本身冇判別力。所以
    # 「補 PI 覆蓋率」幫唔到 —— 呢個同 [[au-pf-coverage-unlock-needs-refit]]
    # 嗰次「覆蓋率升三倍但輸」係同一個道理。
    #
    # 孤立 A/B（713 場，移除 + 等價權重換算，**冇** re-fit，所以量到嘅係移除本身）：
    #   全樣本  6 升 / 4 跌      dev  6 升 / 4 跌      holdout  7 升 / 1 跌
    # holdout 107 場，1 場 = 0.93pp，所以全部差異都係 1–2 場級數 → **打和**，
    # 帶輕微正向。移除嘅實際收益係簡化：少一個 leaf，同時報告唔再出
    # 「缺 L400 PI 數據，段速分維持中性」嗰句噪音（21% 嘅馬會見到）。
    #
    # ⚠️ 唔可以引用「移除 + re-fit = 10 升 / 1 跌」做理由 —— 對照組（**保留**段速分、
    # 同一個 seed 重 fit）都係 10 升 / 1 跌，幅度相近。即係嗰個大收益屬於 re-fit，
    # 唔屬於移除。re-fit 係獨立議題，要自己過 walk-forward。
    #
    # Rollback: pace_figure .759174 / sectional .193864 / trial .046962，
    #           MATRIX_DISPLAY_GAINS["pace_perf"] 1.0244，
    #           MATRIX_WEIGHTS 回舊值（見下面 scoring.py 註）。
    "pace_perf": (
        ("pace_figure_score", 0.941744),
        ("trial_score", 0.058256),
    ),
    # 2026-07-11: 檔位形勢 淨化為純檔位/走位（pace_map 100%）。原本借用嘅 30%
    # track_score 已全數歸還「場地適性」維度 —— 消除跨維度重複，track_score 而家
    # 只喺一個維度出現，將來獨立升級唔使兩邊改。權重按代數對調（見 scoring 註）→
    # 逐匹綜合分完全一致（rank-identical，702場驗證 max diff 0.0001）。
    "race_shape": (
        ("pace_map_score", 1.0),
    ),
    # 2026-08-04 內部重配（`au_inner_weights.py`）。舊值 jockey .28 / trainer .20 /
    # jockey_horse_fit **.52** —— 即係判別力最弱嗰個 leaf 攞咗過半內部權重：
    #     jockey_score 0.600 · trainer_score 0.605 · jockey_horse_fit_score **0.532**
    # 而 jockey_horse_fit 逐段實際表現係**非單調**嘅（52–56 帶 +14.2pp、58–60 帶
    # −7.5pp、60–62 帶 +8.2pp）—— 佢唔係弱，係亂，因為入面三個「騎師連續性」
    # 手調項符號同結果相反（見 `au_adjustment_audit.py`）。
    #
    # 五條獨立證據支持減佢權重：
    #   1. leaf AUC 最低（0.532 vs 同維度 0.600 / 0.605）
    #   2. 逐段實際表現非單調（健康 leaf 例如 form_score 係完全單調嘅）
    #   3. SD 對照組：候選贏「保持現行分配、只放大維度權重」4↑/0↓
    #   4. ability 場內 AUC：dev +0.0047 [+0.0005,+0.0087]、
    #      holdout +0.0117 [+0.0046,+0.0197]，頭 5 位配對 holdout +0.0150 ✅
    #   5. 場數指標 dev 同 holdout 全部正
    #
    # ⚠️ walk-forward 只有 3/5，而我一度因此 REJECT 佢。後來校準過條閘：
    # 40 個**確定中性**嘅擾動之下，三道閘全過嘅係 **0/40**，walk-forward 5/5
    # 只有 5/40。即係嗰道閘假陽性率係 0（好），但同時細幅度嘅真改動大機會
    # 過唔到。用佢做唯一裁判會系統性拒絕所有細改善。
    #
    # Rollback: jockey .28 / trainer .20 / jockey_horse_fit .52，
    #           同時 WET_FORM_FEATURE_SCALE 13.47 / MAX_ABS 5.61。
    "jockey_trainer": (
        ("jockey_score", 0.333333),
        ("trainer_score", 0.285714),
        ("jockey_horse_fit_score", 0.380952),
    ),
    # rating_score up-weighted 0.15 -> 0.70 (2026-06-29): official handicap rating
    # is the one run-style-independent ability signal that lifts box4 OOS. Combined
    # with the distance removal above, walk-forward (5-fold, fixed sub-weight, no
    # negative fold on box4) gives box4 +0.6pp, good +0.6pp, champion +0.8pp.
    # 2026-07-29 signal-cleaning audit (710 aligned races): direct class_score
    # removal improved/held competitive recall, NDCG and winner@5 in all five
    # development time folds and the untouched terminal 15% holdout.  Keep
    # class_score available to the contextual mismatch interactions/report, but
    # do not count the same class narrative again in this ranking matrix.
    # 2026-08-01 negative-value leaf 移除：weight_score 退出排名。
    # 710 場實測：84.9% 嘅馬負磅分**恰好** 60（41.5% 嘅場次全場一模一樣，即係
    # 完全冇 gradient），within-race AUC 0.480（低於隨機 0.5），top-3 gap −0.14。
    # 2026-07-24 已經正確判定「負磅嘅能力訊號早已由 rating_score 承擔」而將佢中性化，
    # 但當時保留咗 0.141 權重 —— 即係保留咗一個純噪音項嘅投票權。
    # A/B（710 場，PF off 同 PF on 兩個 footing 各跑一次）：移除後 11 個指標
    # 全部 = 或 ±0.14（＝1 場，噪音級），dev/holdout 皆無實質變化。
    # 負磅仍然係報告內容（頂磅標記、爛地孭重磅、降班配輕磅），只係唔再入排名。
    # Rollback: 加返 ("weight_score", 0.141)。
    "class_weight": (
        ("rating_score", 0.70),
    ),
    "track": (
        ("track_score", 1.0),
    ),
    "form_line": (
        # Report-only opponent evidence: recent form already belongs to
        # stability. Mixing it here made a horse's own placings look like
        # independent evidence about its opponents (EXP-20260902-06).
        ("formline_score", 1.0),
    ),
}

MATRIX_KEYS = tuple(MATRIX_FORMULAS)
LEGACY_MATRIX_ALIASES = {
    "sectional": "pace_perf",
}

# ── 維度顯示尺正規化（2026-08-01）───────────────────────────────────────────
# 每個維度嘅原生 spread 差得好遠，但報告用同一套 band 去畫（85 ✅✅ / 70 ✅ /
# 55 ➖ / 40 ❌）。710 場實測，正規化之前：
#
#   stability       41.6–100.0   SD  9.96   四個 band 都到
#   pace_perf       15.2– 98.9   SD 15.31   五個 band 都到
#   race_shape      50.6– 64.0   SD  2.67   **只有 ➖(97%) 同 ❌(3%)** —— ✅ 到唔到
#   jockey_trainer  51.1– 73.8   SD  3.20   ➖ 98%，✅ 2%，✅✅ 到唔到
#   class_weight    50.9– 69.5   SD  4.00   ➖ 89%，❌ 11%，✅ 到唔到
#   track           42.9– 85.7   SD  5.88   ✅✅ 幾乎到唔到
#
# 即係六個計分維度有三個，無論隻馬幾好都**永遠出唔到正面 band**。唔係噪音，
# 係啞 —— 用戶睇到「一直 60」就係呢個。
#
# 修法：`mx' = clip(60 + (mx − 60) × gain)`，gain =
#   min(TARGET_SD / 實測SD, 令實測極值仍然落喺 1..99 之內嘅最大 gain)
# headroom 那一半好緊要：唔封住就會有一堆馬撞 0/100，製造假平手。
#
# ⚠️ gain 同權重係乘埋一齊影響排名（ranking 只食 weight × gain × deviation），
# 所以呢個正規化本身就係一次 re-weighting。MATRIX_WEIGHTS 已經同步重 fit ——
# 兩者必須一齊改，唔可以只改一邊。等價點 w/gain 可以完全複製舊模型，所以重 fit
# 嘅搜索空間包含舊配置（搜索唔可能輸過舊模型）。
MATRIX_DISPLAY_TARGET_SD = 11.0
MATRIX_DISPLAY_GAINS = {
    "stability": 0.9750,
    # 2026-08-26（EXP-20260826-03）：0.9909 → 0.594。
    #
    # 舊值係喺一個**一半場次入面呢個維度根本係常數**嘅語料上 fit 出嚟。2026-05
    # 之前嘅歸檔冇段速抽取，`pace_figure_score` 成場都係 60，所以嗰 4,788 匹馬嘅
    # raw SD 只有 **0.64**。溝落去令量到嘅 raw SD 由真實嘅 ~18.5 縮到 11.10，
    # 而 11/11.10 = 0.991 —— 即係舊 gain 完全符合公式，只不過餵咗個假 SD。
    #
    #   語料                        raw SD    11/SD
    #   2026-05 之前（PF 全部 60）      0.64      —
    #   2026-08-05 之前（設 gain 嗰陣） 12.07    0.9115
    #   2026-06+（PF 可表達）          18.43    0.5969
    #   2026-08-05+（乾淨）            18.53    0.5937
    #
    # 後果：pace_perf 成品顯示 SD 喺 live 語料係 **18.26**，而其餘四個維度係
    # 10.16–12.81。即係佢比設計意圖大聲 1.68 倍 —— 兩端 band 都爆：❌❌ 佔 14.3%
    # 而 stability / track 只有 0.4%。用戶投訴「一隻唔對板嘅馬又衝上頭位」，
    # 機制就係呢度。
    #
    # ⚠️ 排名**冇改變**。gain 降到 0.594 嘅同時，`MATRIX_WEIGHTS["pace_perf"]`
    # 按 0.9909/0.594 放大再全體歸一，而 `MATRIX_ABILITY_SCALE` 把 ability 軸
    # 還原 —— 1,611 場實測 ability max|Δ| 0.0016（純 round(2) 噪音）、grade 改變 0、
    # 頭三分差 max|Δ| 0.0027、只有 2 場因為 0.002 級數嘅平手而換位。
    #
    # 點解唔順手減佢喺排名嘅份量：試過（gain 0.594 / 0.7161 / 0.85 × 三個語料，
    # 共九格），**冇一格過閘** —— 主裁判全部跨 0，而場數指標係 gold +0.56~+0.97
    # 但 pass −0.19~−1.45。冇量到改善就唔改排名。
    "pace_perf": 0.594,
    "race_shape": 4.1142,
    "jockey_trainer": 2.4973,
    "class_weight": 2.7489,
    "track": 1.5193,
    "form_line": 1.0,
}
# 正規化之後每個維度都用同一把尺，所以敘事門檻唔再需要逐維度磨 magic number。
MATRIX_ADVANTAGE_CUTOFF = 72.0
MATRIX_DISADVANTAGE_CUTOFF = 48.0


def canonical_matrix_key(key):
    """Return the live matrix key for a current or legacy name."""
    return LEGACY_MATRIX_ALIASES.get(str(key), str(key))


def matrix_score(matrix_scores, key, default=60.0):
    """Read a matrix score without silently losing legacy `sectional` data."""
    scores = matrix_scores if isinstance(matrix_scores, dict) else {}
    canonical = canonical_matrix_key(key)
    if canonical in scores:
        return clip_score(scores[canonical], default)
    if canonical == "pace_perf" and "sectional" in scores:
        return clip_score(scores["sectional"], default)
    return clip_score(default, default)


def canonicalize_matrix_scores(matrix_scores, default=60.0):
    return {
        key: round(matrix_score(matrix_scores, key, default), 2)
        for key in MATRIX_KEYS
    }


def map_features_to_matrix_scores(features):
    matrix_scores = {}
    for key, components in MATRIX_FORMULAS.items():
        # Score weighted deviations from neutral.  This is algebraically
        # identical to the old weighted average whenever weights sum to 1, and
        # lets a retired leaf disappear cleanly without shifting the score
        # scale or inventing a fake constant feature.
        score = 60.0 + sum(
            (clip_score(features.get(name, 60)) - 60.0) * weight
            for name, weight in components
        )
        # Put every dimension on one ruler so the bands mean the same thing
        # everywhere (see MATRIX_DISPLAY_GAINS).
        score = 60.0 + (clip_score(score) - 60.0) * MATRIX_DISPLAY_GAINS.get(key, 1.0)
        matrix_scores[key] = round(clip_score(score), 2)
    return matrix_scores


def map_features_to_matrix(features):
    scores = map_features_to_matrix_scores(features)
    return {key: score_band(score) for key, score in scores.items()}
