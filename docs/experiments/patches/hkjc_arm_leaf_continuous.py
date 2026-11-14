"""Kelvin 2026-11-15：19 組訊號公式重建 —— 第一批：將階梯式 leaf 改連續（EXP-20261115-03）。

WC_LEAF_ARM 揀（預先登記，fixed_rule，冇由數據 fit；錨點全部用現行分數）：
  form    近績分：名次先換算做「14 匹場次等效名次」r14 = 1 + (名次 − 1)/(出賽數 − 1) × 13（出賽數由 formguide「名次: P / F」），
          再喺現行錨點之間線性插值：1→100、2→85、3→75、4.5→60、6→40（之後 40）；冇出賽數嘅仗用現行查表
  l400    段速 L400 絕對值：現行五級改連續 —— 錨點 (22.4, +8.62)、(23.0, +4.55)、(23.6, +3.03)、(23.8, 0)、(24.0, −0.73)、(24.6, −5.64)，
          兩端平（用換算負磅之後嘅 L400，同現行一樣）
  finish  段速完成時間：有「近 N 仗修正平均 X 秒」就連續 —— 錨點 (0.15, +6.52)、(0.55, +1.42)、(1.05, −4.0)、(1.55, −8.0)，兩端平；
          冇數值嘅（持續／略快於標準）照現行
判法：docs/model-evaluation-contract.md「HKJC 歷史回放尺 v4」。
"""
import os
import re

import numpy as np

ARM = os.environ.get("WC_LEAF_ARM", "")
ARM_NAME = f"leaf_continuous_{ARM}"
FORM_ANCH = ((1, 100.0), (2, 85.0), (3, 75.0), (4.5, 60.0), (6, 40.0))
L400_ANCH = ((22.4, 8.62), (23.0, 4.55), (23.6, 3.03), (23.8, 0.0), (24.0, -0.73), (24.6, -5.64))
FIN_ANCH = ((0.15, 6.52), (0.55, 1.42), (1.05, -4.0), (1.55, -8.0))


def interp(x, anch):
    xs, ys = zip(*anch)
    return float(np.interp(x, xs, ys))


def _apply_form():
    import hkjc_auto_orchestrator as orch
    from hkjc_racing_engine.features import form as form_mod
    # 出賽數喺 formguide「名次: P / F」：喺 past_runs 解析／attach 嗰步寫入 _data["form_fields"]
    orig_parse = orch.past_runs.parse_formguide

    def parse(text):
        out = orig_parse(text)
        for block in re.split(r"\n(?=馬號:\s*\d+)", str(text or "")):
            m = re.match(r"\s*馬號:\s*(\d+)", block)
            if not m or int(m.group(1)) not in out:
                continue
            fields = [(int(p), int(f)) for p, f in re.findall(r"名次:\s*(\d+)\s*/\s*(\d+)", block)]
            out[int(m.group(1))]["form_fields"] = fields
        return out
    orch.past_runs.parse_formguide = parse
    orig_pr_attach = orch.past_runs.attach

    def pr_attach(formguide_text, horses, race_context, race_date):
        n = orig_pr_attach(formguide_text, horses, race_context, race_date)
        parsed = parse(formguide_text)
        for num, h in horses.items():
            if isinstance(h, dict) and str(num).isdigit() and int(num) in parsed:
                h.setdefault("_data", {})["form_fields"] = parsed[int(num)].get("form_fields", [])
        return n
    orch.past_runs.attach = pr_attach
    orig_compute = form_mod.FormScorer.compute

    def compute(self):
        res = orig_compute(self)
        data = self.horse_data.get("_data") or {}
        fields = data.get("form_fields") or []
        form = str(self.horse_data.get("last_6_finishes") or "")
        ranks = [int(p.split("/")[0]) for p in form.replace("-", " ").split() if p.split("/")[0].isdigit() and int(p.split("/")[0]) > 0]
        if not ranks or len(fields) < len(ranks[:6]) or [p for p, _ in fields[:len(ranks[:6])]] != ranks[:6]:
            return res
        pdf = data.get("pdf_overseas_races") or []
        if pdf:
            return res          # 有海外往績混合嘅照現行（避免改變海外部分）
        scores = []
        for pos, fld in fields[:6]:
            r14 = 1 + (pos - 1) / max(fld - 1, 1) * 13
            scores.append(interp(r14, FORM_ANCH))
        w = [1.0 / (i + 1) for i in range(len(scores))]
        self.score = sum(s * x for s, x in zip(scores, w)) / sum(w)
        return (self.score, res[1]) if isinstance(res, tuple) else res
    form_mod.FormScorer.compute = compute


def _apply_speed(kind):
    from hkjc_racing_engine.features import speed as sp
    orig = sp.SpeedScorer._compute_core

    def core(self):
        score, note = orig(self)
        rows = getattr(self, "detail", []) or []
        data = self._data()
        delta = 0.0
        for r in rows:
            if kind == "l400" and r.get("factor") == "L400 絕對值":
                m = re.match(r"(\d{2}\.\d{2})s", str(r.get("value") or ""))
                if m:
                    new = interp(float(m.group(1)), L400_ANCH)
                    delta += new - float(r.get("delta") or 0)
                    r["delta"] = round(new, 2)
            if kind == "finish" and r.get("factor") == "輸頭馬差距":
                m = re.search(r"近\s*\d+\s*仗修正平均[:：]\s*([+-]?\d+(?:\.\d+)?)s", str(data.get("finish_time_adj_level") or ""))
                if m:
                    new = interp(float(m.group(1)), FIN_ANCH)
                    delta += new - float(r.get("delta") or 0)
                    r["delta"] = round(new, 2)
        # 段速資料唔齊（打回 60）或者用海外替代指標：唔做連續化
        if not delta or str(note).startswith(("Sectional data incomplete", "海外賽績速度替代指標")):
            return score, note
        from hkjc_racing_engine.scoring import clip_score
        return clip_score(score + delta), note
    sp.SpeedScorer._compute_core = core


def apply():
    if ARM == "form":
        _apply_form()
    elif ARM in ("l400", "finish"):
        _apply_speed(ARM)
    else:
        raise RuntimeError(f"未知 WC_LEAF_ARM：{ARM!r}")
