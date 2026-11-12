"""EXP-20261112-05 arm：段速分「L400 絕對值」按今仗負磅調整，C 跟上仗路程。

調整後 L400 = 上仗 L400 + C(上仗路程) ×（今仗實際負磅 − 上仗實際負磅）。

預先登記（跑之前寫死）：
  C = 0.007 秒／磅（上仗 ≤1200m）、0.016（1201–1799m）、0.021（≥1800m）
    —— EXP-20261112-04 同馬比較量出嚟嘅三個點估計，原封照用，唔再調。
    呢三個數係由 L400 對負磅估出嚟（唔係由上名結果），但用嘅往績同評估語料重疊，所以唔算完全樣本外。
  上仗 = 賽績檔賽日前最近一仗，L400 同 Logic `raw_l400` 相差 ≤0.02s 先調
  判決：hkjc_eval_harness compare --stage4 fixed_rule，只跑呢一個 arm
"""
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
ARM_NAME = "l400_weight_adjusted_by_distance"


def coef(dist):
    return 0.007 if dist <= 1200 else 0.016 if dist < 1800 else 0.021


def apply():
    import hkjc_auto_orchestrator as orch
    from hkjc_l400_weight_screen import RUN
    from hkjc_racing_engine.features.speed import SpeedScorer
    from hkjc_racing_engine.scoring import parse_float

    original = orch._align_runner_headers

    def last_runs(md, race_no, day):
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
            for r in RUN.finditer(block):
                d = datetime.strptime(r.group(2), "%d/%m/%Y").date()
                secs = [float(x) for x in re.findall(r"\d+\.\d+", r.group(10))]
                if d < day and secs:
                    runs.append((d, int(r.group(5)), int(r.group(7)), secs[-1]))
            if runs:
                out[int(m.group(1))] = (int(w.group(1)), max(runs))
        return out

    def patched(logic_path, race_context, horses):
        original(logic_path, race_context, horses)
        md = Path(logic_path).parent
        m = re.match(r"(\d{4}-\d{2}-\d{2})", md.name)
        if not m:
            return
        info = last_runs(md, int(race_context.get("race_number")), datetime.strptime(m.group(1), "%Y-%m-%d").date())
        for num, horse in horses.items():
            e = info.get(int(num)) if isinstance(horse, dict) and str(num).isdigit() else None
            if not e:
                continue
            today, (_d, dist, w, l400) = e
            data = horse.setdefault("_data", {})
            raw = parse_float(data.get("raw_l400"))
            if raw is None or abs(l400 - raw) > 0.02:
                continue
            data["exp1112_l400_shift"] = coef(dist) * (today - w)

    orch._align_runner_headers = patched
    base_data = SpeedScorer._data

    def _data(self):
        data = base_data(self)
        shift = data.get("exp1112_l400_shift")
        raw = parse_float(data.get("raw_l400"))
        if shift is None or raw is None:
            return data
        out = dict(data)
        out["raw_l400"] = f"{raw + float(shift):.2f}"
        return out

    SpeedScorer._data = _data
