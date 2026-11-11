"""EXP-20261111-10 上線後 forward：退返舊版負磅分（宣佈負磅 ≤120／≥132），同 live（評分差距）比較。

Δ = 舊版 − live。Gold／Good／NDCG 全部 ≥ 0 即係「舊版唔輸」→ 交 Kelvin 決定要唔要退返。
Fixed, nothing fitted.
"""
ARM_NAME = "revert_rating_gap"


def apply():
    from hkjc_racing_engine.engine_core import RacingEngine

    original = RacingEngine._weight_score

    def patched(self, features):
        stash = []
        for store in (self.horse_data, getattr(self, "data", None) or {}):
            if isinstance(store, dict) and "rating_gap" in store:
                stash.append((store, store.pop("rating_gap")))
        try:
            return original(self, features)
        finally:
            for store, value in stash:
                store["rating_gap"] = value

    RacingEngine._weight_score = patched
