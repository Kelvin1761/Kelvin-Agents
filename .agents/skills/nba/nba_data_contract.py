"""Version and source receipts required before using NBA statistics."""

NBA_STATISTICS_CONTRACT = 2  # v2: defender sample size is total attempts, not per-game


def statistics_current(meta):
    """A successful extraction needs a nonempty, correctly labelled source."""
    if not isinstance(meta, dict) or type(meta.get("statistics_contract")) is not int:
        return False
    source = meta.get("defender_source")
    if not isinstance(source, dict):
        return False
    return (meta["statistics_contract"] == NBA_STATISTICS_CONTRACT
            and source.get("per_mode") == "Totals"
            and source.get("sample_unit") == "total_attempts"
            and type(source.get("observed_players")) is int
            and source["observed_players"] > 0)
