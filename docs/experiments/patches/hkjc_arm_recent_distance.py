"""EXP-20261019-01：同程往績只計每匹馬最近 N 仗（任何路程）入面喺今仗路程嘅仗數／上名。

baseline = 完整往績（現行 live，2026-10-07 起 Facts 已經係完整版；回放用 EXP-20261018-13 嘅 PIT 注入）。
候選 = 同一個 PIT 賽果庫，但每匹馬只保留 `Date < 賽日` 嘅最近 N 仗，再數同程。
N 由 `WC_RECENT_N` 傳入，只准 6 / 10 / 15。引擎改為**有賽果庫紀錄就用賽果庫**（唔取大），
否則舊存檔截斷版 Facts 會滲返入嚟。
"""
import os

N = int(os.environ["WC_RECENT_N"])
assert N in (6, 10, 15), N
ARM_NAME = f"recent_distance_n{N}"


def apply():
    import re

    import pit_backtest
    from hkjc_racing_engine import engine_core, live_priors

    original_inject = pit_backtest.inject_as_of

    def inject(all_rows, meeting_date):
        out = original_inject(all_rows, meeting_date)
        sub = all_rows[all_rows["Date"] < meeting_date].copy()
        sub["_order"] = range(len(sub))
        sub = sub.sort_values(["Date", "_order"])
        recent = sub.groupby("Horse", sort=False).tail(N)
        live_priors._HORSE_DISTANCE = live_priors.HorseDistanceRecords(
            pit_backtest.bcs.horse_distance_table(recent), temporal_mode="point_in_time", as_of_date=meeting_date,
        )
        return out

    pit_backtest.inject_as_of = inject

    def same_distance_record(self):
        records = live_priors.get_horse_distance_records((self.race_context or {}).get("race_date"))
        if records is not None:
            hit = records.lookup(self.horse_data.get("horse_code") or self._value("horse_code"),
                                 self.horse_data.get("horse_name"), (self.race_context or {}).get("distance"))
            if hit is not None:
                return hit
            if records.by_brand or records.by_name:
                # 有賽果庫但近 N 仗冇呢個路程 → 同程 0 仗（唔好跌返去截斷 Facts）
                return {"wins": 0, "seconds": 0, "thirds": 0, "starts": 0, "places": 0}
        text = self._clean(self.horse_data.get("season_stats") or self._value("season_stats_line") or "")
        match = re.search(r"同程\s*\((\d+)-(\d+)-(\d+)-(\d+)\)", text)
        if not match:
            return None
        wins, seconds, thirds, rest = (int(part) for part in match.groups())
        return {"wins": wins, "seconds": seconds, "thirds": thirds,
                "starts": wins + seconds + thirds + rest, "places": wins + seconds + thirds}

    engine_core.RacingEngine._same_distance_record = same_distance_record
