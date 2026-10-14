#!/usr/bin/env python3
"""HKJC market benchmark: final win odds ranking vs our model, same races, canonical metrics.

Evaluation only — the market never enters the model. Model rankings:
  replay   = current engine replay (scratch/hkjc_race_weight_oracle_20261013/dataset.csv)
  archived = HKJC_Auto_Scoring.csv rank stored in each meeting folder
Market ranking = ascending final win_odds from the meeting's 全日賽果.json.
"""
from __future__ import annotations

import csv
import glob
import json
import math
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

REPO = Path("/Users/imac/Antigravity-repo")
sys.path.insert(0, str(REPO / ".agents/skills/shared_racing"))
from eval_metrics import race_metrics  # noqa: E402

DATASET = REPO / "scratch/hkjc_race_weight_oracle_20261013/dataset.csv"
B = 10000
rng = random.Random(20261014)


def load_results(meeting_dir: Path) -> dict[int, dict[int, tuple[int, float | None]]]:
    files = glob.glob(str(meeting_dir / "*全日賽果.json"))
    if not files:
        return {}
    data = json.load(open(files[0], encoding="utf-8"))
    out: dict[int, dict[int, tuple[int, float | None]]] = {}
    for key, race in data.items():
        rows = {}
        for r in race.get("results", []):
            try:
                pos = int(re.sub(r"\D", "", r.get("pos", "")) or 0)
                no = int(r["horse_no"])
            except (ValueError, KeyError):
                continue
            if pos <= 0:
                continue  # non-finisher / scratched
            try:
                odds = float(r.get("win_odds", ""))
            except ValueError:
                odds = None
            rows[no] = (pos, odds)
        out[int(key)] = rows
    return out


def load_archived(meeting_dir: Path) -> dict[int, dict[int, float]]:
    path = meeting_dir / "HKJC_Auto_Scoring.csv"
    if not path.exists():
        return {}
    out: dict[int, dict[int, float]] = defaultdict(dict)
    for r in csv.DictReader(open(path, encoding="utf-8-sig")):
        try:
            out[int(r["race_number"])][int(r["horse_number"])] = float(r["rank"])
        except (ValueError, KeyError):
            continue
    return out


rows = list(csv.DictReader(open(DATASET, encoding="utf-8-sig")))
by_race: dict[tuple[str, int], list[dict]] = defaultdict(list)
for r in rows:
    by_race[(r["meeting"], int(r["race_number"]))].append(r)

results_cache: dict[str, dict] = {}
archived_cache: dict[str, dict] = {}
races = []
skipped = defaultdict(int)
for (meeting, race_no), rr in sorted(by_race.items(), key=lambda kv: (kv[1][0]["date"], kv[0][1])):
    mdir = Path(meeting)
    if meeting not in results_cache:
        results_cache[meeting] = load_results(mdir)
        archived_cache[meeting] = load_archived(mdir)
    res = results_cache[meeting].get(race_no)
    if not res:
        skipped["no_results_json"] += 1
        continue
    if any(o is None for _, o in res.values()):
        skipped["missing_odds"] += 1
        continue
    finishers = set(res)
    if len(finishers) < 4:
        skipped["field_lt4"] += 1
        continue
    # current_live_rank = archived rank; replay = rank by recomputed ability (as in the oracle harness)
    ability = {int(r["horse_number"]): float(r["current_live_recomputed_ability"]) for r in rr}
    order = sorted(ability, key=lambda h: (-ability[h], h))
    replay = {h: i + 1 for i, h in enumerate(order)}
    if not finishers <= set(replay):
        skipped["finisher_not_in_replay"] += 1
        continue
    arch = archived_cache[meeting].get(race_no, {})
    pos = {h: res[h][0] for h in finishers}
    odds = {h: res[h][1] for h in finishers}
    # Deterministic tie-break by horse number (documented).
    market = sorted(finishers, key=lambda h: (odds[h], h))
    replay_picks = sorted(finishers, key=lambda h: (replay[h], h))
    arch_picks = sorted(finishers, key=lambda h: (arch[h], h)) if finishers <= set(arch) else None
    races.append(
        dict(
            meeting=meeting,
            date=rr[0]["date"],
            venue=rr[0]["venue"],
            race=race_no,
            field=len(finishers),
            pos=pos,
            odds=odds,
            replay_rank=replay,
            picks={"market": market, "replay": replay_picks, "archived": arch_picks},
        )
    )

print("races used:", len(races), "skipped:", dict(skipped))
print("archived ranking available:", sum(1 for r in races if r["picks"]["archived"]))

# terminal = last 15% of unique dates (contract convention)
dates = sorted({r["date"] for r in races})
cut = dates[int(math.floor(len(dates) * 0.85))]
for r in races:
    r["split"] = "terminal" if r["date"] >= cut else "dev"
print("dates:", len(dates), "terminal from", cut)


def metrics(r, who):
    picks = r["picks"][who]
    if picks is None:
        return None
    top3 = {h for h, p in r["pos"].items() if p <= 3}
    winner = next(h for h, p in r["pos"].items() if p == 1)
    m = race_metrics(picks, top3, winner, actual_pos=r["pos"], field_size=r["field"])
    # within-race AUC: placed vs unplaced, by rank (lower rank = more fancied)
    rk = {h: i for i, h in enumerate(picks)}
    placed = [rk[h] for h in top3]
    other = [rk[h] for h in picks if h not in top3]
    auc = sum((a < b) + 0.5 * (a == b) for a in placed for b in other) / (len(placed) * len(other))
    return {
        "gold": float(m["gold"]),
        "gold_strict": float(m["gold_strict"]),
        "good": float(m["good_positional"]),
        "champion": float(m["champion"]),
        "capture5": m["top3_capture_at5"],
        "ndcg5": m["ndcg_at5"],
        "mrr": 1.0 / m["winner_rank"] if m["winner_rank"] else 0.0,
        "auc": auc,
    }


KEYS = ["gold", "gold_strict", "good", "champion", "capture5", "ndcg5", "mrr", "auc"]


def paired(sub, a, b):
    pairs = [(metrics(r, a), metrics(r, b)) for r in sub]
    pairs = [(x, y) for x, y in pairs if x and y]
    n = len(pairs)
    out = {"n": n}
    for k in KEYS:
        xa = np.array([x[k] for x, _ in pairs])
        xb = np.array([y[k] for _, y in pairs])
        d = xa - xb
        boots = []
        idx = np.arange(n)
        nprng = np.random.default_rng(20261014)
        for _ in range(B):
            s = nprng.choice(idx, n)
            boots.append(d[s].mean())
        lo, hi = np.percentile(boots, [2.5, 97.5])
        out[k] = (xa.mean(), xb.mean(), d.mean(), lo, hi)
    return out


def show(title, res, a, b):
    print(f"\n## {title}  (n={res['n']})   {a} vs {b}")
    print(f"{'metric':10s} {a:>9s} {b:>9s} {'diff':>8s}  95% CI")
    for k in KEYS:
        va, vb, d, lo, hi = res[k]
        pct = k in ("gold", "gold_strict", "good", "champion", "capture5")
        f = (lambda v: f"{100*v:8.2f}%") if pct else (lambda v: f"{v:9.4f}")
        fd = (lambda v: f"{100*v:+7.2f}pp") if pct else (lambda v: f"{v:+8.4f}")
        print(f"{k:10s} {f(va)} {f(vb)} {fd(d)}  [{fd(lo).strip()}, {fd(hi).strip()}]")


for split in ("all", "dev", "terminal"):
    sub = races if split == "all" else [r for r in races if r["split"] == split]
    show(f"{split}", paired(sub, "market", "replay"), "market", "replay")
arch_sub = [r for r in races if r["picks"]["archived"]]
show("archived subset", paired(arch_sub, "market", "archived"), "market", "archived")
show("archived subset", paired(arch_sub, "replay", "archived"), "replay", "archived")

# field-size strata (Gold / Good gap)
print("\n## field-size strata, market − replay")
for lo_, hi_ in ((1, 8), (9, 10), (11, 12), (13, 99)):
    sub = [r for r in races if lo_ <= r["field"] <= hi_]
    if len(sub) < 10:
        continue
    res = paired(sub, "market", "replay")
    print(f"field {lo_}-{hi_ if hi_<99 else '+'}: n={res['n']}  gold {100*res['gold'][0]:.1f} vs {100*res['gold'][1]:.1f}  "
          f"good {100*res['good'][0]:.1f} vs {100*res['good'][1]:.1f}  auc {res['auc'][0]:.3f} vs {res['auc'][1]:.3f}")

# Agreement
same_top1 = np.mean([r["picks"]["market"][0] == r["picks"]["replay"][0] for r in races])
rhos = []
for r in races:
    hs = r["picks"]["market"]
    a = np.argsort(np.argsort([r["odds"][h] for h in hs]))
    b = np.argsort(np.argsort([r["replay_rank"][h] for h in hs]))
    if np.std(a) and np.std(b):
        rhos.append(np.corrcoef(a, b)[0, 1])
print(f"\nsame top pick: {100*same_top1:.1f}%   mean within-race Spearman(model, market): {np.mean(rhos):.3f}")


# Benter test: does the model add information beyond the market?
# Conditional logit on finishing first: utility = b1*log(market_prob) + b2*z(model score)
def race_feats(r):
    hs = sorted(r["pos"])
    inv = np.array([1.0 / r["odds"][h] for h in hs])
    mp = inv / inv.sum()
    rank = np.array([r["replay_rank"][h] for h in hs], dtype=float)
    z = -(rank - rank.mean()) / (rank.std() or 1.0)  # higher = model likes more
    win = np.array([r["pos"][h] == 1 for h in hs], dtype=float)
    win = win / win.sum()
    return np.log(mp), z, win


feats = [race_feats(r) for r in races]


def nll(beta, idx, use_model=True):
    total = 0.0
    for i in idx:
        lm, z, w = feats[i]
        u = beta[0] * lm + (beta[1] * z if use_model else 0.0)
        u = u - u.max()
        total -= float((w * (u - np.log(np.exp(u).sum()))).sum())
    return total


all_idx = list(range(len(feats)))
fit_m = minimize(lambda b: nll(b, all_idx), [1.0, 0.0], method="Nelder-Mead")
fit_0 = minimize(lambda b: nll([b[0], 0.0], all_idx, False), [1.0], method="Nelder-Mead")
print(f"\nBenter conditional logit (win): market-only NLL {fit_0.fun:.2f} (b={fit_0.x[0]:.3f}); "
      f"+model NLL {fit_m.fun:.2f} b_market={fit_m.x[0]:.3f} b_model={fit_m.x[1]:+.3f}  LR={2*(fit_0.fun-fit_m.fun):.2f}")
nprng = np.random.default_rng(7)
bs = []
for _ in range(300):
    s = list(nprng.choice(all_idx, len(all_idx)))
    bs.append(minimize(lambda b: nll(b, s), fit_m.x, method="Nelder-Mead").x[1])
print(f"b_model 95% bootstrap CI: [{np.percentile(bs,2.5):+.3f}, {np.percentile(bs,97.5):+.3f}]")

# Out-of-sample version: fit on dev, score terminal
dev_idx = [i for i, r in enumerate(races) if r["split"] == "dev"]
ter_idx = [i for i, r in enumerate(races) if r["split"] == "terminal"]
fm = minimize(lambda b: nll(b, dev_idx), [1.0, 0.0], method="Nelder-Mead").x
f0 = minimize(lambda b: nll([b[0], 0.0], dev_idx, False), [1.0], method="Nelder-Mead").x
print(f"terminal NLL per race: market-only {nll([f0[0],0.0], ter_idx, False)/len(ter_idx):.4f}  "
      f"market+model {nll(fm, ter_idx)/len(ter_idx):.4f}  (dev-fit b_model={fm[1]:+.3f}, n_terminal={len(ter_idx)})")
# Appended to the benchmark: immutable pre-race snapshot ranking (cutoff = race date 12:00 HKT).
import datetime as dt
HKT = dt.timezone(dt.timedelta(hours=8))

def parse_ts(name):
    m = re.match(r"(\d{8}T\d{6})(?:\.\d+)?([+-]\d{4})", name)
    if not m:
        return None
    t = dt.datetime.strptime(m.group(1), "%Y%m%dT%H%M%S")
    off = int(m.group(2)[:3]) * 60 + int(m.group(2)[0] + m.group(2)[3:])
    return t.replace(tzinfo=dt.timezone(dt.timedelta(minutes=off)))

snap_used = {}
for r in races:
    mdir = Path(r["meeting"])
    cutoff = dt.datetime.fromisoformat(r["date"]).replace(hour=12, tzinfo=HKT)
    cands = []
    for sd in ("Prediction_Snapshots", "_prediction_snapshots"):
        for p in (mdir / sd).glob("*") if (mdir / sd).exists() else []:
            ts = parse_ts(p.name)
            f = p / f"Race_{r['race']}_Auto_Scoring.csv"
            if ts and ts < cutoff and f.exists():
                cands.append((ts, f))
    r["picks"]["snapshot"] = None
    if not cands:
        continue
    ts, f = max(cands)
    rank = {}
    for row in csv.DictReader(open(f, encoding="utf-8-sig")):
        try:
            rank[int(row["horse_number"])] = float(row["rank"])
        except (KeyError, ValueError):
            pass
    fin = set(r["pos"])
    if fin <= set(rank):
        r["picks"]["snapshot"] = sorted(fin, key=lambda h: (rank[h], h))
        r["snap_rank"] = rank
        snap_used[(r["meeting"], r["race"])] = str(ts)

snap = [r for r in races if r["picks"]["snapshot"]]
print(f"\nimmutable pre-race snapshot races: {len(snap)} over {len({r['meeting'] for r in snap})} meetings "
      f"({min(r['date'] for r in snap)} .. {max(r['date'] for r in snap)})")
show("snapshot subset", paired(snap, "market", "snapshot"), "market", "snapshot")
show("snapshot subset", paired(snap, "replay", "snapshot"), "replay", "snapshot")

def feats_from(r, rankmap):
    hs = sorted(r["pos"])
    inv = np.array([1.0 / r["odds"][h] for h in hs]); mp = inv / inv.sum()
    rank = np.array([rankmap[h] for h in hs], dtype=float)
    z = -(rank - rank.mean()) / (rank.std() or 1.0)
    w = np.array([r["pos"][h] == 1 for h in hs], dtype=float); w /= w.sum()
    return np.log(mp), z, w

def benter(label, sub, key):
    global feats
    feats = [feats_from(r, r[key]) for r in sub]
    idx = list(range(len(feats)))
    fm = minimize(lambda b: nll(b, idx), [1.0, 0.0], method="Nelder-Mead")
    f0 = minimize(lambda b: nll([b[0], 0.0], idx, False), [1.0], method="Nelder-Mead")
    g = np.random.default_rng(11); bs = []
    for _ in range(300):
        s = list(g.choice(idx, len(idx)))
        bs.append(minimize(lambda b: nll(b, s), fm.x, method="Nelder-Mead").x[1])
    print(f"Benter [{label}] n={len(sub)}: b_model={fm.x[1]:+.3f} CI [{np.percentile(bs,2.5):+.3f}, {np.percentile(bs,97.5):+.3f}]  "
          f"LR={2*(f0.fun-fm.fun):.2f}  NLL/race {f0.fun/len(sub):.4f} -> {fm.fun/len(sub):.4f}")

for r in races:
    arch = archived_cache[r["meeting"]].get(r["race"], {})
    r["arch_rank"] = arch
print()
benter("replay, all", races, "replay_rank")
benter("archived, all", races, "arch_rank")
benter("snapshot only", snap, "snap_rank")
benter("replay, same snapshot races", snap, "replay_rank")
