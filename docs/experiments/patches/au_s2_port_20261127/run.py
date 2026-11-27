#!/usr/bin/env python3
"""EXP-20261127-02（見 PROTOCOL.md）。 run.py BASE.json OUT.json"""
import collections, json, sys
from pathlib import Path
import numpy as np
REPO = Path(__file__).resolve().parents[4]
SC = REPO / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
for p in (SC, REPO / ".agents/skills/shared_racing", REPO / ".agents/skills/shared_racing/scripts", REPO / "scratch"):
    sys.path.insert(0, str(p))
import au_logloss_ruler as L  # noqa: E402
import au_sb_total_speed_20261016 as sb  # noqa: E402
from au_racing_engine.scoring import MATRIX_WEIGHTS  # noqa: E402
from au_walkforward_refit import exact_score  # noqa: E402
from au_archive_calibrator import ARCHIVE_ROOT  # noqa: E402

dump = json.loads(Path(sys.argv[1]).read_text())
base = L.eligible(dump["races"])
mism = sum(1 for r in base for x in r["rows"] if abs(exact_score(x, MATRIX_WEIGHTS) - x["ability"]) > 0.02)
print("baseline 重算唔夾", mism, "／", sum(len(r["rows"]) for r in base), flush=True)
events, histories, audit = sb.parse_corpus(ARCHIVE_ROOT)
print("sb audit", dict(audit), flush=True)
asb = sb.compute_asb({"races": base}, events, histories)
cov = sum(1 for v in asb.values() if v["raw"] is not None) / max(len(asb), 1)
print("A_sb coverage", round(cov, 3), flush=True)
W_UP = dict(MATRIX_WEIGHTS); W_UP["pace_perf"] = MATRIX_WEIGHTS["pace_perf"] * (0.177 / 0.108)

def arm(speed_on, weights):
    out = []
    for r in base:
        rows = []
        for x in r["rows"]:
            d = asb.get(f"{r['date']}|{r['meeting']}|{r['race']}|{x['n']}") or {}
            z = d.get("z", 0.0) if d.get("raw") is not None else 0.0
            f = dict(x["features"]); f["pace_figure_score"] = round(0.5 * f["pace_figure_score"] + 0.5 * (60 + 10 * z), 6)
            row = {**x, "features": f, "speed": (x.get("speed") or 0.0) if speed_on else 0.0}
            rows.append({**x, "ability": exact_score(row, weights)})
        out.append({**r, "rows": rows})
    return out

arms = {"A": arm(True, MATRIX_WEIGHTS), "B": arm(False, MATRIX_WEIGHTS), "C": arm(True, W_UP), "D": arm(False, W_UP)}
out = {"baseline_mismatch": mism, "asb_coverage": cov}
for name, cand in arms.items():
    v = L.evaluate(base, cand, nnull=100)
    cb, cc = L.calibrations(base), L.calibrations(cand); rr = []
    for b_, c_ in zip(base, cand):
        if b_["date"] in cb:
            lb, nn = L._nll(b_, cb[b_["date"]]); lc, _ = L._nll(c_, cc[c_["date"]]); rr.append((b_["date"], lc - lb, nn))
    byd = collections.defaultdict(list)
    for ii, q in enumerate(rr): byd[q[0]].append(ii)
    days = sorted(byd); dl = np.array([q[1] for q in rr]); nnn = np.array([q[2] for q in rr]); rng = np.random.default_rng(0); bs = []
    for _ in range(2000):
        jj = np.concatenate([byd[days[q]] for q in rng.integers(0, len(days), len(days))]); bs.append(dl[jj].sum() / nnn[jj].sum())
    v["p"] = float((np.array(bs) >= 0).mean()); out[name] = v
    print(name, v["verdict"], v["reason"], [round(t, 6) for t in v["dlogloss"]], "p", v["p"], "G", [round(t, 2) for t in v["gold_pp"]],
          "Gd", [round(t, 2) for t in v["good_pp"]], "cap5", round(v["capture5_pp"], 2), "top2", round(v["top2_any_hit_pp"], 2), v["checks"], flush=True)
ps = sorted((v["p"], k) for k, v in out.items() if isinstance(v, dict) and "p" in v)
for rank, (p, k) in enumerate(ps):
    out[k]["holm_p"] = min(1.0, max(min(1.0, (len(ps) - j) * ps[j][0]) for j in range(rank + 1)))
print({k: round(out[k]["holm_p"], 4) for _, k in ps})
Path(sys.argv[2]).write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float))
