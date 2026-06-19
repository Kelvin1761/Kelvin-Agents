# AU Wong Choi Comprehensive Improvement Shadow Test

Each variant is tested independently against the full archive.
Only variants showing **positive Pass delta AND reduced 0-hit** should be considered.

Archive: `316` races from `Archive_Race_Analysis/AU_Racing/`

### V1: Matrix rebalance (stability↓ class_weight↑ form_line↑)

**Verdict: ❌ FAIL**

| Metric | Value |
|---|---|
| Races | 316 |
| Champion | 18.7% |
| Gold | 3.5% |
| Good | 17.7% |
| Pass | 35.1% |
| Top3 Place | 40.7% |
| 0-hit | 52 |
| 1-hit | 153 |
| 2-hit | 100 |
| 3-hit | 11 |

| ΔGold | ΔGood | ΔPass | ΔPlace | Δ0-hit | Δ1-hit |
|---:|---:|---:|---:|---:|---:|
| -0.3pp | +0.3pp | -0.3pp | -0.4pp | +2 | -1 |

### V2: Form score going adjustment + finer placing

**Verdict: ❌ FAIL**

| Metric | Value |
|---|---|
| Races | 316 |
| Champion | 20.9% |
| Gold | 3.8% |
| Good | 17.7% |
| Pass | 35.1% |
| Top3 Place | 41.1% |
| 0-hit | 49 |
| 1-hit | 156 |
| 2-hit | 99 |
| 3-hit | 12 |

| ΔGold | ΔGood | ΔPass | ΔPlace | Δ0-hit | Δ1-hit |
|---:|---:|---:|---:|---:|---:|
| +0.0pp | +0.3pp | -0.3pp | +0.0pp | -1 | +2 |

### V3: Sectional PI avg 2→4 + trial extreme bonus

**Verdict: ❌ FAIL**

| Metric | Value |
|---|---|
| Races | 316 |
| Champion | 20.3% |
| Gold | 3.2% |
| Good | 18.4% |
| Pass | 35.1% |
| Top3 Place | 40.8% |
| 0-hit | 50 |
| 1-hit | 155 |
| 2-hit | 101 |
| 3-hit | 10 |

| ΔGold | ΔGood | ΔPass | ΔPlace | Δ0-hit | Δ1-hit |
|---:|---:|---:|---:|---:|---:|
| -0.6pp | +0.9pp | -0.3pp | -0.3pp | +0 | +1 |

### V4: Pace map running-style × barrier interaction

**Verdict: ❌ FAIL**

| Metric | Value |
|---|---|
| Races | 316 |
| Champion | 20.9% |
| Gold | 3.8% |
| Good | 17.7% |
| Pass | 35.1% |
| Top3 Place | 41.1% |
| 0-hit | 49 |
| 1-hit | 156 |
| 2-hit | 99 |
| 3-hit | 12 |

| ΔGold | ΔGood | ΔPass | ΔPlace | Δ0-hit | Δ1-hit |
|---:|---:|---:|---:|---:|---:|
| +0.0pp | +0.3pp | -0.3pp | +0.0pp | -1 | +2 |

### V5: Barrier bias expansion from archive data

**Verdict: ✅ PASS**

| Metric | Value |
|---|---|
| Races | 316 |
| Champion | 21.2% |
| Gold | 1.9% |
| Good | 16.1% |
| Pass | 37.0% |
| Top3 Place | 41.0% |
| 0-hit | 50 |
| 1-hit | 149 |
| 2-hit | 111 |
| 3-hit | 6 |

| ΔGold | ΔGood | ΔPass | ΔPlace | Δ0-hit | Δ1-hit |
|---:|---:|---:|---:|---:|---:|
| -1.9pp | -1.3pp | +1.6pp | -0.1pp | +0 | -5 |

### V6: Combined V1+V2+V3 (safe subset)

**Verdict: ❌ FAIL**

| Metric | Value |
|---|---|
| Races | 316 |
| Champion | 18.7% |
| Gold | 3.2% |
| Good | 17.4% |
| Pass | 35.4% |
| Top3 Place | 40.7% |
| 0-hit | 52 |
| 1-hit | 152 |
| 2-hit | 102 |
| 3-hit | 10 |

| ΔGold | ΔGood | ΔPass | ΔPlace | Δ0-hit | Δ1-hit |
|---:|---:|---:|---:|---:|---:|
| -0.6pp | +0.0pp | +0.0pp | -0.4pp | +2 | -2 |

### V7: class_weight 3%→8% (surgical)

**Verdict: ❌ FAIL**

| Metric | Value |
|---|---|
| Races | 316 |
| Champion | 19.6% |
| Gold | 3.2% |
| Good | 17.7% |
| Pass | 34.8% |
| Top3 Place | 41.0% |
| 0-hit | 47 |
| 1-hit | 159 |
| 2-hit | 100 |
| 3-hit | 10 |

| ΔGold | ΔGood | ΔPass | ΔPlace | Δ0-hit | Δ1-hit |
|---:|---:|---:|---:|---:|---:|
| -0.6pp | +0.3pp | -0.6pp | -0.1pp | -3 | +5 |

---

## Summary Table

| Variant | Pass Δ | Gold Δ | Good Δ | Place Δ | 0-hit Δ | Verdict |
|---|---:|---:|---:|---:|---:|---|