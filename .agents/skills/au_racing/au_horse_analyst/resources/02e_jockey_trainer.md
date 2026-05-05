<!-- ============================================================ -->
<!-- Jockey, Trainer & Debut (Steps 11-13) — TRIMMED 2026-04-25 -->
<!-- Removed: SIP-RR10, SIP-RR06/RH05, verbose case studies -->
<!-- Dependencies: None -->
<!-- Referenced by: 02f_synthesis.md -->
<!-- ============================================================ -->

### Step 11: Jockey Info
- Track win rate (last 30 days) + golden jockey-trainer combo
- Engine match: pace jockey on closer = -10%. Jockey change: top-tier to lower = cooling, reverse = big test

- **[SIP-RR05] Elite Jockey-Trainer Prestige Track Cross-Check:**
  - T1 jockey + T1 trainer combo: if horse Soft WR% < 30%, prestige bonus halved (max +0.5 grade).
  - **[SIP-RH03] Prestige Without Fit Trap:** T1 jockey x T1 trainer + settling runner (>= 5th) + >= 10 runners + no clear pace/draw/track-family edge -> prestige bonus = 0, mark `[PRESTIGE WITHOUT FIT]`. Exempt if track specialist (WR >= 30%, sample >= 3) or speed map gives a clear run.

### Step 12: Risk & Trainer Intent
- Risk markers: roarer | lugging | age 8+ | long stride tight turn | slow beginner
- **[Respiratory Wet Compounding]:** Bleeder/roarer + Soft 6+ = counts as 2 risk markers.
- Momentum Score: weighted recent margins. Place Stability Index: top-3 in last 10 runs / 10.
- Weight: drop >6kg warning | gain 4-8kg positive. TVI tactical variability. WFA calibration.
- **Strong deployment signals:**
  - `Waller 3rd-Up` | `Waller Wet Track` | `Waller Quick Backup` (Maiden/BM58, <=7 day backup + >=2kg drop)
  - `Waller Metro Debut` (Metro + >=2 gear items -> can reach the general debut cap A-)
  - `Waterhouse/Bott Pace` (first blinkers + pace change) | `Waterhouse/Bott Debut` (trial strong + barrier 1-4 + pace jockey -> can reach the general debut cap A-)
  - `Maher Far Raid` (interstate + top jockey) | `Maher Quick Backup` (<=14 day re-run)
  - `Cummings Autumn Trail` (Godolphin autumn carnival buildup) | `Cummings Import Strike` (overseas import debut)
  - `Snowden Sprint` (2YO/3YO sprint specialist debut) | `Neasham First-Up` (high first-up strike rate)
  - `Freedman Stayer` (season mid-range distance increase) | `Baker Metro Drop` (provincial -> metro class drop + weight drop + inside draw)
  - Jockey swap to apprentice = warm-up discount | swap back to top = big test. 3-4 week spacing = loading.
- **[Trainer-Track Specialisation Search]:** Search `"[Trainer] [Track] stats [Season]"`. If >= 30% win rate at that track, auto +1 micro adjustment.
- **[SIP-FL05] Trainer Allocation Guessing Ban:** Same trainer 2+ horses in same race -> each horse rated independently. No "stable's main runner" speculation allowed.
- **[Condition Specialist Detection]:** Same venue + same distance >= 2 wins but volatile form -> mark `[Condition Specialist]`. If today matches conditions, stability override to Neutral.
- **[SIP-5] Momentum Factor:**

  | Level | Condition | Effect |
  |:---|:---|:---|
  | **Strong** | 3 consecutive wins (all within 90 days) | Auto +1 grade, can offset 1 draw penalty |
  | **Positive** | 2 consecutive wins (within 60 days) | +0.5 signal (needs other positive factors) |
  | **Decayed** | Streak >120 days ago or recent decline | No momentum credit |
  | **Neutral** | No streak | Not applicable |

  - **[SIP-RR17] Soft 7+ Momentum Floor:** Soft 7/Heavy + 2+ consecutive wins -> minimum floor B+.
  - Output format: mark `[Momentum: 3-streak]` or `[Momentum: positive]` in analysis.

- **[SIP-RH06] Last Win Correction:** "Last win" upgrade (+0.5) requires >= 2/3 of: same venue / same distance (+-200m) / same surface (+-1 grade). Else neutral. G2+ from lower class -> +0.25 only.

### Step 13: Debut Runner & Trial Trap [maiden only]
- Trial: placing + sectionals + urging level. Trials have no race pressure — auxiliary reference only.
- **[Trial Mirage Warning]:** Synthetic/inner grass trial dominant win but today on main turf -> discount 30%.
- Sire projection (-> `<sire_reference>`): distance, surface, maturity speed. Bloodline class > trial placing.
- Trainer debut strike rate: >20% trustworthy; <10% default to fitness run.
- Support signals: top jockey debut + dam has winners = positive. Lower jockey + no trial = high unknown.
- **General debut cap: A-.** A+ / S-tier requires formal race evidence and cannot be created from debut reputation alone.
- **Trial-only cap: B maximum.** Exceptional trial + sire + trainer = B+ cap. A- requires a genuine elite debut deployment signal, not only a good trial.
- **[Waller Metro Debut Override]:** Waller + Metro + >= 2 gear items (tongue tie / cross-over noseband / ear muffs off) -> can reach A- if the 7D matrix also supports it.
- **[Waterhouse/Bott Debut Override]:** Waterhouse & Bott + debut + strong trial pace + barrier 1-4 + pace jockey -> can reach A- if the 7D matrix also supports it.
- **[SIP-10] Imported Upside Buffer:** Top stable (Maher/Waller/O'Brien/Hayes) + top jockey + >= 1 positive AU trial -> cannot use "no AU data" as downgrade reason. Treat as `[Stable Import Intent]`, cap unlocked to A-/A. Exception: sire AWD > 2200m but racing 1200-1400m = warm-up, buffer invalid.

<!-- SIP-RR10 (Interstate Raid) and SIP-RR06/RH05 (G1 Pipeline / NZ Discount) archived 2026-04-25.
     Rarely triggered. Full logic in archive/02e_jockey_trainer_BACKUP.md -->
