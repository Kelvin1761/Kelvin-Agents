# ruff: noqa
"""EXP-20261113-07：前段組件唔換算負磅（Kelvin：「前段負磅基本唔影響」）。
預先登記：同 EXP-04／06 一樣，只改一樣 —— 前段偏差唔加負磅換算。標準化 mean／SD 用 dev 半重估。
版本：V0 雙向、V1 單邊（慢唔扣）；b ∈ {0.25, 0.5}；dev < 09-06 揀、holdout ≥ 09-06 判；null = 場內調換 z 100 次。
另報有／冇負磅兩個值嘅相關，同埋有負磅版喺同一離線框架嘅結果做對照。"""
import json, sys
from pathlib import Path
import numpy as np
REPO = Path.cwd()
sys.path.insert(0, str(REPO / "docs/experiments/patches")); sys.path.insert(0, str(REPO / ".agents/scripts")); sys.path.insert(0, str(REPO / ".agents/skills/shared_racing"))
from hkjc_std_pace_table import parse_fg
from eval_metrics import race_metrics
import wongchoi_paths
from inject_hkjc_fact_anchors import get_reference_sections
BETA = 0.01123; SD = 9.4487; N = sys.argv[1]
root = Path(wongchoi_paths.HK_RACING)

def front(items, tw, use_w):
    vals = []
    for dist, secs, w, std in items[:6]:
        if not std or len(std) != len(secs) or len(std) < 3 or dist <= 400 or (use_w and (w is None or tw is None)):
            continue
        lens = [dist - 400 * (len(std) - 1)] + [400] * (len(std) - 1)
        d = [a - b + (BETA * L / 1000.0 * (tw - w) if use_w else 0.0) for a, b, L in zip(secs, std, lens)]
        vals.append(sum(d[:-1]) / ((dist - 400) / 400.0))
    if len(vals) < 2:
        return None
    wt = [1.0 / k for k in range(1, len(vals) + 1)]
    return -sum(v * x for v, x in zip(vals, wt)) / sum(wt)

R = []
for line in open(f"{N}/lab/labels_final.jsonl"):
    x = json.loads(line)
    if "error" in x or not x.get("horses"):
        continue
    pos = {h["n"]: h["pos"] for h in x["horses"] if h["pos"]}
    if sum(p <= 3 for p in pos.values()) < 3:
        continue
    md = root / x["meeting"]
    cls = str((json.loads((md / f"Race_{x['race']}_Logic.json").read_text(encoding="utf-8")).get("race_analysis") or {}).get("race_class") or "")
    fg = parse_fg(md, int(x["race"]))
    hs = []
    for h in x["horses"]:
        fw = fn = None
        e = fg.get(h["n"])
        if e and cls:
            tw, runs = e
            runs = sorted([r for r in runs if r["date"] < x["date"]], key=lambda r: r["date"], reverse=True)[:6]
            items = [(r["dist"], r["secs"], r["w"], [float(s) for s in ((get_reference_sections(r["venue"], r["dist"], cls) or {}).get("sections") or [])] or None) for r in runs]
            fw, fn = front(items, tw, True), front(items, tw, False)
        hs.append({"n": h["n"], "raw": h["raw"], "speed": h["f"]["speed_score"], "pos": h["pos"], "fw": fw, "fn": fn})
    R.append({"x": x, "hs": hs, "pos": pos, "dev": x["date"] < "2026-09-06"})
dev = np.array([r["dev"] for r in R])
pairs = np.array([(h["fw"], h["fn"]) for r in R for h in r["hs"] if h["fw"] is not None and h["fn"] is not None])
print(f"{len(R)} 場（dev {dev.sum()}／holdout {(~dev).sum()}）；有／冇負磅相關 r = {np.corrcoef(pairs.T)[0,1]:.3f}，"
      f"差異 SD {np.std(pairs[:,0]-pairs[:,1]):.3f} vs 值 SD {np.std(pairs[:,1]):.3f} s/400m")
stats = {}
for key in ("fw", "fn"):
    v = [h[key] for r in R if r["dev"] for h in r["hs"] if h[key] is not None]
    stats[key] = (np.mean(v), np.std(v))
    for r in R:
        for h in r["hs"]:
            h["z_" + key] = None if h[key] is None else max(-2.5, min(2.5, (h[key] - stats[key][0]) / stats[key][1]))
print("dev 標準化：", {k: (round(a, 3), round(b, 3)) for k, (a, b) in stats.items()})

def met(r, s):
    n = np.array([h["n"] for h in r["hs"]]); order = list(n[np.lexsort((n, -np.array(s)))])
    m = race_metrics(order, [k for k, p in r["pos"].items() if p <= 3], actual_pos=r["pos"])
    return [m["gold"], m["good_positional"], m["top3_capture_at5"], (m.get("top2_hits") or 0) >= 1]

def run(key, V, b, zmap=None):
    out = []
    for i, r in enumerate(R):
        s = []
        for j, h in enumerate(r["hs"]):
            z = h["z_" + key] if zmap is None else zmap[i][j]
            v = h["raw"]
            if z is not None:
                pts = b * SD * (z if V == "V0" else max(z, 0))
                v += 0.1285 * (min(100, max(0, h["speed"] + pts)) - h["speed"])
            s.append(v)
        out.append(met(r, s))
    return np.array(out, float)

base = run("fn", "V0", 0.0)
rng = np.random.default_rng(5)
K = ("Gold", "Good", "cap5", "頭二")
f = lambda d: "｜".join(f"{k} {v:+.2f}" for k, v in zip(K, d))
for key, lab in (("fn", "冇負磅"), ("fw", "有負磅（對照）")):
    for V in ("V0", "V1"):
        for b in (0.25, 0.5):
            D = (run(key, V, b) - base) * 100
            NL = []
            for _ in range(100):
                zm = []
                for r in R:
                    zs = [h["z_" + key] for h in r["hs"] if h["z_" + key] is not None]; rng.shuffle(zs); it = iter(zs)
                    zm.append([next(it) if h["z_" + key] is not None else None for h in r["hs"]])
                NL.append((run(key, V, b, zm) - base) * 100)
            NL = np.array(NL)
            print(f"{lab} {V} b={b}")
            for nm, m in (("dev", dev), ("holdout", ~dev)):
                d = D[m].mean(0); nd = NL[:, m].mean(1)
                print(f"  {nm:<7} {f(d)}｜null 百分位 Gold {np.mean(nd[:,0] < d[0])*100:.0f}% Good {np.mean(nd[:,1] < d[1])*100:.0f}% cap5 {np.mean(nd[:,2] < d[2])*100:.0f}% 頭二 {np.mean(nd[:,3] < d[3])*100:.0f}%", flush=True)
