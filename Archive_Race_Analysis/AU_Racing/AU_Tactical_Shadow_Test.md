# AU Tactical Adjustments Shadow Test

## Baseline
- Races: **395**
- Champion: **71 / 395 = 18.0%**
- Good: **68 / 395 = 17.2%**
- Pass: **135 / 395 = 34.2%**
- Order Issue: **149**

## Variants
| Variant | Champion | Gold | Good | Pass | MRR | Order | Avg Top4 Hits | Delta |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| baseline | 71 | 14 | 68 | 135 | 0.3126 | 149 | 1.522 | C +0 / Pass +0 / Order +0 |
| tactical_only | 72 | 14 | 65 | 136 | 0.3167 | 149 | 1.527 | C +1 / Pass +1 / Order +0 |
| tactical_aggressive | 72 | 14 | 66 | 137 | 0.3183 | 146 | 1.522 | C +1 / Pass +2 / Order -3 |
| tightening_only | 71 | 14 | 68 | 134 | 0.3124 | 150 | 1.529 | C +0 / Pass -1 / Order +1 |
| tactical_and_tightening | 72 | 14 | 65 | 135 | 0.3164 | 150 | 1.534 | C +1 / Pass +0 / Order +1 |
| tactical_agg_and_tight | 72 | 14 | 66 | 136 | 0.3181 | 147 | 1.529 | C +1 / Pass +1 / Order -2 |