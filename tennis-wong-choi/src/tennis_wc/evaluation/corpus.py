"""Which prop rows a judgement may be measured on.

2026-08-26. `prop_tracker`'s headline record was not a record. Every one of the
13,658 rows carried a `recorded_at` in 2026-08, and a SINGLE run on 2026-08-10
wrote 9,594 of them covering match dates 2026-05-10 through 08-11 -- three
months of "history" priced after the results were known. Measured on the same
corpus, split by whether the row was written before its match started:

    post-hoc backfill        1,962 value bets   ROI  +6.05%  CI [+1.32, +10.86]
    genuinely pre-match        342 value bets   ROI -15.45%  CI [-25.14, -5.04]
    both pooled (published)  2,304 value bets   ROI  +2.86%  CI [ -1.45,  +7.12]

The published number is the average of a real loss and an artefact. Pooled
model-vs-market AUC (0.82) comes from the same place and is not evidence either.

So the corpus needs a definition, in one place, that every scorecard, weight
fit, stop rule and report shares -- the same reason AU has `corpus_paths.py`.

WHAT COUNTS AS PRE-MATCH

Not the date. `match_date` is the tournament's local day and `recorded_at` is
UTC, so 335 rows look pre-match by date and were in fact written after the ball
was in the air. The only sound comparison is against `matches.start_time_utc`,
which is why three states are needed rather than a boolean:

    POINT_IN_TIME (1)  recorded_at < start_time_utc      -- provably pre-match
    POST_START    (0)  recorded_at >= start_time_utc     -- provably too late
    UNVERIFIABLE (NULL) no start_time_utc on the match   -- unknown, so excluded

UNVERIFIABLE is deliberately NOT admitted. 467 of those rows look pre-match by
date and 4,708 look post-match, and there is no way to tell which is which; a
corpus that admits "probably fine" is the corpus we just finished discarding.
Judgement queries therefore ask for `= 1`, never `!= 0`.

The column is stored, not re-derived, because `start_time_utc` gets backfilled
and corrected over time -- re-deriving would silently reclassify rows that were
already used in a decision.

WHICH READERS GATE AND WHICH MUST NOT

Only readers whose output informs a DECISION. Gated: `family_reliability`,
`prop_roi_report`, `model_vs_market_scorecard`, the weekly review, the stop
rule, `holdout_validation`, `evaluate_market_residual_props` and the four
per-market evaluators, `replay_prop_strategy`.

Deliberately NOT gated, and gating them would be a bug: settlement itself
(a post-start row still has to be graded, or it sits PENDING forever), the
`prop_live_bets` lookup, the card builder in `tennis_daily_schedule`, and the
row counts in `validation.checks` -- a data check that only looked at the clean
subset could not see the problem it exists to report.

The test is not "does this query touch prop_tracker" but "would a number from
it change what we do".
"""
from __future__ import annotations

POINT_IN_TIME = 1
POST_START = 0
UNVERIFIABLE = None

# The one-off classifier for rows written before the column existed, and the
# expression the migration uses. Kept beside the runtime predicate so the two
# can never drift apart.
CLASSIFY_SQL = """
    CASE
        WHEN m.start_time_utc IS NULL OR m.start_time_utc = '' THEN NULL
        WHEN p.recorded_at < m.start_time_utc THEN 1
        ELSE 0
    END
"""


def point_in_time_clause(alias: str = "p") -> str:
    """SQL predicate admitting only provably pre-match rows.

    Use this in every query whose output informs a decision -- reliability
    weights, model-vs-market scorecards, ROI segments, the stop rule. Do not
    hand-write `recorded_at < match_date`: that admitted 335 post-start rows.
    """
    return f"{alias}.is_point_in_time = 1"


def classify_point_in_time(recorded_at: str | None,
                           start_time_utc: str | None) -> int | None:
    """Classify one row. Returns POINT_IN_TIME / POST_START / UNVERIFIABLE.

    Both arguments are ISO-8601 UTC strings, which compare correctly as text
    provided they carry the same shape -- they do, both come from `utc_now()`
    or from the provider's own `start_time_utc`.
    """
    if not start_time_utc or not recorded_at:
        return UNVERIFIABLE
    return POINT_IN_TIME if str(recorded_at) < str(start_time_utc) else POST_START


def corpus_summary(conn) -> dict[str, int]:
    """Row counts per class, for the health report and for tests.

    Reported rather than asserted: the pre-match share is a fact about how the
    scheduler ran, and it is allowed to be small. What is not allowed is for a
    judgement to quietly borrow the other classes to make itself look big.
    """
    rows = conn.execute(
        """
        SELECT is_point_in_time AS cls,
               COUNT(*) AS n,
               SUM(CASE WHEN result_status IN ('WON','LOST') THEN 1 ELSE 0 END) AS graded,
               SUM(CASE WHEN result_status IN ('WON','LOST')
                         AND is_value = 1 AND stake_units > 0 THEN 1 ELSE 0 END) AS staked
        FROM prop_tracker GROUP BY is_point_in_time
        """
    ).fetchall()
    out = {
        "point_in_time": 0, "point_in_time_graded": 0, "point_in_time_staked": 0,
        "post_start": 0, "post_start_graded": 0, "post_start_staked": 0,
        "unverifiable": 0, "unverifiable_graded": 0, "unverifiable_staked": 0,
    }
    for row in rows:
        cls = row["cls"] if not isinstance(row, tuple) else row[0]
        n, graded, staked = (row["n"], row["graded"], row["staked"]) \
            if not isinstance(row, tuple) else (row[1], row[2], row[3])
        prefix = {1: "point_in_time", 0: "post_start"}.get(cls, "unverifiable")
        out[prefix] += n or 0
        out[f"{prefix}_graded"] += graded or 0
        out[f"{prefix}_staked"] += staked or 0
    return out
