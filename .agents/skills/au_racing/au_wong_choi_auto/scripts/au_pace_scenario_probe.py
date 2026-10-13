#!/usr/bin/env python3
"""EXP-20261013-11：步速運氣、步速形勢、speed map 準確度、PI 重審。

研究工具（唔郁 engine）。重用 `au_speed_rebuild_probe` 嘅往績解析同 Stage 4 v2 判決。

    PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 au_pace_scenario_probe.py build LEAVES OUT
    PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 au_pace_scenario_probe.py diag  LEAVES OUT
    PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 au_pace_scenario_probe.py judge LEAVES OUT FEATURE
"""
import json
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import au_speed_rebuild_probe as base  # noqa: E402

SPEEDPOS = re.compile(r"^SpeedPos:\s+(\d+)", re.M)


def _f800(r):
    if r["p800"] and r["starters"] and r["starters"] > 1:
        return min(1.0, (r["p800"] - 1) / (r["starters"] - 1))
    return None


def build(leaves_path, out_path):
    races = json.load(open(leaves_path))["races"]
    mi = base.meeting_index()
    per_race, all_runs, actual = {}, [], {}
    for race in races:
        md = mi.get(race["meeting"])
        fg = next(iter(md.glob(f"* Race {race['race']} Formguide.md")), None) if md else None
        if not fg:
            continue
        text = fg.read_text(encoding="utf-8", errors="replace")
        heads = list(base.HORSE.finditer(text))
        horses = {}
        for i, h in enumerate(heads):
            end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
            block = text[h.end():end]
            name = base.norm(h.group(2))
            runs = base.parse_runs(block)
            for r in runs:                       # 今仗實際走位：由之後嘅 Formguide 攞
                f = _f800(r)
                if f is not None:
                    actual[(name, r["date"])] = f
            sp = SPEEDPOS.search(block)
            horses[name] = ([r for r in runs if r["date"] < race["date"]], int(sp.group(1)) if sp else None)
            all_runs += horses[name][0]
        per_race[(race["meeting"], race["race"], race["date"])] = horses

    gs = [r["margin"] / (r["finish"] - 1) for r in all_runs
          if r["finish"] and r["finish"] > 1 and r["margin"] is not None and r["margin"] > 0]
    G = statistics.median(gs)
    uniq = {(r["date"], r["venue"], r["dist"], r["finish"], r["margin"], r["p800"]): r for r in all_runs}

    def early_speed(r):
        if r["wt"] is None or r["l600"] is None or r["dist"] <= 800:
            return None
        t = r["wt"] - r["l600"]
        sp = (r["dist"] - 600) / t if t > 0 else 0
        return sp if 11 < sp < 19 else None

    cells = {}
    for r in uniq.values():
        if r["date"] < base.STD_CUTOFF and (e := early_speed(r)):
            cells.setdefault((r["dist"] // 100, r["going"]), []).append(e)
    std = {k: (statistics.median(v), statistics.pstdev(v)) for k, v in cells.items() if len(v) >= 30}

    def early_z(r):
        e = early_speed(r)
        s = std.get((r["dist"] // 100, r["going"])) if e else None
        return max(-3, min(3, (e - s[0]) / s[1])) if (s and s[1] > 0) else None

    def own_early_z(r):
        e, f = early_speed(r), None
        if e and r["p800"] and r["p400"]:
            behind = ((r["p800"] + r["p400"]) / 2 - 1) * G
            t = (r["dist"] - 600) / e + behind * base.LBL
            f = (r["dist"] - 600) / t
        s = std.get((r["dist"] // 100, r["going"])) if f else None
        return max(-3, min(3, (f - s[0]) / s[1])) if (s and s[1] > 0) else None

    def disadv(r):
        ez, f = early_z(r), _f800(r)
        return ez * (1 - 2 * f) if (ez is not None and f is not None) else None

    # β：標準期逐仗負距對 disadv
    xs, ys = [], []
    for r in uniq.values():
        if r["date"] < base.STD_CUTOFF and r["margin"] is not None and (d := disadv(r)) is not None:
            xs.append(d)
            ys.append(r["margin"])
    mx, my = statistics.mean(xs), statistics.mean(ys)
    beta = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)

    out, targets = {}, {}
    for (meeting, rno, date), horses in per_race.items():
        for name, (runs, speedpos) in horses.items():
            recent = sorted(runs, key=lambda x: x["date"], reverse=True)
            feats = {}

            def mean_of(fn, limit=4):
                vals = [v for v in (fn(r) for r in recent) if v is not None][:limit]
                return statistics.mean(vals) if vals else None

            feats["f800_hist"] = mean_of(_f800)
            feats["early_own"] = mean_of(own_early_z)
            feats["pi_mean"] = mean_of(lambda r: (r["p800"] - r["finish"]) / r["starters"]
                                       if (r["p800"] and r["finish"] and r["starters"]) else None)
            feats["pi_fast"] = mean_of(lambda r: (r["p800"] - r["finish"]) / r["starters"]
                                       if (r["p800"] and r["finish"] and r["starters"] and (early_z(r) or 0) > 0) else None)
            feats["pi_slow"] = mean_of(lambda r: (r["p800"] - r["finish"]) / r["starters"]
                                       if (r["p800"] and r["finish"] and r["starters"] and early_z(r) is not None
                                           and early_z(r) <= 0) else None)
            feats["pace_luck"] = mean_of(disadv)
            feats["pace_adj_margin"] = mean_of(lambda r: -(r["margin"] - beta * disadv(r))
                                               if (r["margin"] is not None and disadv(r) is not None) else None)
            feats["margin_raw"] = mean_of(lambda r: -r["margin"] if r["margin"] is not None else None)
            feats["speedpos"] = speedpos
            out[f"{meeting}|{rno}|{name}"] = {k: v for k, v in feats.items() if v is not None}
            if (name, date) in actual:
                targets[f"{meeting}|{rno}|{name}"] = actual[(name, date)]
    json.dump({"G": G, "beta": beta, "features": out, "actual_f800": targets}, open(out_path, "w"))
    print(f"G={G:.3f}  β={beta:+.3f} 馬位/單位蝕步速  馬 {len(out)}  有今仗實際走位 {len(targets)}")


def _z(vals):
    have = [v for v in vals if v is not None]
    if len(have) < 2 or statistics.pstdev(have) <= 0:
        return [0.0 if v is None else 0.0 for v in vals]
    m, s = statistics.mean(have), statistics.pstdev(have)
    return [0.0 if v is None else (v - m) / s for v in vals]


def add_scenario(races, predictor):
    """C3：用預測 f800（細 = 前）砌單騎領放分，寫入 row['_sf']['pace_scenario']。"""
    for race in races:
        preds = [predictor(row) for row in race["rows"]]
        have = sorted(p for p in preds if p is not None)
        if len(have) < 4:
            continue
        cut = have[max(0, len(have) // 4 - 1)]
        for row, p in zip(race["rows"], preds):
            if p is None:
                continue
            front = 1 - sum(1 for q in have if q < p) / (len(have) - 1)
            pressure = sum(1 for q in have if q <= cut) - (1 if p <= cut else 0)
            row["_sf"]["pace_scenario"] = front * (1 - min(pressure, 3) / 3)


def diag(leaves_path, feats_path):
    races = base.attach(leaves_path, feats_path)
    act = json.load(open(feats_path))["actual_f800"]
    print("D1 speed map —— 預測今仗實際 800m 位置（場內 Spearman，越大越準）")
    preds = {
        "P0 Sportsbet SpeedPos": lambda row: row["_sf"].get("speedpos"),
        "P1 過往 f800": lambda row: row["_sf"].get("f800_hist"),
        "P2 本駒頭段速度": lambda row: (-row["_sf"]["early_own"]) if "early_own" in row["_sf"] else None,
    }
    best = (None, -1)
    for label, fn in list(preds.items()) + [("P3 P1+P2", None)]:
        rhos, n = [], 0
        for race in races:
            rows = [row for row in race["rows"]
                    if f"{race['meeting']}|{race['race']}|{base.norm(row['name'])}" in act]
            if label.startswith("P3"):
                a = _z([preds["P1 過往 f800"](r) for r in rows])
                b = _z([preds["P2 本駒頭段速度"](r) for r in rows])
                pv = [(x + y) if (preds["P1 過往 f800"](r) is not None) else None
                      for r, x, y in zip(rows, a, b)]
            else:
                pv = [fn(r) for r in rows]
            pairs = [(p, act[f"{race['meeting']}|{race['race']}|{base.norm(r['name'])}"])
                     for r, p in zip(rows, pv) if p is not None]
            if len(pairs) >= 4:
                s = base._spearman([p for p, _ in pairs], [a for _, a in pairs])
                if s is not None:
                    rhos.append(s)
                    n += len(pairs)
        m = statistics.mean(rhos) if rhos else float("nan")
        print(f"   {label:24} ρ {m:+.3f}   （{len(rhos)} 場、{n} 匹）")
        if rhos and m > best[1]:
            best = (label, m)
    print(f"   → 最好：{best[0]} ρ {best[1]:+.3f}")
    print("\nD2 PI 同步速相關特徵 —— 場內上名 AUC")
    for f in ("pi_mean", "pi_fast", "pi_slow", "pace_luck", "pace_adj_margin", "margin_raw"):
        w = t = cov = 0
        for race in races:
            vp = [(row["_sf"][f], row["pos"]) for row in race["rows"] if f in row["_sf"]]
            cov += len(vp)
            if len(vp) >= 3 and (a := base._auc_place(vp)):
                w += a[0]
                t += a[1]
        runners = sum(len(r["rows"]) for r in races)
        print(f"   {f:16} 覆蓋 {100 * cov / runners:5.1f}%  AUC {w / t if t else float('nan'):.4f}")
    return best


def judge(leaves_path, feats_path, feature):
    if feature != "pace_scenario":
        return base.judge(leaves_path, feats_path, feature)
    # pace_scenario 要先砌：用 D1 最好嘅預測器 —— 2026-10-13 實測係 P1 過往 f800（ρ +0.451；
    # P3 P1+P2 只有 +0.394，P0 SpeedPos +0.163）
    orig_attach = base.attach

    def attach_with_scenario(lp, fp):
        races = orig_attach(lp, fp)
        for race in races:
            for row in race["rows"]:
                row["_pred_f800"] = row["_sf"].get("f800_hist")
        add_scenario(races, lambda row: row["_pred_f800"])
        return races
    base.attach = attach_with_scenario
    try:
        return base.judge(leaves_path, feats_path, feature)
    finally:
        base.attach = orig_attach


if __name__ == "__main__":
    cmd = sys.argv[1]
    {"build": lambda: build(sys.argv[2], sys.argv[3]),
     "diag": lambda: diag(sys.argv[2], sys.argv[3]),
     "judge": lambda: judge(sys.argv[2], sys.argv[3], sys.argv[4])}[cmd]()
