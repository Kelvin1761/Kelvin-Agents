"""Version and source receipts required before using NBA statistics."""


# v2: defender sample size is total attempts, not per-game.
# v3 (2026-11-01, ESPN as the one source): no defender table is required --
# tracking data exists on stats.nba.com only and changed no probability
# (EXP-20261031-01) -- and every package names the ruler its numbers came from.
NBA_STATISTICS_CONTRACT = 3
STAT_SOURCES = ("espn", "nbacom", "mixed")


# Marker on the retired tracking tables (defenders, DvP: stats.nba.com only).
# EXP-20261031-01: removing key_defenders changed no probability across 13,376
# replayed legs; EXP-20261101-60 retired them with stats.nba.com.
TRACKING_UNAVAILABLE = "stats_nba_tracking_only"


def stat_source(package):
    """Which feed the package's statistics came from: 'espn', 'nbacom' or 'mixed'.

    Game logs carry their own ``source`` ('espn' / 'nba'); league tables are
    ESPN-computed when ``data_sources[label].source`` is ``espn_box``, and an
    nba.com snapshot is still nba.com. Training refuses 'mixed' corpora (one
    ruler per training window); publishing does not.
    """
    players = [p for team in (package.get("players") or {}).values() for p in team or []]
    logs = [str((p.get("gamelog") or {}).get("source") or "nba") for p in players if p.get("gamelog")]
    tables = [info for label, info in ((package.get("meta") or {}).get("data_sources") or {}).items()
              if label in ("team_stats", "player_advanced") and (info or {}).get("rows")]
    kinds = {"espn" if source == "espn" else "nbacom" for source in logs}
    kinds |= {"espn" if str((info or {}).get("source", "")).startswith("espn") else "nbacom"
              for info in tables}
    if not kinds:
        return "mixed"   # nothing to vouch for a single ruler
    return kinds.pop() if len(kinds) == 1 else "mixed"


def statistics_current(meta):
    """A successful extraction needs a nonempty, correctly labelled source.

    v3: a known ``stat_source``. v2: the one empty source accepted is a
    defender table explicitly marked as unavailable during an nba.com outage
    -- never a silently empty one.
    """
    if not isinstance(meta, dict) or type(meta.get("statistics_contract")) is not int:
        return False
    if meta["statistics_contract"] == NBA_STATISTICS_CONTRACT:
        return meta.get("stat_source") in STAT_SOURCES
    if meta["statistics_contract"] != 2:
        return False
    # v2 packages (before 2026-11-01) still validate under their own rule.
    source = meta.get("defender_source")
    if not isinstance(source, dict):
        return False
    observed = source.get("observed_players")
    return (source.get("per_mode") == "Totals"
            and source.get("sample_unit") == "total_attempts"
            and type(observed) is int
            and (observed > 0
                 or (observed == 0 and source.get("unavailable") == TRACKING_UNAVAILABLE)))
