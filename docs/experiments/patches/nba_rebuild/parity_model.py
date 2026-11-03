"""Parity: nba_engine.model S and C against the probabilities the live system archived.

usage: python3 parity_model.py <repo_root> <analysis_root>
"""
import glob
import json
import sys
from pathlib import Path

repo, root = Path(sys.argv[1]), Path(sys.argv[2])
sys.path[:0] = [str(repo / ".agents/skills/nba")]
from nba_engine import model  # noqa: E402
from nba_identity import player_name_key as name_key  # noqa: E402

STAT = {"pts": "PTS", "reb": "REB", "ast": "AST", "fg3m": "FG3M"}
n = s_bad = c_bad = s_null = 0
worst_s = worst_c = 0.0
for sidecar in sorted(root.glob("* NBA Analysis/Game_*_Full_Analysis.md.market_legs.json")):
    tag = sidecar.name[len("Game_"):-len("_Full_Analysis.md.market_legs.json")]
    gd_path = sidecar.parent / f"nba_game_data_{tag}.json"
    if not gd_path.exists():
        continue
    side, gd = json.loads(sidecar.read_text()), json.loads(gd_path.read_text())
    season = gd["meta"].get("roster_season")
    players = {(team, name_key(p["name"])): p for team, ps in gd["players"].items() for p in ps}
    for leg in side["legs"]:
        stat = STAT.get(leg["market"])
        p = players.get((leg["team"], name_key(leg["player"])))
        if not stat or p is None:
            continue
        n += 1
        s_new = model.s_prob((p.get("gamelog") or {}).get("season_log"), stat, leg["line"],
                             (gd.get("opponent_context") or {}).get(leg["team"]), season, leg["team"])
        s_old = leg.get("season_rate_v4_prob_S")
        if (s_new is None) != (s_old is None):
            s_null += 1
        elif s_new is not None:
            d = abs(round(s_new, 4) - s_old)
            worst_s = max(worst_s, d)
            s_bad += d > 1e-4
        c_new = model.c_prob(stat, leg["price"], leg["p_l10_base_rate"])
        if c_new is not None and leg.get("p_final") is not None and "calibrated" in str(leg.get("engine")):
            d = abs(round(c_new, 3) - leg["p_final"])
            worst_c = max(worst_c, d)
            c_bad += d > 1.1e-3
print(f"legs={n} S: mismatch={s_bad} null_mismatch={s_null} worst={worst_s:.4f} | "
      f"C: mismatch={c_bad} worst={worst_c:.4f}")
