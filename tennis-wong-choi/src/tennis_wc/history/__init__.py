"""Point-in-time feature history.

The rest of the system stores a player's rating and rank as single mutable
columns on ``players``, overwritten every time the builder runs.  A feature
snapshot taken after a match therefore embeds a rating that already contains
that match's result -- 3,776 of 16,046 stored snapshots (23.5%) were built
after their match day.  Anything a backtest reads must be as-of, not latest.
"""
