"""EXP-20261112-01：歷史仗負磅 screening（只量度，唔改模型）。

Kelvin 2026-11-12：「模型過份偏好高分重磅馬，好多馬未證明到重磅下有成績；段速同近績要唔要睇埋當時負磅？」

用法：
  PYTHONDONTWRITEBYTECODE=1 python3 docs/experiments/patches/hkjc_weight_history_screen.py <dump.jsonl>
<dump.jsonl> = hkjc_eval_harness.py run --dump-matrix（production baseline，PIT 回放）。
今仗同歷史仗負磅都由賽前嘅 `*賽績.md` 讀（兩邊都係實際負磅，已扣見習減磅）；歷史仗只收賽日之前嘅。

預先登記嘅特徵（睇結果之前定，唔改）：
  dw_last   今仗負磅 − 上仗負磅（磅）
  dw_avg    今仗負磅 − 近 6 仗平均負磅
  dw_place  今仗負磅 − 近 6 仗上名（頭三）嗰啲仗入面最重嗰次；冇上名 = 缺
  unproven  今仗 ≥ HEAVY 磅，而近 6 仗冇一仗喺「今仗負磅 − 2 磅」或以上跑入頭三
  l400_w    近 6 仗最快 L400 嗰仗嘅負磅，今仗 − 嗰仗
主測試：讓磅賽、非初出，place ~ z(模型 raw，場內) + 特徵；係數 CI 用場次 bootstrap；5 個特徵 Holm。
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

REPO = Path(__file__).resolve().parents[3]
for p in (REPO / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts",
          REPO / ".agents/skills/hkjc_racing/hkjc_reflector/scripts", REPO):
    sys.path.insert(0, str(p))
HANDICAP = ("第一班", "第二班", "第三班", "第四班", "第五班")
HEAVY = 130
NEAR = 2

RUN_RE = re.compile(r"\[(\d+)\]\s+(\d{2}/\d{2}/\d{4})\s*\|[^\n]*\n[^\n]*負磅:\s*(\d+)[^\n]*名次:\s*(\S+)\s*/\s*(\d+)"
                    r"(?:\s*\n[^\n]*分段時間:\s*([\d\., ]+))?")


def formguide(md, race_no):
    """{馬號: {"today": 磅, "runs": [(date, 磅, 名次 or None, L400 or None), ...最新先]}}"""
    hits = sorted(p for p in md.glob("*賽績.*") if p.suffix in (".md", ".txt") and re.search(rf"Race[ _]{race_no}\b", p.name))
    if not hits:
        return "", {}
    text = hits[0].read_text(encoding="utf-8")
    out = {}
    for block in re.split(r"\n(?=馬號:\s*\d+)", text):
        m = re.match(r"馬號:\s*(\d+)", block)
        w = re.search(r"\n負磅:\s*(\d+)", block)
        if not m or not w:
            continue
        runs = []
        for r in RUN_RE.finditer(block):
            try:
                d = datetime.strptime(r.group(2), "%d/%m/%Y").date()
            except ValueError:
                continue
            pos = int(r.group(4)) if r.group(4).isdigit() else None
            secs = [float(x) for x in re.findall(r"\d+\.\d+", r.group(6) or "")]
            runs.append((d, int(r.group(3)), pos, secs[-1] if secs else None))
        out[int(m.group(1))] = {"today": int(w.group(1)), "runs": runs}
    return text[:400], out


_LOGIC = {}


def last_class(md, race_no, n):
    """上仗班次（1–5），由賽前 Logic `recent_6_detail` 讀；讀唔到 = None。"""
    key = (str(md), race_no)
    if key not in _LOGIC:
        f = md / f"Race_{race_no}_Logic.json"
        _LOGIC[key] = (json.loads(f.read_text(encoding="utf-8")).get("horses") or {}) if f.exists() else {}
    d = ((_LOGIC[key].get(str(n)) or {}).get("_data") or {}).get("recent_6_detail") or ""
    m = re.search(r"第1仗\([^)]*?(第[一二三四五]班)", str(d))
    return HANDICAP.index(m.group(1)) + 1 if m else None


def build(dump):
    import wongchoi_paths
    root = Path(wongchoi_paths.HK_RACING)
    rows, miss = [], 0
    for line in open(dump, encoding="utf-8"):
        r = json.loads(line)
        if "error" in r or not r.get("horses"):
            continue
        if set(r.get("meeting_dead_fields") or []) - {"track_going_score", "trackwork_trend_score"}:
            continue
        head, fg = formguide(root / r["meeting"], int(r["race"]))
        if not fg:
            miss += 1
            continue
        if not any(c in head for c in HANDICAP):
            continue
        day = datetime.strptime(r["date"], "%Y-%m-%d").date()
        rank = {n: i + 1 for i, n in enumerate(r["picks"])}
        hs = [h for h in r["horses"] if h["pos"] is not None and h["n"] in fg]
        if len(hs) < 5:
            continue
        top = max(fg[h["n"]]["today"] for h in hs)
        for h in hs:
            e = fg[h["n"]]
            runs = sorted([x for x in e["runs"] if x[0] < day], reverse=True)[:6]
            t = e["today"]
            row = {"race": f"{r['meeting']}|{r['race']}", "date": r["date"], "place": float(h["pos"] <= 3),
                   "raw": h["raw"], "mrank": rank.get(h["n"], 99), "today": t, "from_top": top - t,
                   "nruns": len(runs), "speed": h["f"].get("speed_score"), "form": h["f"].get("form_score")}
            if runs:
                ws = [x[1] for x in runs]
                placed = [x[1] for x in runs if x[2] is not None and x[2] <= 3]
                row["dw_last"] = t - ws[0]
                row["dw_avg"] = t - float(np.mean(ws))
                row["dw_place"] = t - max(placed) if placed else np.nan
                row["never_placed"] = not placed
                row["at_weight"] = float(any(w >= t - NEAR for w in placed))   # 任何負磅：喺今仗−2 磅或以上上過名
                row["cls_last"] = last_class(root / r["meeting"], int(r["race"]), h["n"])
                row["cls_today"] = next((i for i, c in enumerate(HANDICAP, 1) if c in head), None)
                row["unproven"] = float(t >= HEAVY and not any(w >= t - NEAR for w in placed))
                row["heavy"] = t >= HEAVY
                l4 = [(x[3], x[1]) for x in runs if x[3]]
                row["l400_w"] = t - min(l4)[1] if l4 else np.nan
                row["l400_last_w"] = t - runs[0][1] if runs[0][3] else np.nan
            rows.append(row)
    df = pd.DataFrame(rows)
    g = df.groupby("race")
    df["zraw"] = (df.raw - g.raw.transform("mean")) / g.raw.transform("std").replace(0, np.nan)
    print(f"賽績檔搵唔到：{miss} 場")
    return df.dropna(subset=["zraw"]).reset_index(drop=True)


def boot(df, fn, n=1000):
    races = df.race.unique()
    idx = {r: np.where(df.race.values == r)[0] for r in races}
    rng = np.random.default_rng(0)
    bs = np.array([fn(df.iloc[np.concatenate([idx[r] for r in rng.choice(races, len(races))])]) for _ in range(n)])
    bs = bs[~np.isnan(bs)]
    p = 2 * min((bs <= 0).mean(), (bs >= 0).mean())
    return fn(df), np.percentile(bs, 2.5), np.percentile(bs, 97.5), min(1.0, p)


def coef(df, col):
    d = df.dropna(subset=[col])

    def fit(x):
        return LogisticRegression(max_iter=2000, C=1e6).fit(x[["zraw", col]], x.place).coef_[0][1]
    return (*boot(d, fit), len(d))


def resid_diff(df, mask_a, mask_b):
    """上名率 − 模型預期，A 組 − B 組。"""
    def fn(x):
        a, b = x[mask_a(x)], x[mask_b(x)]
        if not len(a) or not len(b):
            return np.nan
        return ((a.place - a.exp).mean() - (b.place - b.exp).mean()) * 100
    return boot(df, fn)


def table(df, label, groups):
    print(f"\n{label}")
    for lab, s in groups:
        if len(s):
            print(f"  {lab:<26} n={len(s):>5}  上名 {s.place.mean()*100:5.1f}%  模型預期 {s.exp.mean()*100:5.1f}%"
                  f"  差 {(s.place - s.exp).mean()*100:+6.2f}pp")


def main():
    df = build(sys.argv[1])
    print(f"讓磅賽 {df.race.nunique()} 場 / {len(df)} 匹（{df.date.min()} → {df.date.max()}）；有往績 {int((df.nruns > 0).sum())} 匹")
    df["exp"] = LogisticRegression(max_iter=2000, C=1e6).fit(df[["zraw"]], df.place).predict_proba(df[["zraw"]])[:, 1]
    h = df[df.nruns > 0].copy()

    print("\n== 1. 模型有冇高估重磅馬（上名率 vs 模型分預期）==")
    table(df, "全部馬，按今仗實際負磅", [("≥130 磅", df[df.today >= 130]), ("124–129", df[df.today.between(124, 129)]),
                                 ("≤123", df[df.today <= 123])])
    for lo, hi, lab in ((1, 1, "模型首選"), (1, 3, "模型頭三"), (4, 99, "模型 4 名以後")):
        s = df[df.mrank.between(lo, hi)]
        table(s, f"{lab}，按距頂磅", [("頂磅（距頂 ≤1）", s[s.from_top <= 1]), ("距頂 2–7", s[s.from_top.between(2, 7)]),
                                 ("距頂 ≥8", s[s.from_top >= 8])])
    s = df[df.mrank <= 3]
    p, lo, hi, pv = resid_diff(s, lambda x: x.from_top <= 1, lambda x: x.from_top > 1)
    print(f"  模型頭三：頂磅 − 其餘 = {p:+.2f}pp [{lo:+.2f},{hi:+.2f}] p={pv:.3f}")

    print("\n== 2. 預先登記特徵：place ~ z(模型) + 特徵（每磅 log-odds；unproven 係 0/1）==")
    res = []
    for c in ("dw_last", "dw_avg", "dw_place", "unproven", "l400_w"):
        p, lo, hi, pv, n = coef(h, c)
        res.append((c, p, lo, hi, pv, n))
    order = sorted(res, key=lambda x: x[4])
    holm = {c: min(1.0, pv * (len(res) - i)) for i, (c, _, _, _, pv, _) in enumerate(order)}
    for c, p, lo, hi, pv, n in res:
        print(f"  {c:<9} {p:+.4f} [{lo:+.4f},{hi:+.4f}]  p={pv:.3f}  Holm={holm[c]:.3f}  n={n}")

    print("\n== 3. 重磅馬（今仗 ≥130）：證明過 vs 未證明 ==")
    hv = h[h.heavy]
    table(hv, "全部重磅馬", [("證明過（近6仗 ≥今仗−2 磅上名）", hv[hv.unproven == 0]), ("未證明", hv[hv.unproven == 1]),
                          ("  其中：近6仗完全冇上名", hv[(hv.unproven == 1) & hv.never_placed.astype(bool)]),
                          ("  其中：有上名但都係輕磅", hv[(hv.unproven == 1) & ~hv.never_placed.astype(bool)])])
    p, lo, hi, pv = resid_diff(hv, lambda x: x.unproven == 1, lambda x: x.unproven == 0)
    print(f"  未證明 − 證明過 = {p:+.2f}pp [{lo:+.2f},{hi:+.2f}] p={pv:.3f}")
    t3 = hv[hv.mrank <= 3]
    table(t3, "重磅馬而且模型頭三", [("證明過", t3[t3.unproven == 0]), ("未證明", t3[t3.unproven == 1])])
    p, lo, hi, pv = resid_diff(t3, lambda x: x.unproven == 1, lambda x: x.unproven == 0)
    print(f"  未證明 − 證明過 = {p:+.2f}pp [{lo:+.2f},{hi:+.2f}] p={pv:.3f}")

    print("\n== 4. 加磅幅度（今仗 − 上仗）==")
    table(h, "全部", [("減 ≥8", h[h.dw_last <= -8]), ("減 3–7", h[h.dw_last.between(-7, -3)]), ("±2", h[h.dw_last.between(-2, 2)]),
                    ("加 3–7", h[h.dw_last.between(3, 7)]), ("加 8–14", h[h.dw_last.between(8, 14)]), ("加 ≥15", h[h.dw_last >= 15])])
    t3 = h[h.mrank <= 3]
    table(t3, "模型頭三", [("減 ≥3", t3[t3.dw_last <= -3]), ("±2", t3[t3.dw_last.between(-2, 2)]),
                       ("加 3–7", t3[t3.dw_last.between(3, 7)]), ("加 ≥8", t3[t3.dw_last >= 8])])

    print("\n== 5. 段速：段速分高（≥68）嘅馬，最快 L400 嗰仗係咩磅做 ==")
    sp = h[(h.speed >= 68) & h.l400_w.notna()]
    table(sp, "段速分 ≥68", [("今仗輕過或相若（≤+2）", sp[sp.l400_w <= 2]), ("今仗重 3–7", sp[sp.l400_w.between(3, 7)]),
                          ("今仗重 ≥8", sp[sp.l400_w >= 8])])
    p, lo, hi, pv = resid_diff(sp, lambda x: x.l400_w >= 8, lambda x: x.l400_w < 8)
    print(f"  今仗重 ≥8 − 其餘 = {p:+.2f}pp [{lo:+.2f},{hi:+.2f}] p={pv:.3f}")

    print("\n== 6. 近績：近績分高（≥75）嘅馬，今仗比上名嗰啲仗重幾多 ==")
    fm = h[(h.form >= 75) & h.dw_place.notna()]
    table(fm, "近績分 ≥75", [("≤+2", fm[fm.dw_place <= 2]), ("重 3–7", fm[fm.dw_place.between(3, 7)]), ("重 ≥8", fm[fm.dw_place >= 8])])
    p, lo, hi, pv = resid_diff(fm, lambda x: x.dw_place >= 8, lambda x: x.dw_place < 8)
    print(f"  重 ≥8 − 其餘 = {p:+.2f}pp [{lo:+.2f},{hi:+.2f}] p={pv:.3f}")

    print("\n== 7.（事後探索，唔係預先登記）近 6 仗有上過名嘅馬：喺今仗磅數上過名 vs 只喺輕磅上過名 ==")
    pl = h[~h.never_placed.astype(bool)].copy()
    for lab, s in (("今仗 ≥130", pl[pl.today >= 130]), ("今仗 124–129", pl[pl.today.between(124, 129)]), ("今仗 ≤123", pl[pl.today <= 123])):
        table(s, lab, [("喺今仗磅數上過名", s[s.at_weight == 1]), ("只喺輕磅上過名", s[s.at_weight == 0])])
        p, lo, hi, pv = resid_diff(s, lambda x: x.at_weight == 0, lambda x: x.at_weight == 1)
        print(f"  只喺輕磅 − 喺今仗磅數 = {p:+.2f}pp [{lo:+.2f},{hi:+.2f}] p={pv:.3f}")
    lt = pl[(pl.at_weight == 0) & pl.cls_last.notna()]
    table(lt, "只喺輕磅上過名，按班次變動", [("降班（今仗班次低過上仗）", lt[lt.cls_today > lt.cls_last]), ("同班", lt[lt.cls_today == lt.cls_last]),
                                   ("升班", lt[lt.cls_today < lt.cls_last])])
    for c in ("at_weight",):
        p, lo, hi, pv, n = coef(pl, c)
        print(f"  有上名馬：place ~ z(模型) + at_weight：{p:+.4f} [{lo:+.4f},{hi:+.4f}] p={pv:.3f} n={n}")
    np_ = h[h.never_placed.astype(bool)]
    table(np_, "近 6 仗冇上過名", [("今仗 ≥130", np_[np_.today >= 130]), ("今仗 124–129", np_[np_.today.between(124, 129)]), ("今仗 ≤123", np_[np_.today <= 123])])
    hv2 = np_[np_.today >= 130]
    hv2 = hv2[hv2.cls_last.notna()]
    table(hv2, "冇上過名＋重磅，按班次變動", [("降班", hv2[hv2.cls_today > hv2.cls_last]), ("同班", hv2[hv2.cls_today == hv2.cls_last])])
    tt = h[(h.today >= 130) & (h.mrank <= 3)]
    table(tt, "模型頭三＋重磅，三分", [("喺今仗磅數上過名", tt[tt.at_weight == 1]), ("只喺輕磅上過名", tt[(tt.at_weight == 0) & ~tt.never_placed.astype(bool)]),
                              ("近6仗冇上過名", tt[tt.never_placed.astype(bool)])])

    print("\n相關：", h[["dw_last", "dw_avg", "dw_place", "unproven", "from_top", "zraw"]].corr(method="spearman").round(2).to_string())


if __name__ == "__main__":
    main()
