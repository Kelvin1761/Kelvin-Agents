"""AU 表現評分（EXP-20261122-05）—— 由賽前 Formguide 往績計「輸距＋負磅」表現（PR1）。唯一計算位置。

每仗（只用日期早過今仗嘅正式賽；試閘唔計）：
  每馬位磅數 LPL = 3.0 ×（1000 ÷ 路程）^0.75；輸距 m（頭馬 = −勝距，取下一行第二名馬位），限 [−5, 15]
  P = −LPL·m + 2.2 ×（負磅 kg − 57）
PR1 = 最近 6 仗 P 嘅加權平均（1／0.8／0.6／0.4／0.3／0.2）；冇往績 = None。
"""
from __future__ import annotations

import re

HEAD = re.compile(r"^\[(\d+)\]\s+(.+?) \((\d+)\)\s*$", re.M)
RUN = re.compile(r"^(?P<venue>.+?) R\d+ (?P<date>\d{4}-\d{2}-\d{2}) (?P<dist>\d+)m cond:\S* \$(?P<prize>\d+) .*? "
                 r"(?P<wt>\d+(?:\.\d+)?)kg .*?margin:(?P<m>[\d.]+)L starters:(?P<s>\d+) finish:(?P<f>\d+)/\d+", re.M)
SECOND = re.compile(r"2-[^,]*?\([\d.]+kg\)\s*([\d.]+)L")
WEIGHTS = (1.0, 0.8, 0.6, 0.4, 0.3, 0.2)


def run_performances(section: str, before: str) -> list[float]:
    lines = section.splitlines()
    runs = []
    for i, line in enumerate(lines):
        if "(TRIAL)" in line:
            continue
        m = RUN.match(line.strip())
        if not m or m.group("date") >= before or int(m.group("prize")) <= 0:
            continue
        margin = float(m.group("m"))
        if int(m.group("f")) == 1:
            nxt = SECOND.search(lines[i + 1] if i + 1 < len(lines) else "")
            margin = -float(nxt.group(1)) if nxt else 0.0
        margin = max(-5.0, min(15.0, margin))
        lpl = 3.0 * (1000.0 / int(m.group("dist"))) ** 0.75
        runs.append((m.group("date"), -lpl * margin + 2.2 * (float(m.group("wt")) - 57.0)))
    runs.sort(reverse=True)
    return [p for _d, p in runs[:6]]


def pr1(section: str, before: str) -> float | None:
    perf = run_performances(section, before)
    if not perf:
        return None
    w = WEIGHTS[:len(perf)]
    return sum(p * x for p, x in zip(perf, w)) / sum(w)


def formguide_sections(text: str) -> dict[int, str]:
    heads = list(HEAD.finditer(text))
    return {int(h.group(1)): text[h.start(): heads[i + 1].start() if i + 1 < len(heads) else len(text)]
            for i, h in enumerate(heads)}
