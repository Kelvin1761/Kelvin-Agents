"""EXP-20261119-06 追加候選 X1w（預先登記，Kelvin 2026-11-19 揀咗實驗性上線 X1 之後）：
耀寶 10-07「難以望空／受困之際未能被力策」、09-13「收慢避開」冇被現行受阻 regex 捉到。
X1w = X1，但受阻加三組同義字：難以望空｜受困｜未能被力策（唔加「收慢」：12% 太闊）。
家族變 3（X1、X2、X1w）。用法同 build_excuse_streak.py。
"""
import os, runpy, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import diag_excuse_streak as d  # noqa: E402
d.BLK = d.BLK + "|難以望空|受困|未能被力策"
d.STRICT = f"{d.BLK}|{d.W}|{d.RIDE}"
d.BROAD = f"{d.STRICT}|{d.INTERF}|{d.SLOW}"
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_excuse_streak.py")).read()
src = src.replace('import diag_excuse_streak as d  # noqa: E402', '')
src = src.replace('for j, arm in enumerate(("X1", "X2")):', 'for j, arm in enumerate(("X1w", "X2w")):')
src = src.replace('arm=f"excuse_streak_{arm}"', 'arm=f"excuse_streak_{arm}"')
exec(compile(src, "build_excuse_streak.py", "exec"), {"__name__": "__main__", "d": d, "__file__": __file__})
