# EXP-20261101-60 NBA: ESPN for everything — remove every remaining nba.com dependency

- **Date**: 2026-11-01 (Claude Code; Kelvin: "let's change everything that is using nba.com into using espn")
- **Platform**: NBA
- **Nature**: data sources and engineering. **Does not change any probability, coefficient or model.** Removing the official injury report = removing a safety rail that could only make banker selection stricter (decided by Kelvin).
- **Prior records searched**: EXP-20261101-01/02 (PBP lineups, one ruler; ESPN is already the stats source), EXP-20261030-01 (ESPN fallback), EXP-20261026-02 (official injury report + `availability_obs`), EXP-20261025-07 (opportunity sources), EXP-20261023-02 (injury name matching).

## Scope (two releases)

**R1 reflector**
1. `fetch_nba_results.py`: ESPN primary. Scoreboard and summary all go through `nba_espn_http.get_json` (`fresh_after`, shared rate limit and cache; previously the summary bypassed it via `requests`). nba.com scoreboard/box score/`leaguegamefinder` removed. Finality = ESPN completed + box-score points sum equals ESPN score; when ESPN is unreachable the game is not final.
2. `fetch_nba_pbp.py`: rewritten to read ESPN play-by-play (`nba_espn_lineups.fetch_summary`, each game fetched once ever); `PBP_Brief` schema keys unchanged.
3. `nba_backtester.py`: no caller, writes a DB that doesn't exist → deleted.
4. `build_nba_ml_dataset.py`: `fetch_boxscore` (BoxScoreTraditionalV2) is dead code → deleted; `fetch_results_for_date` used to call the nba.com scoreboard and returned None when it came back empty, now it goes through R1-1's ESPN path.

**R2 extractor** (starts after `claude-nba-data-repair-20261101` lands)
5. `nba_extractor.py`: every nba.com endpoint branch deleted, ESPN is the only path; `nbacom` mode removed → `nba_api_breaker.py`, `nba_league_snapshot.py`, `track_stats_nba_source` retire along with it.
6. `nba_opportunities.py`: `player_base`, `team_base` rebuilt from ESPN box; the 5 Second Spectrum tracking tables (`passing`, `rebounding`, `possessions`, `catch_shoot`, `pull_up`) **retired** — ESPN has none of them, and a PBP proxy would be a different definition and wouldn't use the same name. Descriptive only (`model_input_enabled: False`).
7. IDs: switch to ESPN athlete/team id (fixes the 2026 rookies missing from the offline nba_api roster); every `player_id` reader checked before switching.
8. `nba_official_injuries.py` (official.nba.com PDF): **removed** (Kelvin decided). Bankers go back to ESPN-only rules: ESPN `Out` → removed; ESPN `Day-To-Day` → not in bankers.
9. `requirements.txt`/SETUP.md drop `nba_api`. Done = `grep -rn nba_api` hits no live code.

## Historical effect of the official injury report (measured before removal, `evidence/EXP-20261101-60-nba-official-injury-effect.py`)

Ledger `availability_obs` (latest published pre-tip snapshot per player-game) joined to Results_Brief box scores: 302 player-games over 5 dates (10-26, 10-27, 10-28, 10-29, 11-01).

| League report stricter than ESPN | Player-games | Didn't play | Priced by Sportsbet pre-tip |
|---|---|---|---|
| ESPN unlisted → league Out/Doubtful | 45 | **45 (100%)** | 0 |
| ESPN unlisted → league Questionable (banker excluded) | 13 | 8 | 2 (Isaiah Stewart, Andrew Nembhard; **both played**) |
| ESPN Day-To-Day → league Out (removed from every combo) | 5 | 5 | 1 (Keegan Murray, 24 legs) |

- The 3 priced players had `picked_in` empty in all `model_obs` rows and appear in no `sgm_obs`/`banker_shadow_obs` → **in 5 days the official report changed 0 published bankers/SGMs**.
- The 45 Out calls were all correct, but none of them were priced by Sportsbet (two-way / G-League / long-term injuries), so they don't affect legs.
- Losses after removal: (a) a case like Murray (ESPN DTD, actually Out) would go back into non-banker combos — still excluded from bankers by ESPN DTD; (b) ESPN has no Questionable/Doubtful status, so league Questionable without an ESPN listing (like Stewart/Nembhard) would become banker-eligible. Both happened about once in 5 days, and both of those players played.
- Limitation: only 5 dates, low power; this is a description, not a threshold.

## Pre-registered gates (written before running, committed before results)

| Item | Gate | Fail = |
|---|---|---|
| R1-1 results | Re-settle with ESPN only every date that already has a `Results_Brief`: per-leg `outcome`/`actual` vs the stored brief **100% identical**; each difference explained case by case (e.g. ESPN stat corrections); any unexplained difference = no release | REJECT R1 |
| R1-2 PBP | Schema keys same as the 10-27 brief; quarter scores match box score | fix then re-test |
| R1-4 labels | 49-event corpus (EXP-20261023-06 manifest) labels `hit` **100% identical** | REJECT R1 |
| R2-5/7 extractor + IDs | Same-day before/after re-extraction (ESPN mode, same cache): packages equal after excluding timestamps, `player_id`, `meta.data_sources`; `hit_rate_l10` 100% identical; **C-layer `p_final` 0 changes** | REJECT R2 |
| R2-6 opportunities | `player_base`/`team_base` vs the 2025-26 nba.com final snapshot: per-game box median \|Δ\| ≤ 0.1 (same box-score source) | fix then re-test |
| R2-8 injuries | Replay the latest snapshot for the 5 dates above: number of published bankers/SGMs that change (expected 0) | report only (Kelvin has decided) |

Neither release touches C coefficients, refits or windows.

## Results

### R1 (2026-11-01)

**R1-1 settlement parity** (`evidence/EXP-20261101-60-nba-results-settlement-parity.py`): 9 US dates that have a stored Results_Brief (10-20..10-28, 10-31; 7 nba.com, 2 already ESPN). All 81 final scores match, game by game.

| | Legs |
|---|---|
| Settled with the stored brief | 14,814 |
| Settled with the ESPN brief | 15,648 |
| **Identical** | **14,695** |
| Only ESPN settles (stored brief fetched before the game ended: 10-27 US date stored had 1 final, ESPN 4) | 890 (253 hit + 637 miss; no outcome difference, stored was incomplete) |
| Stored void, ESPN PLAYER_NOT_FOUND (unsettled) | 56 (3 players) |
| Actual value differs | 58 legs / 11 players; **outcome flips 5** (4 hit→miss, 1 miss→hit) |

Explained case by case:
- **Inactive players**: nba.com's box listed inactives (comment → VOID_DNP), ESPN's box leaves them out. First run 120 legs / 7 players were unsettled → fixed: ESPN `injuries` players with `status: Out` join the box as inactive (comment, minutes empty → VOID_DNP; summed score unchanged, tested). Down to 56 legs / 3 players (Malik Monk, Kyrie Irving, Ausar Thompson): **nowhere in the ESPN summary, not even under injuries** → stay PLAYER_NOT_FOUND (held, not guessed; void legs are excluded from evaluation anyway, so metrics are unchanged).
- **Stat differences**: ESPN and nba.com credit a different player for the same play (e.g. 10-25 MEM@SAC: Cameron Boozer ESPN 14 pts / nba.com 16; Jaylen Wells reb 7/5; Ty Jerome ast 7/6). Final scores match on both sides, so this is how points/rebounds/assists were attributed (stat corrections), not missing data. 5/14,695 = 0.03% outcome flips. Which side is right can't be checked against a third source; from now on ESPN is the single source.
- Verdict: per the pre-registered rule every difference has an explanation → **R1-1 PASS**.

**R1-2 PBP**: `PBP_Brief` schema keys identical to the stored 10-27 brief (top and game level); on 10-27 BKN@BOS (OT) quarter_breakdown is digit-for-digit the same as the nba.com version. Quarter totals vs box-score final: 25/26 games match; POR@LAL ESPN PBP final 138-129 but box/scoreboard 136-129 (inconsistency inside ESPN; descriptive only, doesn't feed settlement). Fixed along the way: an existing bug where quarters were string-sorted so OT1 came before Q1 and Q1 came out negative (nba.com had the same bug).

**R1-4 labels** (`evidence/EXP-20261101-60-nba-label-parity.py`): 49-event corpus 8,286 labelled rows, 24 dates. Rows ESPN can re-label: **7,464/7,464 `hit` and `actual_value` 100% identical**. 822 rows (5 playoff events: 04-25 NYK@ATL, 04-27 OKC@PHX, 04-30 DEN@MIN, 05-07 and 05-13 CLE@DET) can't be re-labelled because the **ESPN summary 404s** (the same 8-game gap as in EXP-20261101-02); `fetch_results_for_date` reuses the existing final brief first and never overwrites it, so the existing corpus loses no labels. Limitation: a corpus rebuilt from zero would be missing these 5 events.

**R1-3**: `nba_backtester.py` deleted (no caller; doc pointer changed to the reflector).
