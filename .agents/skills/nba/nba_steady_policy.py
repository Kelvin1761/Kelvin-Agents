"""Formal steady (B2) banker policy and its pre-registered stop-loss.

EXP-20261027-21: combo 1 is the B2 selection (no EV gates, verified SGM price
>=2.0), flat $1.  The model itself expects negative EV, so the stop rules are
frozen here and in the protocol; a pause never lifts itself.
"""
import argparse
import json
import os
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

POLICY = "banker-steady-b2-v1"
PROTOCOL = "EXP-20261027-21"
STOP_UNITS = -10.0          # S1
CI_MIN_BETS = 60            # S2
REVIEW_MIN_BETS = 40        # S3
REVIEW_GAP = 0.10
BOOTSTRAP_DRAWS = 2000
BOOTSTRAP_SEED = 20261027
DISCLAIMER = ("正式穩膽 = steady（B2，EXP-20261027-21）：命中率產品線，模型預期 EV 為負；"
              "固定 $1 平注；累計 −10u 或 60 注後 ROI 上限 <0 自動暫停。")


def state_path():
    override = os.environ.get("WONGCHOI_NBA_STEADY_STATE")
    if override:
        return Path(override)
    ledger = os.environ.get("WONGCHOI_NBA_MARKET_LEDGER_ROOT")
    return Path(ledger or Path.home() / "WongChoiData" / "NBA_Market_Eval") / "steady_policy_state.json"


def load_state():
    """Missing file = active.  Tests never read the production file."""
    if "pytest" in sys.modules and not os.environ.get("WONGCHOI_NBA_STEADY_STATE"):
        return {"status": "active", "history": []}
    try:
        state = json.loads(state_path().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"status": "active", "history": []}
    except (OSError, ValueError):
        # Unreadable state must not silently re-enable betting.
        return {"status": "paused", "reason": "state_unreadable", "history": []}
    if not isinstance(state, dict) or state.get("status") not in {"active", "paused"}:
        return {"status": "paused", "reason": "state_invalid", "history": []}
    state.setdefault("history", [])
    return state


def save_state(state):
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def paused_reason():
    state = load_state()
    return (state.get("reason") or "paused") if state["status"] == "paused" else None


def counted(records, since=None):
    """Settled policy bets after the latest resume (or from the start)."""
    return [r for r in records
            if r.get("strategy_profile") == POLICY and r.get("state") in {"won", "lost"}
            and isinstance(r.get("profit"), (int, float)) and (not since or str(r.get("day")) >= since)]


def roi_upper_ci(rows):
    days = sorted({r["day"] for r in rows})
    by_day = {d: [r["profit"] for r in rows if r["day"] == d] for d in days}
    rng = random.Random(BOOTSTRAP_SEED)
    rois = []
    for _ in range(BOOTSTRAP_DRAWS):
        sample = [p for d in (rng.choice(days) for _ in days) for p in by_day[d]]
        rois.append(sum(sample) / len(sample))
    rois.sort()
    return rois[int(0.975 * BOOTSTRAP_DRAWS) - 1]


def evaluate(records, since=None):
    rows = counted(records, since)
    n = len(rows)
    profit = round(sum(r["profit"] for r in rows), 2)
    hits = sum(r["state"] == "won" for r in rows)
    probs = [r["model_probability"] for r in rows if isinstance(r.get("model_probability"), (int, float))]
    out = {"bets": n, "hits": hits, "profit": profit, "roi": round(profit / n, 4) if n else None,
           "hit_rate": round(hits / n, 4) if n else None,
           "model_hit_rate": round(sum(probs) / len(probs), 4) if probs else None,
           "roi_upper_ci": None, "stop": None, "review": None}
    if profit <= STOP_UNITS:
        out["stop"] = f"S1 累計 {profit:+.2f}u ≤ {STOP_UNITS:g}u"
    if n >= CI_MIN_BETS:
        out["roi_upper_ci"] = round(roi_upper_ci(rows), 4)
        if out["roi_upper_ci"] < 0 and not out["stop"]:
            out["stop"] = f"S2 {n} 注 ROI 95% 上限 {out['roi_upper_ci']:+.1%} < 0"
    if (n >= REVIEW_MIN_BETS and out["model_hit_rate"] is not None
            and out["hit_rate"] <= out["model_hit_rate"] - REVIEW_GAP):
        out["review"] = f"S3 命中 {out['hit_rate']:.1%} vs 模型 {out['model_hit_rate']:.1%}（{n} 注）"
    return out


def check(records, now=None):
    """Apply the stop rules once.  Returns (state, newly_paused, metrics)."""
    state = load_state()
    metrics = evaluate(records, state.get("since"))
    newly = False
    if state["status"] == "active" and metrics["stop"]:
        stamp = (now or datetime.now(timezone.utc)).isoformat()
        state.update(status="paused", reason=metrics["stop"], paused_at=stamp)
        state["history"].append({"event": "paused", "at": stamp, "reason": metrics["stop"], "metrics": metrics})
        save_state(state)
        newly = True
    return state, newly, metrics


def resume(actor, reason, today, now=None):
    state = load_state()
    if state["status"] != "paused":
        raise SystemExit("steady policy is not paused")
    stamp = (now or datetime.now(timezone.utc)).isoformat()
    state["history"].append({"event": "resumed", "at": stamp, "actor": actor, "reason": reason,
                             "previous_reason": state.get("reason")})
    state.update(status="active", reason=None, paused_at=None, since=today)
    save_state(state)
    return state


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--actor")
    parser.add_argument("--reason")
    args = parser.parse_args(argv)
    if args.resume:
        if not args.actor or not args.reason:
            parser.error("--resume needs --actor and --reason")
        today = datetime.now().strftime("%Y-%m-%d")
        print(json.dumps(resume(args.actor, args.reason, today), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(load_state(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
