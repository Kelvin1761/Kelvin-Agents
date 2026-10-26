# Canonical tennis history — correctness policy before implementation

Goal: stop counting source observations as independent matches while preserving every raw row. Do not tune weights, prefer profitable outcomes, or delete player/opponent/date groups wholesale.

The coarse key is a candidate group only: player, opponent and recorded date. A public season-file observation is anchored by tour, its upstream tournament identifier, a recognized knockout round and format. Revisions of its match ordinal can describe the same event; ordinal alone is not a durable match identity. Different known events or rounds remain separate.

Within an anchored event, contradictory outcomes or overlapping measurements are held. Agreeing observations use the earliest immutable row ID; no later information is attached to an earlier forecast. Sackmann and TennisMyLife share an explicit public tournament namespace; other provider IDs are not silently treated as equivalent.

Additional observations in a coarse group that cannot be mapped to the anchored event are marked unverified and withheld from verified statistics, rather than declared duplicates. If they contradict the only anchored event's outcome, hold that event too; do not choose a winner. Known distinct rounds/events remain usable. Unanchored groups with multiple observations and insufficient event identity are held pending source evidence. A single source observation remains a single observation, not an independently verified event.

Outputs must expose policy version, selected source row IDs, held IDs and reasons, and collapsed same-event members. This is a conservative lower bound on usable history, not a claim that every held row is false. Original rows/forecasts/results remain intact. Applying ingestion cutoffs precedes canonical selection. A later source revision cannot retroactively make an old forecast's receipt verified.

Before wiring a consumer, test same-event ordinal changes, opposite player perspectives, actual distinct rounds/events, source conflicts, unknown-round groups, chronological cutoffs and idempotency. Measure baseline/candidate on the same immutable corpus. Elo rebuilds and feature consumers require separate impact comparisons; never overwrite the only known-good ratings as an unmeasured side effect.

Known source example (read-only snapshot SHA256 2e13a17a...): player 18 vs 85, 2026-07-24 has public TML `ATP-2026-319-26-loser` and `ATP-2026-319-25-loser`, both tournament 2026-319, SF, identical recorded measurements, first imported in July versus October. Composite/Explorer observations in the same coarse group have different provider-local tournament IDs; they are not merged on the date key alone.
