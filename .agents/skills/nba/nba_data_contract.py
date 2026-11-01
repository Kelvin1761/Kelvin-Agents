"""Version and source receipts required before using NBA statistics."""

NBA_STATISTICS_CONTRACT = 2  # v2: defender sample size is total attempts, not per-game


# Marker the extractor writes when stats.nba.com was unreachable and the
# defender table (tracking data, nba.com only) came back empty. EXP-20261031-01:
# removing key_defenders changed no probability across 13,376 replayed legs.
TRACKING_UNAVAILABLE = "stats_nba_tracking_only"


def statistics_current(meta):
    """A successful extraction needs a nonempty, correctly labelled source.

    The one empty source accepted is a defender table explicitly marked as
    unavailable during an nba.com outage -- never a silently empty one.
    """
    if not isinstance(meta, dict) or type(meta.get("statistics_contract")) is not int:
        return False
    source = meta.get("defender_source")
    if not isinstance(source, dict):
        return False
    observed = source.get("observed_players")
    return (meta["statistics_contract"] == NBA_STATISTICS_CONTRACT
            and source.get("per_mode") == "Totals"
            and source.get("sample_unit") == "total_attempts"
            and type(observed) is int
            and (observed > 0
                 or (observed == 0 and source.get("unavailable") == TRACKING_UNAVAILABLE)))
