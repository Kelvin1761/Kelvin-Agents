"""研究計劃第 2b 步：現有訊號審計 —— 逐組關掉（設中性），量邊個係噪音、邊個方向錯。

用 WC_AUDIT_GROUP 揀組（一次一組）。權重表原地改（in-place），所以 `from scoring import X` 嘅模組都跟住變。
組（預先登記，跑之前寫死；唔准睇完結果先加組）：
  speed_l400        段速 L400 五級門檻加減分 → 0
  speed_finish      完成時間（步速修正）等級加減分 → 0
  speed_l400_trend  L400 趨勢加減分 → 0
  speed_engine      引擎類型加減分 → 0
  speed_dist        段速入面嘅路程配合 ±1.5 → 0
  ts_history        人馬歷史 ±4／±2 → 0
  ts_combo          騎練組合 ±4／±2 → 0
  ts_distance       騎師／練馬師同程 → 0
  ts_change         換騎 −1.5 → 0
  class_micro       級數微調（生涯標記、出賽數、季內上名）→ 0
  health_medical    醫療加減分 → 0
  health_days       相隔日數加減分 → 0
  health_weight     體重變化／波幅加減分 → 0
  shape_fit         形勢：走位配合度／PI（沙田 fit 同跑馬地 delta）加減分 → 0
  shape_robust      形勢 ±10 收窄 → 取消（legacy_unbounded）
  sip_off           SIP-C +1.0 → 取消
  consistency_off   逐仗連輸距 consistency override → 取消（返回原本計法）
  formline_fix      【正確性】賽績線強度只讀括號前標籤（「中弱 (強組比例…)」唔再因為有「強」字攞 78）
  l400_coef         【正確性】L400 負磅係數改做實測 0.0077／0.0085／0.0060（EXP-20261114-01）
"""
import os

GROUP = os.environ.get("WC_AUDIT_GROUP", "")
ARM_NAME = f"audit_{GROUP}"


def _zero(d, prefixes=(), keys=()):
    n = 0
    for k in list(d):
        if k in keys or any(k.startswith(p) for p in prefixes):
            d[k] = 0.0
            n += 1
    if n == 0:
        raise RuntimeError(f"audit {GROUP}: 冇 key 被改 —— 冇接通")


def apply():
    from hkjc_racing_engine import scoring as s
    g = GROUP
    if g == "speed_l400":
        _zero(s.SPEED_MICRO_WEIGHTS, prefixes=("l400_22", "l400_23", "l400_24"))
    elif g == "speed_finish":
        _zero(s.SPEED_MICRO_WEIGHTS, prefixes=("finish_",))
    elif g == "speed_l400_trend":
        _zero(s.SPEED_MICRO_WEIGHTS, prefixes=("l400_trend_",))
    elif g == "speed_engine":
        _zero(s.SPEED_MICRO_WEIGHTS, prefixes=("engine_",))
    elif g == "speed_dist":
        _zero(s.SPEED_MICRO_WEIGHTS, keys=("dist_match_bonus", "dist_unproven_pen"))
    elif g == "ts_history":
        _zero(s.TRAINER_SIGNAL_CONTEXT_WEIGHTS, prefixes=("horse_history_",))
    elif g == "ts_combo":
        _zero(s.TRAINER_SIGNAL_CONTEXT_WEIGHTS, keys=("combo_elite", "combo_positive", "combo_negative"))
    elif g == "ts_distance":
        _zero(s.TRAINER_SIGNAL_CONTEXT_WEIGHTS, prefixes=("jockey_distance_", "trainer_distance_"))
    elif g == "ts_change":
        _zero(s.TRAINER_SIGNAL_CONTEXT_WEIGHTS, keys=("jockey_change_negative",))
    elif g == "class_micro":
        _zero(s.CLASS_MICRO_WEIGHTS, prefixes=("",))
    elif g == "health_medical":
        _zero(s.HORSE_HEALTH_CONTEXT_WEIGHTS, prefixes=("medical_",))
    elif g == "health_days":
        _zero(s.HORSE_HEALTH_CONTEXT_WEIGHTS, prefixes=("days_",))
    elif g == "health_weight":
        _zero(s.HORSE_HEALTH_CONTEXT_WEIGHTS, prefixes=("weight_", "span_"))
    elif g == "shape_fit":
        _zero(s.RACE_SHAPE_FIT_WEIGHTS, prefixes=("match", "mismatch", "active", "pi_"))
        _zero(s.RACE_SHAPE_CONTEXT_DELTA_WEIGHTS, prefixes=("",))
    elif g == "shape_robust":
        os.environ["WC_HKJC_RACE_SHAPE_ROBUSTNESS"] = "legacy_unbounded"
    elif g == "sip_off":
        import hkjc_auto_orchestrator as orch
        orch._apply_sip_enhancements = lambda horses: None
    elif g == "consistency_off":
        from hkjc_racing_engine import engine_core
        cls = engine_core.RacingEngine
        if not hasattr(cls, "_consistency_from_runs"):
            raise RuntimeError("audit consistency_off: 搵唔到 _consistency_from_runs —— 冇接通")
        cls._consistency_from_runs = lambda self: None
    elif g == "formline_fix":
        from hkjc_racing_engine import engine_core
        cls = engine_core.RacingEngine
        orig = cls._formline_strength_signal

        def fixed(self):
            text = self._clean(self._value("formline_strength") or "").split("(")[0].split("（")[0]
            if "極強" in text:
                return "elite"
            if "弱" in text:
                return "weak"
            if "強" in text:
                return "strong"
            if text.strip() and text.strip() not in ("N/A", "無資料"):
                return "neutral"
            return "unknown"
        cls._formline_strength_signal = fixed
        cls._formline_strength_signal_original = orig
    elif g == "l400_coef":
        s.L400_WEIGHT_SECONDS_PER_LB = ((1200, 0.0077), (1799, 0.0085), (None, 0.0060))
    else:
        raise RuntimeError(f"未知 audit 組：{g!r}")
