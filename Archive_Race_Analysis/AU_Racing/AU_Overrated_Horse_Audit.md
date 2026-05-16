# AU Overrated Horse Audit

- Definition: model 預測第 1 / 2，但實際跑入全場後段 batch。
- 後段 batch 定義: `max(4, ceil(field_size * 2 / 3))` 或更後名次。

- Cases: **153**
- `0-hit`: **55**
- `1-hit`: **98**
- Pred rank 1: **73** | Pred rank 2: **80**

## Buckets

- Good/Firm: **105 = 68.6%**
- Soft: **24 = 15.7%**
- Heavy: **24 = 15.7%**
- BM58-70: **58 = 37.9%**
- BM72+: **8 = 5.2%**
- Group/Listed: **30 = 19.6%**
- Maiden: **13 = 8.5%**
- Other: **44 = 28.8%**

## Most Common Overtrusted Sections

| Section | Count | Share |
|---|---:|---:|
| form_line | 140 | 45.8% |
| stability | 117 | 38.2% |
| jockey_trainer | 19 | 6.2% |
| class_weight | 16 | 5.2% |
| track | 10 | 3.3% |
| race_shape | 4 | 1.3% |

## Most Common Weak Sections In These Horses

| Section | Count | Share |
|---|---:|---:|
| race_shape | 78 | 25.5% |
| track | 78 | 25.5% |
| class_weight | 68 | 22.2% |
| sectional | 46 | 15.0% |
| jockey_trainer | 33 | 10.8% |
| stability | 3 | 1.0% |

## Example Cases

| Race | Miss | Pred | Horse | Actual | Top Signals | Weak Signals |
|---|---|---:|---|---:|---|---|
| 2025-08-02 Flemington Race 1-9 R3 | 1-hit | 2 | She's Pretty Rich | 11/16 | stability 81.6 / form_line 77.1 | sectional 62.3 / race_shape 62.8 |
| 2025-08-02 Flemington Race 1-9 R5 | 0-hit | 2 | Paradise Storm | 10/12 | form_line 75.1 / stability 73.5 | track 57.3 / class_weight 59.5 |
| 2025-08-02 Flemington Race 1-9 R8 | 0-hit | 1 | One Long Day | 10/15 | stability 86.7 / form_line 79.6 | sectional 68.3 / track 71.9 |
| 2025-08-02 Flemington Race 1-9 R9 | 0-hit | 2 | Illyivy | 10/13 | stability 83.8 / form_line 80.2 | race_shape 60.2 / track 61.4 |
| 2025-08-09 Randwick Race 1-10 R3 | 0-hit | 1 | Regimental Colours | 8/8 | stability 82.2 / form_line 78.2 | race_shape 61.0 / track 61.5 |
| 2025-08-09 Randwick Race 1-10 R3 | 0-hit | 2 | Dollar Magic | 8/8 | stability 75.9 / form_line 75.7 | class_weight 62.5 / sectional 65.6 |
| 2025-08-09 Randwick Race 1-10 R4 | 0-hit | 1 | Amreekiyah | 8/8 | stability 80.6 / form_line 76.2 | class_weight 58.9 / track 63.2 |
| 2025-08-09 Randwick Race 1-10 R4 | 0-hit | 2 | Tuileries | 8/8 | form_line 73.7 / stability 72.2 | race_shape 62.4 / track 65.5 |
| 2025-08-09 Randwick Race 1-10 R5 | 0-hit | 1 | Bundeena | 8/11 | stability 79.1 / form_line 75.1 | jockey_trainer 63.1 / sectional 65.0 |
| 2025-08-09 Randwick Race 1-10 R5 | 0-hit | 2 | Zouperb | 8/11 | stability 84.0 / form_line 79.6 | race_shape 58.7 / track 59.1 |
| 2025-08-09 Randwick Race 1-10 R7 | 0-hit | 1 | Kerguelen | 8/12 | stability 78.3 / form_line 74.6 | class_weight 62.5 / race_shape 67.5 |
| 2025-08-09 Randwick Race 1-10 R7 | 0-hit | 2 | Theblade | 8/12 | jockey_trainer 76.2 / form_line 72.0 | track 59.1 / class_weight 62.4 |
| 2025-08-09 Randwick Race 1-10 R8 | 0-hit | 1 | Romeo's Choice | 8/10 | stability 86.8 / form_line 79.6 | class_weight 57.7 / race_shape 61.4 |
| 2025-08-09 Randwick Race 1-10 R8 | 0-hit | 2 | Robusto | 8/10 | stability 77.9 / form_line 76.2 | class_weight 64.0 / sectional 65.4 |
| 2025-08-23 Randwick Race 1-10 R3 | 1-hit | 2 | Stylebender | 9/12 | stability 84.6 / form_line 79.0 | race_shape 59.6 / track 61.5 |
| 2025-08-23 Randwick Race 1-10 R5 | 0-hit | 2 | Tajanis | 6/7 | form_line 74.3 / stability 72.5 | track 58.9 / race_shape 65.6 |
| 2025-09-21 Flemington Race 1-8 R4 | 1-hit | 2 | Heed The Omens | 11/13 | stability 80.7 / form_line 77.6 | race_shape 59.1 / class_weight 63.3 |
| 2025-09-21 Flemington Race 1-8 R7 | 1-hit | 2 | Super Paradise | 12/12 | form_line 75.7 / stability 75.3 | track 59.1 / jockey_trainer 61.0 |
| 2025-10-04 Flemington Race 1-10 R5 | 1-hit | 2 | Movin Out | 9/10 | form_line 71.2 / jockey_trainer 69.9 | track 59.1 / race_shape 60.1 |
| 2025-10-04 Flemington Race 1-10 R6 | 1-hit | 1 | Jimmy Recard | 6/9 | stability 85.5 / form_line 79.6 | track 61.5 / class_weight 64.0 |
| 2025-10-04 Flemington Race 1-10 R6 | 1-hit | 2 | Inkaruna | 7/9 | stability 81.6 / form_line 77.6 | race_shape 66.8 / track 67.9 |
| 2025-10-04 Flemington Race 1-10 R7 | 0-hit | 1 | Mormona | 14/16 | stability 83.0 / form_line 79.0 | class_weight 60.5 / jockey_trainer 65.2 |
| 2025-10-04 Flemington Race 1-10 R7 | 0-hit | 2 | Sayedaty Sadaty | 12/16 | stability 85.0 / form_line 79.0 | class_weight 60.0 / jockey_trainer 64.7 |
| 2025-10-04 Randwick Race 1-10 R4 | 1-hit | 2 | Cobra Club | 10/10 | form_line 71.8 / stability 71.0 | class_weight 59.7 / sectional 64.8 |
| 2025-10-04 Randwick Race 1-10 R5 | 1-hit | 2 | Glad You Think So | 13/18 | stability 77.3 / form_line 76.2 | jockey_trainer 57.9 / track 64.7 |
| 2025-10-04 Randwick Race 1-10 R9 | 1-hit | 2 | Glory Daze | 13/18 | stability 85.4 / form_line 79.0 | sectional 62.1 / class_weight 62.4 |
| 2025-10-04 Randwick Race 1-10 R10 | 0-hit | 1 | Les Vampires | 14/15 | stability 77.9 / form_line 76.5 | class_weight 57.8 / jockey_trainer 63.0 |
| 2025-11-01 Flemington Race 1-9 R3 | 0-hit | 2 | Star Patrol | 11/13 | jockey_trainer 74.8 / form_line 71.8 | class_weight 65.0 / sectional 65.6 |
| 2025-11-01 Flemington Race 1-9 R8 | 1-hit | 1 | Splash Back | 8/11 | stability 81.6 / form_line 77.6 | race_shape 63.2 / class_weight 64.0 |
| 2025-11-01 Flemington Race 1-9 R9 | 0-hit | 2 | She's Bulletproof | 11/12 | form_line 73.2 / stability 73.0 | class_weight 64.0 / sectional 65.5 |
| 2025-11-01 Randwick Race 1-10 R1 | 1-hit | 1 | Chicama | 6/7 | stability 82.5 / form_line 80.2 | track 56.9 / class_weight 66.4 |
| 2025-11-01 Randwick Race 1-10 R2 | 1-hit | 1 | Concoction | 10/15 | stability 82.1 / form_line 78.2 | race_shape 60.9 / track 63.7 |
| 2025-11-01 Randwick Race 1-10 R2 | 1-hit | 2 | Lightning Speed | 15/15 | form_line 75.7 / stability 75.3 | race_shape 56.1 / track 56.3 |
| 2025-11-01 Randwick Race 1-10 R4 | 1-hit | 1 | Vetwelve | 18/18 | stability 85.5 / form_line 79.6 | track 61.5 / race_shape 62.4 |
| 2025-11-01 Randwick Race 1-10 R8 | 1-hit | 1 | Fully Lit | 11/16 | stability 84.0 / form_line 79.0 | class_weight 56.7 / race_shape 62.2 |
| 2025-11-01 Randwick Race 1-10 R9 | 1-hit | 1 | Maison Louis | 12/15 | stability 74.5 / form_line 73.2 | class_weight 57.9 / track 63.9 |
| 2025-11-04 Flemington Race 1-10 R1 | 1-hit | 1 | Knurl | 10/12 | class_weight 74.2 / form_line 72.6 | sectional 64.1 / jockey_trainer 64.2 |
| 2025-11-04 Flemington Race 1-10 R4 | 1-hit | 2 | That'smoneybrother | 9/11 | form_line 75.1 / stability 71.7 | race_shape 59.4 / track 62.7 |
| 2025-11-04 Flemington Race 1-10 R6 | 0-hit | 1 | Flying Valley | 9/9 | form_line 73.7 / stability 73.5 | track 55.8 / sectional 63.4 |
| 2025-11-04 Flemington Race 1-10 R6 | 0-hit | 2 | Garachico | 7/9 | stability 74.8 / form_line 72.6 | class_weight 50.5 / race_shape 62.2 |