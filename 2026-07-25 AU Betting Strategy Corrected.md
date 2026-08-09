# AU Wong Choi — 投注策略修正：edge 喺共識唔喺分歧 (2026-07-25)

Kelvin was right to doubt the overlay result. Re-tested on ALL 710 races with
split-half stability + bootstrap CI (which I had NOT done before — my error).

## The overlay "edge" was variance, not edge

| strategy | bets | strike | ROI | 1st half | 2nd half | verdict |
|---|---:|---:|---:|---:|---:|---|
| **D. WIN: model top2, market 7+ (overlay)** | 204 | 4.9% | +49.9% | **−27.5%** | **+127.3%** | ⚠️ pure variance |

A 4.9%-strike strategy is dominated by one or two big-priced winners. My earlier
+58.9% figure came from a cherry-picked cell without stability testing. The full
model-rank × market-rank grid confirms it: neighbouring low-strike cells swing
from −12% to +196%, which is noise, not signal.

## What IS stable — consensus, not disagreement

| strategy | bets | strike | ROI | 1st half | 2nd half | 95% CI | verdict |
|---|---:|---:|---:|---:|---:|---|---|
| **C. WIN: model top2 AND market top2** | 647 | 32.8% | **+8.5%** | +11.0% | +6.0% | [−5%, +21%] | ✅ stable |
| **F. PLACE: model #1 AND market #1** | 242 | **72.3%** | **+3.8%** | +4.9% | +2.8% | [−5%, +13%] | ✅ stable |
| E. WIN: model top4, market 7+ | 558 | 4.1% | +24.7% | +27.5% | +21.8% | [−29%, +85%] | positive but huge CI |
| A. PLACE: model top2 AND market top2 | 647 | 64.1% | +0.0% | −1.5% | +1.5% | [−6%, +6%] | break-even |
| B. PLACE: model top3 AND market top3 | 1207 | 57.4% | −2.5% | −3.0% | −2.1% | [−8%, +3%] | negative |

**The stable edge is where the model and the market AGREE** — model top-2 that
the market also rates top-2 wins 32.8% of the time and returns +8.5% at BSP,
positive in both halves of the archive with a decent sample (647 bets).

This corrects my earlier framing. The model's independent opinion is still what
lets you FIND these horses, but the profitable action is backing the ones the
market confirms — not the ones it dismisses. Longshot disagreement plays have
positive point estimates only because of fat-tailed variance.

## Recommendation for Kelvin's actual goal (spotting placegetters)

Kelvin's current rule (top-2 picks, place bet when place odds > 2, both if > 3)
tested at −11.3% / −23.5% — selecting for long place odds is adverse selection.

**Replace with:**
1. **PLACE bets: only when model #1 = market #1** (72.3% strike, +3.8% at BSP).
   High hit rate suits Kelvin's "spot horses that place" objective, and it stays
   positive across both halves.
2. **WIN bets: model top-2 that the market also has top-2** (32.8% strike,
   +8.5%). This is the best risk-adjusted play found in the whole project.
3. **Skip** long-odds place filters and longshot overlays — both are traps
   (adverse selection / variance respectively).

Caveats: all ROIs are at Betfair BSP with 5% commission; bookmaker prices differ.
CIs still include zero, so paper-trade and size conservatively — but unlike the
overlay, these two survive split-half stability on a large sample.
