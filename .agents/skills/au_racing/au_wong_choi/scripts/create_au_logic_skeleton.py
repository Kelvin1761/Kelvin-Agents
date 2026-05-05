#!/usr/bin/env python3
import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys, re, json, os, argparse, io
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
create_au_logic_skeleton.py — V9 Python-Native Skeleton Generator for AU Racing

Extracts factual data from AU Facts.md for a SINGLE horse and
pre-fills Logic.json. LLM only needs to fill [FILL] analysis fields.

Usage:
  python3 create_au_logic_skeleton.py <facts_path> <race_num> <horse_num>
"""

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


def extract_horse_block(facts_content, horse_num):
    """Extract the text block for a single horse from AU Facts.md.
    AU format uses [#X] markers instead of ### 馬號 X."""
    # Try AU format first
    pattern = rf'\[#{horse_num}\]'
    match = re.search(pattern, facts_content)
    if not match:
        # Try HKJC-style format as fallback
        pattern = rf'### 馬號 {horse_num} — '
        match = re.search(pattern, facts_content)
    if not match:
        # Try V2 format
        pattern = rf'### 馬匹 #{horse_num}\b'
        match = re.search(pattern, facts_content, re.IGNORECASE)
    if not match:
        # Try Runner X format
        pattern = rf'(?:Runner|Horse)\s+{horse_num}\b'
        match = re.search(pattern, facts_content, re.IGNORECASE)
    if not match:
        return None

    start = match.start()
    # Find next horse marker
    next_patterns = [
        rf'\[#{horse_num + 1}\]',
        r'\[#\d+\]',
        r'### 馬號 \d+ — ',
        r'### 馬匹 #\d+',
        r'(?:Runner|Horse)\s+\d+\b',
    ]
    for np in next_patterns:
        next_match = re.search(np, facts_content[match.end():])
        if next_match:
            return facts_content[start:match.end() + next_match.start()]
    return facts_content[start:]


def parse_horse_header(block):
    """Extract horse name, jockey, trainer from AU Facts block."""
    result = {}

    # Try [#X] Name format
    m = re.search(r'\[#(\d+)\]\s*(.+?)(?:\n|$)', block)
    if m:
        result['num'] = int(m.group(1))
        result['name'] = m.group(1).strip()
        # The name might be on the same line or the next
        name_line = m.group(2).strip()
        if name_line:
            result['name'] = name_line.split('|')[0].split('—')[0].strip()

    # Try V2 format
    m3 = re.search(r'### 馬匹 #(\d+)\s+(.+?)\s+\(檔位\s*(\d+)\)\s*\|\s*騎師:\s*(.+?)\s*\|\s*練馬師:\s*(.+?)(?:\s*\||\n|$)', block)
    if m3:
        result['num'] = int(m3.group(1))
        result['name'] = m3.group(2).strip()
        result['barrier'] = int(m3.group(3))
        result['jockey'] = m3.group(4).strip()
        result['trainer'] = m3.group(5).strip()
        return result

    # Try HKJC-compatible format as fallback
    m2 = re.search(r'### 馬號 (\d+) — (.+?) \| 騎師:\s*(.+?) \| 練馬師:\s*(.+?) \| 負磅:\s*(\d+) \| 檔位:\s*(\d+)', block)
    if m2:
        result['num'] = int(m2.group(1))
        result['name'] = m2.group(2).strip()
        result['jockey'] = m2.group(3).strip()
        result['trainer'] = m2.group(4).strip()
        result['weight'] = int(m2.group(5))
        result['barrier'] = int(m2.group(6))
        return result

    # Extract individual fields
    for field, patterns in [
        ('jockey', [r'(?:Jockey|騎師)[：:]\s*(.+?)(?:\n|\||$)']),
        ('trainer', [r'(?:Trainer|練馬師)[：:]\s*(.+?)(?:\n|\||$)']),
        ('weight', [r'(?:Weight|Wt|負磅)[：:]\s*(\d+(?:\.\d+)?)']),
        ('barrier', [r'(?:Barrier|Draw|Gate|檔位)[：:]\s*(\d+)']),
    ]:
        for p in patterns:
            m = re.search(p, block, re.IGNORECASE)
            if m:
                if field in ('weight', 'barrier'):
                    try: result[field] = int(float(m.group(1)))
                    except: result[field] = 0
                else:
                    result[field] = m.group(1).strip()
                break
    return result


def parse_recent_race(block):
    """Extract L400, position from the most recent race for AU."""
    result = {}
    # Look for table rows after any table header
    table_rows = re.findall(r'^\|(.+?)\|$', block, re.MULTILINE)
    data_rows = [r for r in table_rows if not re.match(r'\s*[-]+', r.split('|')[0].strip())]
    # Skip header row
    if len(data_rows) > 1:
        # First data row (most recent race)
        cols = [c.strip() for c in data_rows[1].split('|')]
        # Try to find L400 column (look for decimal number like 22.59)
        for i, c in enumerate(cols):
            if re.match(r'\d{2}\.\d{2}$', c):
                result['raw_L400'] = c
                break
        # Try to find position column (look for patterns like 6-7-5)
        for i, c in enumerate(cols):
            if re.match(r'^\d{1,2}-\d{1,2}(?:-\d{1,2})?$', c):
                result['last_run_position'] = c
                break

    # Fallback: extract from text
    if 'raw_L400' not in result:
        m = re.search(r'L400[：:]\s*([\d.]+)', block)
        if m: result['raw_L400'] = m.group(1)

    if 'last_run_position' not in result:
        m = re.search(r'(?:沿途位|Position|Settling)[：:]\s*([\d-]+)', block, re.IGNORECASE)
        if m: result['last_run_position'] = m.group(1)

    return result


def parse_trends(block):
    """Extract trend summaries."""
    result = {}
    patterns = {
        'l400_trend': r'L400:\s*(.+?)$',
        'energy_trend': r'(?:能量|Energy):\s*(.+?)$',
        'engine': r'(?:引擎|Engine):\s*(.+?)$',
        'formline_strength': r'(?:\*\*綜合評估:\*\*|Formline:)\s*(.+?)$',
        'weight_trend': r'(?:\*\*體重趨勢:\*\*|Weight Trend:)\s*(.+?)$',
    }
    for key, pat in patterns.items():
        m = re.search(pat, block, re.MULTILINE | re.IGNORECASE)
        if m: result[key] = m.group(1).strip()
    return result


def parse_career_info(block):
    """Extract official career starts and derive AU career tag."""
    career_starts = 0

    m = re.search(r'生涯標記:\s*`(DEBUT|EARLY_CAREER|IMPORTED_DEBUT|ESTABLISHED)`', block)
    explicit_tag = m.group(1) if m else ''

    for pat in [
        r'生涯:\s*(\d+)\s*:',
        r'Career[：:]\s*(\d+)\s*:',
        r'Career\s+(\d+)\s*:',
    ]:
        m = re.search(pat, block, re.IGNORECASE)
        if m:
            career_starts = int(m.group(1))
            break

    if explicit_tag:
        career_tag = explicit_tag
    elif career_starts == 0:
        career_tag = 'DEBUT'
    elif career_starts <= 5:
        career_tag = 'EARLY_CAREER'
    else:
        career_tag = 'ESTABLISHED'

    if career_starts == 0:
        stage_label = '初出馬'
    elif career_starts == 1:
        stage_label = '生涯第2場'
    elif career_starts <= 5:
        stage_label = f'生涯第{career_starts + 1}場'
    else:
        stage_label = ''

    return {
        'career_starts': career_starts,
        'career_tag': career_tag,
        'career_stage_label': stage_label,
    }


def build_skeleton(data):
    """Build JSON skeleton for AU horse analysis. V4.2 — 7 dimensions."""
    import secrets
    name = data.get('name', '未知')
    raw_l400 = data.get('raw_L400', 'N/A')
    last_pos = data.get('last_run_position', 'N/A')
    recent_form = data.get('recent_form', 'N/A')
    l400_trend = data.get('l400_trend', 'N/A')
    engine = data.get('engine', 'N/A')
    best_dist = data.get('best_distance', 'N/A')
    same_dist = data.get('same_distance_record', 'N/A')
    jockey = data.get('jockey', '')
    trainer = data.get('trainer', '')
    gear = data.get('gear', 'N/A')
    weight = data.get('weight', 0)
    barrier = data.get('barrier', 0)
    rating = data.get('rating', 'N/A')
    class_move = data.get('class_move', 'N/A')
    good_track = data.get('good_track_record', 'N/A')
    venue_hist = data.get('venue_history', 'N/A')
    formline_str = data.get('formline_strength', 'N/A')
    track_bias = data.get('track_bias', 'N/A')
    career_starts = data.get('career_starts', 0)
    career_tag = data.get('career_tag', 'DEBUT' if career_starts == 0 else ('EARLY_CAREER' if career_starts <= 5 else 'ESTABLISHED'))
    career_stage_label = data.get('career_stage_label', '')
    is_debut = career_tag == 'DEBUT'
    is_early_career = career_tag in ('DEBUT', 'EARLY_CAREER') or career_starts <= 5
    debut_sectional_note = (
        "[初出馬規則: 無正式段速時，段速與引擎改用 Sire 距離投影 + 試閘速度；必須引用 sire reference。]\n"
        if is_debut else ""
    )
    debut_class_note = (
        "[初出馬規則: vs 初出馬通常 ➖；vs 有經驗且有勝績對手通常 ❌，除非有明確 elite debut deployment。]\n"
        if is_debut else ""
    )
    debut_track_note = (
        "[初出馬規則: 場地適性改用 Sire 場地偏好 + 試閘場地參考；資料不足通常 ➖。]\n"
        if is_debut else ""
    )
    debut_formline_note = (
        "[初出馬規則: 無正式賽績線一律 ➖；如試閘對手已正式出賽可低信心參考，不可當強賽績線。]\n"
        if is_debut else ""
    )
    debut_core_logic = (
        "[FILL — 初出馬專用格式，約80-120字矩陣總結。必須涵蓋：(1) Career=0，不能用正常近績/first-up模板；"
        "(2) 試閘/Sire/騎練部署係主要證據；(3) Pace Confidence、檔位及場地 family 對初出適應風險；"
        "(4) trial-only 最高 B/B+，elite debut deployment 先可 A-。]"
        if is_debut else
        "[FILL — 根據上方 7 維度評級矩陣嘅結果寫約80-120字嘅矩陣總結。必須：(1) 核心維度結論（穩定性、段速）；(2) 半核心結論（形勢、騎練）；(3) 輔助維度亮點/弱點；(4) 整體前景判斷。唔好重複 reasoning 原文。]"
    )

    # ===== Data-Anchored Reasoning (AU V4.3) =====
    r_stability = (
        f"[Resource Check: 02b_form_analysis.md Step 1 / 狀態週期+寬恕過濾]\n"
        f"[Evidence Confidence: FILL High/Medium/Low/Unknown — formal race sample after forgive filter]\n"
        f"[數據: 近績序列={recent_form}]\n"
        f"[生涯標記: {career_tag}; 正式賽事場次={career_starts}; "
        f"{'初出馬需按 02h_debut_guide.md 用試閘質素判斷穩定性，嚴禁寫成休出/First-up。' if is_debut else '早期生涯馬需用「生涯第X場」描述，嚴禁寫成休出/First-up。' if is_early_career else '按標準備戰週期判斷。'}]\n"
        f"[❗ 數據可靠性: 必須逐場標記近5場(受阻/競賽事件), "
        f"受阻場次名次不作參考]\n"
        f"[📂 必須閱讀上方「📋 完整賽績檔案」全部賽事記錄，唔淮得淨督近5場 — 需要綜合全部賽績判斷穩定性趨勢]\n"
        f"[📎 必讀: 02b_form_analysis.md 狀態評估規則]\n"
        f"→ [判讀: FILL]"
    )
    r_speed_engine = (
        f"[Resource Check: 02b_form_analysis.md Step 2 + 02f_synthesis.md / 引擎+距離合併規則]\n"
        f"[Evidence Confidence: FILL High/Medium/Low/Unknown — class-par sectionals / PI proxy / trial-only]\n"
        f"[數據: 上仗L400={raw_l400}, L400趨勢={l400_trend}, "
        f"引擎={engine}, 最佳距離={best_dist}, "
        f"同程紀錄={same_dist}]\n"
        f"{debut_sectional_note}"
        f"[V4.2 合併規則: 距離適性、距離轉換風險、Sire 距離投影已併入「段速與引擎」。"
        f"段速好但今日距離明顯未證或不合,最高通常只可 ✅/➖,不可輕易 ✅✅]\n"
        f"[❗ 數據可靠性: 必須逐場標記段速可靠性, "
        f"受阻場次段速不作參考, 判斷時優先用其他有效場次]\n"
        f"[📂 必須閱讀上方「📋 完整賽績檔案」全部段速/消耗/走位數據，綜合判斷段速趨勢而唔淮淨督近5場]\n"
        f"[📎 必讀: 02b_form_analysis.md 段速剖面規則 + "
        f"02b_straight_sprint_engine.md (如適用直路賽)]\n"
        f"→ [判讀: FILL]"
    )
    r_race_shape = (
        f"[Resource Check: 02d_pace_notes.md + 02a_pre_analysis.md / Pace Confidence + course geometry]\n"
        f"[Pace Confidence: FILL Clear/Mixed/Low — Clear 先可 ✅✅]\n"
        f"[數據: 上仗走位={last_pos}, 檔位={barrier}, "
        f"跑道偏差={track_bias}]\n"
        f"[步速形勢: 必須分析上方🗺️自動步速圖 — "
        f"判讀前速壓力、前置馬數量、後上受惠/受害, "
        f"結合馬匹跑法判斷形勢配合度]\n"
        f"[Track Geometry: 檢查急彎/長直路/直路賽/首次場地 family 轉換]\n"
        f"[走位模式: 必須引用完整賽績檔案近5仗嘅走位/消耗/沿途位, "
        f"做2-3句走位模式短分析, 結合跑道偏差判讀檔位]\n"
        f"[📎 必讀: 02d_pace_notes.md 步速形勢規則 + "
        f"04b_track_*.md 對應場地檔位偏差]\n"
        f"→ [判讀: FILL]"
    )
    r_jockey_trainer = (
        f"[Resource Check: 02e_jockey_trainer.md + 02c_track_and_gear.md / 騎練部署+配備意圖]\n"
        f"[Evidence Confidence: FILL High/Medium/Low/Unknown — deployment/rider-fit/gear intent anchors]\n"
        f"[數據: 騎師={jockey}, 練馬師={trainer}, "
        f"配備={gear}]\n"
        f"[人馬配搭: {{PYTHON: {jockey}×此馬: X戰Y勝 "
        f"(勝率%, 位率%, 平均名次) "
        f"vs 其他騎師: [騎師A: X戰Y勝 (勝率%, 位率%, 平均名次), ...]}}]\n"
        f"[V4.2 合併規則: 配備意圖、首戴裝備、Elite Stable Gear Premium 已併入「騎練訊號」。"
        f"配備必須針對已確認問題並有獨立支持先可升 ✅；同一配備事件不可再用 GEAR_POSITIVE 微調]\n"
        f"[配備意圖: 分析配備變動及目的；冇明確 deployment signal 就保持 ➖]\n"
        f"[📎 必讀: 02e_jockey_trainer.md 騎練組合規則 + "
        f"07_jockey_profiles.md 檢查騎師 {jockey} 評級同專長 + "
        f"07b_trainer_signals.md 檢查練馬師 {trainer} 特殊訊號]\n"
        f"→ [判讀: FILL (包含配備意圖分析)]"
    )
    r_class_weight = (
        f"[Resource Check: 02b_form_analysis.md Step 3 + 03e_class_standards.md / AU class normalization]\n"
        f"[AU Class Normalization: FILL Metro/Provincial/Country + BM/Set Weight/WFA context]\n"
        f"[數據: Rating={rating}, 班次變動={class_move}, "
        f"負重={weight}kg]\n"
        f"{debut_class_note}"
        f"[級數對比: Rating vs 同場最高/平均, "
        f"負重對比: 負磅 vs 全場最重/平均/差距]\n"
        f"[📎 必讀: 03e_class_standards.md 班次標準 + "
        f"03f_wfa_scale.md WFA 減磅表]\n"
        f"→ [判讀: FILL]"
    )
    r_track_surface = (
        f"[Resource Check: 02c_track_and_gear.md + 04a_track_core.md / Track Family Confidence]\n"
        f"[Track Family Confidence: FILL High/Medium/Low/Unknown — same venue/geometry/direction/surface/going]\n"
        f"[數據: 場地紀錄={good_track}, "
        f"跑道適配={venue_hist}]\n"
        f"{debut_track_note}"
        f"[🏥 健康評估規則: 有健康事故(bleeding/vet scratch/illness)+復原證據(後續好表現)=已復原(➖/✅); "
        f"有事故+未復原=風險(❌); 無事故=正常(✅)]\n"
        f"[📎 必讀: 04a_track_core.md 場地通則 + "
        f"04b_track_*.md 對應場地資料 + "
        f"04d_wet_track.md (如軟/重地)]\n"
        f"→ [判讀: FILL]"
    )
    r_formline = (
        f"[Resource Check: 02b_form_analysis.md 賽績線規則 + Facts.md 對手後續表]\n"
        f"[Evidence Confidence: FILL High/Medium/Low/Unknown — >=2/N same-or-higher-class opponent support]\n"
        f"[數據: 賽績線強度={formline_str}]\n"
        f"{debut_formline_note}"
        f"[必須分析近3場對手後續表現]\n"
        f"[📎 必讀: 02b_form_analysis.md 賽績線評估規則]\n"
        f"→ [判讀: FILL]"
    )

    return {
        # ===== LOCKED DATA =====
        '_locked': True,
        '_validation_nonce': 'SKEL_' + secrets.token_hex(4),
        'horse_name': name,
        'jockey': jockey,
        'trainer': trainer,
        'weight': weight,
        'barrier': barrier,
        'career_tag': career_tag,
        'career_race_starts': career_starts,
        'career_stage_label': career_stage_label,

        # ===== ANALYSIS FIELDS (V4.2: matrix-only, legacy fields removed) =====
        'status_cycle': '[FILL]',
        'trend_summary': '[FILL]',

        'forgiveness_archive': {
            'factors': '[FILL]',
            'conclusion': '[FILL]',
        },

        # V4.2: 7 dimensions — English canonical keys, ✅✅ only for core+semi
        'matrix': {
            'stability':      {'score': '[FILL: ✅✅/✅/➖/❌/❌❌]', 'reasoning': r_stability},
            'sectional':      {'score': '[FILL: ✅✅/✅/➖/❌/❌❌]', 'reasoning': r_speed_engine},
            'race_shape':     {'score': '[FILL: ✅✅/✅/➖/❌/❌❌]', 'reasoning': r_race_shape},
            'jockey_trainer': {'score': '[FILL: ✅✅/✅/➖/❌/❌❌]', 'reasoning': r_jockey_trainer},
            'class_weight':   {'score': '[FILL: ✅/➖/❌]', 'reasoning': r_class_weight},
            'track':          {'score': '[FILL: ✅/➖/❌]', 'reasoning': r_track_surface},
            'form_line':      {'score': '[FILL: ✅/➖/❌]', 'reasoning': r_formline},
        },

        'base_rating': '[AUTO]',

        # ===== 微調因素 (Fine-Tune) =====
        # 從以下列表中揀選觸發代碼，唔好自由填寫！
        # Python 會驗證你嘅選擇係咪合法代碼。
        #
        # ⚠️ WALL-012 規則：direction=+/- 時，trigger_code 必須揀一個合法代碼（唔可以係「無」）
        #                   direction=無 時，trigger_code 必須係「無」
        #
        # ⚠️ 反雙重計算規則：微調因素必須係「未納入 7 維度」嘅額外因素！
        #   如果你嘅理由已經係某個矩陣維度嘅 ✅ 來源，咁你就係雙重計算！
        #   ❌ 錯誤：「超強組賽績」→ 已反映在「賽績線 ✅」
        #   ❌ 錯誤：「騎師引擎匹配」→ 已反映在「騎練訊號 ✅」
        #   ❌ 錯誤：「配備正面」→ 已反映在「騎練訊號 ✅」(V3: 配備已入騎練)
        #   ✅ 正確：PACE_FIT — 步速預測未納入 7 維度
        #   ✅ 正確：TRAINER_TRACK — 場地專精非標準騎練訊號
        'fine_tune': {
            'direction': '[FILL: +/-/無]',
            # 升級觸發（揀一個或填「無」）:
            #   PACE_FIT      — 步速形勢配合（今場步速強烈配合跑法）[安全：無對應維度]
            #   JOCKEY_FIT    — 人馬配搭契合（騎師引擎匹配+黃金組合）[⚠️ 檢查騎練訊號是否已✅]
            #   WEIGHT_SYNERGY — 負重/班次協同（升班輕磅≥4.5kg / 見習減磅）[⚠️ 檢查級數與負重是否已✅]
            #   GEAR_POSITIVE — 配備正面變動（首戴裝備針對已確認問題）[⚠️ 檢查騎練訊號是否已✅ — V3: 配備已入騎練]
            #   ❌ FORGIVE_BOUNCE 已移除 — 寬恕已納入矩陣(+1輔助✅)，不可再用微調加分
            #   TRAINER_TRACK — 練馬師場地專精（該場當季WR≥30%）[安全：非標準騎練訊號]
            #   MOMENTUM_3WIN — 連勝動力（3連勝90日內）[⚠️ 檢查狀態與穩定性是否已✅]
            #   MOMENTUM_2WIN — 連勝動力（2連勝60日內，需配合其他因素）[⚠️ 同上]
            #   WEIGHT_EXTREME — 負重極端優勢（全場最輕，差≥5kg）[⚠️ 檢查級數與負重是否已✅]
            #   MID_CLASS_LIGHT — 中高班輕磅（BM72+，≤54kg+≤5檔）[⚠️ 同上]
            #   SOFT_LIGHT     — Soft場超輕磅（≤56kg+≤8檔）[安全：跨維度]
            #   LAST_WIN       — 上仗勝出修正加分（滿足同場/同距/同場地≥2項）[⚠️ 檢查狀態是否已✅]
            # 降級觸發（揀一個或填「無」）:
            #   FATAL_DRAW     — 致命死檔（急彎窄場外檔10+）
            #   INSIDE_TRAP    — 內檔被困（1-2檔+非領放+≥10匹）
            #   INTERSTATE     — 跨州水土不服（首次跨州+負面變數）
            #   DISTANCE_JUMP  — 增程斷氣（400m+增程）
            #   WIN_REGRESSION — 贏馬回落（上仗贏+加磅+≥7歲）
            #   TOP_WEIGHT     — 頂磅斷尾（≥60kg無克服紀錄）
            #   PACE_AGAINST   — 引擎-步速逆轉（步速嚴重不利跑法）
            #   JOCKEY_CLASH   — 人馬配搭不合（騎師風格衝突）
            #   PACE_BURN      — 步速互燒前領崩潰（C欄+≥12匹+≥3前置）
            #   CONTRADICTION  — 存在未解決矛盾 → 封頂B
            'trigger_code': '[FILL: 代碼或「無」]',
            # trigger_detail 必須解釋呢個因素點解係「額外」嘅，而非重複矩陣已有嘅 ✅
            'trigger_detail': '[FILL: 一句話解釋點解呢個因素未被矩陣維度覆蓋]',
        },

        # ===== 覆蓋規則 =====
        # 參考 02g_override_chain.md 嘅規則代碼
        # 常見: TRIAL_CAP_B+ / WET_UNKNOWN / IRON_LEGS_FLOOR / RISK_CAP / 無
        'override': {'rule': '[FILL: 規則代碼或「無」]'},

        'final_rating': '[AUTO]',
        'core_logic': debut_core_logic,

        # ===== 🧠 PRE-ANALYSIS CHECKLIST (必須先填，引導思考) =====
        # LLM 必須逐項回答以下問題，答案會直接影響矩陣評分。
        # 呢個 checklist 嘅目的係迫使你喺評分前先認清馬匹嘅本質。
        'pre_analysis_checklist': {
            # Q1: 呢隻馬有幾多場正式比賽（唔計試閘）？
            # 0 = 初出馬, 1-2 = 經驗淺, 3+ = 有實戰數據
            'career_race_starts': career_starts,

            # Q2: 呢隻馬嘅核心競爭力證據來自邊度？
            # 只可以揀一個: 'race_form' / 'trial_only' / 'bloodline_only' / 'mixed'
            # ⚠️ 如果答案係 'trial_only'，代表你無任何正式賽事數據支持評級！
            #    → 自動觸發試閘虛火規則：最高評級 B（+血統+練馬師最高 B+）
            #    → 必須將下面 trial_illusion 設為 true
            'primary_evidence_source': '[FILL: race_form / trial_only / bloodline_only / mixed]',

            # Q3: 試閘表現對你嘅分析影響有幾大？（0-100%）
            # 如果 > 50%，你嘅分析可能過度依賴試閘。
            # 記住：試閘冇實戰壓力，僅為狀態參考。
            'trial_influence_pct': '[FILL: 0-100]',

            # Q4: 如果完全移除試閘數據，你仲會俾同一個評級嗎？
            # 'yes' = 試閘只係錦上添花，評級有其他支撐
            # 'no' = 試閘係評級嘅主要支柱 → 你需要降低評級
            # 'no_data' = 移除試閘後完全冇數據可用 → 必須 trial_illusion = true
            'grade_without_trial': '[FILL: yes / no / no_data]',
        },

        'advantages': '[FILL: 列舉2-3個主要優勢]',
        'disadvantages': '[FILL: 列舉2-3個致命風險或劣勢]',
        'stability_index': '[FILL]',
        'tactical_plan': {
            'expected_position': '[FILL]',  # Used by compile_analysis_template.py L322
            'race_scenario': '[FILL]',      # Used by compile_analysis_template.py L323
        },
        'dual_track': {'triggered': False},
        'underhorse': {'triggered': False, 'condition': '', 'reason': ''},

        # ===== OVERRIDE CHAIN INPUTS (V2 engine) =====
        'risk_markers': [],          # e.g. ['wide_barrier', 'top_weight', 'pace_dependent']
        'recent_3_top3': False if is_debut else '[FILL]',   # bool: has top-3 finish in last 3 starts (SIP-SL01)
        'debut_runner': is_debut,    # bool: Career=0 official starts; hard cap A-
        'is_2yo': False,             # bool: 2-year-old
        'distance_wall': False,      # bool: attempting distance never tried
        'long_spell': False,         # bool: >12 weeks between runs
        'trial_illusion': False,     # ⚠️ 如果 pre_analysis_checklist.primary_evidence_source = 'trial_only'
                                     #    或 grade_without_trial = 'no_data'，必須設為 True → 封頂 B+
        'wet_track_tier': 0,         # int: 0=N/A, 1-3=positive, 4=unknown, 5=risk
        'good_track_win_rate': None, # float: e.g. 0.11 = 11%
        'good_track_sample': 0,      # int: number of Good track runs
        'closer_cap_track': False,   # bool: Rosehill/MooneeV/Caulfield tight turn
        'rosehill_1200_traffic': False, # bool: closer + traffic history at Rosehill 1200m
        'momentum_level': '',        # 'positive'=2-win / 'strong'=3-win (SIP-RR17)
        'shape_3_adverse': False,   # bool: 3 consecutive adverse race shape
        'good_barrier': False,       # bool: barrier ≤6
        'rating_top3_field': False,  # bool: horse rating is top-3 in field (SIP-C14-3)
        'class_advantage_2bm': False, # bool: ≥2 BM class above field
    }


def main():
    parser = argparse.ArgumentParser(description='AU V9 Skeleton Generator')
    parser.add_argument('facts_path', help='Path to Facts.md')
    parser.add_argument('race_num', type=int, help='Race number')
    parser.add_argument('horse_num', type=int, help='Horse number to extract')
    parser.add_argument('--output', help='Output Logic.json path')
    args = parser.parse_args()

    with open(args.facts_path, 'r', encoding='utf-8') as f:
        facts_content = f.read()

    block = extract_horse_block(facts_content, args.horse_num)
    if not block:
        print(f'❌ Cannot find horse #{args.horse_num} in Facts')
        sys.exit(1)

    header = parse_horse_header(block)
    recent = parse_recent_race(block)
    trends = parse_trends(block)
    career = parse_career_info(block)
    horse_data = {**header, **recent, **trends, **career}

    skeleton = build_skeleton(horse_data)

    json_path = args.output or os.path.join(
        os.path.dirname(args.facts_path),
        f'Race_{args.race_num}_Logic.json'
    )

    if os.path.exists(json_path):
        with open(json_path, 'r', encoding='utf-8') as f:
            logic_data = json.load(f)
    else:
        logic_data = {
            'race_analysis': {'race_number': args.race_num, 'speed_map': {}},
            'horses': {},
        }

    if 'horses' not in logic_data:
        logic_data['horses'] = {}

    horse_key = str(args.horse_num)
    existing = logic_data['horses'].get(horse_key, {})
    if existing and '[FILL]' not in json.dumps(existing):
        print(f'✅ Horse #{args.horse_num} ({header.get("name", "")}) already analyzed, skipping.')
        sys.exit(0)

    # V9.6: MERGE mode — only fill missing/[FILL] fields, preserve existing analysis
    if existing:
        def merge_skeleton(base, fresh):
            """Recursively merge: only replace values that are missing or contain [FILL]."""
            merged = dict(base)
            for k, v in fresh.items():
                if k not in merged:
                    merged[k] = v
                elif isinstance(v, dict) and isinstance(merged.get(k), dict):
                    merged[k] = merge_skeleton(merged[k], v)
                elif isinstance(merged[k], str) and '[FILL' in merged[k]:
                    merged[k] = v  # Re-inject [FILL] template (keeps prompt text)
                # else: keep existing value (already filled by analyst)
            return merged
        logic_data['horses'][horse_key] = merge_skeleton(existing, skeleton)
    else:
        logic_data['horses'][horse_key] = skeleton

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(logic_data, f, ensure_ascii=False, indent=2)

    name = header.get('name', '?')
    print(f'✅ Created skeleton for Horse #{args.horse_num} ({name})')
    print(f'   → L400: {recent.get("raw_L400", "N/A")}')
    print(f'   → Position: {recent.get("last_run_position", "N/A")}')
    print(f'   → Barrier: {header.get("barrier", "N/A")}')


if __name__ == '__main__':
    main()
