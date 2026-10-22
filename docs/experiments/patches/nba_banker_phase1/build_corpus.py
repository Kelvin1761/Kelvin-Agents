"""Phase 1 corpus: last season's pre-game Sportsbet milestone ladders joined to
point-in-time L10 and box-score outcomes.

Inputs : <odds_root>/<US game date>/Sportsbet_Odds_<AWAY>_<HOME>.json  (extraction_time is
         pre-game; folder date = US game date, extraction is the Sydney day before)
         NBA PlayerGameLogs 2025-26 Regular Season + Playoffs (fetched once, cached)
Output : corpus.csv  one row per (date, player, stat, milestone line, price)

Game date: the first head-to-head game on/after the extraction time (converted to US Eastern),
within 2 days; otherwise the file is skipped. Folder name is the Sydney analysis date, NOT the
game date.

Point-in-time: L10/L5 use only games with GAME_DATE < game date; DNP / MIN==0 rows are
not in the history and a missing outcome row is `dnp` (Sportsbet voids; excluded later).
"""
import argparse, glob, json, os, re, sys, unicodedata
import pandas as pd

STAT = {"points": "PTS", "rebounds": "REB", "assists": "AST", "threes_made": "FG3M"}


def norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"[.'’]", "", s).lower()
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", s)
    return re.sub(r"\s+", " ", s).strip()


def load_logs(cache: str) -> pd.DataFrame:
    if os.path.exists(cache):
        return pd.read_csv(cache, parse_dates=["GAME_DATE"])
    from nba_api.stats.endpoints import playergamelogs
    frames = []
    for st in ("Regular Season", "PlayIn", "Playoffs"):
        df = playergamelogs.PlayerGameLogs(season_nullable="2025-26", season_type_nullable=st, timeout=60).get_data_frames()[0]
        df["SEASON_TYPE"] = st
        frames.append(df)
    df = pd.concat(frames)
    df = df[["PLAYER_ID", "PLAYER_NAME", "TEAM_ABBREVIATION", "GAME_DATE", "MATCHUP", "MIN", "PTS", "REB", "AST", "FG3M", "SEASON_TYPE"]]
    df["GAME_DATE"] = pd.to_datetime(df["GAME_DATE"])
    df.to_csv(cache, index=False)
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--odds-root", required=True)
    ap.add_argument("--cache", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    logs = load_logs(a.cache)
    logs["key"] = logs["PLAYER_NAME"].map(norm)
    played = logs[logs["MIN"].fillna(0) > 0].sort_values("GAME_DATE")
    by_player = {k: g.reset_index(drop=True) for k, g in played.groupby("key")}
    rows, miss_players, skipped_files = [], set(), 0
    for f in sorted(glob.glob(os.path.join(a.odds_root, "*", "Sportsbet_Odds_*.json"))):
        day = os.path.basename(os.path.dirname(f))
        d = json.load(open(f))
        away, home = d["away_team"], d["home_team"]
        away_abbr = os.path.basename(f).split("_")[2]
        home_abbr = os.path.basename(f).split("_")[3].split(".")[0]
        # extraction_time is Sydney local (AEST, UTC+10 in Apr-Jun); US-Eastern = Sydney - 14h.
        ext_et = pd.Timestamp(d["extraction_time"]) - pd.Timedelta(hours=14)
        ext_day = ext_et.normalize()
        h2h = played[(played["MATCHUP"].str.contains(away_abbr)) & (played["MATCHUP"].str.contains(home_abbr))
                     & (played["TEAM_ABBREVIATION"].isin([away_abbr, home_abbr]))]
        nxt = h2h[h2h["GAME_DATE"] >= ext_day]["GAME_DATE"]
        if nxt.empty or (nxt.min() - ext_day).days > 2:
            skipped_files += 1
            continue
        gdate = nxt.min()
        for mkt, stat in STAT.items():
            for player, rec in (d["player_props"].get(mkt) or {}).items():
                g = by_player.get(norm(player))
                if g is None:
                    miss_players.add(player); continue
                prior = g[g["GAME_DATE"] < gdate].tail(10)
                if len(prior) < 5:
                    continue
                today = g[(g["GAME_DATE"] == gdate) & (g["TEAM_ABBREVIATION"].isin([away_abbr, home_abbr]))]
                actual = float(today.iloc[0][stat]) if len(today) else None
                mins = float(today.iloc[0]["MIN"]) if len(today) else None
                team = today.iloc[0]["TEAM_ABBREVIATION"] if len(today) else prior.iloc[-1]["TEAM_ABBREVIATION"]
                l10 = prior[stat].tolist()[::-1]  # newest first
                l5 = l10[:5]
                sd = (sum((x - sum(l10) / len(l10)) ** 2 for x in l10) / len(l10)) ** 0.5
                avg10 = sum(l10) / len(l10)
                cov = sd / avg10 if avg10 else 0.0
                mins10 = prior['MIN'].mean()
                prev_team = prior.iloc[-1]["TEAM_ABBREVIATION"]
                po_in_l10 = int((prior["SEASON_TYPE"] == "Playoffs").sum())
                for line, price in (rec.get("lines") or {}).items():
                    try:
                        line, price = float(line), float(price)
                    except ValueError:
                        continue
                    rows.append(dict(
                        date=gdate.strftime("%Y-%m-%d"), extraction_time=d["extraction_time"], player=player, team=team, prev_team=prev_team,
                        stat=stat, line=line, price=price, implied=1 / price,
                        n_l10=len(l10), hit_l10=sum(x >= line for x in l10) / len(l10),
                        hit_l5=sum(x >= line for x in l5) / len(l5),
                        avg_l10=avg10, l3_avg=sum(l10[:3]) / len(l10[:3]), cov=cov, min_avg=mins10,
                        game=f"{away_abbr}@{home_abbr}", po_in_l10=po_in_l10,
                        actual=actual, minutes=mins,
                        y=(None if actual is None else int(actual >= line)),
                    ))
    df = pd.DataFrame(rows)
    df.to_csv(a.out, index=False)
    print(f"rows={len(df)} with_outcome={int(df['y'].notna().sum())} dnp={int(df['y'].isna().sum())} "
          f"dates={df['date'].nunique()} players_unmatched={len(miss_players)} files_skipped={skipped_files}")


if __name__ == "__main__":
    sys.exit(main())
