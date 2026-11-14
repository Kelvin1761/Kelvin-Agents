"""HKJC 歷史引擎回放：忠實度閘（docs/plans/2026-11-13-hkjc-historic-engine-replay.md 第 3 步）。

比較同一批 2026 場次：真版（live 輸入，harness --dump-matrix）vs 回放版（歷史輸入生成）。
Kelvin 2026-11-13：對照用「真版減能量」—— 回放冇 SpeedPRO 能量，所以真版先扣走能量小項
（0.1285 × Δspeed），差異先係「其他欄位砌錯」。

預先登記門檻（寫死，唔准調）：
  raw 分場內 Spearman 中位數 ≥ 0.90；首選一致率 ≥ 80%；Gold、Good 同真版減能量相差各 ≤ 2pp
另外逐維度報場內 Spearman 中位數，用嚟搵邊個欄位砌錯（唔係閘）。

用法：python3 hkjc_history_replay_fidelity.py <real_dump.jsonl> <replay_dump.jsonl>
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[5]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / ".agents/skills/shared_racing"))
import wongchoi_paths  # noqa: E402
from eval_metrics import race_metrics  # noqa: E402

W_SECT = 0.1285
DIMS = ("stability", "trainer_signal", "sectional", "race_shape", "horse_health", "distance_fit", "form_line", "class_advantage")


def energy_bonus(text) -> float:
    e = str(text or "")
    if "上升" in e and "✅" in e:
        return 1.96
    if "穩定" in e:
        return 2.78
    if "下降" in e and "⚠️" in e:
        return -2.74
    return 0.0


def spearman(a, b) -> float | None:
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 3 or a.std() == 0 or b.std() == 0:
        return None
    ra, rb = a.argsort().argsort(), b.argsort().argsort()
    return float(np.corrcoef(ra, rb)[0, 1])


def picks_of(ns, score):
    ns, s = np.asarray(ns), np.asarray(score, float)
    return [int(v) for v in ns[np.lexsort((ns, -s))]]


def metrics(picks, horses):
    pos = {h["n"]: h["pos"] for h in horses if h["pos"]}
    top = [k for k, p in pos.items() if p <= 3]
    if len(top) < 3:
        return None
    m = race_metrics(picks, top, actual_pos=pos)
    return [float(m["gold"]), float(m["good_positional"]), float(m["top3_capture_at5"]), float(m["top2_any_hit"])]


def main() -> None:
    real = {(x["meeting"], x["race"]): x for x in map(json.loads, open(sys.argv[1])) if "horses" in x}
    rep = {(x["meeting"], x["race"]): x for x in map(json.loads, open(sys.argv[2])) if "horses" in x}
    # 同 hkjc_eval_harness compare 一樣（預設 --exclude-dead speed_score）：真版段速 leaf 死咗嘅賽日唔比 ——
    # 嗰啲係真版數據壞（2026-04 幾個賽日 speed_score 全 60），唔係回放錯。
    dead = {k for k, x in real.items() if "speed_score" in (x.get("meeting_dead_fields") or [])}
    # 真版舊格式賽日（rescore_backtest.meeting_is_legacy_schema：_data 中位數 < 20 欄，2026-04 至 05 初）
    # 冇抓馬匹頁、冇醫療／近六仗／賽績線表 —— 真版本身降級，唔可以用嚟量回放忠唔忠實。
    sys.path.insert(0, str(_HERE.parent))
    from rescore_backtest import meeting_is_legacy_schema
    legacy_meet = {m for m in {k[0] for k in real} if meeting_is_legacy_schema(Path(wongchoi_paths.HK_RACING) / m)}
    legacy = {k for k in real if k[0] in legacy_meet}
    keys = sorted((set(real) & set(rep)) - dead - legacy)
    print(f"剔走真版段速死咗嘅場次：{len(dead)}；真版舊格式賽日 {len(legacy_meet)} 個（{len(legacy)} 場）；兩樣合共剔 {len(dead | legacy)} 場")
    print(f"真版 {len(real)} 場、回放 {len(rep)} 場、共同 {len(keys)} 場")
    rho_raw, rho_dim, same_top, M_real, M_rep, runner_mismatch = [], {d: [] for d in DIMS}, 0, [], [], 0
    for k in keys:
        a, b = real[k], rep[k]
        logic = Path(wongchoi_paths.HK_RACING) / a["meeting"] / f"Race_{a['race']}_Logic.json"
        try:
            H = json.loads(logic.read_text(encoding="utf-8"))["horses"]
            eb = {int(n): energy_bonus((h.get("_data") or {}).get("energy_trend")) for n, h in H.items()}
        except (OSError, ValueError, KeyError):
            eb = {}
        ah = {h["n"]: h for h in a["horses"]}
        bh = {h["n"]: h for h in b["horses"]}
        ns = sorted(set(ah) & set(bh))
        if set(ah) != set(bh):
            runner_mismatch += 1
        if len(ns) < 3:
            continue
        def raw_minus_energy(h):
            sp = h["f"]["speed_score"]
            return h["raw"] - W_SECT * (sp - max(0.0, min(100.0, sp - eb.get(h["n"], 0.0))))
        ra = [raw_minus_energy(ah[n]) for n in ns]
        rb = [bh[n]["raw"] for n in ns]
        r = spearman(ra, rb)
        if r is not None:
            rho_raw.append(r)
        for d in DIMS:
            r = spearman([ah[n]["m"].get(d, 60) for n in ns], [bh[n]["m"].get(d, 60) for n in ns])
            if r is not None:
                rho_dim[d].append(r)
        pa, pb = picks_of(ns, ra), picks_of(ns, rb)
        same_top += pa[0] == pb[0]
        hs = [ah[n] for n in ns]
        ma, mb = metrics(pa, hs), metrics(pb, hs)
        if ma and mb:
            M_real.append(ma)
            M_rep.append(mb)
    n = len(rho_raw)
    med = float(np.median(rho_raw)) if rho_raw else float("nan")
    top_rate = same_top / max(len(keys), 1)
    A, B = np.array(M_real), np.array(M_rep)
    d = B - A
    bs = d[np.random.default_rng(0).integers(0, len(d), (2000, len(d)))].mean(1)
    print(f"\n跑者名單唔一致：{runner_mismatch} 場")
    print(f"raw 場內 Spearman 中位數 {med:.3f}（{n} 場）｜門檻 ≥ 0.90 → {'✅' if med >= 0.90 else '❌'}")
    print(f"首選一致 {top_rate * 100:.1f}%｜門檻 ≥ 80% → {'✅' if top_rate >= 0.80 else '❌'}")
    for i, lab in enumerate(("Gold", "Good", "capture@5", "頭二選有中")):
        diff = d[:, i].mean() * 100
        gate = "" if i > 1 else (f"｜門檻 |差| ≤ 2pp → {'✅' if abs(diff) <= 2 else '❌'}")
        print(f"{lab}：真版減能量 {A[:, i].mean() * 100:.2f}%｜回放 {B[:, i].mean() * 100:.2f}%｜差 {diff:+.2f} "
              f"[{np.percentile(bs[:, i], 2.5) * 100:+.2f},{np.percentile(bs[:, i], 97.5) * 100:+.2f}]{gate}")
    print("\n逐維度場內 Spearman 中位數（診斷，唔係閘）：")
    for dname in DIMS:
        v = rho_dim[dname]
        print(f"  {dname:<16} {np.median(v) if v else float('nan'):.3f}（{len(v)} 場有變化）")


if __name__ == "__main__":
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    main()
