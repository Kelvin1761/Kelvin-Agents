# AU Auto SIP Test Results

Each SIP is tested independently against the 315-race archive.
Only SIPs showing positive results should be promoted to production.

## Baseline (Current Engine)

| Baseline | 315 | 3.8% | 16.5% | 35.9% | 47.3% | 41.1% | 52 | 150 | 101 | 12 |
| Races=315 | Gold 3.8% | Good 16.5% | Pass 35.9% | Win 47.3% | Place 41.1% | 0H 52 | 1H 150 | 2H 101 | 3H 12 |

## SIP-9: JT cap + Narrow shield

| SIP-9: JT cap + Narrow shield | 315 | 3.8% | 17.5% | 37.5% | 48.3% | 41.4% | 54 | 143 | 106 | 12 |
| Races=315 | Gold 3.8% | Good 17.5% | Pass 37.5% | Win 48.3% | Place 41.4% | 0H 54 | 1H 143 | 2H 106 | 3H 12 |

| ΔGold | ΔGood | ΔPass | ΔPlace Prec | Δ0-hit | Δ1-hit |
|---:|---:|---:|---:|---:|---:|
| +0.0pp | +1.0pp | +1.6pp | +0.3pp | +2 | -7 |

### Field Size Breakdown

| Field Size | Races | Gold | Good | Pass | Place Prec | 0-hit | 1-hit | 2-hit | 3-hit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Field <=8 | 53 | 5.7% | 24.5% | 62.3% | 52.8% | 5 | 15 | 30 | 3 |
| Field 9-12 | 181 | 5.0% | 20.4% | 38.7% | 43.5% | 24 | 87 | 61 | 9 |
| Field 13+ | 81 | 0.0% | 6.2% | 18.5% | 29.2% | 25 | 41 | 15 | 0 |

---

## Verdict

SIPs with **positive Pass delta AND reduced 0-hit** should be promoted.
SIPs with negative or zero impact should be redesigned before promotion.
