"""Replay the legacy NBA generator on archived inputs and dump its candidate pool.

For each archived day folder and game, runs generate_nba_reports.main() with:
  * select_combo_1 wrapped so the full candidate list (every engine feature) and the
    B2 selection are recorded;
  * the SGM quote replaced by the product of single-leg prices (past games cannot be
    re-priced; the >=2.0 floor is then applied to that product);
  * the steady stop-loss state pointed at a missing file (= active).
Output: one JSONL row per candidate leg, plus the B2 pick flag.

usage: python3 replay_legacy.py <repo_root> <analysis_root> <out.jsonl> [day ...]
"""
import contextlib
import io
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

repo, root, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
days = sys.argv[4:]
os.environ["WONGCHOI_NBA_STEADY_STATE"] = str(Path(tempfile.mkdtemp()) / "missing.json")
os.environ["WC_TELEGRAM_DISABLE"] = "1"
scripts = repo / ".agents/skills/nba/nba_wong_choi/scripts"
sys.path[:0] = [str(scripts), str(repo / ".agents/skills/nba")]
import generate_nba_reports as g  # noqa: E402
from nba_sgm_quote import QuotedCombo  # noqa: E402

CAPTURE = {}
_orig_select = g.select_combo_1


def select_wrapper(candidates, **kw):
    sel = _orig_select(candidates, **kw)
    CAPTURE["candidates"] = candidates
    CAPTURE["selected"] = list(sel)
    CAPTURE["rule"] = getattr(sel, "selection_rule", None)
    return sel


def fake_quote(odds, legs, **kw):
    price = 1.0
    for leg in legs:
        price *= float(leg["odds"])
    now = datetime.now(timezone.utc)
    return QuotedCombo(legs, {"status": "ok", "source": "replay_product", "decimal_odds": round(price, 4), "quote_id": "replay",
                              "captured_at": now.isoformat(),
                              "expires_at": (now + timedelta(seconds=300)).isoformat()})


g.select_combo_1 = select_wrapper
g.quote_combo = fake_quote
g.quote_valid = lambda quote, odds, legs, **kw: quote.get("status") == "ok"

KEEP = ("player", "team", "category", "line_val", "odds", "hit_l10", "hit_l5", "hit_l3", "cov", "avg",
        "l3_avg", "sd", "l10", "edge", "estimated_prob", "implied_prob", "base_rate", "market_type",
        "bench_minutes_risk", "day_to_day", "early_season_guard", "min_avg", "desc", "season_phase")

with out.open("a", encoding="utf-8") as fh:
    for day_dir in sorted(root.glob("* NBA Analysis")):
        day = day_dir.name.split()[0]
        if days and day not in days:
            continue
        for gd in sorted(day_dir.glob("nba_game_data_*.json")):
            tag = gd.stem.replace("nba_game_data_", "")
            sb = day_dir / f"Sportsbet_Odds_{tag}.json"
            if not sb.exists():
                continue
            CAPTURE.clear()
            tmp = Path(tempfile.mkdtemp()) / f"Game_{tag}_Full_Analysis.md"
            sys.argv = ["g", "--sportsbet", str(sb), "--extractor", str(gd), "--output", str(tmp)]
            buf = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
            try:
                with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                    g.main()
            except SystemExit:
                pass
            except Exception as exc:  # noqa: BLE001
                print(f"{day} {tag} ERROR-after-capture {type(exc).__name__}: {exc}", flush=True)
            cands = CAPTURE.get("candidates") or []
            picked = {(c["player"], c.get("category"), c.get("line_val")) for c in CAPTURE.get("selected", [])}
            for c in cands:
                row = {k: c.get(k) for k in KEEP}
                row.update(day=day, game=tag, rule=CAPTURE.get("rule"),
                           b2_pick=(c["player"], c.get("category"), c.get("line_val")) in picked)
                fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
            print(f"{day} {tag} candidates={len(cands)} picked={len(picked)} rule={CAPTURE.get('rule')}", flush=True)
