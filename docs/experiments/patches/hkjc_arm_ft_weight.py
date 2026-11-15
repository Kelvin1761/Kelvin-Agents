"""Kelvin 2026-11-16「負磅殘差：直接修正，或者調整段速差異；呢個真係發生緊」（EXP-20261116-05）。

背景：live 模型每重 10 磅（相對場均）高估 0.79pp [±0.58]（v3 回放 61,482 匹次）。L400 已按今仗負磅換算（445df354），
但段速 FT 組件（`pit_sections.ft_values`，前段＋全程對 as-of 標準）用嘅過往分段時間**冇按負磅換算** ——
匹馬今仗重咗 10 磅，佢之前輕磅跑出嚟嘅全程時間照計。
arm：每仗分段偏差（秒／400 米）加 c ×（今仗負磅 − 嗰仗負磅），正 = 今仗預期慢啲。
c 由物理量度嚟（EXP-20261112-06：完成時間每磅 0.01123 s/km → 每 400 米 0.00449 s），唔由數據 fit。
WC_FTW_ARM（預先登記，Holm 3）：
  W1  全程 c=0.00449，前段唔郁
  W2  全程同前段都 c=0.00449
  W3  全程 c=0.00898（2×，敏感度）
冇負磅（今仗或嗰仗）嘅仗唔換算。判法：docs/model-evaluation-contract.md「HKJC 歷史回放尺 v4」。
"""
import os

ARM = os.environ.get("WC_FTW_ARM", "")
ARM_NAME = f"ft_weight_{ARM}"
C = {"W1": (0.00449, 0.0), "W2": (0.00449, 0.00449), "W3": (0.00898, 0.0)}


def apply():
    if ARM not in C:
        raise RuntimeError(f"未知 WC_FTW_ARM：{ARM!r}")
    c_total, c_first = C[ARM]
    from hkjc_racing_engine import past_runs, pit_sections

    orig_parse = past_runs.parse_formguide

    def parse(text):
        out = orig_parse(text)
        for entry in out.values():
            tw = entry.get("today_weight")
            for r in entry.get("runs") or []:
                r["wd"] = (tw - r["weight"]) if (tw is not None and r.get("weight") is not None) else 0
        return out
    past_runs.parse_formguide = parse

    def sectional_ft(runs, race_date, today_class, run_classes):
        table = pit_sections.load_table()
        if not table:
            return None
        rows = []
        for r in runs:
            if not r.get("splits"):
                continue
            track = "AWT" if r.get("awt") else ("HV" if "跑馬地" in str(r.get("venue")) else "ST")
            rows.append({"date": r["date"].isoformat(), "track": track, "dist": r["distance"],
                         "cls": run_classes.get(r["date"]) or "OT", "secs": r["splits"], "wd": r.get("wd", 0)})
        first_v, total_v = ft_values(rows, race_date.isoformat(), today_class, table)
        if first_v is None and total_v is None:
            return None
        return {"first_v": first_v, "total_v": total_v, "points": round(pit_sections.ft_points(first_v, total_v, table), 4)}
    past_runs._sectional_ft = sectional_ft

    def ft_values(runs, race_date, today_cls, table):
        season = pit_sections.season_of(race_date)
        tcls = pit_sections.CLASS_CODE.get(str(today_cls or ""), "OT")
        acc = {"first_v": [], "total_v": []}
        nsec = table.get("nsec") or {}
        eligible = [r for r in runs if r["date"] < race_date and r.get("dist") and len(r.get("secs") or []) >= 3
                    and len(r["secs"]) == nsec.get(f"{r['track']}|{r['dist']}", len(r["secs"]))][:6]
        for r in eligible:
            secs = r["secs"]
            n = len(secs)
            st = pit_sections._std(table, season, r["track"], r["dist"], tcls, n) or \
                pit_sections._std(table, season, r["track"], r["dist"], r.get("cls") or "OT", n)
            if st is None:
                continue
            dv = [a - b for a, b in zip(secs, st)]
            first_len = r["dist"] - 400 * (n - 1)
            v = (table.get("variant") or {}).get(f"{r['date']}|{r['track']}") or {}
            wd = r.get("wd", 0) or 0
            acc["first_v"].append(dv[0] / (first_len / 400) - v.get("first", 0.0) + c_first * wd)
            total_adj = (v.get("first", 0.0) + v.get("l400", 0.0)) / 2 if v else 0.0
            acc["total_v"].append(sum(dv) / (r["dist"] / 400) - total_adj + c_total * wd)
        out = []
        for k in ("first_v", "total_v"):
            xs = acc[k]
            if len(xs) < 2:
                out.append(None)
                continue
            w = [1.0 / i for i in range(1, len(xs) + 1)]
            out.append(-sum(x * wi for x, wi in zip(xs, w)) / sum(w))
        return out[0], out[1]
