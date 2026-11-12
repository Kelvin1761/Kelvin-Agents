"""EXP-20261112-07 arm：段速維度入面，近仗表現逐仗按今仗負磅換算。

背景：`finish_time_adj`（步速修正偏差）= 完成時間 − 頭馬時間 = 輸幾多秒（inject_hkjc_fact_anchors.py V5.1），
引擎用近 3 仗平均分四級（<0.3 +8／<0.8 +1／<1.3 −4／≥1.3 −8）。呢個數完全冇理當時負磅。

換算（跑之前寫死，冇擬合）：
  FT   每仗偏差 += 0.01123 × 路程(km) ×（今仗實際負磅 − 嗰仗實際負磅）秒
       —— 0.01123 s/km／磅 係 EXP-20261112-06 只用 2026-05-03 之前賽果估嘅值。近 3 仗平均後照舊四級門檻。
       賽績檔賽日前嘅仗數要同 Logic 偏差串嘅仗數一樣先換算（對唔上 = 有仗冇標準時間，唔郁嗰匹）。
  L400 同 EXP-20261112-05 一樣：上仗 L400 += C(上仗路程) × 負磅差，C = 0.007／0.016／0.021
  WC_EXP_SEC_PARTS = "ft"（只換算完成時間偏差）或 "ft+l400"（兩樣都換算 = 主 arm）
  判決：hkjc_eval_harness compare --stage4 fixed_rule；兩個都報，"ft+l400" 係主 arm，"ft" 係 ablation
"""
import os
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
PARTS = os.environ["WC_EXP_SEC_PARTS"]
ARM_NAME = f"sectional_weight_converted_{PARTS}"
BETA_KM = 0.01123


def l400_coef(dist):
    return 0.007 if dist <= 1200 else 0.016 if dist < 1800 else 0.021


def level(avg):
    if avg < 0.3:
        return "✅ 步速修正後仍具競爭力"
    if avg < 0.8:
        return "➖ 步速修正後接近平均"
    if avg < 1.3:
        return "⚠️ 步速修正後仍偏慢"
    return "❌ 步速修正後明顯落後"


def apply():
    import hkjc_auto_orchestrator as orch
    from hkjc_l400_weight_screen import RUN
    from hkjc_racing_engine.features.speed import SpeedScorer
    from hkjc_racing_engine.scoring import parse_float

    original = orch._align_runner_headers
    HEAD = re.compile(r"\[(\d+)\]\s+(\d{2}/\d{2}/\d{4})\s*\|[^|\n]*\|\s*\S+\s+\"[^\"]*\"\s+(\d{3,4})\s+\S+\s*\n[^\n]*負磅:\s*(\d+)")

    def runs_for(md, race_no, day):
        hits = sorted(p for p in md.glob("*賽績.*") if p.suffix in (".md", ".txt") and re.search(rf"Race[ _]{race_no}\b", p.name))
        out = {}
        if not hits:
            return out
        for block in re.split(r"\n(?=馬號:\s*\d+)", hits[0].read_text(encoding="utf-8")):
            m = re.match(r"馬號:\s*(\d+)", block)
            w = re.search(r"\n負磅:\s*(\d+)", block)
            if not m or not w:
                continue
            runs = []
            for r in HEAD.finditer(block):
                d = datetime.strptime(r.group(2), "%d/%m/%Y").date()
                if d < day:
                    runs.append((d, int(r.group(3)), int(r.group(4))))
            l4 = {}
            for r in RUN.finditer(block):
                secs = [float(x) for x in re.findall(r"\d+\.\d+", r.group(10))]
                if secs:
                    l4[datetime.strptime(r.group(2), "%d/%m/%Y").date()] = secs[-1]
            out[int(m.group(1))] = (int(w.group(1)), sorted(runs, reverse=True), l4)
        return out

    def patched(logic_path, race_context, horses):
        original(logic_path, race_context, horses)
        md = Path(logic_path).parent
        m = re.match(r"(\d{4}-\d{2}-\d{2})", md.name)
        if not m:
            return
        info = runs_for(md, int(race_context.get("race_number")), datetime.strptime(m.group(1), "%Y-%m-%d").date())
        for num, horse in horses.items():
            e = info.get(int(num)) if isinstance(horse, dict) and str(num).isdigit() else None
            if not e or not e[1]:
                continue
            today, runs, l4 = e
            data = horse.setdefault("_data", {})
            vals = re.findall(r"[+-]\d+\.\d+s", str(data.get("finish_time_adj") or ""))
            lvl = re.search(r"修正平均:\s*([+-]?\d+\.\d+)s", str(data.get("finish_time_adj_level") or ""))
            if lvl and vals and len(vals) == len(runs[:6]) and len(vals) >= 2:
                use = runs[:min(3, len(vals))]
                shift = sum(BETA_KM * d / 1000.0 * (today - w) for _dt, d, w in use) / len(use)
                data["exp1112_ft_avg"] = float(lvl.group(1)) + shift
            raw = parse_float(data.get("raw_l400"))
            d0, dist0, w0 = runs[0]
            if raw is not None and d0 in l4 and abs(l4[d0] - raw) <= 0.02:
                data["exp1112_l400_shift"] = l400_coef(dist0) * (today - w0)

    orch._align_runner_headers = patched
    base_data = SpeedScorer._data

    def _data(self):
        data = base_data(self)
        out = None
        avg = data.get("exp1112_ft_avg")
        if avg is not None:
            out = dict(data)
            out["finish_time_adj_level"] = f"{level(float(avg))} (近仗修正平均按今仗負磅換算: {float(avg):+.2f}s)"
        if "l400" in PARTS and data.get("exp1112_l400_shift") is not None and parse_float(data.get("raw_l400")) is not None:
            out = out or dict(data)
            out["raw_l400"] = f"{parse_float(data.get('raw_l400')) + float(data['exp1112_l400_shift']):.2f}"
        return out or data

    SpeedScorer._data = _data
