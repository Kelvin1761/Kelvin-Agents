"""EXP-20261111-12 arm：未知騎師／練馬師唔再用**匹馬**嘅海外班次計分，一律中性 60。

現行：騎師／練馬師喺實績評分同層級表都搵唔到（=60）時，如果匹馬有海外往績，
騎師 85（匹馬跑過 G1）／70，練馬師 85／75／70 或者抄騎師層級。量嘅係匹馬，唔係人。
呢個 arm 喺 compute() 之後，凡係 reason 以 "Overseas" 開頭就改返 60。冇 fit 任何數值。
離場時喺 stderr 印觸發次數（量覆蓋用）。
"""
import atexit
import sys
from collections import Counter

ARM_NAME = "no_overseas_jt_fallback"
HITS = Counter()


def apply():
    from hkjc_racing_engine.features.jockey import JockeyScorer
    from hkjc_racing_engine.features.trainer import TrainerScorer

    for cls, who in ((JockeyScorer, "jockey"), (TrainerScorer, "trainer")):
        original = cls.compute

        def patched(self, _orig=original, _who=who):
            score, reason = _orig(self)
            if str(reason or "").startswith("Overseas"):
                HITS[(_who, str(reason), float(score))] += 1
                self.score, self.reason = 60.0, f"Neutral {_who.title()}（本地冇紀錄；唔再用匹馬海外班次代替）"
                return self.score, self.reason
            return score, reason

        cls.compute = patched

    atexit.register(lambda: print(f"[overseas_jt_hits] {dict(HITS)}", file=sys.stderr))
