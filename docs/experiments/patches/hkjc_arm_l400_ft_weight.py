"""EXP-20261115-10（Kelvin 2026-11-15）：末段 L400 睇近 6 仗＋逐仗負磅換算；段速 FT 全程逐仗負磅調整。

WC_LW_ARM（預先登記，冇由數據 fit；係數全部用現行已量度值）：
  l400_6  入分用嘅 L400 = 近 6 仗（有分段、有負磅）每仗 L400 換算到今仗負磅（scoring.l400_weight_seconds_per_lb(嗰仗路程)），
          1/k 加權平均（同 FT 一樣嘅近重遠輕）；L400 分級門檻照舊
  ft_w    FT 全程：每仗 total_v += (今仗負磅 − 嗰仗負磅) × 0.0112 秒/公里 × 0.4（換做每 400 米；EXP 負磅效應實測值）；前段唔郁
  both    兩樣一齊
"""
import os

ARM = os.environ.get("WC_LW_ARM", "")
ARM_NAME = f"weight_adj_{ARM}"
FT_SEC_PER_LB_PER_400 = 0.0112 * 0.4


def _apply_l400():
    from hkjc_racing_engine import past_runs, scoring
    from hkjc_racing_engine.features import speed as sp
    orig_attach = past_runs.attach

    def attach(formguide_text, horses, race_context, race_date):
        n = orig_attach(formguide_text, horses, race_context, race_date)
        if race_date is None:
            return n
        parsed = past_runs.parse_formguide(formguide_text)
        for num, horse in horses.items():
            if not isinstance(horse, dict) or not str(num).isdigit() or int(num) not in parsed:
                continue
            entry = parsed[int(num)]
            today = entry["today_weight"]
            runs = sorted([r for r in entry["runs"] if r["date"] < race_date], key=lambda r: r["date"], reverse=True)
            vals = [r["splits"][-1] + scoring.l400_weight_seconds_per_lb(r["distance"]) * (int(today) - int(r["weight"]))
                    for r in runs if r.get("splits") and r.get("weight") is not None and r.get("distance") and today is not None][:6]
            if vals:
                horse.setdefault("_data", {})["l400_runs6"] = vals
        return n
    past_runs.attach = attach
    import hkjc_auto_orchestrator as orch
    orch.past_runs.attach = attach
    orig_adj = sp.l400_weight_adjustment

    def adj(data):
        out = orig_adj(data)
        vals = (data or {}).get("l400_runs6") if isinstance(data, dict) else None
        if out is None or not vals:
            return out
        w = [1.0 / k for k in range(1, len(vals) + 1)]
        mean = float(f"{sum(v * x for v, x in zip(vals, w)) / sum(w):.2f}")
        return dict(out, adjusted=mean, shift=round(mean - out["raw"], 2))
    sp.l400_weight_adjustment = adj


def _apply_ft():
    from hkjc_racing_engine import past_runs, pit_sections
    orig_attach = past_runs.attach
    state = {}

    def attach(formguide_text, horses, race_context, race_date):
        parsed = past_runs.parse_formguide(formguide_text) if race_date is not None else {}
        state["w"] = {int(k): v for k, v in parsed.items()}
        return orig_attach(formguide_text, horses, race_context, race_date)
    past_runs.attach = attach
    import hkjc_auto_orchestrator as orch
    orch.past_runs.attach = attach

    orig_sft = past_runs._sectional_ft

    def sft(runs, race_date, today_class, run_classes):
        # 搵返呢匹馬嘅今仗負磅：用 runs 身份對返 parsed entry
        today = None
        for e in state.get("w", {}).values():
            if e["runs"] and runs and any(r["date"] == runs[0]["date"] and r.get("splits") == runs[0].get("splits") and r.get("weight") == runs[0].get("weight") for r in e["runs"]):
                today = e["today_weight"]
                break
        if today is None:
            return orig_sft(runs, race_date, today_class, run_classes)
        wmap = {r["date"].isoformat(): r.get("weight") for r in runs}
        orig_fv = pit_sections.ft_values

        def fv(rows, rd, tcls, table):
            season = pit_sections.season_of(rd)
            tc = pit_sections.CLASS_CODE.get(str(tcls or ""), "OT")
            acc = {"first_v": [], "total_v": []}
            nsec = table.get("nsec") or {}
            eligible = [r for r in rows if r["date"] < rd and r.get("dist") and len(r.get("secs") or []) >= 3
                        and len(r["secs"]) == nsec.get(f"{r['track']}|{r['dist']}", len(r["secs"]))][:6]
            for r in eligible:
                secs = r["secs"]; n = len(secs)
                st = pit_sections._std(table, season, r["track"], r["dist"], tc, n) or pit_sections._std(table, season, r["track"], r["dist"], r.get("cls") or "OT", n)
                if st is None:
                    continue
                dv = [a - b for a, b in zip(secs, st)]
                first_len = r["dist"] - 400 * (n - 1)
                v = (table.get("variant") or {}).get(f"{r['date']}|{r['track']}") or {}
                acc["first_v"].append(dv[0] / (first_len / 400) - v.get("first", 0.0))
                total_adj = (v.get("first", 0.0) + v.get("l400", 0.0)) / 2 if v else 0.0
                wv = wmap.get(r["date"])
                wshift = (int(today) - int(wv)) * FT_SEC_PER_LB_PER_400 if wv is not None else 0.0
                acc["total_v"].append(sum(dv) / (r["dist"] / 400) - total_adj + wshift)
            out = []
            for k in ("first_v", "total_v"):
                xs = acc[k]
                if len(xs) < 2:
                    out.append(None); continue
                w = [1.0 / i for i in range(1, len(xs) + 1)]
                out.append(-sum(x * wi for x, wi in zip(xs, w)) / sum(w))
            return out[0], out[1]
        pit_sections.ft_values = fv
        try:
            return orig_sft(runs, race_date, today_class, run_classes)
        finally:
            pit_sections.ft_values = orig_fv
    past_runs._sectional_ft = sft


def apply():
    if ARM in ("l400_6", "both"):
        _apply_l400()
    if ARM in ("ft_w", "both"):
        _apply_ft()
    if ARM not in ("l400_6", "ft_w", "both"):
        raise RuntimeError(f"未知 WC_LW_ARM：{ARM!r}")
