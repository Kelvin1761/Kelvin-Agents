"""Kelvin 2026-11-16「方向 b 係咪要睇晒 6 仗，唔止上兩仗？」：近 6 仗（有報告嘅場次）事件報告，喺 live I1（已含上仗 W／M）之上嘅殘差。
上仗要有報告。「之前」= 上仗之前嘅 2–6 仗（上仗已經由 live／標籤處理）。
用法：python3 diag_last6.py <live dump I1> <old_incidents.json>
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import diag_round3 as d  # noqa: E402
from diag import CATS  # noqa: E402
W = CATS["走外疊冇遮擋"]; M = CATS["醫療（喘鳴／流鼻血／心律／跛）"]; B = d.BLK; SL = d.SLOW
R = f"{d.INSTR}|{d.RIDE_Q}|{d.RIDE_WARN}"


def features(prev):
    rep = [v[2] for v in prev if v[2] is not None]
    if not prev or prev[-1][2] is None or len(rep) < 3:
        return None
    last, before = rep[-1], rep[-6:-1]          # 上仗；之前 2–6 仗（最多 5 場）
    h = d.has
    cnt = lambda p: sum(h(p, s) for s in before)
    # 時間衰減：上上仗 1、再前 0.5、0.33…（只計之前 2–6 仗）
    dec = lambda p: sum(h(p, s) / (i + 1) for i, s in enumerate(reversed(before)))
    w6 = cnt(W)
    return {
        "走外疊：2–6 仗 ≥1 次（上仗冇）": w6 >= 1 and not h(W, last),
        "走外疊：2–6 仗 ≥2 次（上仗冇）": w6 >= 2 and not h(W, last),
        "走外疊：只係 3–6 仗有（上仗、上上仗冇）": (not h(W, last)) and (not h(W, before[-1])) and w6 >= 1,
        "走外疊：衰減分 ≥1（上仗冇）": dec(W) >= 1 and not h(W, last),
        "走外疊：近 6 仗合共 ≥3 次": (w6 + h(W, last)) >= 3,
        "醫療：3–6 仗有（上仗、上上仗冇）": (not h(M, last)) and (not h(M, before[-1])) and cnt(M) >= 1,
        "受阻：2–6 仗 ≥2 次": cnt(B) >= 2,
        "受阻：近 6 仗 ≥3 次": (cnt(B) + h(B, last)) >= 3,
        "騎法被查詢：2–6 仗有（上仗冇）": cnt(R) >= 1 and not h(R, last),
        "出閘慢：近 6 仗 ≥3 次": (cnt(SL) + h(SL, last)) >= 3,
        "任何藉口（走外疊／受阻）近 6 仗 ≥3 次": sum(h(W, s) or h(B, s) for s in before + [last]) >= 3,
        "近 6 仗事件報告全部空白": all(s == "" for s in before + [last]),
    }


d.features = features
d.main()
