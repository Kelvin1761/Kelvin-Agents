# AU Wong Choi — Pedigree + Excuse angles: offline verdict (2026-07-25)

Kelvin: build 血統 (pedigree) + LLM excuse-extraction layer. Disciplined
offline-first (validate signal on data we already have BEFORE any extraction/
LLM build). Both come back null.

## Good news: both angles' data already existed — no new extraction needed
- `sire_line` (sire name) is already in _data.
- `recent_shape_wide_no_cover_count` (white-run/WNC) already extracted.
- interference keywords (受阻/被夾/檢討/checked/blocked...) parseable from the
  facts record table (28% of horses flagged).

## Excuse signal — REFUTED (both the cheap and the correct proxy)
Do horses that had trouble last start out-perform their model rank (i.e. is the
bad run forgivable)? Actual top-3 finish by model-rank band:

| band | no-trouble | had-trouble |
|---|---:|---:|
| model top-4 | 41.6% | 42.0% (WNC 41.0%) |
| model 5-8 | 20.9% | 18.5% (WNC 18.9%) |

Trouble-flagged horses do NOT bounce back — in the 5-8 band they finish WORSE.
Interference is common (28%), often reflects a genuinely slow/awkward horse, and
the model's form/consistency already dampen a single bad run. A severity-aware
LLM read *might* isolate the rare "badly checked, should've won" case, but the
28%-coverage keyword proxy shows zero residual → low prior; not worth the build.

## Pedigree (sire) — NEGLIGIBLE
As-of-date (leak-free) sire top-3 strike rate, does it separate its runners?

| | sire high (>=30%) | sire low |
|---|---:|---:|
| all | 29.6% | 29.1% |
| lightly-raced (<=2 starts) | 33.9% | 33.6% |

0.3-0.5pp — sire OVERALL strike is too coarse for an individual runner, and the
good progeny are already captured by their own form/rating. Even for
lightly-raced horses (where sire should matter most) it's negligible. A sire
WET/DISTANCE aptitude split might be sharper but needs an external pedigree
database, and the prior is now low.

## The one angle still genuinely unchecked
Gear changes (first-time blinkers): my n=3 probe (1/3 first-time gear) was too
small to dismiss — the honest test needs the BASE RATE of first-time gear
(a ~90-race racenet extraction). Still open, but low prior.

## Honest meta-conclusion (now very robust)
Tested offline this session, conditional on the model: gear (weak), first-up
(refuted), trial-quality (washes out), pedigree/sire (null), excuse/interference
(null). EVERY individual-horse raw angle washes out — the model has extracted
what the current data supports at the individual level. This is not defeatism;
it is the pre-registered gate working. The one repeatedly-proven lever left is
the MARKET column (orthogonal, +36% BSP overlay edge) — which is set aside by
choice, not because it failed.

## What shipped this session regardless
Data coverage/confidence as first-class (資料 column + python_auto.data_coverage)
— the transparency fix, independent of these null signals.
