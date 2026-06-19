# AU Shadow Bundle Benchmark

## Baseline
- Races: **395**
- Champion: **89 / 395 = 22.5%**
- Good: **80 / 395 = 20.3%**
- Pass: **154 / 395 = 39.0%**
- Order Issue: **151**

## Variants

| Variant | Champion | Gold | Good | Pass | MRR | Order | Avg Top4 Hits | Delta |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| baseline | 89 | 17 | 80 | 154 | 0.3702 | 151 | 1.628 | C +0 / Good +0 / Pass +0 / Order +0 |
| bundle_conservative | 90 | 14 | 76 | 150 | 0.3681 | 154 | 1.638 | C +1 / Good -4 / Pass -4 / Order +3 |
| bundle_recommended | 90 | 14 | 76 | 150 | 0.3675 | 153 | 1.638 | C +1 / Good -4 / Pass -4 / Order +2 |
| bundle_wet_sectional | 90 | 15 | 74 | 152 | 0.3654 | 157 | 1.625 | C +1 / Good -6 / Pass -2 / Order +6 |