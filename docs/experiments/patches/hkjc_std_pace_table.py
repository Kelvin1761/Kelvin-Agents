"""EXP-20261112-09 準備：按 Kelvin 2026-11-12 嘅定義重做「步速修正完成時間偏差」，逐場逐匹寫成 JSON 畀 arm 讀。

Kelvin：「步速修正偏差應該係每一段段速對馬會該路程同場地嘅標準去修正」（唔係而家嘅「減頭馬偏差」= 輸頭馬幾多秒），
另外要睇近 6 仗、逐仗連當時負磅。

每一仗（賽績檔：匹馬自己嘅分段時間、負磅、場地、路程；班次由 Logic `recent_6_detail`）：
  標準      馬會標準分段（`hkjc_standard_times.json` reference_sectionals），**一律用今仗班次**嗰行做共同標準
            （令唔同班次跑出嚟嘅往績可以直接比）；今仗班次喺嗰個場地路程冇標準就用嗰仗自己班次；都冇就唔計嗰仗
  偏差      dev = Σ(分段 − 標準分段)（= 完成時間 − 標準時間）
  步速修正  early = 末段之前各段偏差之和；adj = dev − (1 − ρ) × early
            ρ = 早段每慢 1 秒、末段平均追返幾多秒（馬匹 FE 回歸，只用 2026-05-03 之前嘅仗估；唔用賽果）
  負磅換算  adjw = adj + 0.01123 × 路程(km) ×（今仗實際負磅 − 嗰仗實際負磅）
  近 6 仗   權重 1/k（越近越重），最少 2 仗
三個值（每個加一樣嘢）：P0 = dev、P1 = adj、P2 = adjw（P2 = Kelvin 完整定義，主 arm）
四級門檻：只用 dev 半（< 2026-09-06）有現行等級嘅馬，按現行四級比例喺各自分佈上取分位數（唔睇賽果）

用法：PYTHONDONTWRITEBYTECODE=1 python3 docs/experiments/patches/hkjc_std_pace_table.py <base.jsonl> <out.json>
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / ".agents/scripts"))
BETA_KM, SPLIT, EVAL_START = 0.01123, "2026-09-06", "2026-05-03"
LEVELS = ("仍具競爭力", "接近平均", "仍偏慢", "明顯落後")
RUN = re.compile(r"\[(\d+)\]\s+(\d{2}/\d{2}/\d{4})\s*\|[^|\n]*\|\s*(\S+)\s+\"([^\"]*)\"\s+(\d{3,4})\s+(\S+)\s*\n"
                 r"[^\n]*負磅:\s*(\d+)[^\n]*名次:\s*(\S+)\s*/\s*(\d+)\s*\n[^\n]*分段時間:\s*([\d\., ]+)")
CLS = re.compile(r"第\d仗\((\d{2}/\d{2}/\d{4})\s+([^)]*?)\)")


def parse_fg(md, race_no):
    hits = sorted(p for p in md.glob("*賽績.*") if p.suffix in (".md", ".txt") and re.search(rf"Race[ _]{race_no}\b", p.name))
    out = {}
    if not hits:
        return out
    for block in re.split(r"\n(?=馬號:\s*\d+)", hits[0].read_text(encoding="utf-8")):
        m = re.match(r"馬號:\s*(\d+)", block)
        w = re.search(r"\n負磅:\s*(\d+)", block)
        if not m or not w:
            continue
        runs = []
        for r in RUN.finditer(block):
            secs = [float(x) for x in re.findall(r"\d+\.\d+", r.group(10))]
            venue = r.group(3) + ("AWT" if "AWT" in r.group(4).upper() else "")
            runs.append({"date": datetime.strptime(r.group(2), "%d/%m/%Y").date().isoformat(), "d": r.group(2), "venue": venue,
                         "dist": int(r.group(5)), "w": int(r.group(7)), "secs": secs})
        out[int(m.group(1))] = (int(w.group(1)), runs)
    return out


def main():
    import wongchoi_paths
    from inject_hkjc_fact_anchors import get_reference_sections
    root = Path(wongchoi_paths.HK_RACING)

    def ref(venue, dist, cls):
        r = get_reference_sections(venue, dist, cls) if cls else {}
        return r.get("sections") or None

    recs, per_race = [], {}
    for line in open(sys.argv[1], encoding="utf-8"):
        x = json.loads(line)
        if "error" in x or not x.get("horses"):
            continue
        md = root / x["meeting"]
        logic = json.loads((md / f"Race_{x['race']}_Logic.json").read_text(encoding="utf-8"))
        today_cls = str((logic.get("race_analysis") or {}).get("race_class") or "")
        fg = parse_fg(md, int(x["race"]))
        rows = {}
        for h in x["horses"]:
            lg = (logic.get("horses") or {}).get(str(h["n"])) or {}
            e = fg.get(h["n"])
            if not e:
                continue
            today_w, runs = e
            cls_by_date = dict(CLS.findall(str((lg.get("_data") or {}).get("recent_6_detail") or "")))
            lvl = str((lg.get("_data") or {}).get("finish_time_adj_level") or "")
            cur = next((i for i, s in enumerate(LEVELS) if s in lvl), None)
            use = []
            for r in sorted([r for r in runs if r["date"] < x["date"]], key=lambda r: r["date"], reverse=True)[:6]:
                std = ref(r["venue"], r["dist"], today_cls) or ref(r["venue"], r["dist"], cls_by_date.get(r["d"]))
                if not std or len(std) != len(r["secs"]):
                    continue
                dev = [a - b for a, b in zip(r["secs"], std)]
                use.append({"date": r["date"], "horse": lg.get("horse_name"), "dist": r["dist"], "w": r["w"],
                            "dev": sum(dev), "early": sum(dev[:-1]), "l400": dev[-1]})
            rows[h["n"]] = (today_w, use, cur)
            recs.extend(use)
        per_race[(x["meeting"], x["race"], x["date"])] = rows
    A = pd.DataFrame(recs).drop_duplicates(["horse", "date"])
    pre = A[A.date < EVAL_START]
    pre = pre[pre.groupby("horse").date.transform("count") >= 3]
    d = pre[["l400", "early"]] - pre.groupby("horse")[["l400", "early"]].transform("mean")
    rho = -float((d.l400 * d.early).sum() / (d.early ** 2).sum())
    rho_by = {}
    for lab, s in (("≤1200", pre[pre.dist <= 1200]), ("1400–1650", pre[pre.dist.between(1400, 1650)]), ("≥1800", pre[pre.dist >= 1800])):
        dd = s[["l400", "early"]] - s.groupby("horse")[["l400", "early"]].transform("mean")
        rho_by[lab] = round(-float((dd.l400 * dd.early).sum() / (dd.early ** 2).sum()), 3)
    print(f"往績 {len(A)} 仗（去重），估 ρ 用 {len(pre)} 仗 / {pre.horse.nunique()} 匹（< {EVAL_START}）")
    print(f"ρ = {rho:.3f}（早段每慢 1 秒，末段追返 {rho:.2f} 秒）；分路程 {rho_by}  ← 預先登記用全路程單一 ρ")
    print(f"早段偏差 SD {A.early.std():.2f}s；末段偏差 SD {A.l400.std():.2f}s；完成時間偏差 SD {A.dev.std():.2f}s")

    table, dev_vals = {}, {0: [], 1: [], 2: []}
    cover = [0, 0]
    for (meeting, race, date), rows in per_race.items():
        out = {}
        for n, (today_w, use, cur) in rows.items():
            cover[1] += 1
            if len(use) < 2:
                continue
            cover[0] += 1
            wt = 1.0 / np.arange(1, len(use) + 1)
            p0 = np.array([u["dev"] for u in use])
            p1 = np.array([u["dev"] - (1 - rho) * u["early"] for u in use])
            p2 = p1 + np.array([BETA_KM * u["dist"] / 1000.0 * (today_w - u["w"]) for u in use])
            vals = [float((v * wt).sum() / wt.sum()) for v in (p0, p1, p2)]
            out[str(n)] = [round(v, 4) for v in vals]
            if cur is not None and date < SPLIT:
                for i in range(3):
                    dev_vals[i].append((vals[i], cur))
        table[f"{meeting}|{race}"] = out
    K = np.array([k for _v, k in dev_vals[0]])
    shares = [float((K == i).mean()) for i in range(4)]
    cuts = {}
    for i in range(3):
        v = np.array([a for a, _k in dev_vals[i]])
        cuts[f"P{i}"] = [float(np.quantile(v, sum(shares[:j + 1]))) for j in range(3)]     # 偏差越細越好
        rk = np.corrcoef(np.argsort(np.argsort(v)), np.argsort(np.argsort(K)))[0, 1]
        print(f"P{i}：門檻（秒）{[round(c, 3) for c in cuts[f'P{i}']]}；同現行等級 Spearman {rk:+.3f}")
    json.dump({"rho": rho, "shares": shares, "cuts": cuts, "table": table}, open(sys.argv[2], "w"))
    print(f"現行四級比例 {[round(s, 3) for s in shares]}；有新數值 {cover[0]}/{cover[1]} 匹（{cover[0]/cover[1]*100:.1f}%）")


if __name__ == "__main__":
    main()
