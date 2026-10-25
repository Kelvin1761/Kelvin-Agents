"""EXP-20261025-08 arm B: L400 由「上仗」改做「近 6 仗最快」（Kelvin 2026-10-25 建議）。

輸入：Facts「完整賽績檔案（近 6 場）」每仗嘅 L400 欄，**按表頭搵欄**。
`raw_l400` 換成近 6 仗最細 L400；SpeedScorer 門檻同權重完全唔變（22.4／23.0／23.6／24.0／24.6）。
近 6 仗冇任何 L400 → 保留原本 `raw_l400`（即唔郁）。

接線：包住 `_load_formline_opponent_summaries`，覆寫 summaries 嘅 `raw_l400`
（score_race 會將 summaries 合併入 `_data`）。接線證明：races_with_ranking_change > 0。
"""
import re
from pathlib import Path

ARM_NAME = "best_l400"
NUM = re.compile(r"\d{2}\.\d{1,2}")


def facts_best_l400(facts_path):
    text = Path(facts_path).read_text(encoding="utf-8")
    parts = re.split(r"^### 馬號 (\d+) — ", text, flags=re.M)
    out = {}
    for i in range(1, len(parts), 2):
        block = parts[i + 1]
        if "完整賽績檔案" not in block:
            continue
        col, vals = None, []
        for line in block.split("完整賽績檔案")[1].splitlines()[1:]:
            if col is not None and not line.strip().startswith("|"):
                break  # end of this table
            c = [x.strip() for x in line.strip().strip("|").split("|")]
            if c and c[0] == "#":
                col = c.index("L400") if "L400" in c else None
                continue
            if col is not None and c and c[0].isdigit() and len(c) > col and NUM.fullmatch(c[col]):
                vals.append(float(c[col]))
        if vals:
            out[parts[i]] = min(vals)
    return out


def apply():
    import hkjc_auto_orchestrator as orch

    load = orch._load_formline_opponent_summaries

    def wrapped(race_file, race_context, horses):
        summaries = load(race_file, race_context, horses)
        rn = re.search(r"Race_(\d+)_Logic", Path(race_file).name)
        facts = sorted(Path(race_file).parent.glob(f"* Race {rn.group(1)} Facts.md")) if rn else []
        if facts:
            summaries = dict(summaries)
            for num, best in facts_best_l400(facts[0]).items():
                key = num if num in horses else (int(num) if int(num) in horses else None)
                if key is not None:
                    summaries[key] = {**summaries.get(key, {}), "raw_l400": best}
        return summaries

    orch._load_formline_opponent_summaries = wrapped
