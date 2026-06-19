# AU 06-06 Validation Before Implementation

- Live races: **19**
- Archive subset races: **94**

## Live ability_score baseline

- Races: **19**
- Labels: Gold 1, Good 1, Pass 1, 1 Hit 13, Miss 3
- Top3 precision: **35.1%**
- Winner in Top3: **15.8%**
- Top1 winner: **5.3%**

## Live rank_score baseline

- Races: **19**
- Labels: Gold 1, Good 1, Pass 1, 1 Hit 13, Miss 3
- Top3 precision: **35.1%**
- Winner in Top3: **15.8%**
- Top1 winner: **5.3%**

## Live close-gap candidate

- Races: **19**
- Labels: Gold 1, Good 1, Pass 1, 1 Hit 12, Miss 4
- Top3 precision: **33.3%**
- Winner in Top3: **15.8%**
- Top1 winner: **5.3%**

## Live JT/confidence candidate

- Races: **19**
- Labels: Gold 1, Good 1, Pass 1, 1 Hit 12, Miss 4
- Top3 precision: **33.3%**
- Winner in Top3: **10.5%**
- Top1 winner: **5.3%**

## Live pace/track candidate

- Races: **19**
- Labels: Gold 1, Good 1, Pass 1, 1 Hit 13, Miss 3
- Top3 precision: **35.1%**
- Winner in Top3: **15.8%**
- Top1 winner: **5.3%**

## Live combined candidate

- Races: **19**
- Labels: Gold 1, Good 1, Pass 1, 1 Hit 12, Miss 4
- Top3 precision: **33.3%**
- Winner in Top3: **15.8%**
- Top1 winner: **5.3%**

## Archive rank_score baseline

- Races: **94**
- Labels: Gold 2, Good 8, Pass 16, 1 Hit 50, Miss 18
- Top3 precision: **36.9%**
- Winner in Top3: **45.7%**
- Top1 winner: **19.1%**

## Archive combined candidate

- Races: **94**
- Labels: Gold 2, Good 15, Pass 20, 1 Hit 39, Miss 18
- Top3 precision: **40.8%**
- Winner in Top3: **45.7%**
- Top1 winner: **20.2%**

## ML Gate

- Train archive subset: **94 races / 1056 horses**
- Live labels: Gold 0, Good 2, Pass 2, 1 Hit 12, Miss 3
- Live Top3 precision: **35.1%**
- Live Winner in Top3: **10.5%**
- Top linear ML feature weights:
  - `rating_score`: 0.0601
  - `consistency_score`: 0.0584
  - `mx_stability`: 0.0584
  - `jockey_score`: 0.0516
  - `trainer_score`: 0.0516
  - `mx_jockey_trainer`: 0.0457
  - `mx_class_weight`: 0.0428
  - `form_score`: 0.0395
  - `track_score`: 0.0265
  - `mx_track`: 0.0265
  - `trial_score`: 0.0245
  - `pace_map_score`: -0.0195

