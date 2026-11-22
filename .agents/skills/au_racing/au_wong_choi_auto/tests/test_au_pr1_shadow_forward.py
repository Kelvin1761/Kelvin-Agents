"""EXP-20261122-05 PR1 shadow：計法同研究一樣、幅度凍結、只郁 forward 期。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import au_perf_rating as PR  # noqa: E402
import au_pr1_shadow_forward as F  # noqa: E402

SECTION = """[3] Fire Star (5)
Rosehill Gardens R9 2026-08-01 1300m cond:Soft $160000 Rachel King (4) 57.0kg . margin:1.33L starters:11 finish:3/11 RaceClass:[BM94]
1-A (57kg), 2-B (57kg) 0.5L, 3-Fire Star (57kg) 1.33L
Grafton R7 2026-07-15 1200m cond:Good $200000 X Y (11) 58.5kg . margin:0L starters:15 finish:1/15 RaceClass:[X]
1-Fire Star (58.5kg), 2-Other (57kg) 0.40L, 3-Z (55kg) 0.9L
Warwick Farm **(TRIAL)** R6 2026-11-12 821m cond:Good $0 R K (None) Nonekg . margin:1.50L starters:9 finish:3/9 RaceClass:[T]
"""


def test_pr1_formula():
    perf = PR.run_performances(SECTION, "2026-11-21")
    lpl1300, lpl1200 = 3.0 * (1000 / 1300) ** 0.75, 3.0 * (1000 / 1200) ** 0.75
    assert abs(perf[0] - (-lpl1300 * 1.33)) < 1e-9                        # 最新先；試閘唔計
    assert abs(perf[1] - (lpl1200 * 0.40 + 2.2 * 1.5)) < 1e-9              # 頭馬 = −勝距，負磅 58.5
    assert abs(PR.pr1(SECTION, "2026-11-21") - (perf[0] * 1.0 + perf[1] * 0.8) / 1.8) < 1e-9
    assert PR.pr1(SECTION, "2026-07-01") is None                            # 冇早過今仗嘅往績


def test_shadow_frozen_and_forward_only():
    assert (F.BETA, F.START_DATE, F.TARGET_RACES) == (0.148, "2026-11-23", 1000)
    races = [{"date": "2026-11-22", "rows": [{"ability": 60.0, "pr1": 5.0}, {"ability": 60.0, "pr1": -5.0}]},
             {"date": "2026-11-23", "rows": [{"ability": 60.0, "pr1": 5.0}, {"ability": 60.0, "pr1": None}, {"ability": 60.0, "pr1": -5.0}]}]
    out = F.candidate(races)
    assert out[0]["rows"][0]["ability"] == 60.0
    assert abs(out[1]["rows"][0]["ability"] - (60 + 0.148 * 5)) < 1e-9 and out[1]["rows"][1]["ability"] == 60.0
