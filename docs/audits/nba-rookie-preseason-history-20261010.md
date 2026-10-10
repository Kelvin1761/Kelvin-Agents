# NBA preseason rookie history recovery — 2026-10-10

Production `06:30` final refresh for MEM_CHI passed odds extraction but failed report validation. The report contained zero priced player cards, blocked by FW-06 and FW-08. The 10:30 health run correctly reported `missing_prediction`. No official prediction snapshot was created.

Captured Sportsbet odds at 06:36:46 named Cameron Boozer and Caleb Wilson. Current NBA and ESPN rosters both confirm their exact full names and team identities. NBA roster IDs are 1643409 (MEM) and 1643410 (CHI), both with official `EXP=R`. The extractor filtered core players using 2025-26 advanced usage, retaining 17 MEM and 15 CHI veterans while dropping both priced rookies.

Official NBA PlayerGameLog queries for 2026-27 `Pre Season`, with the original `date_to=10/08/2026`, return actual prior completed games:

- Cameron Boozer: October 7 (16 PTS, 6 REB, 2 AST, 22 MIN) and October 5 (11 PTS, 5 REB, 4 AST, 18 MIN).
- Caleb Wilson: October 7 (15 PTS, 4 REB, 2 AST, 29 MIN).

Raw response proof is saved in `/private/tmp/nba-rookie-history-20261010/`. The US event day and future rows are excluded by the existing cutoff filter. No fabricated games, NCAA data, padded L10 or market-implied history are introduced.

Recovery retains the complete current preseason roster, explicitly queries current preseason history for official rookies, and preserves prior-season regular/playoff history for veterans. Preseason caches lacking the new history contract are re-extracted. Each report card discloses source season/type, actual sample count and cutoff. The report adds one deduplicated small-sample NO BET warning; the entire preseason workflow remains SHADOW/NO BET.

No weights, formulas, trained artifacts, probability gates or publication validators are changed. This fixes extraction coverage, not a claimed model-performance improvement. A missing or failed preseason source still yields no history; it never generates replacement observations.

Validation: 120 NBA tests pass, including new roster retention, explicit preseason endpoint selection, original event-day exclusion, empty-source behavior, stale cache/existing-report invalidation, unknown official roster position preservation and report provenance. The latest daily scheduler suite passes 104 tests; the prior broader NBA run passed 120. Required quick gate passes; full release gate evidence is recorded in the immutable release manifest. The first canonical full run reached schema validation and exposed null positions for two newly retained roster members. Unknown positions are now preserved as empty strings, and invalid caches are rebuilt. The original failed output is retained; the second full run passed schema validation and generated eight player/category cards, but FW-04 correctly blocked eight identical warning sentences. The warning now appears once at report level, with each player’s actual sample count; card-level source provenance remains. A regression check keeps FW-04 unchanged. A subsequent unprivileged attempt could not reach the official schedule API and stopped safely. The network-enabled canonical rerun completed with exit 0: schema and report firewall both passed with zero errors/warnings, eight cards were generated, and Master SGM and Banker reports were compiled. The original NBA v3 model loaded with all 27 features; no artifacts changed.

The full-run fixture uses genuine odds captured before tipoff and invokes the actual extractor/report/validator/SGM orchestrator, with publication disabled. The game has already started, so this is a functional test only: it must not create a retrospective official prediction snapshot. A new immutable SHA approval is required before production activation, and full future pregame/postgame evidence remains pending.

Isolated proof root: `/private/tmp/nba-rookie-live-candidate-iuxnqpuk`. `TEST_RUN.json` records after-tipoff/test-only limitations; `full-run.log` retains the first schema failure; `full-run-second.log` records the warning failure, `full-run-third.log` the safely stopped network-restricted attempt, and `full-run-fourth.log` / `RESULT_FOURTH.json` the successful canonical rerun.
