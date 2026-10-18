"""EXP-20261018-09：賽績線標籤只睇標籤本身；中弱／弱 → neutral（64），唔開動未驗證嘅 weak 54。

現行（main）：「(強組比例…)」個「強」令極強以外全部 strong（78），weak 由來冇觸發（EXP-20261018-08）。
候選：極強 → elite 88；強／中強 → strong 78；中弱／弱 → neutral 64；無資料／空／N/A → unknown 60。
"""
ARM_NAME = "formline_label_neutral_weak"


def apply():
    from hkjc_racing_engine import engine_core

    def signal(self):
        text = self._clean(self._value("formline_strength") or "").split("(")[0].split("（")[0].strip()
        if not text or text == "N/A" or "無資料" in text:
            return "unknown"
        if "極強" in text:
            return "elite"
        if "強" in text:
            return "strong"
        if "弱" in text:
            return "neutral"
        return "neutral"

    engine_core.RacingEngine._formline_strength_signal = signal
