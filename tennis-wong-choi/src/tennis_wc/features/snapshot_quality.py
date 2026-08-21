"""One definition of "the data quality of this match".

Feature snapshots accumulate rather than upsert -- 4,353 (match, player) pairs
hold more than one and there are 18,447 extra rows -- so "the" quality of a
match is ambiguous, and three separate places resolved it independently with
``MIN(data_quality_score)`` over every snapshot ever written.  That returns the
worst score the match has ever had rather than its current one, so no rebuild
could improve any of the gates however much better the data became: the prop
pricer stripped derived families' value flag, and the ROI report excluded the
same rows from the evidence the strategy gate reads.

The current quality is the LATEST snapshot per player, then the worse of the
two players.
"""
from __future__ import annotations

LATEST_QUALITY_CTE = """
    SELECT fs.match_id, MIN(fs.data_quality_score) AS data_quality_score
    FROM feature_snapshots fs
    WHERE fs.id = (
        SELECT MAX(x.id) FROM feature_snapshots x
        WHERE x.match_id = fs.match_id AND x.player_id = fs.player_id
    )
    GROUP BY fs.match_id
"""


def match_quality(conn, match_id: int):
    """Current quality for one match, or None when it has no snapshot."""
    row = conn.execute(
        f"SELECT data_quality_score FROM ({LATEST_QUALITY_CTE}) WHERE match_id = ?",
        (match_id,),
    ).fetchone()
    return row[0] if row else None
