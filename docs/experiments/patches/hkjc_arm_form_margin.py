"""EXP-20261123-12 預先登記 arm（Kelvin 2026-11-23：「近績分只睇名次（唔理輸幾遠）…要改 leaf 計法、重建回放 —— go ahead」）。
寫喺跑之前。改 `features/form.py` FormScorer 嘅「每仗分」，其餘（1/k 加權、近 6 仗、海外往績、冇往績 = 60）一律唔郁。

現行：名次分 1名100、2名85、3名75、4–5名60、其餘40（唔理輸幾遠、班次、出馬數）。
WC_EXP_FORM：
  F1  輸馬位：頭馬 100；其他 = 100 − 8 × min(輸馬位, 7.5)（輸 1 個馬位 92、2 個 84、7.5 個或以上 40 —— 同現行上下限一樣，冇擬合）
  F2  F1 ＋ 班次：每仗 + 5 ×（今仗班次級數 − 嗰仗班次級數），上下限 ±10，最後 clip 0–100
      級數：一級賽 0、二級賽 1、三級賽 2、第一班 3、第二班 4、第三班 5、第四班 6、第五班 7、其他（4R／新馬…）= 今仗級數（唔加減）
      即係喺高過今仗嘅班跑出嚟嘅表現加分（例如今仗二級賽，之前一級賽跑第 3 +5）。5 分 = 一級 ≈ 現行名次分一級距離嘅一半，冇擬合。
  F3  （EXP-20261124-13，Kelvin 2026-11-24「近績分應該睇埋班次」；寫喺跑之前）名次分照現行（1名100、2名85、3名75、4–5名60、其他40，唔計輸馬位），
      每仗再 + 5 ×（今仗班次級數 − 嗰仗班次級數），封頂 ±10，clip 0–100（同 F2 嘅班次部分一樣，但唔郁名次分）。
      判：兩次 harness（現行 vs F3，同一份 code）v5.2 dev／holdout PASS ＋ 兩窗頭二入頭三 Δ ≥ 0；11-22 否決。
  F4  （Kelvin 2026-11-24「班次應該 blend 埋名次，高班輸遠唔應該俾太高分」；寫喺跑之前）同 F3，但班次調整 ×
      max(0, 1 − 輸馬位／6)（頭馬 1、輸 3 個馬位 0.5、輸 ≥6 個馬位 0；解唔到馬位 = 0.5）。判同 F3（F3 同 F4 都同現行比）。
輸馬位嚟自 `_data.recent_6_detail`（「第N仗(日期 班次): 名次 馬位」，同 last_6_finishes 同一批仗）；馬位文字：
  鼻位 0.05、短馬頭位 0.1、馬頭位 0.2、頭位 0.2、頸位 0.3、數字（1-1/4 = 1.25）；解唔到 = 用現行名次分（唔郁嗰仗）。
判（由 replay 腳本做）：兩次 harness（現行 vs arm）喺同一批回放賽日，差距加落 live base（SW），v5.2 dev PASS ＋ 頭二入頭三 Δ ≥ 0；
holdout 第一次睇（呢個家族未睇過）；11-22 否決。
"""
import os
import re

ARM_NAME = f"form_margin_{os.environ.get('WC_EXP_FORM', 'F1')}"
VARIANT = os.environ.get("WC_EXP_FORM", "F1")
WORDS = (("短馬頭位", 0.1), ("馬頭位", 0.2), ("鼻位", 0.05), ("頸位", 0.3), ("頭位", 0.2))
CLASS = (("一級賽", 0), ("二級賽", 1), ("三級賽", 2), ("第一班", 3), ("第二班", 4), ("第三班", 5), ("第四班", 6), ("第五班", 7))


def lengths(text):
    t = str(text or "").strip()
    for w, v in WORDS:
        if w in t:
            return v
    m = re.fullmatch(r"(\d+)(?:-(\d+)/(\d+))?|(\d+)/(\d+)", t)
    if not m:
        return None
    if m.group(4):
        return int(m.group(4)) / int(m.group(5))
    return int(m.group(1)) + (int(m.group(2)) / int(m.group(3)) if m.group(2) else 0.0)


def class_level(text):
    for w, v in CLASS:
        if w in str(text or ""):
            return v
    return None


def runs(detail):
    out = []
    for part in str(detail or "").split("|"):
        m = re.search(r"\(([^)]*)\)\s*[:：]\s*(\d+)名\s*(\S+)?", part)
        if m:
            cls = m.group(1).split()[-1] if m.group(1).split() else ""
            out.append((int(m.group(2)), lengths(m.group(3)), class_level(cls)))
    return out


def apply():
    from hkjc_racing_engine.features import form as F
    from hkjc_racing_engine import scoring
    orig = F.FormScorer.compute

    def compute(self):
        score, reason = orig(self)
        data = self.horse_data.get("_data") if isinstance(self.horse_data.get("_data"), dict) else {}
        rr = runs(data.get("recent_6_detail"))
        if not rr or score == 60.0 and reason == "No recent form (Neutral)":
            return score, reason
        w = scoring.FORM_MICRO_WEIGHTS
        today = class_level((self.race_context or {}).get("race_class"))
        num = den = 0.0
        for i, (pos, L, cl) in enumerate(rr[:6]):
            if VARIANT in ("F3", "F4"):
                s = w["rank_1"] if pos == 1 else w["rank_2"] if pos == 2 else w["rank_3"] if pos == 3 else w["rank_4_5"] if pos <= 5 else w["rank_other"]
            elif pos == 1:
                s = 100.0
            elif L is None:
                s = w["rank_2"] if pos == 2 else w["rank_3"] if pos == 3 else w["rank_4_5"] if pos <= 5 else w["rank_other"]
            else:
                s = 100.0 - 8.0 * min(L, 7.5)
            if VARIANT in ("F2", "F3", "F4") and today is not None and cl is not None:
                adj = max(-10.0, min(10.0, 5.0 * (today - cl)))
                if VARIANT == "F4":
                    lens = 0.0 if pos == 1 else L
                    adj *= 0.5 if lens is None else max(0.0, 1.0 - min(lens, 6.0) / 6.0)
                s += adj
            s = max(0.0, min(100.0, s))
            num += s / (i + 1); den += 1.0 / (i + 1)
        if not den:
            return score, reason
        self.score = num / den
        return self.score, reason

    F.FormScorer.compute = compute
