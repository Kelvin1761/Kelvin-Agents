"""EXP-20261112-10：「步速修正等級」用 P3（現行：近 3 仗輸頭馬幾多秒）同 P0／P1／P2（EXP-09 對馬會標準）加權混合。

Kelvin 2026-11-12：「P2 同現行差少少，應該係正確方向；加埋輸頭馬幾多秒做 P3，或者調 P0／P1／P2 嘅比重。」

預先登記（跑之前寫死）：
  對象   只改「現行已有等級（P3 有值）而且有 P0／P1／P2」嘅馬；其餘一律唔郁
         （咁做段速訊號數目唔變，離線模擬同真回放等價，見下）
  標準化 z = 值 ÷ dev 半（< 2026-09-06）同一 population 嘅 SD；全部「越細越好」
  混合   b = w × z(Px) + (1 − w) × z(P3)，x ∈ {0, 1, 2}，w ∈ {0.25, 0.5, 0.75}；w = 1 只做參考
  門檻   b 喺 dev 半嘅分位數，比例 = 現行四級喺同一 population 嘅比例（唔睇賽果）
  加減分 照現行 SPEED_MICRO_WEIGHTS：+6.52／+1.42／−4／−8
  揀法   **只有 P2 混合**有資格揀（主 arm）；P0／P1 混合只做 ablation。
         dev 上 Gold、Good 都 ≥0 嘅 w 入面揀 Gold+Good 最大，打和揀細 w；冇合格 = REJECT，唔開 holdout
  判決   揀中嗰個喺 holdout（≥ 2026-09-06）用 harness compare（fixed_rule）判一次；之後再用真回放確認
  注意   holdout 半喺 EXP-07／08／09 已經睇過，唔係乾淨未見過；乾淨證據要靠 forward

離線等價：段速分只改等級加減分 → 段速分變 Δ；raw 變 = r × Δ，r 由 EXP-09 P2 真回放逐匹量（0.127–0.130，只經 sectional 維度）。
k=0（全部唔郁）必須逐場重現 baseline，否則停。

用法：
  PYTHONDONTWRITEBYTECODE=1 python3 docs/experiments/patches/hkjc_pace_blend_sim.py <base.jsonl> <stdP2.jsonl> <stdtable.json> <outdir>
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
for p in (REPO, REPO / ".agents/skills/shared_racing", REPO / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts"):
    sys.path.insert(0, str(p))
HARNESS = REPO / ".agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py"
RANKING = ("top3_capture_at5", "ndcg_at5", "competitive_recall_at5")
LEVELS = ("仍具競爭力", "接近平均", "仍偏慢", "明顯落後")
SPLIT = "2026-09-06"
GRID = (0.25, 0.5, 0.75)
# 第二輪（EXP-20261112-10 leaf 篩選之後先加，跑之前寫死）：用 EXP-08 PIT 表現數字（W = 按今仗負磅換算，主；U = 唔換算，ablation）
# 同 P3 混合；leaf 層 figW 喺 P3 之上 −0.360 [−0.494,−0.235] 而 P3 跌到 −0.090 跨零，所以 w = 1 都有資格揀。
FIG_GRID = (0.5, 0.75, 1.0)


def main():
    import wongchoi_paths
    from eval_metrics import race_metrics
    from hkjc_racing_engine import scoring
    W = scoring.SPEED_MICRO_WEIGHTS
    PTS = (W["finish_competitive_bonus"], W["finish_avg_bonus"], W["finish_slow_pen"], W["finish_far_behind_pen"])
    root = Path(wongchoi_paths.HK_RACING)
    base_path, p2_path, table_path, out = sys.argv[1], sys.argv[2], sys.argv[3], Path(sys.argv[4])
    fig_mode = len(sys.argv) > 5      # argv[5] = figtable.json → 用表現數字（F／W），X 軸 0 = U、1 = W
    out.mkdir(parents=True, exist_ok=True)
    rows = [r for r in map(json.loads, open(base_path, encoding="utf-8")) if "error" not in r and r.get("horses")]
    p2run = {(r["meeting"], r["race"]): r for r in map(json.loads, open(p2_path, encoding="utf-8")) if "error" not in r and r.get("horses")}
    table = json.load(open(table_path))["table"]
    if fig_mode:
        ft = json.load(open(sys.argv[5]))["table"]
        table = {k: {n: [-v[0], -v[1], -v[1]] for n, v in row.items()} for k, row in ft.items()}   # 轉做越細越好；第 3 欄留空位

    # 每匹：現行等級、P3 數值、P0/P1/P2、r（raw 對段速分嘅傳導）
    info, ratios = {}, []
    for r in rows:
        logic = json.loads((root / r["meeting"] / f"Race_{r['race']}_Logic.json").read_text(encoding="utf-8")).get("horses") or {}
        tab = table.get(f"{r['meeting']}|{r['race']}") or {}
        alt = {h["n"]: h for h in p2run[(r["meeting"], r["race"])]["horses"]}
        for h in r["horses"]:
            lvl = str(((logic.get(str(h["n"])) or {}).get("_data") or {}).get("finish_time_adj_level") or "")
            cur = next((i for i, s in enumerate(LEVELS) if s in lvl), None)
            m = re.search(r"修正平均:\s*([+-]?\d+\.\d+)s", lvl)
            ds = alt[h["n"]]["f"]["speed_score"] - h["f"]["speed_score"]
            rr = (alt[h["n"]]["raw"] - h["raw"]) / ds if abs(ds) > 1e-9 else None
            if rr:
                ratios.append(rr)
            info[(r["meeting"], r["race"], h["n"])] = {"cur": cur, "p3": float(m.group(1)) if m else None,
                                                         "p": tab.get(str(h["n"])), "r": rr, "speed": h["f"]["speed_score"],
                                                         "date": r["date"]}
    r_med = float(np.median(ratios))
    pop = [v for v in info.values() if v["cur"] is not None and v["p3"] is not None and v["p"]]
    dev = [v for v in pop if v["date"] < SPLIT]
    print(f"{len(rows)} 場；可改嘅馬 {len(pop)}（dev {len(dev)}）；r 中位 {r_med:.4f}（{len(ratios)} 匹實測）")
    # 現行等級同 P3 一致性
    cuts3 = (0.3, 0.8, 1.3)
    agree = np.mean([v["cur"] == (0 if v["p3"] < cuts3[0] else 1 if v["p3"] < cuts3[1] else 2 if v["p3"] < cuts3[2] else 3) for v in pop])
    print(f"現行等級 = P3 門檻（0.3／0.8／1.3）一致：{agree*100:.1f}%")
    shares = [np.mean([v["cur"] == i for v in dev]) for i in range(4)]
    sd = {"p3": float(np.std([v["p3"] for v in dev]))}
    for x in range(3):
        sd[x] = float(np.std([v["p"][x] for v in dev])) or 1.0
    print(f"dev 四級比例 {[round(s, 3) for s in shares]}；SD P3 {sd['p3']:.3f}、P0 {sd[0]:.3f}、P1 {sd[1]:.3f}、P2 {sd[2]:.3f}")
    for x in range(3):
        print(f"  corr(P3, P{x}) = {np.corrcoef([v['p3'] for v in pop], [v['p'][x] for v in pop])[0, 1]:+.3f}")

    def levels(x, w):
        def b(v):
            return w * v["p"][x] / sd[x] + (1 - w) * v["p3"] / sd["p3"]
        dv = np.array([b(v) for v in dev])
        cuts = [float(np.quantile(dv, sum(shares[:j + 1]))) for j in range(3)]
        res = {}
        for k, v in info.items():
            if v in pop:
                bb = b(v)
                res[k] = 0 if bb < cuts[0] else 1 if bb < cuts[1] else 2 if bb < cuts[2] else 3
        return res

    def rescore(row, lv):
        horses = []
        for h in row["horses"]:
            v = info[(row["meeting"], row["race"], h["n"])]
            raw = h["raw"]
            if (row["meeting"], row["race"], h["n"]) in lv:
                new = min(100.0, max(0.0, v["speed"] - PTS[v["cur"]] + PTS[lv[(row["meeting"], row["race"], h["n"])]]))
                raw += (v["r"] or r_med) * (new - v["speed"])
            horses.append((raw, h["n"]))
        picks = [n for _s, n in sorted(horses, key=lambda t: (-t[0], t[1]))]
        pos = {h["n"]: h["pos"] for h in row["horses"] if h["pos"] is not None}
        m = race_metrics(picks, [n for n, p in pos.items() if p <= 3], actual_pos=pos)
        m["mean_top3_model_rank"] = m.get("top3_mean_model_rank")
        new = {a: v for a, v in row.items() if a != "horses"}
        new["picks"] = picks
        for key in ("gold", "gold_strict", "good_positional", "champion", *RANKING, "mean_top3_model_rank"):
            new[key] = m.get(key)
        return new

    for r in rows:
        z = rescore(r, {})
        if any(z[a] != r[a] for a in ("picks", "gold", "good_positional", *RANKING)):
            raise SystemExit(f"k=0 重現唔到 baseline：{r['meeting']} R{r['race']}")
    print("k=0 逐場重現 baseline：OK")
    lv0 = levels(2, 0.0)
    print(f"w=0（只用 P3 分位數）同現行等級一致：{np.mean([lv0[k] == info[k]['cur'] for k in lv0])*100:.1f}%")

    def dump(name, sel, lv):
        p = out / f"{name}.jsonl"
        with open(p, "w", encoding="utf-8") as f:
            for r in rows:
                if sel(r):
                    f.write(json.dumps(rescore(r, lv), ensure_ascii=False) + "\n")
        return p

    def compare(b, c, o):
        res = subprocess.run([sys.executable, str(HARNESS), "compare", str(b), str(c), "--stage4", "fixed_rule",
                              "--leakage-audit-passed", "--out", str(o)], capture_output=True, text=True)
        if res.returncode:
            raise SystemExit(res.stderr[-1500:])
        return json.loads(Path(o).read_text(encoding="utf-8"))

    def line(rep):
        d = rep["verdict"]["detail"]
        g, q = d["primary"]["gold"], d["primary"]["good_positional"]
        c, n = d["ranking"]["top3_capture_at5"], d["ranking"]["ndcg_at5"]
        return (f"{rep['races']:>4} 場 郁 {rep['races_with_ranking_change']:>3}｜Gold {g['delta']*100:+.2f} [{g['ci_low']*100:+.2f},{g['ci_high']*100:+.2f}]"
                f"｜Good {q['delta']*100:+.2f} [{q['ci_low']*100:+.2f},{q['ci_high']*100:+.2f}]｜capture@5 {c['delta']*100:+.2f}"
                f"｜NDCG {n['delta']:+.4f}｜{rep['verdict']['verdict']}/{rep['verdict']['reason']}"), g["delta"], q["delta"]

    parts = {"dev": lambda r: r["date"] < SPLIT, "holdout": lambda r: r["date"] >= SPLIT, "all": lambda r: True}
    base = {n: dump(f"base_{n}", s, {}) for n, s in parts.items()}
    res = {}
    xs = (1, 0) if fig_mode else (2, 1, 0)
    grid = FIG_GRID if fig_mode else (*GRID, 1.0)
    main_x = 1 if fig_mode else 2
    name = (lambda x: ("figU", "figW")[x]) if fig_mode else (lambda x: f"P{x}")
    for x in xs:
        for w in grid:
            lv = levels(x, w)
            moved = np.mean([lv[k] != info[k]["cur"] for k in lv]) * 100
            for n, s in parts.items():
                res[(x, w, n)] = (compare(base[n], dump(f"{name(x)}_w{w}_{n}", s, lv), out / f"{name(x)}_w{w}_{n}.cmp.json"), moved)
    print("\n== dev（< 2026-09-06）==")
    ok = []
    for x in xs:
        tag = "主 arm" if x == main_x else "ablation"
        for w in grid:
            rep, moved = res[(x, w, "dev")]
            text, g, q = line(rep)
            eligible = x == main_x and (fig_mode or w in GRID)
            note = "" if eligible or x != main_x else "（只做參考）"
            print(f"  {name(x)} w={w:<4} 換級 {moved:4.1f}%：{text} {tag}{note}")
            if eligible and g >= 0 and q >= 0:
                ok.append((-(g + q), w))
    if not ok:
        print(f"\ndev 冇一個 {name(main_x)} 混合合格 → REJECT，holdout 唔開。")
        pick = None
    else:
        pick = sorted(ok)[0][1]
        print(f"\n揀中 {name(main_x)} w={pick}")
        print("== holdout（只判揀中）==")
        print(f"  {name(main_x)} w={pick}: {line(res[(main_x, pick, 'holdout')][0])[0]}")
    print("\n== 全語料（參考）==")
    for x in xs:
        for w in grid:
            print(f"  {name(x)} w={w:<4}: {line(res[(x, w, 'all')][0])[0]}")
    print("== holdout 全部（事後參考，唔用嚟揀）==")
    for x in xs:
        for w in grid:
            print(f"  {name(x)} w={w:<4}: {line(res[(x, w, 'holdout')][0])[0]}")
    if pick is not None:
        print("分層（全語料，揀中）：", json.dumps(res[(main_x, pick, "all")][0]["cohorts"], ensure_ascii=False))
        json.dump({"sd": sd, "shares": shares, "pick": pick}, open(out / "pick.json", "w"))


if __name__ == "__main__":
    main()
