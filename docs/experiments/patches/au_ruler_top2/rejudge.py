#!/usr/bin/env python3
"""EXP-20261121-32：AU ranking metric 加「頭二選有中／頭二上名率／頭三上名率」嘅把尺驗證。

  rejudge.py pairs  BASE.json CAND.json [...]   舊尺 vs 新尺重判 fixed_rule 候選（同一份 dump、同一個判決器）
  rejudge.py null   BASE.json SIGMA SEEDS        純噪音候選（ability + N(0,σ)）嘅誤判 WIN 率，舊尺 vs 新尺
"""
import json, random, sys
from pathlib import Path
W = Path(__file__).resolve().parents[4]
SCRIPTS = W / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
for p in (SCRIPTS, SCRIPTS.parents[2] / "shared_racing"):
    sys.path.insert(0, str(p))
from au_eval import RANKING_METRICS, RANKING_METRICS_PRE_20261121, _stage4_metric_rows  # noqa: E402
from model_evaluation_decision import evaluate_full_record  # noqa: E402


def load(path):
    races = [r for r in json.loads(Path(path).read_text())["races"] if r["date"] >= "2026-08-05"
             and sum(x["pos"] <= 3 for x in r["rows"]) >= 3 and any(x["pos"] == 1 for x in r["rows"])]
    return sorted(races, key=lambda r: (r["date"], r["meeting"], r["race"]))


def judge(base, cand, metrics, score=lambda r: r["ability"]):
    dates = [r["date"] for r in base]
    v = evaluate_full_record(domain="au", mode="fixed_rule", dates=dates,
                             baseline_rows=_stage4_metric_rows(base, score),
                             candidate_rows=_stage4_metric_rows(cand, score),
                             leakage_audit_passed=True, ranking_metrics=metrics)
    rk = (v.get("detail") or {}).get("ranking") or {}
    return v["verdict"], v["reason"], {k: [round(x["delta"] * 100, 3), round(x["ci_low"] * 100, 3), round(x["ci_high"] * 100, 3)]
                                      for k, x in rk.items()}


def pairs(base_path, cands):
    base = load(base_path)
    keys = [(r["meeting"], r["race"]) for r in base]
    out = {"races": len(base), "aa": {}}
    for name, m in (("old", RANKING_METRICS_PRE_20261121), ("new", RANKING_METRICS)):
        out["aa"][name] = judge(base, base, m)[:2]
    for path in cands:
        cand = load(path)
        assert [(r["meeting"], r["race"]) for r in cand] == keys, path
        o, n = judge(base, cand, RANKING_METRICS_PRE_20261121), judge(base, cand, RANKING_METRICS)
        out[Path(path).stem] = {"old": o[:2], "new": n[:2], "new_ranking": n[2]}
        print(Path(path).stem, o[:2], "->", n[:2], flush=True)
    print(json.dumps(out, ensure_ascii=False, indent=1))


def null(base_path, sigma, seeds):
    base = load(base_path)
    res = {"old": [], "new": []}
    for seed in range(int(seeds)):
        rng = random.Random(seed)
        noise = {(r["meeting"], r["race"], i): rng.gauss(0, float(sigma)) for r in base for i in range(len(r["rows"]))}
        cand = [dict(r, rows=[dict(x, ability=x["ability"] + noise[(r["meeting"], r["race"], i)])
                              for i, x in enumerate(r["rows"])]) for r in base]
        for name, m in (("old", RANKING_METRICS_PRE_20261121), ("new", RANKING_METRICS)):
            res[name].append(judge(base, cand, m)[0])
        print(seed, res["old"][-1], res["new"][-1], flush=True)
    print(json.dumps({k: {"win": sum(v != "REJECT" for v in vs), "n": len(vs)} for k, vs in res.items()}))


def _ranks(race):
    order = sorted(range(len(race["rows"])), key=lambda i: -race["rows"][i]["ability"])
    return {i: k + 1 for k, i in enumerate(order)}


def power(base_path, bump, share, seeds, target="all"):
    """敏感度：隨機揀 `share` 嘅實際上名馬加 `bump` 分（人工、已知係真改善），睇兩把尺幾多次判 WIN。"""
    base = load(base_path)
    res = {"old": [], "new": []}
    for seed in range(int(seeds)):
        rng = random.Random(1000 + seed)
        cand = []
        for r in base:
            rk = _ranks(r)
            ok = (lambda i: True) if target == "all" else (lambda i: 3 <= rk[i] <= 5)
            cand.append(dict(r, rows=[dict(x, ability=x["ability"] + (float(bump) if x["pos"] <= 3 and ok(i)
                                                                     and rng.random() < float(share) else 0.0))
                                      for i, x in enumerate(r["rows"])]))
        for name, m in (("old", RANKING_METRICS_PRE_20261121), ("new", RANKING_METRICS)):
            res[name].append(judge(base, cand, m)[0])
        print(seed, res["old"][-1], res["new"][-1], flush=True)
    print(json.dumps({k: {"win": sum(v != "REJECT" for v in vs), "n": len(vs)} for k, vs in res.items()}))


if __name__ == "__main__":
    {"pairs": lambda: pairs(sys.argv[2], sys.argv[3:]), "null": lambda: null(*sys.argv[2:5]), "power": lambda: power(*sys.argv[2:7])}[sys.argv[1]]()
