# Tennis history generations and source-context integrity

This is a correctness repair. Probability weights, stake limits, family promotion rules and evaluation splits remain unchanged. It does not establish an accuracy or profitability gain.

## Reproduced bugs and repairs

The old history upsert keyed a match by provider ordinal and player, then replaced statistics without replacing opponent/date/round headers. A reused ordinal therefore attached a new match's aces to an old opponent. Renumbering the same knockout match also created extra rows. Both failures were reproduced before the fix.

Public knockout history now uses provider, tour, tournament identity/year, round and player pair as its event identity. Source ordinals remain separate metadata. Unsupported/weak identities retain their source reference and date; different providers are not merged. The three history writers use this path. Cross-provider ingestion also stops treating a player pair within ±10 days as proof of duplication: it requires the shared year-qualified public tournament ID, recognized knockout round and supplied format. This preserves actual rematches in different events/rounds and recognizes the same identified event across differing source dates. A contradictory winner for that identified event fails visibly instead of silently dropping a source. Missing identity stays unverified and is not declared duplicate. Changed facts create a new generation with its actual observation time; the old generation and an append-only observation are retained. Repeated identical facts are idempotent. Conflicting facts inside the same saved raw response raise an explicit error. Player-ID merges can reattach an existing semantic event, and corrections crossing New Year retain the tournament's year identity.

History consumers, settlement fallbacks, calibration and Elo now exclude superseded/disputed generations and self-opponent rows. Identity selection counts usable rows rather than revision count. Elo and calibration retain source-reference ordering, so an internal hash does not reorder same-day matches. These repairs do not rebuild or overwrite the live Elo archive by themselves. The ace-conceded profile also checks the opponent perspective's ingestion cutoff. Historical report context excludes future/late-ingested history and uses the shared qualifying/BO5 rule. Conflicting history count candidates cannot silently settle a forecast.

Round normalization is idempotent for F/SF/QF and other existing canonical codes; previously F/SF/QF became UNKNOWN. Strategy reference text is generated from the registry, constants and executable gate predicates with source fingerprints. Unsupported historical calibration/profitability wording has been removed.

## Source-context audit

Frozen source: `/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-bugs-20261026/bug_research_baseline.db`, SHA256 `2e13a17a63871cbd5e108a4c258ec1c7193d1c032752ed74025f8f02249284ac`.

The read-only audit inspected 160,768 legacy public-history rows. It verified 134,421 headers against the saved source and found **88 proven mismatches**, all TennisMyLife: 24 opponent, 49 date and 35 round discrepancies (reasons overlap). It left 22,245 rows with unknown date/round, 3,154 unknown player mappings and 860 unknown raw matches explicitly unverified. This is not certification of the remaining dataset. Full cases are in `tennis-history-source-context-20261027.json`.

`audit_legacy_history.py` defaults to read-only. `--apply --backup-dir ...` requires a checked, consistent SQLite backup; DBs above 1GB require the mounted external archive. It validates every planned row's complete state under a write transaction before marking only proven cases DISPUTED and recording their original facts. It neither guesses replacement statistics nor rewrites old forecasts/settlements. Live application must follow activation of consumers that understand this status.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python scripts/audit_legacy_history.py \
  --db '/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-bugs-20261026/bug_research_baseline.db' \
  --output /private/tmp/tennis-legacy-history-context-baseline.json
```

## Component evidence and limitations

The same twelve date-stratified fixtures from the preceding audit were retained before viewing outcomes. A 36MB projection preserves every feature input used by these fixtures; all twelve control payloads matched the preceding full-source B3 combined arm exactly. Raw response bodies are omitted, so this projection cannot support source-context audit claims. Builders/probe drivers are archived under `support/`.

Round correction changed 6/12 win probabilities, maximum absolute change **0.0056300703**. The final feature payloads equal the round-only candidate on this unchanged legacy projection. This isolates component behavior; it is not an outcome-based evaluation of history quarantine or a profitability test. Detailed probabilities, hashes and projection manifest are in `tennis-history-correctness-20261027.json`.

The separate production-Elo input replay used complete player/history tables (25,224 players, 419,769 history rows; 177MB source projection). Baseline processed 198,806 winner rows. Self-pair exclusion alone processed 198,796; proven source-context quarantine alone 198,751; combined 198,741. All arms used identical fixed parameters. Combined changes propagated to 9,288 final overall ratings, with a maximum absolute change of 17.569 Elo points. This is input/rebuild impact, not historical predictive performance, and no production archive was overwritten. Ablations, source hashes and largest changes are in `tennis-elo-integrity-impact-20261027.json`. Working copies were processed and removed sequentially below the 1GB temporary-data rule.

The cross-provider canonical reader remains **diagnostic only**. In a deliberately duplicate-heavy sample of 20 groups/80 rows it selected 18, collapsed 18 additional agreeing observations and held 44. These are biased diagnostic counts, not corpus rates. Different recorded dates, provider-local event namespaces and older season-file availability remain unresolved. Do not wire this selector, rebuild the sole known-good Elo archive, or use these results to tune weights without independent impact comparisons.

Native tests and quick checks are recorded in the delivery closeout; immutable full release checks and live data repair require separate confirmation. The rejected WTA history candidate stays rejected. Elo shadow still needs its registered forward sample before promotion.
