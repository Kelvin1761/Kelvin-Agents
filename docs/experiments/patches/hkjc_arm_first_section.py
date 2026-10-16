"""EXP-20261016-32: 最快第一段（e1_best）加入 段速表現 —— 預先登記固定分段。

輸入：Facts「全段速剖面」近 6 仗 Δ1（對 HKJC 標準時間，負 = 快），**按表頭搵 Δ1 欄**
（表格有 12／14 欄兩種）。m = 近 6 仗最細嘅 Δ1（最快嗰仗）。有效仗數 < 2 → 唔加減。

分段（秒）：
    m < −0.3        → +K
    −0.3 ≤ m < 0    → +K/2
    0 ≤ m < 0.3     → 0
    0.3 ≤ m < 0.6   → −K/4
    m ≥ 0.6         → −K/2
K 由 `WC_FIRST_SECTION_K` 傳入，只准 2 / 4 / 6。

接線：包住 orchestrator 嘅 `_load_formline_opponent_summaries`（score_race 用佢將 Facts 資料
合併入 `_data`），加 `first_section_min_delta`；再 patch `engine_core.SpeedScorer`
（top-level `speed` module，patch package 路徑會冇接通）。
"""
import os
import re
from pathlib import Path

K = float(os.environ["WC_FIRST_SECTION_K"])
assert K in (2.0, 4.0, 6.0), K
ARM_NAME = f"first_section_k{int(K)}"
NUM = re.compile(r"[+-]?\d+(?:\.\d+)?")


def facts_min_delta1(facts_path):
    text = Path(facts_path).read_text(encoding="utf-8")
    parts = re.split(r"^### 馬號 (\d+) — ", text, flags=re.M)
    out = {}
    for i in range(1, len(parts), 2):
        block = parts[i + 1]
        if "全段速剖面" not in block:
            continue
        col = None
        vals = []
        for line in block.split("全段速剖面")[1].split("🔧")[0].splitlines():
            c = [x.strip() for x in line.strip().strip("|").split("|")]
            if c and c[0] == "#":
                col = c.index("Δ1") if "Δ1" in c else None
                continue
            if col is not None and c and c[0].isdigit() and len(c) > col and NUM.fullmatch(c[col]):
                vals.append(float(c[col]))
        if len(vals) >= 2:
            out[parts[i]] = min(vals)
    return out


def band(m):
    if m < -0.3:
        return K, "第一段曾快過標準 >0.3s"
    if m < 0:
        return K / 2, "第一段曾快過標準"
    if m < 0.3:
        return 0.0, "第一段接近標準"
    if m < 0.6:
        return -K / 4, "第一段偏慢"
    return -K / 2, "第一段明顯慢"


def apply():
    import hkjc_auto_orchestrator as orch
    from hkjc_racing_engine import engine_core
    from hkjc_racing_engine.scoring import clip_score

    load = orch._load_formline_opponent_summaries

    def wrapped(race_file, race_context, horses):
        summaries = load(race_file, race_context, horses)
        rn = re.search(r"Race_(\d+)_Logic", Path(race_file).name)
        facts = sorted(Path(race_file).parent.glob(f"* Race {rn.group(1)} Facts.md")) if rn else []
        if facts:
            for num, m in facts_min_delta1(facts[0]).items():
                key = num if num in horses else (int(num) if int(num) in horses else None)
                if key is not None:
                    summaries = dict(summaries)
                    summaries.setdefault(key, {})
                    summaries[key] = {**summaries[key], "first_section_min_delta": m}
        return summaries

    orch._load_formline_opponent_summaries = wrapped

    cls = engine_core.SpeedScorer
    original = cls.compute

    def compute(self):
        score, note = original(self)
        m = self._data().get("first_section_min_delta")
        if m is None:
            return score, note
        delta, why = band(float(m))
        self.detail = list(getattr(self, "detail", []) or []) + [
            {"factor": "最快第一段", "value": f"{float(m):+.2f}s", "delta": round(delta, 2), "why": why}]
        return clip_score(score + delta), note

    cls.compute = compute
