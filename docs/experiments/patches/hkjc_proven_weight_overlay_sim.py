"""EXP-20261112-03：重磅未證明 → 總分扣 k 分（overlay 位置）嘅劑量梯。

點解可以離線做：正式排名 = `ability_score_raw` 由大到細（harness `_ranking`；baseline 449/449 場對得返），
overlay 係喺 9D 同 robustness 之後直接加喺 raw（`overlays.py`），所以「raw − k 再重排」同真回放等價。
k=0 會先同 baseline 逐場對 picks 同指標，唔一樣就停。

預先登記（跑之前寫死）：
  對象   讓磅賽、有往績、今仗實際負磅 ≥130、近 6 仗冇喺「今仗 − 2 磅」或以上上名（同 EXP-20261112-01 定義）
  劑量   k ∈ {0.5, 1.0, 1.5, 2.0, 3.0} raw 分（screening 反推 ≈ 0.2545 / 0.771 × 3.88 ≈ 1.3）
  切法   dev = 2026-09-06 之前；holdout = 2026-09-06 起（賽日中位，EXP-01 用過同一切點）
  揀法   只睇 dev：Gold、Good 都 ≥0 嘅 k 入面揀 Gold+Good 最大，打和揀細 k；冇一個合格 = REJECT，唔開 holdout
  判決   揀中嗰個 k 喺 holdout 用 harness compare（fixed_rule）判一次；全語料數字只做參考
  注意   訊號本身係喺全語料（包括 holdout 半）量出嚟，所以 holdout 唔係完全未見過；乾淨證據要靠 forward

用法：
  PYTHONDONTWRITEBYTECODE=1 python3 docs/experiments/patches/hkjc_proven_weight_overlay_sim.py <base.jsonl> <outdir>
"""
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
for p in (REPO / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts",
          REPO / ".agents/skills/hkjc_racing/hkjc_reflector/scripts",
          REPO / ".agents/skills/shared_racing", REPO, Path(__file__).resolve().parent):
    sys.path.insert(0, str(p))
from hkjc_weight_history_screen import HANDICAP, formguide  # noqa: E402

HARNESS = REPO / ".agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py"
RANKING = ("top3_capture_at5", "ndcg_at5", "competitive_recall_at5")
GRID = (0.5, 1.0, 1.5, 2.0, 3.0)
SPLIT = "2026-09-06"
HEAVY, NEAR = 130, 2


def flags(row, root):
    """{馬號: 'placed_light' | 'never_placed'}，只計讓磅賽。"""
    head, fg = formguide(root / row["meeting"], int(row["race"]))
    if not fg or not any(c in head for c in HANDICAP):
        return {}
    day = datetime.strptime(row["date"], "%Y-%m-%d").date()
    out = {}
    for n, e in fg.items():
        runs = sorted([x for x in e["runs"] if x[0] < day], reverse=True)[:6]
        t = e["today"]
        if not runs or t < HEAVY:
            continue
        placed = [x[1] for x in runs if x[2] is not None and x[2] <= 3]
        if not any(w >= t - NEAR for w in placed):
            out[n] = "placed_light" if placed else "never_placed"
    return out


def rescore(row, fl, k, kinds=("placed_light", "never_placed")):
    from eval_metrics import race_metrics
    horses = row["horses"]
    order = sorted(horses, key=lambda h: (-(h["raw"] - (k if fl.get(h["n"]) in kinds else 0.0)), h["n"]))
    picks = [h["n"] for h in order]
    pos = {h["n"]: h["pos"] for h in horses if h["pos"] is not None}
    m = race_metrics(picks, [n for n, p in pos.items() if p <= 3], actual_pos=pos)
    m["mean_top3_model_rank"] = m.get("top3_mean_model_rank")
    new = {k2: v for k2, v in row.items() if k2 != "horses"}
    new["picks"] = picks
    for key in ("gold", "gold_strict", "good_positional", "champion", *RANKING, "mean_top3_model_rank"):
        new[key] = m.get(key)
    return new


def compare(base, cand, out):
    r = subprocess.run([sys.executable, str(HARNESS), "compare", str(base), str(cand), "--stage4", "fixed_rule",
                        "--leakage-audit-passed", "--out", str(out)], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(r.stderr[-2000:])
    return json.loads(Path(out).read_text(encoding="utf-8"))


def line(rep):
    d = rep["verdict"]["detail"]
    g, q, n = d["primary"]["gold"], d["primary"]["good_positional"], d["ranking"]["ndcg_at5"]
    return (f"{rep['races']:>4} 場 郁 {rep['races_with_ranking_change']:>3}｜Gold {g['delta']*100:+.2f} [{g['ci_low']*100:+.2f},{g['ci_high']*100:+.2f}]"
            f"｜Good {q['delta']*100:+.2f} [{q['ci_low']*100:+.2f},{q['ci_high']*100:+.2f}]"
            f"｜NDCG {n['delta']:+.4f} [{n['ci_low']:+.4f},{n['ci_high']:+.4f}]｜{rep['verdict']['verdict']}/{rep['verdict']['reason']}"), g["delta"], q["delta"]


def main():
    import wongchoi_paths
    root = Path(wongchoi_paths.HK_RACING)
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    rows = [json.loads(x) for x in open(sys.argv[1], encoding="utf-8")]
    rows = [r for r in rows if "error" not in r and r.get("horses")]
    fl = {(r["meeting"], r["race"]): flags(r, root) for r in rows}
    print(f"{len(rows)} 場；受影響 {sum(1 for v in fl.values() if v)} 場 / {sum(len(v) for v in fl.values())} 匹"
          f"（有上名但輕磅 {sum(k == 'placed_light' for v in fl.values() for k in v.values())}、"
          f"冇上過名 {sum(k == 'never_placed' for v in fl.values() for k in v.values())}）")
    for r in rows:   # k=0 一定要逐場重現 baseline
        z = rescore(r, {}, 0.0)
        bad = [k for k in ("picks", "gold", "good_positional", *RANKING) if z[k] != r[k]]
        if bad:
            raise SystemExit(f"k=0 重現唔到 baseline：{r['meeting']} R{r['race']} {bad}")
    print("k=0 逐場重現 baseline：OK")

    def dump(name, sel, k=0.0, kinds=("placed_light", "never_placed")):
        p = out / f"{name}.jsonl"
        with open(p, "w", encoding="utf-8") as f:
            for r in rows:
                if sel(r):
                    f.write(json.dumps(rescore(r, fl[(r["meeting"], r["race"])], k, kinds), ensure_ascii=False) + "\n")
        return p

    parts = {"dev": lambda r: r["date"] < SPLIT, "holdout": lambda r: r["date"] >= SPLIT, "all": lambda r: True}
    base = {n: dump(f"base_{n}", s) for n, s in parts.items()}
    res = {}
    for k in GRID:
        for n, s in parts.items():
            res[(k, n)] = compare(base[n], dump(f"k{k}_{n}", s, k), out / f"k{k}_{n}.cmp.json")
    print("\n== dev（揀 k 只睇呢度）==")
    ok = []
    for k in GRID:
        text, g, q = line(res[(k, "dev")])
        print(f"  k={k}: {text}")
        if g >= 0 and q >= 0:
            ok.append((-(g + q), k))
    if not ok:
        print("\ndev 冇一個 k 合格（Gold、Good 都 ≥0）→ REJECT，holdout 唔開。")
        print("\n== 全語料（參考）==")
        for k in GRID:
            print(f"  k={k}: {line(res[(k, 'all')])[0]}")
        return
    pick = sorted(ok)[0][1]
    print(f"\n揀中 k={pick}")
    print("\n== holdout（只判揀中嗰個）==")
    print(f"  k={pick}: {line(res[(pick, 'holdout')])[0]}")
    print("\n== 全語料（參考）==")
    for k in GRID:
        print(f"  k={k}: {line(res[(k, 'all')])[0]}")
    print("\n== 拆開兩類（參考，全語料，k=揀中）==")
    for kind in ("placed_light", "never_placed"):
        rep = compare(base["all"], dump(f"k{pick}_{kind}", parts["all"], pick, (kind,)), out / f"k{pick}_{kind}.cmp.json")
        print(f"  只扣 {kind}: {line(rep)[0]}")
    print("\n== holdout 其餘 k（事後參考，唔用嚟揀）==")
    for k in GRID:
        if k != pick:
            print(f"  k={k}: {line(res[(k, 'holdout')])[0]}")


if __name__ == "__main__":
    main()
