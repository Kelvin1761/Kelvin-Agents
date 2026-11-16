"""EXP-20261116-08 tennis: per-family probability calibration for props.

Pre-registered 2026-11-16 BEFORE any number below was looked at
(the odds-band diagnosis that prompted it is in the EXP record).

Question: does a per-family calibration of the model probability stop the
long-price (odds >= 3) losses, and does it make value selection pay?

Corpus: live prop_tracker, read-only. is_point_in_time=1, WON/LOST, fixture
not DISPUTED, the six score-settled families the 精選 rule uses, evidence
source_quality >= 0.65 where evidence exists (it only exists from late
October; amended before any result was seen, applies to every arm).
Split (chronological by match_date, fixed now):
  dev     <= 2026-10-15   (fit only)
  holdout >= 2026-10-16   (report only, nothing tuned on it)
Arms (fit per family on dev, maximum likelihood logistic):
  A  current: p = model_prob_raw
  B  Platt on the model only: logit p = a + b*logit(model)
  C  market-anchored: logit p = a + b*logit(fair) + g*(logit(model) - logit(fair))
Value rule for every arm = families.is_value_selection with the arm's p
(the family's min_edge, odds band, p*odds > 1). One row = 1u flat.
Metrics on holdout: logloss / Brier vs the de-vigged market (paired by match);
value bets: count, hit, ROI, and the odds >= 3 subset; P/L difference vs A,
match-cluster bootstrap 4000 draws, seed 20260826, 95%.
Verdict: KEEP a calibration arm only if holdout logloss is not worse than A
(CI) AND its holdout value-bet P/L beats A with CI above zero. A calibration
that only removes bets (P/L up because fewer losing bets) is reported as a
safety rail, not as an edge.
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "tennis-wong-choi" / "src"))
from tennis_wc.pricing.families import family_for_market, is_value_selection, value_profile_for_family  # noqa: E402
from tennis_wc.select.featured import FAMILIES, _live_quality  # noqa: E402

DEV_END = "2026-10-15"
SEED = 20260826
DRAWS = 4000
EPS = 1e-4


def logit(p):
    p = np.clip(np.asarray(p, float), EPS, 1 - EPS)
    return np.log(p / (1 - p))


def fit_logistic(X, y, l2=1e-3):
    X = np.column_stack([np.ones(len(y)), X])
    w = np.zeros(X.shape[1])
    for _ in range(100):
        p = 1 / (1 + np.exp(-X @ w))
        g = X.T @ (p - y) + l2 * np.r_[0, w[1:]]
        H = (X.T * (p * (1 - p))) @ X + l2 * np.diag(np.r_[0, np.ones(len(w) - 1)])
        step = np.linalg.solve(H, g)
        w -= step
        if np.max(np.abs(step)) < 1e-9:
            break
    return w


def predict(w, X):
    X = np.column_stack([np.ones(len(X)), X])
    return 1 / (1 + np.exp(-X @ w))


def load(db):
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT p.id, p.match_id, p.match_date, p.market_key, p.decimal_odds,
               p.model_prob_raw, p.market_prob_fair, p.result_status, p.is_value,
               p.pricing_evidence_json
        FROM prop_tracker p JOIN matches m ON m.id = p.match_id
        WHERE p.is_point_in_time = 1 AND p.result_status IN ('WON','LOST')
          AND COALESCE(m.fixture_status,'') != 'DISPUTED'
          AND p.model_prob_raw IS NOT NULL AND p.market_prob_fair IS NOT NULL
          AND p.decimal_odds > 1""").fetchall()
    out = []
    for r in rows:
        fam = family_for_market(r["market_key"] or "")
        if fam not in FAMILIES:
            continue
        q = _live_quality(r["pricing_evidence_json"])
        # Evidence only exists from late October; before that the gate cannot be
        # applied, so it is applied only where it is known (same for every arm).
        if q is not None:
            q = float(q)
            q = q / 100 if q > 1 else q
            if q < 0.65:
                continue
        out.append(dict(id=r["id"], match=r["match_id"], date=r["match_date"], fam=fam,
                        odds=float(r["decimal_odds"]), model=float(r["model_prob_raw"]),
                        fair=float(r["market_prob_fair"]), y=1.0 if r["result_status"] == "WON" else 0.0,
                        is_value=int(r["is_value"] or 0)))
    return out


def ll(p, y):
    p = np.clip(p, EPS, 1 - EPS)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def cluster_ci(matches, values, draws=DRAWS, seed=SEED, ratio_den=None):
    """Bootstrap by match. values (and ratio_den) are per-row arrays; returns point, lo, hi of sum or ratio."""
    rng = np.random.default_rng(seed)
    idx_by = defaultdict(list)
    for i, m in enumerate(matches):
        idx_by[m].append(i)
    keys = list(idx_by)
    num = np.array([values[idx_by[k]].sum() for k in keys])
    den = np.array([ratio_den[idx_by[k]].sum() for k in keys]) if ratio_den is not None else None
    point = num.sum() / den.sum() if den is not None else num.sum()
    stats = []
    for _ in range(draws):
        s = rng.integers(0, len(keys), len(keys))
        if den is not None:
            d = den[s].sum()
            stats.append(num[s].sum() / d if d else 0.0)
        else:
            stats.append(num[s].sum())
    lo, hi = np.percentile(stats, [2.5, 97.5])
    return point, lo, hi


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(REPO / "tennis-wong-choi" / "tennis_wc.db"))
    ap.add_argument("--json-out")
    args = ap.parse_args()
    rows = load(args.db)
    dev = [r for r in rows if r["date"] <= DEV_END]
    hold = [r for r in rows if r["date"] > DEV_END]
    print(f"rows: dev {len(dev)} ({min(r['date'] for r in dev)}..{max(r['date'] for r in dev)}) | "
          f"holdout {len(hold)} ({min(r['date'] for r in hold)}..{max(r['date'] for r in hold)})")

    fits = {}
    for fam in sorted(FAMILIES):
        d = [r for r in dev if r["fam"] == fam]
        if len(d) < 50:
            fits[fam] = None
            continue
        y = np.array([r["y"] for r in d])
        lm = logit([r["model"] for r in d])
        lf = logit([r["fair"] for r in d])
        fits[fam] = dict(n=len(d), B=fit_logistic(lm[:, None], y).tolist(),
                         C=fit_logistic(np.column_stack([lf, lm - lf]), y).tolist())
        print(f"fit {fam:32s} n={len(d):5d}  B a,b={np.round(fits[fam]['B'],3)}  C a,b(mkt),g(gap)={np.round(fits[fam]['C'],3)}")

    def arm_probs(rs, arm):
        out = np.empty(len(rs))
        for i, r in enumerate(rs):
            f = fits.get(r["fam"])
            if arm == "A" or f is None:
                out[i] = r["model"]
            elif arm == "B":
                out[i] = predict(np.array(f["B"]), logit([r["model"]])[:, None])[0]
            else:
                lf = logit([r["fair"]])[0]
                lm = logit([r["model"]])[0]
                out[i] = predict(np.array(f["C"]), np.array([[lf, lm - lf]]))[0]
        return out

    result = {"fits": fits, "split": {"dev_end": DEV_END}, "arms": {}}
    for label, rs in (("dev", dev), ("holdout", hold)):
        y = np.array([r["y"] for r in rs])
        matches = [r["match"] for r in rs]
        fair = np.array([r["fair"] for r in rs])
        odds = np.array([r["odds"] for r in rs])
        pl_unit = np.where(y == 1, odds - 1, -1.0)
        ll_m = ll(fair, y)
        print(f"\n== {label}: n={len(rs)} matches={len(set(matches))}  market LL {ll_m.mean():.4f} Brier {np.mean((fair-y)**2):.4f}")
        base_bets = None
        for arm in "ABC":
            p = arm_probs(rs, arm)
            d_ll = ll(p, y) - ll_m
            pt, lo, hi = cluster_ci(matches, d_ll, ratio_den=np.ones(len(y)))
            bets = np.array([is_value_selection(p[i], fair[i], odds[i], value_profile_for_family(rs[i]["fam"]))
                             for i in range(len(rs))])
            if arm == "A":
                base_bets = bets
            n = int(bets.sum())
            line = (f"  {arm}: LL {ll(p,y).mean():.4f} (vs market {pt:+.4f} [{lo:+.4f},{hi:+.4f}]) "
                    f"Brier {np.mean((p-y)**2):.4f} | bets {n}")
            rec = dict(ll=float(ll(p, y).mean()), d_ll_vs_market=[pt, lo, hi], bets=n)
            if n:
                roi, rlo, rhi = cluster_ci(matches, pl_unit * bets, ratio_den=bets.astype(float))
                big = bets & (odds >= 3)
                line += f" hit {y[bets].mean():.3f} ROI {roi*100:+.1f}% [{rlo*100:+.1f},{rhi*100:+.1f}] P/L {pl_unit[bets].sum():+.1f}u"
                line += f" | odds>=3: {int(big.sum())} bets P/L {pl_unit[big].sum():+.1f}u"
                rec.update(hit=float(y[bets].mean()), roi=[roi, rlo, rhi], pl=float(pl_unit[bets].sum()),
                           ge3_bets=int(big.sum()), ge3_pl=float(pl_unit[big].sum()))
            if arm != "A":
                diff = pl_unit * bets - pl_unit * base_bets
                dp, dlo, dhi = cluster_ci(matches, diff)
                line += f" | ΔP/L vs A {dp:+.1f}u [{dlo:+.1f},{dhi:+.1f}]"
                rec["d_pl_vs_A"] = [dp, dlo, dhi]
            print(line)
            result["arms"].setdefault(label, {})[arm] = rec
        if label == "holdout":
            print("  per family (holdout), market vs A vs C LL, bets A/C, P/L A/C:")
            for fam in sorted(FAMILIES):
                ix = [i for i, r in enumerate(rs) if r["fam"] == fam]
                if not ix:
                    continue
                pa, pc = arm_probs([rs[i] for i in ix], "A"), arm_probs([rs[i] for i in ix], "C")
                yy, ff, oo = y[ix], fair[ix], odds[ix]
                ba = np.array([is_value_selection(pa[k], ff[k], oo[k], value_profile_for_family(fam)) for k in range(len(ix))])
                bc = np.array([is_value_selection(pc[k], ff[k], oo[k], value_profile_for_family(fam)) for k in range(len(ix))])
                pu = np.where(yy == 1, oo - 1, -1.0)
                print(f"    {fam:32s} n={len(ix):5d} LL mkt {ll(ff,yy).mean():.4f} A {ll(pa,yy).mean():.4f} C {ll(pc,yy).mean():.4f}"
                      f" | bets A {int(ba.sum())} ({pu[ba].sum():+.1f}u) C {int(bc.sum())} ({pu[bc].sum():+.1f}u)")
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(result, indent=2, default=float))


if __name__ == "__main__":
    main()
