"""上上仗（倒數第二場有報告嘅賽事）走外疊冇遮擋／醫療，喺 live I1（已含上仗）之上嘅殘差。"""
import sys
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import diag_round3 as d  # noqa: E402
from diag import CATS  # noqa: E402
W = CATS["走外疊冇遮擋"]; M = CATS["醫療（喘鳴／流鼻血／心律／跛）"]


def features(prev):
    rep = [v[2] for v in prev if v[2] is not None]
    if not prev or prev[-1][2] is None or len(rep) < 2:
        return None
    last, two = rep[-1], rep[-2]
    h = d.has
    return {
        "走外疊：上上仗（上仗冇）": h(W, two) and not h(W, last),
        "走外疊：上兩仗都有": h(W, two) and h(W, last),
        "走外疊：近5仗≥2次": sum(h(W, s) for s in rep[-5:]) >= 2,
        "醫療：上上仗（上仗冇）": h(M, two) and not h(M, last),
        "醫療：近5仗任一（上仗冇）": any(h(M, s) for s in rep[-5:-1]) and not h(M, last),
        "上上仗冇報告類別（對照）": two == "",
    }


d.features = features
sys.argv = [sys.argv[0], sys.argv[1], sys.argv[2]]
d.main()
