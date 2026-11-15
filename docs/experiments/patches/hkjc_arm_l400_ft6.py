"""EXP-20261115-13（Kelvin 2026-11-15「L400 近 6 仗加負磅深挖」）：L400 對標準＋扣當日快慢＋負磅換算，近 6 仗。

每仗（有完整分段、有負磅、有 as-of 標準）：v = L400 − 標準L400(跑道, 路程, 今仗班次；冇就嗰仗班次)
                                          − 當日跑道 L400 快慢（pit_sections variant.l400）
                                          + l400_weight_seconds_per_lb(嗰仗路程) × (今仗負磅 − 嗰仗負磅)
近 6 仗 1/k 加權平均（最少 2 仗）。分數 = −6.5 × clip(v, −1.5, +1.5)（6.5 分／秒 ≈ 現行 L400 分級斜率；預先登記，冇 fit）。
WC_L4_ARM：add = 保留上仗 L400 分級再加；replace = 剷走「L400 絕對值」嗰行再加。
"""
import os

ARM = os.environ.get("WC_L4_ARM", "")
ARM_NAME = f"l400_ft6_{ARM}"
PTS_PER_SEC = 6.5
CLIP = 1.5


def apply():
    if ARM not in ("add", "replace"):
        raise RuntimeError(f"未知 WC_L4_ARM：{ARM!r}")
    from datetime import datetime
    from hkjc_racing_engine import past_runs, pit_sections, scoring
    from hkjc_racing_engine.scoring import clip_score
    from hkjc_racing_engine.features import speed as sp
    import hkjc_auto_orchestrator as orch
    orig_attach = past_runs.attach

    def attach(formguide_text, horses, race_context, race_date):
        n = orig_attach(formguide_text, horses, race_context, race_date)
        table = pit_sections.load_table()
        if race_date is None or not table:
            return n
        parsed = past_runs.parse_formguide(formguide_text)
        tcls = past_runs.class_code(race_context.get("race_class"))
        season = pit_sections.season_of(race_date.isoformat())
        nsec = table.get("nsec") or {}
        for num, horse in horses.items():
            if not isinstance(horse, dict) or not str(num).isdigit() or int(num) not in parsed:
                continue
            entry = parsed[int(num)]
            today = entry["today_weight"]
            if today is None:
                continue
            data = horse.setdefault("_data", {})
            run_classes = {}
            for d, cls in past_runs._RECENT_CLASS.findall(str(data.get("recent_6_detail") or "")):
                try:
                    run_classes[datetime.strptime(d, "%d/%m/%Y").date()] = past_runs.class_code(cls)
                except ValueError:
                    continue
            runs = sorted([r for r in entry["runs"] if r["date"] < race_date], key=lambda r: r["date"], reverse=True)
            vals = []
            for r in runs:
                secs = r.get("splits") or []
                if len(secs) < 3 or r.get("weight") is None or not r.get("distance"):
                    continue
                track = "AWT" if r.get("awt") else ("HV" if "跑馬地" in str(r.get("venue")) else "ST")
                if len(secs) != nsec.get(f"{track}|{r['distance']}", len(secs)):
                    continue
                k = len(secs) - 1
                st = (pit_sections._std(table, season, track, r["distance"], pit_sections.CLASS_CODE.get(str(tcls or ""), "OT"), len(secs))
                      or pit_sections._std(table, season, track, r["distance"], run_classes.get(r["date"]) or "OT", len(secs)))
                if st is None:
                    continue
                var = (table.get("variant") or {}).get(f"{r['date'].isoformat()}|{track}") or {}
                v = secs[k] - st[k] - var.get("l400", 0.0) + scoring.l400_weight_seconds_per_lb(r["distance"]) * (int(today) - int(r["weight"]))
                vals.append(v)
                if len(vals) == 6:
                    break
            if len(vals) >= 2:
                w = [1.0 / i for i in range(1, len(vals) + 1)]
                data["l400_ft6"] = sum(a * b for a, b in zip(vals, w)) / sum(w)
        return n
    past_runs.attach = attach
    orch.past_runs.attach = attach
    orig_compute = sp.SpeedScorer.compute

    def compute(self):
        score, note = orig_compute(self)
        v = self._data().get("l400_ft6")
        if v is None:
            return score, note
        pts = -PTS_PER_SEC * max(-CLIP, min(CLIP, float(v)))
        if ARM == "replace":
            old = sum(float(r.get("delta") or 0) for r in (getattr(self, "detail", []) or []) if r.get("factor") == "L400 絕對值")
            pts -= old
        return clip_score(score + pts), note
    sp.SpeedScorer.compute = compute
