"""EXP-20261122-29 預先登記（Kelvin 2026-11-22「L400 段速按場地同路程標準化；前段同全程已經標準化，要一齊考慮」）。

現況：段速分有四部分 —— 「L400 絕對值」階梯（≤22.4 +8、≤23.0 +5、≤23.6 +2、≥24.0 −2、≥24.6 −5，原始秒數）、輸頭馬、
最快第一段（對標準）、FT 前段＋全程（對 as-of 標準、扣當日快慢，`pit_sections`）。只有 L400 冇標準化：
1000 米直路／短途嘅末段天生快過 2000 米，沙田快過谷草 → 短程上仗嘅馬去長程，段速分虛高。
一樣嘢只准一個標準：L400 用同 FT 一樣嘅 `pit_sections` 標準表（track|dist|cls|最後一段）同當日快慢 variant.l400。

ARM（環境變數 WC_L400_ARM）：
  L1  階梯照用，但入階梯嘅值 = 23.56 +（上仗 L400 − 標準最後一段 − 當日 variant.l400）＋ 負磅換算 shift。
      23.56 = dev 窗（2020-09～2024-07）上仗 L400 原始中位數（跑候選之前計）；標準化偏差中位數 0.000。
      標準：今仗班次；冇就上仗班次；再冇就 ALL。搵唔到標準 → 唔郁（用返絕對值）。
  L2  剷走「L400 絕對值」階梯（delta = 0）；L400 嘅資訊由已標準化嘅全程（FT total）代表。
其他（門檻、權重、FT、輸頭馬、第一段）一行唔改。判：hkjc_replay_compare_v5.py；base = 同一份 code 冇 arm 嘅回放；Holm 家族 2。
"""
import os

ARM_NAME = "l400_std_" + os.environ.get("WC_L400_ARM", "L1")
CENTRE = 23.56


def apply():
    from hkjc_racing_engine import past_runs, pit_sections
    from hkjc_racing_engine.features import speed
    arm = os.environ.get("WC_L400_ARM", "L1")
    orig_attach = past_runs.attach

    def attach(formguide_text, horses, race_context, race_date):
        n = orig_attach(formguide_text, horses, race_context, race_date)
        if race_date is None:
            return n
        parsed = past_runs.parse_formguide(formguide_text)
        tcls = past_runs.class_code(race_context.get("race_class"))
        for num, horse in horses.items():
            if not isinstance(horse, dict) or not str(num).isdigit():
                continue
            last = (horse.get("_data") or {}).get("l400_last_run")
            entry = parsed.get(int(num))
            if not isinstance(last, dict) or not entry:
                continue
            runs = sorted([r for r in entry["runs"] if r["date"] < race_date], key=lambda r: r["date"], reverse=True)
            if not runs or runs[0]["date"].isoformat() != last.get("date"):
                continue
            r = runs[0]
            track = "AWT" if r.get("awt") else ("HV" if "跑馬地" in str(r.get("venue")) else "ST")
            cls = None
            for d, c in past_runs._RECENT_CLASS.findall(str(horse["_data"].get("recent_6_detail") or "")):
                if d == r["date"].strftime("%d/%m/%Y"):
                    cls = past_runs.class_code(c)
            last.update(track=track, nsec=len(r["splits"]), run_cls=cls or "OT", today_cls=tcls or "OT")
        return n

    past_runs.attach = attach
    orig_core = speed.SpeedScorer._compute_core

    def standardised(data):
        last = data.get("l400_last_run") or {}
        if not last.get("track") or not last.get("nsec"):
            return None
        table = pit_sections.load_table()
        if not table:
            return None
        season = pit_sections.season_of(last["date"])
        st = None
        for cls in (last.get("today_cls"), last.get("run_cls")):
            st = pit_sections._std(table, season, last["track"], int(last["distance"]), cls or "OT", int(last["nsec"]))
            if st:
                break
        if not st:
            return None
        v = ((table.get("variant") or {}).get(f"{last['date']}|{last['track']}") or {}).get("l400", 0.0)
        adj = speed.l400_weight_adjustment(data)
        shift = adj["shift"] if adj else 0.0
        return round(CENTRE + (float(last["l400"]) - st[-1] - v) + shift, 2)

    def ladder(x):
        w = speed.scoring.SPEED_MICRO_WEIGHTS
        if x <= 22.4: return w.get("l400_22_4_bonus", 8.0)
        if x <= 23.0: return w.get("l400_23_0_bonus", 5.0)
        if x <= 23.6: return w.get("l400_23_6_bonus", 2.0)
        if x >= 24.6: return w.get("l400_24_6_pen", -5.0)
        if x >= 24.0: return w.get("l400_24_0_pen", -2.0)
        return 0.0

    def core(self):
        score, note = orig_core(self)
        item = next((d for d in (getattr(self, "detail", None) or []) if d.get("factor") == "L400 絕對值"), None)
        if item is None:
            return score, note
        old = float(item.get("delta") or 0.0)
        if arm == "L2":
            new = 0.0
        else:
            x = standardised(self._data())
            if x is None:
                return score, note
            new = ladder(x)
            item["value"] = f"{x:.2f}s（標準化）"
        item["delta"] = round(new, 2)
        return speed.clip_score(score + new - old), note

    speed.SpeedScorer._compute_core = core
