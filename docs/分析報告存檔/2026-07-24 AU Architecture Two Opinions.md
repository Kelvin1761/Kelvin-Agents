# AU Wong Choi — Architecture in Plain Language (2026-07-24)

Answering Kelvin's worry: "if we mix in odds, aren't we just reading the odds —
why build a model at all?" **You are right to worry, and the correct
architecture specifically avoids that trap.**

## The one idea: the model is a SECOND OPINION, not an odds-reader

- The **model** = an opinion about each horse formed **without looking at the
  money** (form, sectionals, class, trials...).
- The **odds** = the crowd's opinion (which you can indeed read for free).
- **The value is the DISAGREEMENT between them** — and you can only know the
  crowd is wrong if you have an independent opinion to compare against.

Reading the odds alone tells you *what the crowd thinks*. It can NEVER tell you
*when the crowd is wrong*. The model exists to say "I rate this $71 horse a
top-2 chance" — a statement that only has value because it was made without
seeing the $71. That is Savagery Vibe.

So: **we do NOT blend odds into the model's ranking.** Blending into one number
would dilute the model into the odds — exactly the thing you fear. We keep them
as two separate columns and read the gap.

## Three zones (this is the whole product)

| Model says | Market says | Meaning | Action |
|---|---|---|---|
| good | good | both agree | confident placer — but NO bet value (already priced) |
| **good** | **bad** | **model's edge** | **overlay / value bet** (Savagery Vibe) — findable ONLY with an independent model |
| bad | good | model blind spot | a "check yourself" flag — market may know something we don't |

## Data backing this (61-date Betfair sample)

- **Zone 2 pays:** model-top2 / market-hated horses that WON = 28 in the
  archive; that is where the +36% take-SP ROI lives. Reading odds alone finds
  ZERO of these (they're longshots the crowd dismissed).
- **Zone 3 is real (answers #3):** 215 short-priced favourites PLACED (90 of
  them WON) while our model ranked them ≥5. These are genuine model blind
  spots. We can now *see* them (they're simply the market's top-2) without
  hard-rescuing — a diagnostic list, not an auto-override.

## #2 — did mixing odds improve trifecta-in-top4?

| 4-horse selection | all 3 placegetters in it | ≥2 of 3 |
|---|---:|---:|
| model top-4 (odds-blind) | 13.1% | 58.7% |
| model top2 ∪ market top3 (~3.8) | 12.2% | **67.1%** |

Honest read: mixing the market does **not** improve the hard "all 3" trifecta
(≈13% either way) — that is genuinely hard. It clearly improves "≥2 of 3"
coverage (58.7% → 67.1%) in fewer horses, which is what most place / quinella /
box structures actually need. So: better *breadth*, not better *exacta*.

## What this means for the build

1. Model stays **odds-blind** (protect the asset — the independent opinion).
2. Add ONE derived column: the horse's **market rank** (day-before), shown
   beside the model rank. Never merged into the model score.
3. The dashboard surfaces the **three zones** — especially Zone 2 (your bets)
   and Zone 3 (model blind spots to review).
4. This needs only a market RANK (racenet gives it free, no Betfair needed).
   Betfair is only for the betting-execution price + money-flow later.

You are not building a model to read the odds. You are building a model to find
where the odds are wrong — which reading the odds alone can never do.
