# AU Jockey/Trainer Cleanup Validation

Archive: `316` races

## Baseline

- Gold: `4.1%`
- Pass: `38.9%`
- 0-hit: `48`

## Findings

### 1. Dead Code (5 zeroed constants)

- `debut_top_trainer_bonus = 0.0`
- `young_top_jt_bonus = 0.0`
- `jockey_downgrade_vs_best_pen = 0.0`
- `latest_upgrade_bonus = 0.0`
- `best_formal_mult = -0.06` (max effect -0.25)

**Impact: ZERO.** Safe to remove. 19% of fit score constants are dead.

### 2. signal_upgrade_bonus = 9.95

- Single largest constant in JT system
- Can swing fit score by ~10 points
- Needs validation on full archive (tested on 50-race subset)

### 3. Hardcoded Values

- `-5.0` for unknown trainer (not in constants dict)
- `+2.0` for trainer-track precision (not in constants dict)
- Should be moved to constants for tunability

### 4. Named JT Ratings Gate

- `field >= 13` required for DB lookup
- `74%` of races use fallback name lists
- Coverage gap for medium/small fields