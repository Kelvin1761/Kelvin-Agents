# AU Auto SIP Test Results

Each SIP is tested independently against the 315-race archive.
Only SIPs showing positive results should be promoted to production.

## Baseline (Current Engine)

| Baseline | 136 | 1.5% | 5.9% | 21.3% | 33.1% | 30.1% | 44 | 63 | 27 | 2 |
| Races=136 | Gold 1.5% | Good 5.9% | Pass 21.3% | Win 33.1% | Place 30.1% | 0H 44 | 1H 63 | 2H 27 | 3H 2 |

## SIP-1: high_consumption_load penalty

| SIP-1: high_consumption_load penalty | 136 | 0.7% | 5.9% | 19.1% | 31.6% | 29.7% | 42 | 68 | 25 | 1 |
| Races=136 | Gold 0.7% | Good 5.9% | Pass 19.1% | Win 31.6% | Place 29.7% | 0H 42 | 1H 68 | 2H 25 | 3H 1 |

| ΔGold | ΔGood | ΔPass | ΔPlace Prec | Δ0-hit | Δ1-hit |
|---:|---:|---:|---:|---:|---:|
| -0.7pp | +0.0pp | -2.2pp | -0.5pp | -2 | +5 |

### Class Breakdown (SIP-1)

| Class | Races | Gold | Good | Pass | Place Prec | 0-hit | 1-hit | 2-hit | 3-hit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| BM58-70 | 61 | 0.0% | 1.6% | 16.4% | 28.4% | 19 | 32 | 10 | 0 |
| BM72-84 | 10 | 0.0% | 10.0% | 20.0% | 23.3% | 5 | 3 | 2 | 0 |
| BM88+ | 3 | 0.0% | 0.0% | 0.0% | 22.2% | 1 | 2 | 0 | 0 |
| Group 1 | 9 | 0.0% | 0.0% | 33.3% | 37.0% | 2 | 4 | 3 | 0 |
| Group 2/3 | 14 | 0.0% | 7.1% | 14.3% | 26.2% | 5 | 7 | 2 | 0 |
| Maiden | 5 | 0.0% | 0.0% | 20.0% | 40.0% | 0 | 4 | 1 | 0 |
| Other | 34 | 2.9% | 14.7% | 23.5% | 32.4% | 10 | 16 | 7 | 1 |

## SIP-2: Soft track rebalance

| SIP-2: Soft track rebalance | 136 | 1.5% | 5.9% | 21.3% | 33.1% | 30.1% | 44 | 63 | 27 | 2 |
| Races=136 | Gold 1.5% | Good 5.9% | Pass 21.3% | Win 33.1% | Place 30.1% | 0H 44 | 1H 63 | 2H 27 | 3H 2 |

| ΔGold | ΔGood | ΔPass | ΔPlace Prec | Δ0-hit | Δ1-hit |
|---:|---:|---:|---:|---:|---:|
| +0.0pp | +0.0pp | +0.0pp | +0.0pp | +0 | +0 |

### Condition Breakdown (SIP-2)

| Condition | Races | Gold | Good | Pass | Place Prec | 0-hit | 1-hit | 2-hit | 3-hit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Good/Firm | 82 | 1.2% | 6.1% | 19.5% | 29.7% | 26 | 40 | 15 | 1 |
| Soft | 33 | 0.0% | 3.0% | 18.2% | 29.3% | 10 | 17 | 6 | 0 |
| Heavy | 21 | 4.8% | 9.5% | 33.3% | 33.3% | 8 | 6 | 6 | 1 |

## SIP-3: Barrier bias

| SIP-3: Barrier bias | 136 | 1.5% | 7.4% | 24.3% | 35.3% | 30.9% | 45 | 58 | 31 | 2 |
| Races=136 | Gold 1.5% | Good 7.4% | Pass 24.3% | Win 35.3% | Place 30.9% | 0H 45 | 1H 58 | 2H 31 | 3H 2 |

| ΔGold | ΔGood | ΔPass | ΔPlace Prec | Δ0-hit | Δ1-hit |
|---:|---:|---:|---:|---:|---:|
| +0.0pp | +1.5pp | +2.9pp | +0.7pp | +1 | -5 |

## SIP-4: Dynamic place dampening

| SIP-4: Dynamic place dampening | 136 | 1.5% | 5.9% | 21.3% | 33.1% | 30.1% | 44 | 63 | 27 | 2 |
| Races=136 | Gold 1.5% | Good 5.9% | Pass 21.3% | Win 33.1% | Place 30.1% | 0H 44 | 1H 63 | 2H 27 | 3H 2 |

| ΔGold | ΔGood | ΔPass | ΔPlace Prec | Δ0-hit | Δ1-hit |
|---:|---:|---:|---:|---:|---:|
| +0.0pp | +0.0pp | +0.0pp | +0.0pp | +0 | +0 |

### Field Size Breakdown (SIP-4)

| Field Size | Races | Gold | Good | Pass | Place Prec | 0-hit | 1-hit | 2-hit | 3-hit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Field <=8 | 99 | 2.0% | 7.1% | 23.2% | 30.0% | 35 | 41 | 21 | 2 |
| Field 9-12 | 27 | 0.0% | 3.7% | 18.5% | 32.1% | 6 | 16 | 5 | 0 |
| Field 13+ | 10 | 0.0% | 0.0% | 10.0% | 26.7% | 3 | 6 | 1 | 0 |

## SIP-5: JT sample-size confidence cap

| SIP-5: JT sample-size confidence cap | 136 | 1.5% | 5.9% | 21.3% | 33.1% | 30.4% | 43 | 64 | 27 | 2 |
| Races=136 | Gold 1.5% | Good 5.9% | Pass 21.3% | Win 33.1% | Place 30.4% | 0H 43 | 1H 64 | 2H 27 | 3H 2 |

| ΔGold | ΔGood | ΔPass | ΔPlace Prec | Δ0-hit | Δ1-hit |
|---:|---:|---:|---:|---:|---:|
| +0.0pp | +0.0pp | +0.0pp | +0.2pp | -1 | +1 |

### Field Size Breakdown

| Field Size | Races | Gold | Good | Pass | Place Prec | 0-hit | 1-hit | 2-hit | 3-hit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Field <=8 | 99 | 2.0% | 7.1% | 23.2% | 30.3% | 34 | 42 | 21 | 2 |
| Field 9-12 | 27 | 0.0% | 3.7% | 18.5% | 32.1% | 6 | 16 | 5 | 0 |
| Field 13+ | 10 | 0.0% | 0.0% | 10.0% | 26.7% | 3 | 6 | 1 | 0 |

## SIP-6: Overrated shield

| SIP-6: Overrated shield | 136 | 2.2% | 5.9% | 20.6% | 30.9% | 29.7% | 46 | 62 | 25 | 3 |
| Races=136 | Gold 2.2% | Good 5.9% | Pass 20.6% | Win 30.9% | Place 29.7% | 0H 46 | 1H 62 | 2H 25 | 3H 3 |

| ΔGold | ΔGood | ΔPass | ΔPlace Prec | Δ0-hit | Δ1-hit |
|---:|---:|---:|---:|---:|---:|
| +0.7pp | +0.0pp | -0.7pp | -0.5pp | +2 | -1 |

### Field Size Breakdown

| Field Size | Races | Gold | Good | Pass | Place Prec | 0-hit | 1-hit | 2-hit | 3-hit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Field <=8 | 99 | 2.0% | 5.1% | 21.2% | 30.0% | 33 | 45 | 19 | 2 |
| Field 9-12 | 27 | 0.0% | 7.4% | 18.5% | 29.6% | 8 | 14 | 5 | 0 |
| Field 13+ | 10 | 10.0% | 10.0% | 20.0% | 26.7% | 5 | 3 | 1 | 1 |

## SIP-7: JT cap + Overrated shield

| SIP-7: JT cap + Overrated shield | 136 | 2.2% | 5.9% | 20.6% | 30.9% | 29.7% | 46 | 62 | 25 | 3 |
| Races=136 | Gold 2.2% | Good 5.9% | Pass 20.6% | Win 30.9% | Place 29.7% | 0H 46 | 1H 62 | 2H 25 | 3H 3 |

| ΔGold | ΔGood | ΔPass | ΔPlace Prec | Δ0-hit | Δ1-hit |
|---:|---:|---:|---:|---:|---:|
| +0.7pp | +0.0pp | -0.7pp | -0.5pp | +2 | -1 |

### Field Size Breakdown

| Field Size | Races | Gold | Good | Pass | Place Prec | 0-hit | 1-hit | 2-hit | 3-hit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Field <=8 | 99 | 2.0% | 5.1% | 21.2% | 30.0% | 33 | 45 | 19 | 2 |
| Field 9-12 | 27 | 0.0% | 7.4% | 18.5% | 29.6% | 8 | 14 | 5 | 0 |
| Field 13+ | 10 | 10.0% | 10.0% | 20.0% | 26.7% | 5 | 3 | 1 | 1 |

## SIP-8: Narrow overrated shield

| SIP-8: Narrow overrated shield | 136 | 1.5% | 5.9% | 20.6% | 33.1% | 29.9% | 44 | 64 | 26 | 2 |
| Races=136 | Gold 1.5% | Good 5.9% | Pass 20.6% | Win 33.1% | Place 29.9% | 0H 44 | 1H 64 | 2H 26 | 3H 2 |

| ΔGold | ΔGood | ΔPass | ΔPlace Prec | Δ0-hit | Δ1-hit |
|---:|---:|---:|---:|---:|---:|
| +0.0pp | +0.0pp | -0.7pp | -0.2pp | +0 | +1 |

### Field Size Breakdown

| Field Size | Races | Gold | Good | Pass | Place Prec | 0-hit | 1-hit | 2-hit | 3-hit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Field <=8 | 99 | 2.0% | 7.1% | 23.2% | 30.0% | 35 | 41 | 21 | 2 |
| Field 9-12 | 27 | 0.0% | 3.7% | 18.5% | 32.1% | 6 | 16 | 5 | 0 |
| Field 13+ | 10 | 0.0% | 0.0% | 0.0% | 23.3% | 3 | 7 | 0 | 0 |

## SIP-9: JT cap + Narrow shield

| SIP-9: JT cap + Narrow shield | 136 | 1.5% | 5.9% | 20.6% | 33.1% | 30.1% | 43 | 65 | 26 | 2 |
| Races=136 | Gold 1.5% | Good 5.9% | Pass 20.6% | Win 33.1% | Place 30.1% | 0H 43 | 1H 65 | 2H 26 | 3H 2 |

| ΔGold | ΔGood | ΔPass | ΔPlace Prec | Δ0-hit | Δ1-hit |
|---:|---:|---:|---:|---:|---:|
| +0.0pp | +0.0pp | -0.7pp | +0.0pp | -1 | +2 |

### Field Size Breakdown

| Field Size | Races | Gold | Good | Pass | Place Prec | 0-hit | 1-hit | 2-hit | 3-hit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Field <=8 | 99 | 2.0% | 7.1% | 23.2% | 30.3% | 34 | 42 | 21 | 2 |
| Field 9-12 | 27 | 0.0% | 3.7% | 18.5% | 32.1% | 6 | 16 | 5 | 0 |
| Field 13+ | 10 | 0.0% | 0.0% | 0.0% | 23.3% | 3 | 7 | 0 | 0 |

---

## Verdict

SIPs with **positive Pass delta AND reduced 0-hit** should be promoted.
SIPs with negative or zero impact should be redesigned before promotion.
