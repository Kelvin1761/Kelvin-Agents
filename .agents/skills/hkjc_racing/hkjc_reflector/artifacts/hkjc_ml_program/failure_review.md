# HKJC 0-hit / 1-hit Failure Review

Model reviewed: **Matrix Champion**.  All ranks below use pre-race features only; incidents and odds are diagnostic annotations, never training inputs.

## 2026-05-09 R2 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #1 北地烈馬 | 1 | 4 / 0.139 | 4 / 0.139 |
| #2 馬馳登 | 2 | 3 / 0.144 | 3 / 0.144 |
| #5 奇異歡星 | 3 | 2 / 0.157 | 2 / 0.157 |

Overrated Top-2 review: #7 川河石駒 (actual 5, p=0.162).
Pre-race signal review: #1 北地烈馬: race_shape 72.2 (+11.1 vs field), sectional 69.7 (+9.3 vs field)；#2 馬馳登: form_line 96.0 (+14.0 vs field), trainer_signal 79.3 (+9.8 vs field)；#5 奇異歡星: race_shape 74.8 (+13.7 vs field), form_line 94.0 (+12.0 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-05-09 R3 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1400m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #12 肥仔精神 | 1 | 12 / 0.023 | 12 / 0.023 |
| #8 巴閉佬 | 2 | 3 / 0.118 | 3 / 0.118 |
| #13 添喜運 | 3 | 1 / 0.215 | 1 / 0.215 |

Overrated Top-2 review: #7 雪茄福星 (actual 10, p=0.129).
Pre-race signal review: #12 肥仔精神: no ≥3-point above-field Matrix dimension；#8 巴閉佬: race_shape 78.6 (+18.0 vs field), sectional 65.5 (+5.8 vs field)；#13 添喜運: race_shape 82.0 (+21.4 vs field), stability 65.0 (+13.5 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-05-09 R8 — model Top-2 hits 0, Matrix 0

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #7 㩒住贏 | 1 | 8 / 0.045 | 8 / 0.045 |
| #11 富國兄弟 | 2 | 3 / 0.144 | 3 / 0.144 |
| #3 手機錶勁 | 3 | 4 / 0.116 | 4 / 0.116 |

Overrated Top-2 review: #4 超寫意 (actual 9, p=0.199)；#10 辣得準 (actual 7, p=0.163).
Pre-race signal review: #7 㩒住贏: stability 64.9 (+4.2 vs field)；#11 富國兄弟: form_line 96.0 (+12.2 vs field), race_shape 75.0 (+11.9 vs field)；#3 手機錶勁: stability 83.5 (+22.7 vs field), trainer_signal 87.0 (+18.6 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-05-09 R9 — model Top-2 hits 0, Matrix 0

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1000m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #7 團結勇士 | 1 | 4 / 0.101 | 4 / 0.101 |
| #13 幸運糖 | 2 | 9 / 0.043 | 9 / 0.043 |
| #14 飛來閃耀 | 3 | 8 / 0.068 | 8 / 0.068 |

Overrated Top-2 review: #2 米奇 (actual 7, p=0.165)；#1 會長之寶 (actual 9, p=0.156).
Pre-race signal review: #7 團結勇士: race_shape 78.2 (+16.7 vs field), stability 65.6 (+6.2 vs field)；#13 幸運糖: form_line 96.0 (+9.1 vs field), trainer_signal 75.0 (+6.2 vs field)；#14 飛來閃耀: form_line 96.0 (+9.1 vs field), class_advantage 75.6 (+7.1 vs field).
Cause assessment: available pre-race Matrix signals did not place enough contenders in the competitive tier.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-05-09 R11 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #4 錶之星河 | 1 | 2 / 0.169 | 2 / 0.169 |
| #2 翠紅 | 2 | 5 / 0.079 | 5 / 0.079 |
| #12 威利金箭 | 3 | 6 / 0.072 | 6 / 0.072 |

Overrated Top-2 review: #6 燈胆將軍 (actual 6, p=0.227).
Pre-race signal review: #4 錶之星河: race_shape 76.0 (+13.8 vs field), stability 74.4 (+11.4 vs field)；#2 翠紅: stability 72.7 (+9.7 vs field), trainer_signal 77.0 (+5.7 vs field)；#12 威利金箭: race_shape 72.6 (+10.4 vs field), trainer_signal 76.0 (+4.7 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-05-13 R1 — model Top-2 hits 1, Matrix 1

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **normal-result cohort**. Venue 跑馬地, Turf, 1650m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #1 焦點 | 1 | 1 / 0.184 | 1 / 0.184 |
| #3 駟跑得 | 2 | 10 / 0.052 | 10 / 0.052 |
| #12 華美之威 | 3 | 11 / 0.043 | 11 / 0.043 |

Overrated Top-2 review: #11 龍又生 (actual 10, p=0.160).
Pre-race signal review: #1 焦點: race_shape 78.8 (+16.2 vs field), stability 68.6 (+12.6 vs field)；#3 駟跑得: no ≥3-point above-field Matrix dimension；#12 華美之威: horse_health 73.2 (+4.5 vs field).
Cause assessment: available pre-race Matrix signals did not place enough contenders in the competitive tier.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-05-17 R2 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1000m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #14 拉合爾 | 1 | 1 / 0.133 | 1 / 0.133 |
| #10 致力之城 | 2 | 3 / 0.109 | 3 / 0.109 |
| #4 鄉村威龍 | 3 | 4 / 0.104 | 4 / 0.104 |

Overrated Top-2 review: #1 日出東方 (actual 10, p=0.128).
Pre-race signal review: #14 拉合爾: form_line 96.0 (+16.1 vs field), trainer_signal 80.3 (+10.5 vs field)；#10 致力之城: trainer_signal 77.0 (+7.3 vs field), race_shape 69.2 (+5.2 vs field)；#4 鄉村威龍: trainer_signal 84.8 (+15.0 vs field), stability 66.3 (+7.1 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-05-17 R3 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #3 快樂高球 | 1 | 8 / 0.079 | 8 / 0.079 |
| #11 東方寶寶 | 2 | 3 / 0.089 | 3 / 0.089 |
| #5 後無來者 | 3 | 2 / 0.120 | 2 / 0.120 |

Overrated Top-2 review: #4 首駿 (actual 5, p=0.133).
Pre-race signal review: #3 快樂高球: form_line 96.0 (+12.4 vs field)；#11 東方寶寶: trainer_signal 74.8 (+6.1 vs field)；#5 後無來者: trainer_signal 84.8 (+16.1 vs field), race_shape 68.8 (+7.0 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-05-17 R7 — model Top-2 hits 0, Matrix 0

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1400m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #1 自動自覺 | 1 | 6 / 0.070 | 6 / 0.070 |
| #4 實力加 | 2 | 5 / 0.078 | 5 / 0.078 |
| #3 八仟好運 | 3 | 4 / 0.097 | 4 / 0.097 |

Overrated Top-2 review: #2 哥倫布 (actual 5, p=0.162)；#12 瀧澤飛駒 (actual 4, p=0.137).
Pre-race signal review: #1 自動自覺: class_advantage 74.1 (+8.5 vs field), stability 62.4 (+8.2 vs field)；#4 實力加: stability 65.0 (+10.8 vs field), sectional 67.0 (+6.2 vs field)；#3 八仟好運: trainer_signal 78.3 (+10.3 vs field), stability 58.6 (+4.4 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-05-17 R8 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1800m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #14 夢照發 | 1 | 3 / 0.109 | 3 / 0.109 |
| #7 佰勝金龍 | 2 | 8 / 0.048 | 8 / 0.048 |
| #5 超開心 | 3 | 1 / 0.198 | 1 / 0.198 |

Overrated Top-2 review: #4 赤風驪 (actual 11, p=0.110).
Pre-race signal review: #14 夢照發: stability 71.2 (+16.2 vs field), class_advantage 75.6 (+10.0 vs field)；#7 佰勝金龍: stability 61.0 (+6.0 vs field), sectional 59.5 (+4.5 vs field)；#5 超開心: stability 73.2 (+18.2 vs field), trainer_signal 87.0 (+15.6 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-05-17 R9 — model Top-2 hits 1, Matrix 1

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1400m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #5 百勝威龍 | 1 | 8 / 0.053 | 8 / 0.053 |
| #13 飛躍成就 | 2 | 12 / 0.034 | 12 / 0.034 |
| #7 洪才 | 3 | 2 / 0.133 | 2 / 0.133 |

Overrated Top-2 review: #12 星光快驅 (actual 9, p=0.174).
Pre-race signal review: #5 百勝威龍: form_line 96.0 (+7.2 vs field)；#13 飛躍成就: horse_health 72.2 (+4.2 vs field), class_advantage 69.2 (+3.1 vs field)；#7 洪才: stability 66.8 (+13.0 vs field), race_shape 73.1 (+12.5 vs field).
Cause assessment: available pre-race Matrix signals did not place enough contenders in the competitive tier.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-05-20 R3 — model Top-2 hits 1, Matrix 1

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **normal-result cohort**. Venue 跑馬地, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #2 星火燎原 | 1 | 8 / 0.063 | 8 / 0.063 |
| #8 星辰千帥 | 2 | 7 / 0.074 | 7 / 0.074 |
| #4 佐治傳奇 | 3 | 1 / 0.192 | 1 / 0.192 |

Overrated Top-2 review: #6 烈焰光芒 (actual 5, p=0.123).
Pre-race signal review: #2 星火燎原: race_shape 76.8 (+16.3 vs field)；#8 星辰千帥: form_line 96.0 (+9.1 vs field), stability 63.0 (+6.3 vs field)；#4 佐治傳奇: stability 73.7 (+17.0 vs field), race_shape 73.0 (+12.5 vs field).
Cause assessment: available pre-race Matrix signals did not place enough contenders in the competitive tier.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-05-20 R4 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 跑馬地, Turf, 1650m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #8 有情有義 | 1 | 1 / 0.248 | 1 / 0.248 |
| #10 北海盜 | 2 | 3 / 0.088 | 3 / 0.088 |
| #3 財富非凡 | 3 | 5 / 0.082 | 5 / 0.082 |

Overrated Top-2 review: #12 多利神駒 (actual 7, p=0.107).
Pre-race signal review: #8 有情有義: trainer_signal 87.0 (+17.1 vs field), race_shape 76.6 (+13.9 vs field)；#10 北海盜: race_shape 76.0 (+13.3 vs field), class_advantage 72.3 (+4.6 vs field)；#3 財富非凡: race_shape 75.0 (+12.3 vs field), form_line 96.0 (+11.9 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-05-20 R7 — model Top-2 hits 0, Matrix 0

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 跑馬地, Turf, 1650m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #11 紫辰之星 | 1 | 3 / 0.145 | 3 / 0.145 |
| #4 泰力 | 2 | 7 / 0.051 | 7 / 0.051 |
| #5 做好自己 | 3 | 5 / 0.077 | 5 / 0.077 |

Overrated Top-2 review: #1 滿心星 (actual 6, p=0.230)；#3 開心勇駒 (actual 9, p=0.179).
Pre-race signal review: #11 紫辰之星: race_shape 79.8 (+16.3 vs field), form_line 96.0 (+8.4 vs field)；#4 泰力: sectional 67.0 (+8.3 vs field)；#5 做好自己: stability 77.0 (+17.6 vs field), sectional 67.3 (+8.7 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-05-24 R1 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1600m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #1 威力非凡 | 1 | 1 / 0.115 | 1 / 0.115 |
| #14 勁爽 | 2 | 13 / 0.042 | 13 / 0.042 |
| #6 神駒馬靈 | 3 | 3 / 0.098 | 3 / 0.098 |

Overrated Top-2 review: #7 志醒大將 (actual 4, p=0.099).
Pre-race signal review: #1 威力非凡: race_shape 72.5 (+12.8 vs field), trainer_signal 75.8 (+6.3 vs field)；#14 勁爽: stability 61.9 (+5.4 vs field), horse_health 73.2 (+5.4 vs field)；#6 神駒馬靈: stability 71.4 (+14.9 vs field), sectional 66.2 (+6.3 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-05-24 R5 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1600m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #2 大回報 | 1 | 1 / 0.162 | 1 / 0.162 |
| #13 幸運威龍 | 2 | 4 / 0.083 | 4 / 0.083 |
| #4 逍遙騎士 | 3 | 3 / 0.091 | 3 / 0.091 |

Overrated Top-2 review: #7 旌採 (actual 4, p=0.105).
Pre-race signal review: #2 大回報: stability 80.9 (+24.3 vs field), class_advantage 71.6 (+6.8 vs field)；#13 幸運威龍: race_shape 68.8 (+7.9 vs field), form_line 96.0 (+6.4 vs field)；#4 逍遙騎士: stability 67.5 (+11.0 vs field), form_line 96.0 (+6.4 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-05-24 R10 — model Top-2 hits 1, Matrix 1

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #5 煌上 | 1 | 1 / 0.136 | 1 / 0.136 |
| #13 閃電小子 | 2 | 10 / 0.037 | 10 / 0.037 |
| #1 得道猴王 | 3 | 13 / 0.028 | 13 / 0.028 |

Overrated Top-2 review: #12 鈁糖武士 (actual 9, p=0.131).
Pre-race signal review: #5 煌上: stability 82.8 (+20.0 vs field), race_shape 69.2 (+9.1 vs field)；#13 閃電小子: no ≥3-point above-field Matrix dimension；#1 得道猴王: form_line 96.0 (+14.1 vs field).
Cause assessment: available pre-race Matrix signals did not place enough contenders in the competitive tier.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-05-27 R4 — model Top-2 hits 0, Matrix 0

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **normal-result cohort**. Venue 跑馬地, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #5 朗日自強 | 1 | 3 / 0.123 | 3 / 0.123 |
| #11 天下寵兒 | 2 | 10 / 0.058 | 10 / 0.058 |
| #9 頑童 | 3 | 11 / 0.047 | 11 / 0.047 |

Overrated Top-2 review: #1 紅愛舍 (actual 9, p=0.176)；#2 贏得自然 (actual 10, p=0.141).
Pre-race signal review: #5 朗日自強: race_shape 79.0 (+15.4 vs field), sectional 65.8 (+6.8 vs field)；#11 天下寵兒: form_line 96.0 (+10.2 vs field), class_advantage 74.6 (+8.2 vs field)；#9 頑童: sectional 69.1 (+10.1 vs field).
Cause assessment: available pre-race Matrix signals did not place enough contenders in the competitive tier.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-05-27 R5 — model Top-2 hits 1, Matrix 1

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **normal-result cohort**. Venue 跑馬地, Turf, 1650m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #2 穿甲金鷹 | 1 | 1 / 0.258 | 1 / 0.258 |
| #6 智勇名駒 | 2 | 9 / 0.046 | 9 / 0.046 |
| #5 納百川 | 3 | 7 / 0.065 | 7 / 0.065 |

Overrated Top-2 review: #9 榮利雙收 (actual 7, p=0.144).
Pre-race signal review: #2 穿甲金鷹: stability 74.7 (+14.7 vs field), race_shape 80.8 (+13.5 vs field)；#6 智勇名駒: form_line 96.0 (+5.2 vs field)；#5 納百川: race_shape 78.0 (+10.7 vs field).
Cause assessment: available pre-race Matrix signals did not place enough contenders in the competitive tier.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-05-27 R6 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 跑馬地, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #9 風采人生 | 1 | 1 / 0.258 | 1 / 0.258 |
| #8 花好月盈 | 2 | 4 / 0.128 | 4 / 0.128 |
| #7 牛精新星 | 3 | 8 / 0.042 | 8 / 0.042 |

Overrated Top-2 review: #5 環球英雄 (actual 6, p=0.226).
Pre-race signal review: #9 風采人生: race_shape 77.0 (+14.8 vs field), sectional 72.7 (+13.9 vs field)；#8 花好月盈: race_shape 74.0 (+11.8 vs field), stability 70.0 (+10.7 vs field)；#7 牛精新星: stability 62.5 (+3.2 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-05-27 R7 — model Top-2 hits 0, Matrix 0

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **normal-result cohort**. Venue 跑馬地, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #9 幸運愉快 | 1 | 6 / 0.089 | 6 / 0.089 |
| #12 精益大師 | 2 | 10 / 0.041 | 10 / 0.041 |
| #6 新力 | 3 | 7 / 0.085 | 7 / 0.085 |

Overrated Top-2 review: #3 千杯敬典 (actual 9, p=0.158)；#11 良駒好友 (actual 5, p=0.131).
Pre-race signal review: #9 幸運愉快: trainer_signal 78.2 (+6.2 vs field), stability 60.9 (+3.3 vs field)；#12 精益大師: form_line 96.0 (+9.8 vs field)；#6 新力: race_shape 77.0 (+12.7 vs field).
Cause assessment: available pre-race Matrix signals did not place enough contenders in the competitive tier.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-05-27 R8 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 跑馬地, Turf, 1000m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #3 八駿巨昇 | 1 | 9 / 0.041 | 9 / 0.041 |
| #1 馬力 | 2 | 1 / 0.176 | 1 / 0.176 |
| #2 燭光晚餐 | 3 | 3 / 0.127 | 3 / 0.127 |

Overrated Top-2 review: #10 飛龍在天 (actual 7, p=0.167).
Pre-race signal review: #3 八駿巨昇: class_advantage 70.8 (+3.8 vs field)；#1 馬力: trainer_signal 87.0 (+17.2 vs field), form_line 96.0 (+10.1 vs field)；#2 燭光晚餐: race_shape 77.8 (+15.2 vs field), sectional 69.3 (+9.0 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-03 R2 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 跑馬地, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #4 首駿 | 1 | 3 / 0.094 | 3 / 0.094 |
| #3 金風萬里 | 2 | 2 / 0.114 | 2 / 0.114 |
| #12 快馬加鞭 | 3 | 6 / 0.067 | 6 / 0.067 |

Overrated Top-2 review: #2 喆喆友福 (actual 5, p=0.292).
Pre-race signal review: #4 首駿: race_shape 75.8 (+12.9 vs field), stability 64.6 (+9.9 vs field)；#3 金風萬里: form_line 96.0 (+12.8 vs field), sectional 69.1 (+7.8 vs field)；#12 快馬加鞭: class_advantage 73.3 (+5.1 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-03 R6 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 跑馬地, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #1 星運少爵 | 1 | 1 / 0.227 | 1 / 0.227 |
| #4 喵喵怪 | 2 | 8 / 0.034 | 8 / 0.034 |
| #5 銳目 | 3 | 4 / 0.125 | 4 / 0.125 |

Overrated Top-2 review: #7 獵寶勤 (actual 6, p=0.222).
Pre-race signal review: #1 星運少爵: stability 76.5 (+15.5 vs field), trainer_signal 87.0 (+14.2 vs field)；#4 喵喵怪: no ≥3-point above-field Matrix dimension；#5 銳目: race_shape 76.2 (+13.1 vs field), trainer_signal 82.5 (+9.8 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-07 R4 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1400m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #14 挺秀弘利 | 1 | 4 / 0.085 | 4 / 0.085 |
| #6 八仟好運 | 2 | 2 / 0.121 | 2 / 0.121 |
| #7 北極之錶 | 3 | 3 / 0.120 | 3 / 0.120 |

Overrated Top-2 review: #2 龍城強將 (actual 6, p=0.126).
Pre-race signal review: #14 挺秀弘利: sectional 65.5 (+6.0 vs field), trainer_signal 72.8 (+3.6 vs field)；#6 八仟好運: trainer_signal 78.3 (+9.1 vs field), stability 64.0 (+6.7 vs field)；#7 北極之錶: sectional 71.8 (+12.2 vs field), trainer_signal 80.3 (+11.1 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-07 R9 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #5 超寫意 | 1 | 1 / 0.154 | 1 / 0.154 |
| #6 㩒住贏 | 2 | 3 / 0.120 | 3 / 0.120 |
| #2 愛馬善 | 3 | 12 / 0.026 | 12 / 0.026 |

Overrated Top-2 review: #1 得道猴王 (actual 4, p=0.128).
Pre-race signal review: #5 超寫意: race_shape 68.9 (+8.3 vs field), trainer_signal 78.2 (+6.9 vs field)；#6 㩒住贏: stability 85.6 (+23.9 vs field), race_shape 66.7 (+6.1 vs field)；#2 愛馬善: no ≥3-point above-field Matrix dimension.
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-07 R10 — model Top-2 hits 0, Matrix 0

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #8 喜慶寶 | 1 | 3 / 0.124 | 3 / 0.124 |
| #5 魔術控制 | 2 | 10 / 0.044 | 10 / 0.044 |
| #9 威利金箭 | 3 | 4 / 0.113 | 4 / 0.113 |

Overrated Top-2 review: #6 扶搖勢勁 (actual 5, p=0.135)；#3 維港智能 (actual 4, p=0.134).
Pre-race signal review: #8 喜慶寶: stability 75.0 (+12.6 vs field), trainer_signal 80.5 (+9.1 vs field)；#5 魔術控制: no ≥3-point above-field Matrix dimension；#9 威利金箭: race_shape 72.0 (+10.5 vs field), class_advantage 71.8 (+3.9 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-10 R1 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 跑馬地, Turf, 1800m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #2 家樂寶駒 | 1 | 4 / 0.111 | 4 / 0.111 |
| #1 竣誠駒 | 2 | 3 / 0.124 | 3 / 0.124 |
| #10 龍又生 | 3 | 2 / 0.132 | 2 / 0.132 |

Overrated Top-2 review: #5 君智盛 (actual 7, p=0.135).
Pre-race signal review: #2 家樂寶駒: race_shape 77.8 (+17.1 vs field), form_line 95.0 (+14.0 vs field)；#1 竣誠駒: race_shape 73.0 (+12.3 vs field), stability 56.8 (+4.1 vs field)；#10 龍又生: sectional 63.0 (+10.4 vs field), race_shape 63.8 (+3.1 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-10 R2 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 跑馬地, Turf, 1650m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #1 高高至高 | 1 | 4 / 0.106 | 4 / 0.106 |
| #7 準希望 | 2 | 2 / 0.191 | 2 / 0.191 |
| #6 得意佳作 | 3 | 8 / 0.057 | 8 / 0.057 |

Overrated Top-2 review: #5 大千氣象 (actual 5, p=0.192).
Pre-race signal review: #1 高高至高: trainer_signal 80.3 (+12.5 vs field), form_line 96.0 (+10.7 vs field)；#7 準希望: race_shape 74.6 (+12.9 vs field), sectional 65.5 (+9.0 vs field)；#6 得意佳作: sectional 63.6 (+7.1 vs field), class_advantage 70.8 (+3.1 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-10 R3 — model Top-2 hits 0, Matrix 0

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **normal-result cohort**. Venue 跑馬地, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #8 風火猴王 | 1 | 5 / 0.090 | 5 / 0.090 |
| #11 友得盈 | 2 | 8 / 0.067 | 8 / 0.067 |
| #5 勝多多 | 3 | 7 / 0.074 | 7 / 0.074 |

Overrated Top-2 review: #9 良駒好友 (actual 6, p=0.151)；#7 豪邁先登 (actual 8, p=0.139).
Pre-race signal review: #8 風火猴王: sectional 65.0 (+3.9 vs field)；#11 友得盈: class_advantage 72.3 (+6.5 vs field), horse_health 74.0 (+4.3 vs field)；#5 勝多多: trainer_signal 80.5 (+13.0 vs field), class_advantage 70.8 (+5.0 vs field).
Cause assessment: available pre-race Matrix signals did not place enough contenders in the competitive tier.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-10 R4 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 跑馬地, Turf, 1000m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #3 鴻圖新星 | 1 | 1 / 0.216 | 1 / 0.216 |
| #5 美麗登場 | 2 | 4 / 0.114 | 4 / 0.114 |
| #8 天火同人 | 3 | 3 / 0.120 | 3 / 0.120 |

Overrated Top-2 review: #2 紅錢到 (actual 4, p=0.133).
Pre-race signal review: #3 鴻圖新星: race_shape 79.8 (+17.8 vs field), trainer_signal 80.5 (+9.4 vs field)；#5 美麗登場: trainer_signal 85.9 (+14.8 vs field)；#8 天火同人: race_shape 77.8 (+15.8 vs field), class_advantage 70.8 (+4.2 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-10 R5 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 跑馬地, Turf, 1650m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #12 爆竹 | 1 | 8 / 0.050 | 8 / 0.050 |
| #3 紅海勁 | 2 | 5 / 0.082 | 5 / 0.082 |
| #1 上浦福旺 | 3 | 2 / 0.195 | 2 / 0.195 |

Overrated Top-2 review: #5 有情有義 (actual 4, p=0.202).
Pre-race signal review: #12 爆竹: form_line 96.0 (+6.7 vs field), class_advantage 72.3 (+4.8 vs field)；#3 紅海勁: race_shape 75.0 (+11.7 vs field), form_line 95.0 (+5.7 vs field)；#1 上浦福旺: race_shape 81.0 (+17.7 vs field), stability 70.0 (+13.8 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-10 R6 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 跑馬地, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #8 烈焰光芒 | 1 | 3 / 0.135 | 3 / 0.135 |
| #4 日馳千里 | 2 | 4 / 0.095 | 4 / 0.095 |
| #3 風采人生 | 3 | 1 / 0.239 | 1 / 0.239 |

Overrated Top-2 review: #2 巴閉王 (actual 4, p=0.216).
Pre-race signal review: #8 烈焰光芒: trainer_signal 81.6 (+9.8 vs field), form_line 96.0 (+8.8 vs field)；#4 日馳千里: race_shape 78.2 (+16.6 vs field), form_line 96.0 (+8.8 vs field)；#3 風采人生: stability 74.7 (+16.6 vs field), trainer_signal 87.0 (+15.2 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-10 R7 — model Top-2 hits 1, Matrix 1

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **normal-result cohort**. Venue 跑馬地, Turf, 1800m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #5 極光之子 | 1 | 10 / 0.027 | 10 / 0.027 |
| #11 將義 | 2 | 2 / 0.142 | 2 / 0.142 |
| #2 川河耀駒 | 3 | 6 / 0.102 | 6 / 0.102 |

Overrated Top-2 review: #3 豐辰 (actual 4, p=0.206).
Pre-race signal review: #5 極光之子: trainer_signal 76.0 (+6.6 vs field)；#11 將義: race_shape 82.0 (+18.3 vs field), sectional 61.8 (+4.0 vs field)；#2 川河耀駒: race_shape 81.2 (+17.5 vs field), form_line 96.0 (+6.6 vs field).
Cause assessment: available pre-race Matrix signals did not place enough contenders in the competitive tier.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-13 R1 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1000m, Griffin.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #6 星球勇士 | 1 | 1 / 0.198 | 1 / 0.198 |
| #1 禪勝閃亮 | 2 | 4 / 0.151 | 4 / 0.151 |
| #7 量子猴王 | 3 | 3 / 0.171 | 3 / 0.171 |

Overrated Top-2 review: #5 紅悅舍 (actual 4, p=0.172).
Pre-race signal review: #6 星球勇士: trainer_signal 77.0 (+6.6 vs field), race_shape 62.8 (+5.5 vs field)；#1 禪勝閃亮: form_line 78.0 (+7.7 vs field), sectional 62.6 (+3.4 vs field)；#7 量子猴王: form_line 78.0 (+7.7 vs field), sectional 65.3 (+6.0 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-13 R2 — model Top-2 hits 1, Matrix 1

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #8 鄉村樂韻 | 1 | 1 / 0.159 | 1 / 0.159 |
| #4 果然僥倖 | 2 | 7 / 0.052 | 7 / 0.052 |
| #12 朗日雪峰 | 3 | 6 / 0.093 | 6 / 0.093 |

Overrated Top-2 review: #9 爆熱 (actual 5, p=0.159).
Pre-race signal review: #8 鄉村樂韻: sectional 68.0 (+11.9 vs field), trainer_signal 77.2 (+9.8 vs field)；#4 果然僥倖: class_advantage 74.1 (+6.3 vs field), horse_health 71.7 (+3.0 vs field)；#12 朗日雪峰: race_shape 70.8 (+7.9 vs field), class_advantage 72.3 (+4.5 vs field).
Cause assessment: available pre-race Matrix signals did not place enough contenders in the competitive tier.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-13 R6 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1400m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #1 百勝威龍 | 1 | 6 / 0.090 | 6 / 0.090 |
| #11 華麗再贏 | 2 | 1 / 0.147 | 1 / 0.147 |
| #9 遨遊波士 | 3 | 4 / 0.099 | 4 / 0.099 |

Overrated Top-2 review: #3 卓越蒨鋒 (actual 8, p=0.128).
Pre-race signal review: #1 百勝威龍: stability 64.7 (+10.1 vs field), form_line 96.0 (+7.5 vs field)；#11 華麗再贏: trainer_signal 82.5 (+13.1 vs field), stability 65.9 (+11.4 vs field)；#9 遨遊波士: form_line 96.0 (+7.5 vs field), race_shape 65.9 (+5.8 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-13 R7 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #3 巴閉精 | 1 | 1 / 0.211 | 1 / 0.211 |
| #6 利高八斗 | 2 | 3 / 0.123 | 3 / 0.123 |
| #1 鼓浪好友 | 3 | 4 / 0.100 | 4 / 0.100 |

Overrated Top-2 review: #5 巧眼光 (actual 9, p=0.150).
Pre-race signal review: #3 巴閉精: trainer_signal 87.0 (+18.4 vs field), stability 78.0 (+15.6 vs field)；#6 利高八斗: stability 79.5 (+17.2 vs field), trainer_signal 73.9 (+5.4 vs field)；#1 鼓浪好友: form_line 96.0 (+13.4 vs field), race_shape 71.2 (+9.3 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-13 R8 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1600m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #2 太陽勇士 | 1 | 4 / 0.116 | 4 / 0.116 |
| #7 一起美麗 | 2 | 2 / 0.178 | 2 / 0.178 |
| #1 睿盛人生 | 3 | 5 / 0.083 | 5 / 0.083 |

Overrated Top-2 review: #3 包裝福星 (actual 6, p=0.210).
Pre-race signal review: #2 太陽勇士: race_shape 70.1 (+6.5 vs field)；#7 一起美麗: sectional 68.0 (+7.6 vs field), trainer_signal 78.3 (+6.2 vs field)；#1 睿盛人生: trainer_signal 80.5 (+8.4 vs field), race_shape 66.7 (+3.2 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-13 R11 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1400m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #12 櫻花酒杯 | 1 | 3 / 0.121 | 3 / 0.121 |
| #3 綠野飛馳 | 2 | 2 / 0.152 | 2 / 0.152 |
| #4 超勁赤兔 | 3 | 7 / 0.069 | 7 / 0.069 |

Overrated Top-2 review: #7 友瑩亮 (actual 5, p=0.158).
Pre-race signal review: #12 櫻花酒杯: stability 75.3 (+13.6 vs field), trainer_signal 78.3 (+7.4 vs field)；#3 綠野飛馳: trainer_signal 84.8 (+13.9 vs field), form_line 96.0 (+9.6 vs field)；#4 超勁赤兔: sectional 68.0 (+10.7 vs field), stability 71.6 (+9.9 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-21 R1 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1000m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #5 極速神影 | 1 | 6 / 0.063 | 6 / 0.063 |
| #7 致力之城 | 2 | 1 / 0.139 | 1 / 0.139 |
| #9 紅海旺 | 3 | 5 / 0.066 | 5 / 0.066 |

Overrated Top-2 review: #8 將傲 (actual 4, p=0.135).
Pre-race signal review: #5 極速神影: stability 69.4 (+12.3 vs field), horse_health 74.0 (+5.6 vs field)；#7 致力之城: trainer_signal 79.2 (+9.3 vs field), stability 66.4 (+9.2 vs field)；#9 紅海旺: form_line 94.0 (+19.4 vs field), race_shape 68.0 (+5.1 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-21 R3 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #1 包裝明將 | 1 | 2 / 0.111 | 2 / 0.111 |
| #5 祥勝鷹駒 | 2 | 4 / 0.076 | 4 / 0.076 |
| #8 彪形勇將 | 3 | 14 / 0.017 | 14 / 0.017 |

Overrated Top-2 review: #2 博愛先鋒 (actual 4, p=0.246).
Pre-race signal review: #1 包裝明將: stability 71.2 (+17.0 vs field), class_advantage 74.1 (+9.6 vs field)；#5 祥勝鷹駒: stability 61.0 (+6.8 vs field), trainer_signal 75.8 (+6.2 vs field)；#8 彪形勇將: no ≥3-point above-field Matrix dimension.
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-21 R4 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #2 超和平 | 1 | 5 / 0.061 | 5 / 0.061 |
| #3 鋁神 | 2 | 1 / 0.201 | 1 / 0.201 |
| #11 馬鳳凰 | 3 | 10 / 0.050 | 10 / 0.050 |

Overrated Top-2 review: #7 熱氣球 (actual 10, p=0.173).
Pre-race signal review: #2 超和平: form_line 92.0 (+9.9 vs field), stability 59.8 (+5.3 vs field)；#3 鋁神: sectional 72.2 (+13.3 vs field), trainer_signal 80.3 (+12.1 vs field)；#11 馬鳳凰: class_advantage 70.8 (+8.7 vs field), horse_health 72.0 (+4.4 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-21 R5 — model Top-2 hits 0, Matrix 0

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1600m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #3 逍遙騎士 | 1 | 3 / 0.131 | 3 / 0.131 |
| #4 包裝戰仕 | 2 | 11 / 0.036 | 11 / 0.036 |
| #12 好運年 | 3 | 5 / 0.084 | 5 / 0.084 |

Overrated Top-2 review: #2 深心星 (actual 5, p=0.215)；#10 家傳之寶 (actual 4, p=0.146).
Pre-race signal review: #3 逍遙騎士: stability 67.6 (+13.3 vs field), race_shape 71.9 (+12.0 vs field)；#4 包裝戰仕: trainer_signal 82.5 (+11.0 vs field)；#12 好運年: stability 64.5 (+10.2 vs field), form_line 96.0 (+6.2 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-27 R2 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1200m, Class 5.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #12 朗日雪峰 | 1 | 1 / 0.159 | 1 / 0.159 |
| #1 新力驕 | 2 | 9 / 0.058 | 9 / 0.058 |
| #2 鄉村樂韻 | 3 | 3 / 0.115 | 3 / 0.115 |

Overrated Top-2 review: #3 本能 (actual 14, p=0.115).
Pre-race signal review: #12 朗日雪峰: trainer_signal 82.8 (+11.2 vs field), race_shape 71.3 (+9.9 vs field)；#1 新力驕: sectional 65.6 (+6.1 vs field), trainer_signal 75.8 (+4.2 vs field)；#2 鄉村樂韻: stability 66.0 (+10.4 vs field), sectional 66.5 (+6.9 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-27 R3 — model Top-2 hits 0, Matrix 0

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #2 正極 | 1 | 5 / 0.097 | 5 / 0.097 |
| #5 千杯敬典 | 2 | 7 / 0.068 | 7 / 0.068 |
| #8 合夥智能 | 3 | 9 / 0.047 | 9 / 0.047 |

Overrated Top-2 review: #10 小魔怪 (actual 7, p=0.134)；#11 嘉應光彩 (actual 5, p=0.121).
Pre-race signal review: #2 正極: trainer_signal 82.5 (+13.1 vs field), form_line 96.0 (+9.7 vs field)；#5 千杯敬典: form_line 96.0 (+9.7 vs field), class_advantage 72.3 (+5.2 vs field)；#8 合夥智能: stability 59.8 (+6.7 vs field).
Cause assessment: available pre-race Matrix signals did not place enough contenders in the competitive tier.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-27 R5 — model Top-2 hits 0, Matrix 0

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, AWT, 1650m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #10 午夜快車 | 1 | 5 / 0.070 | 5 / 0.070 |
| #12 林寶精神 | 2 | 11 / 0.047 | 11 / 0.047 |
| #4 超加加 | 3 | 3 / 0.099 | 3 / 0.099 |

Overrated Top-2 review: #2 奮鬥心 (actual 5, p=0.165)；#5 精彩動力 (actual 6, p=0.119).
Pre-race signal review: #10 午夜快車: stability 58.5 (+3.9 vs field)；#12 林寶精神: horse_health 73.8 (+4.4 vs field), class_advantage 72.3 (+4.3 vs field)；#4 超加加: race_shape 72.6 (+12.7 vs field), stability 61.5 (+7.0 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-27 R6 — model Top-2 hits 0, Matrix 0

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #8 嘉應駿馬 | 1 | 3 / 0.085 | 3 / 0.085 |
| #4 老鼠斑 | 2 | 9 / 0.058 | 9 / 0.058 |
| #1 怡昌光輝 | 3 | 5 / 0.079 | 5 / 0.079 |

Overrated Top-2 review: #3 風采人生 (actual 10, p=0.202)；#10 快樂高球 (actual 5, p=0.104).
Pre-race signal review: #8 嘉應駿馬: trainer_signal 79.2 (+7.9 vs field), stability 60.8 (+4.1 vs field)；#4 老鼠斑: trainer_signal 80.5 (+9.1 vs field), sectional 64.4 (+3.5 vs field)；#1 怡昌光輝: race_shape 70.1 (+9.7 vs field), trainer_signal 78.2 (+6.9 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-27 R8 — model Top-2 hits 0, Matrix 0

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1000m, Class 1.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #4 顏色之皇 | 1 | 9 / 0.065 | 9 / 0.065 |
| #7 魔術控制 | 2 | 3 / 0.109 | 3 / 0.109 |
| #3 天天同樂 | 3 | 4 / 0.104 | 4 / 0.104 |

Overrated Top-2 review: #8 勇敢巨星 (actual 11, p=0.163)；#2 星際快車 (actual 5, p=0.136).
Pre-race signal review: #4 顏色之皇: class_advantage 75.1 (+3.7 vs field)；#7 魔術控制: stability 65.7 (+4.2 vs field), trainer_signal 72.8 (+4.1 vs field)；#3 天天同樂: stability 69.1 (+7.7 vs field), trainer_signal 74.5 (+5.8 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-27 R9 — model Top-2 hits 1, Matrix 1

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **normal-result cohort**. Venue 沙田, AWT, 1650m, Class 3.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #1 精英雄心 | 1 | 2 / 0.123 | 2 / 0.123 |
| #14 正義波 | 2 | 11 / 0.049 | 11 / 0.049 |
| #12 都靈福星 | 3 | 8 / 0.061 | 8 / 0.061 |

Overrated Top-2 review: #8 自動自覺 (actual 5, p=0.177).
Pre-race signal review: #1 精英雄心: race_shape 71.0 (+10.0 vs field), trainer_signal 78.2 (+8.0 vs field)；#14 正義波: no ≥3-point above-field Matrix dimension；#12 都靈福星: form_line 96.0 (+9.8 vs field), race_shape 67.0 (+6.0 vs field).
Cause assessment: available pre-race Matrix signals did not place enough contenders in the competitive tier.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-07-01 R2 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1400m, Class 5.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #2 天比高 | 1 | 3 / 0.103 | 3 / 0.103 |
| #13 海洋帝君 | 2 | 5 / 0.090 | 5 / 0.090 |
| #4 劍無情 | 3 | 1 / 0.202 | 1 / 0.202 |

Overrated Top-2 review: #1 勇敢孖寶 (actual 12, p=0.107).
Pre-race signal review: #2 天比高: stability 63.5 (+12.1 vs field), sectional 60.9 (+8.0 vs field)；#13 海洋帝君: race_shape 67.6 (+8.3 vs field), sectional 59.9 (+7.0 vs field)；#4 劍無情: race_shape 71.5 (+12.2 vs field), stability 62.0 (+10.5 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-07-01 R4 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1000m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #2 拉合爾 | 1 | 2 / 0.156 | 2 / 0.156 |
| #3 凝聚美麗 | 2 | 5 / 0.073 | 5 / 0.073 |
| #7 赤兔再世 | 3 | 4 / 0.074 | 4 / 0.074 |

Overrated Top-2 review: #13 天天更好 (actual 10, p=0.213).
Pre-race signal review: #2 拉合爾: form_line 96.0 (+18.8 vs field), sectional 72.4 (+12.2 vs field)；#3 凝聚美麗: form_line 96.0 (+18.8 vs field), class_advantage 74.1 (+8.8 vs field)；#7 赤兔再世: trainer_signal 77.2 (+8.1 vs field), race_shape 69.6 (+6.7 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-07-01 R7 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1000m, Class 3.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #6 團結勇士 | 1 | 7 / 0.079 | 7 / 0.079 |
| #12 幸運糖 | 2 | 1 / 0.132 | 1 / 0.132 |
| #2 會長之寶 | 3 | 3 / 0.114 | 3 / 0.114 |

Overrated Top-2 review: #5 精彩福星 (actual 4, p=0.123).
Pre-race signal review: #6 團結勇士: stability 61.0 (+7.7 vs field), class_advantage 74.1 (+6.5 vs field)；#12 幸運糖: stability 72.6 (+19.3 vs field), sectional 69.8 (+7.9 vs field)；#2 會長之寶: stability 65.4 (+12.1 vs field), class_advantage 74.1 (+6.5 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-07-01 R8 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1400m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #3 嵐臣 | 1 | 2 / 0.132 | 2 / 0.132 |
| #4 美麗大獎 | 2 | 3 / 0.105 | 3 / 0.105 |
| #7 龍城強將 | 3 | 8 / 0.058 | 8 / 0.058 |

Overrated Top-2 review: #10 挺秀弘利 (actual 5, p=0.170).
Pre-race signal review: #3 嵐臣: stability 72.7 (+18.3 vs field), form_line 96.0 (+13.2 vs field)；#4 美麗大獎: race_shape 70.2 (+9.6 vs field), trainer_signal 78.3 (+9.0 vs field)；#7 龍城強將: class_advantage 74.1 (+9.4 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-07-01 R9 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1600m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #8 旌採 | 1 | 1 / 0.188 | 1 / 0.188 |
| #11 幸運威龍 | 2 | 8 / 0.061 | 8 / 0.061 |
| #12 君達得 | 3 | 4 / 0.103 | 4 / 0.103 |

Overrated Top-2 review: #13 富裕君子 (actual 8, p=0.121).
Pre-race signal review: #8 旌採: sectional 75.0 (+15.5 vs field), trainer_signal 80.5 (+9.7 vs field)；#11 幸運威龍: form_line 96.0 (+9.2 vs field), trainer_signal 76.7 (+5.9 vs field)；#12 君達得: race_shape 70.6 (+11.3 vs field), class_advantage 75.6 (+7.1 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-07-04 R4 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1200m, Class 2.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #4 扶搖勢勁 | 1 | 1 / 0.201 | 1 / 0.201 |
| #6 巴基之勝 | 2 | 5 / 0.104 | 5 / 0.104 |
| #3 競駿輝煌 | 3 | 4 / 0.157 | 4 / 0.157 |

Overrated Top-2 review: #5 興馳千里 (actual 6, p=0.192).
Pre-race signal review: #4 扶搖勢勁: stability 71.9 (+9.6 vs field), trainer_signal 78.2 (+5.3 vs field)；#6 巴基之勝: form_line 92.0 (+11.0 vs field), class_advantage 74.1 (+4.6 vs field)；#3 競駿輝煌: trainer_signal 87.0 (+14.0 vs field), form_line 84.0 (+3.0 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-07-04 R6 — model Top-2 hits 1, Matrix 1

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **normal-result cohort**. Venue 沙田, AWT, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #7 致力之城 | 1 | 2 / 0.176 | 2 / 0.176 |
| #6 砂漿麒星 | 2 | 7 / 0.057 | 7 / 0.057 |
| #11 瑤瑤日上 | 3 | 8 / 0.052 | 8 / 0.052 |

Overrated Top-2 review: #1 葳莉非凡 (actual 11, p=0.222).
Pre-race signal review: #7 致力之城: sectional 69.8 (+10.4 vs field), stability 71.0 (+8.5 vs field)；#6 砂漿麒星: sectional 66.5 (+7.2 vs field), form_line 86.0 (+6.1 vs field)；#11 瑤瑤日上: race_shape 69.8 (+8.6 vs field), form_line 84.0 (+4.1 vs field).
Cause assessment: available pre-race Matrix signals did not place enough contenders in the competitive tier.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-07-04 R10 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1200m, Class 3.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #7 實力股 | 1 | 5 / 0.070 | 5 / 0.070 |
| #6 巴閉精 | 2 | 2 / 0.256 | 2 / 0.256 |
| #12 辣得準 | 3 | 3 / 0.102 | 3 / 0.102 |

Overrated Top-2 review: #1 精彩駿將 (actual 4, p=0.261).
Pre-race signal review: #7 實力股: race_shape 68.2 (+7.8 vs field), trainer_signal 76.2 (+5.9 vs field)；#6 巴閉精: stability 81.2 (+20.9 vs field), trainer_signal 87.0 (+16.6 vs field)；#12 辣得準: class_advantage 75.6 (+8.8 vs field), trainer_signal 78.3 (+7.9 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-07-08 R1 — model Top-2 hits 1, Matrix 1

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **normal-result cohort**. Venue 跑馬地, Turf, 1000m, Class 5.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #3 萬眾開心 | 1 | 1 / 0.196 | 1 / 0.196 |
| #1 鄉村樂韻 | 2 | 8 / 0.069 | 8 / 0.069 |
| #5 洛河 | 3 | 6 / 0.077 | 6 / 0.077 |

Overrated Top-2 review: #12 天火同德 (actual 8, p=0.140).
Pre-race signal review: #3 萬眾開心: race_shape 75.0 (+12.8 vs field), form_line 96.0 (+11.8 vs field)；#1 鄉村樂韻: stability 67.3 (+12.0 vs field), sectional 70.1 (+9.6 vs field)；#5 洛河: no ≥3-point above-field Matrix dimension.
Cause assessment: available pre-race Matrix signals did not place enough contenders in the competitive tier.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-07-08 R2 — model Top-2 hits 0, Matrix 0

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 跑馬地, Turf, 1650m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #1 暴風之子 | 1 | 5 / 0.096 | 5 / 0.096 |
| #6 贏玥 | 2 | 7 / 0.053 | 7 / 0.053 |
| #8 越駿聯歡 | 3 | 4 / 0.098 | 4 / 0.098 |

Overrated Top-2 review: #2 川河帥駒 (actual 9, p=0.197)；#9 得意佳作 (actual 10, p=0.162).
Pre-race signal review: #1 暴風之子: sectional 65.5 (+6.9 vs field), stability 60.0 (+6.2 vs field)；#6 贏玥: stability 64.9 (+11.1 vs field), sectional 65.9 (+7.2 vs field)；#8 越駿聯歡: race_shape 71.0 (+9.0 vs field), sectional 66.1 (+7.5 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-07-08 R3 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 跑馬地, Turf, 1000m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #11 福進 | 1 | 3 / 0.145 | 3 / 0.145 |
| #4 美麗登場 | 2 | 4 / 0.110 | 4 / 0.110 |
| #8 天火同人 | 3 | 2 / 0.161 | 2 / 0.161 |

Overrated Top-2 review: #1 鴻圖新星 (actual 4, p=0.194).
Pre-race signal review: #11 福進: trainer_signal 84.8 (+11.7 vs field), sectional 64.4 (+8.5 vs field)；#4 美麗登場: stability 70.7 (+18.7 vs field), trainer_signal 87.0 (+13.9 vs field)；#8 天火同人: stability 64.7 (+12.6 vs field), sectional 67.7 (+11.9 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-07-08 R5 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 跑馬地, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #9 至合拍 | 1 | 1 / 0.165 | 1 / 0.165 |
| #2 路路勁 | 2 | 6 / 0.082 | 6 / 0.082 |
| #12 頑童 | 3 | 5 / 0.083 | 5 / 0.083 |

Overrated Top-2 review: #6 勝多多 (actual 5, p=0.120).
Pre-race signal review: #9 至合拍: race_shape 75.8 (+13.6 vs field), sectional 70.6 (+6.9 vs field)；#2 路路勁: form_line 96.0 (+11.2 vs field), race_shape 67.0 (+4.8 vs field)；#12 頑童: sectional 69.1 (+5.4 vs field), class_advantage 67.0 (+3.9 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-07-08 R7 — model Top-2 hits 0, Matrix 0

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 跑馬地, Turf, 1000m, Class 3.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #8 舞林寶典 | 1 | 10 / 0.040 | 10 / 0.040 |
| #1 燭光晚餐 | 2 | 4 / 0.092 | 4 / 0.092 |
| #3 品德寶寶 | 3 | 5 / 0.086 | 5 / 0.086 |

Overrated Top-2 review: #2 連連幸運 (actual 9, p=0.203)；#5 加州本事 (actual 5, p=0.158).
Pre-race signal review: #8 舞林寶典: trainer_signal 84.8 (+11.2 vs field), form_line 89.0 (+5.9 vs field)；#1 燭光晚餐: stability 70.4 (+11.4 vs field), race_shape 66.8 (+5.3 vs field)；#3 品德寶寶: stability 73.4 (+14.3 vs field), trainer_signal 87.0 (+13.4 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-07-12 R1 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1800m, Class 5.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #1 特別美麗 | 1 | 6 / 0.079 | 6 / 0.079 |
| #11 龍又生 | 2 | 2 / 0.107 | 2 / 0.107 |
| #2 光輝歲月 | 3 | 4 / 0.083 | 4 / 0.083 |

Overrated Top-2 review: #4 連連好運 (actual 5, p=0.159).
Pre-race signal review: #1 特別美麗: sectional 60.4 (+7.3 vs field), stability 59.4 (+6.8 vs field)；#11 龍又生: stability 65.0 (+12.4 vs field), class_advantage 70.3 (+8.2 vs field)；#2 光輝歲月: race_shape 68.0 (+7.4 vs field), stability 57.6 (+5.1 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-07-12 R2 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1400m, Class 5.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #7 東方寶寶 | 1 | 1 / 0.161 | 1 / 0.161 |
| #6 籐王駒 | 2 | 12 / 0.035 | 12 / 0.035 |
| #11 海洋帝君 | 3 | 3 / 0.125 | 3 / 0.125 |

Overrated Top-2 review: #10 星之願 (actual 4, p=0.125).
Pre-race signal review: #7 東方寶寶: stability 72.9 (+18.0 vs field), sectional 69.8 (+10.4 vs field)；#6 籐王駒: no ≥3-point above-field Matrix dimension；#11 海洋帝君: stability 63.5 (+8.6 vs field), race_shape 68.3 (+8.3 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-07-12 R3 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1400m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #6 手機錶能 | 1 | 2 / 0.159 | 2 / 0.159 |
| #9 嘉應駿昇 | 2 | 12 / 0.030 | 12 / 0.030 |
| #10 遨遊波士 | 3 | 3 / 0.139 | 3 / 0.139 |

Overrated Top-2 review: #13 勤德皆備 (actual 8, p=0.185).
Pre-race signal review: #6 手機錶能: sectional 70.0 (+14.0 vs field), stability 61.9 (+9.6 vs field)；#9 嘉應駿昇: form_line 96.0 (+11.1 vs field)；#10 遨遊波士: stability 64.4 (+12.0 vs field), form_line 96.0 (+11.1 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-07-12 R5 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #10 綠色鐵驥 | 1 | 11 / 0.034 | 11 / 0.034 |
| #12 快樂高球 | 2 | 2 / 0.134 | 2 / 0.134 |
| #1 渡月橋 | 3 | 4 / 0.117 | 4 / 0.117 |

Overrated Top-2 review: #3 嘉應駿馬 (actual 6, p=0.148).
Pre-race signal review: #10 綠色鐵驥: no ≥3-point above-field Matrix dimension；#12 快樂高球: stability 69.5 (+15.8 vs field), class_advantage 70.3 (+9.8 vs field)；#1 渡月橋: trainer_signal 87.2 (+14.6 vs field), form_line 96.0 (+9.9 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-07-12 R10 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1600m, Class 3.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #13 名揚四海 | 1 | 6 / 0.077 | 6 / 0.077 |
| #4 一生好彩 | 2 | 2 / 0.117 | 2 / 0.117 |
| #12 大回報 | 3 | 3 / 0.096 | 3 / 0.096 |

Overrated Top-2 review: #7 超勁赤兔 (actual 7, p=0.134).
Pre-race signal review: #13 名揚四海: sectional 73.4 (+10.7 vs field)；#4 一生好彩: race_shape 72.2 (+11.5 vs field), sectional 66.6 (+4.0 vs field)；#12 大回報: stability 83.4 (+18.0 vs field), class_advantage 70.3 (+5.1 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-05-09 R1 — model Top-2 hits 0, Matrix 0

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, unknownm, Unknown.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #5 鵲橋飛昇 | 1 | 8 / 0.067 | 8 / 0.067 |
| #2 銳行星 | 2 | 3 / 0.123 | 3 / 0.123 |
| #6 永福 | 3 | 7 / 0.072 | 7 / 0.072 |

Overrated Top-2 review: #1 全能勇士 (actual 5, p=0.169)；#7 極歡欣 (actual 4, p=0.138).
Pre-race signal review: #5 鵲橋飛昇: race_shape 75.0 (+9.5 vs field)；#2 銳行星: trainer_signal 84.8 (+11.7 vs field)；#6 永福: no ≥3-point above-field Matrix dimension.
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #5 鵲橋飛昇 actual 1／odds 49

## 2026-05-09 R4 — model Top-2 hits 1, Matrix 1

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1000m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #10 一舖掂晒 | 1 | 13 / 0.014 | 13 / 0.014 |
| #4 支付之父 | 2 | 2 / 0.134 | 2 / 0.134 |
| #11 致力之城 | 3 | 10 / 0.022 | 10 / 0.022 |

Overrated Top-2 review: #6 鴻圖新星 (actual 12, p=0.237).
Pre-race signal review: #10 一舖掂晒: no ≥3-point above-field Matrix dimension；#4 支付之父: stability 77.9 (+19.4 vs field), race_shape 74.2 (+14.8 vs field)；#11 致力之城: trainer_signal 77.0 (+6.4 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #10 一舖掂晒 actual 1／odds 70

## 2026-05-09 R5 — model Top-2 hits 0, Matrix 0

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #4 君子 | 1 | 12 / 0.026 | 12 / 0.026 |
| #6 老鼠斑 | 2 | 10 / 0.035 | 10 / 0.035 |
| #2 心雄雄 | 3 | 3 / 0.117 | 3 / 0.117 |

Overrated Top-2 review: #9 星辰千帥 (actual 5, p=0.221)；#3 輝灑自如 (actual 9, p=0.158).
Pre-race signal review: #4 君子: no ≥3-point above-field Matrix dimension；#6 老鼠斑: stability 61.2 (+8.4 vs field)；#2 心雄雄: race_shape 74.2 (+11.4 vs field), form_line 84.0 (+4.8 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #4 君子 actual 1／odds 158 | major_incident: #3 輝灑自如: 9 3 輝灑自如 (L281) 見習騎師袁幸堯表示，坐騎在閘內煩躁不安，儘管能夠領放，但在該位置下走勢欠佳。她又說，坐騎於直路上對催策毫無反應，表現令人失望。練馬師姚本輝表示，此駒於是賽前的表現令他滿意。他說，他認為此駒未能適應「好至黏地」的場地狀況，尤其是牠陣上走勢欠佳，數度將頭低俯。賽後立即接受獸醫檢查，內窺鏡檢查顯示此駒的氣管內有很多痰。「輝灑自如」上

## 2026-05-09 R6 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1400m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #6 龍傲綾羅 | 1 | 3 / 0.112 | 3 / 0.112 |
| #7 文明福星 | 2 | 1 / 0.133 | 1 / 0.133 |
| #3 將傲 | 3 | 10 / 0.042 | 10 / 0.042 |

Overrated Top-2 review: #9 開心旺財 (actual 8, p=0.117).
Pre-race signal review: #6 龍傲綾羅: trainer_signal 87.0 (+17.3 vs field), stability 65.2 (+11.5 vs field)；#7 文明福星: race_shape 82.0 (+21.6 vs field), stability 64.7 (+11.0 vs field)；#3 將傲: race_shape 64.2 (+3.8 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: interference: #9 開心旺財: 8 9 開心旺財 (L045) 接近三百五十米處時向內斜跑，與「龍傲綾羅」互相觸碰。三百五十米處至二百五十米處之間在靠近「笑必勝」處於窘境之際受困而未能望空。

## 2026-05-09 R7 — model Top-2 hits 0, Matrix 0

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1600m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #13 金鑽精靈 | 1 | 10 / 0.051 | 10 / 0.051 |
| #8 好運年 | 2 | 8 / 0.066 | 8 / 0.066 |
| #11 君達得 | 3 | 12 / 0.031 | 12 / 0.031 |

Overrated Top-2 review: #1 威武年代 (actual 14, p=0.138)；#5 大千雄心 (actual 9, p=0.122).
Pre-race signal review: #13 金鑽精靈: stability 74.3 (+16.7 vs field), class_advantage 75.6 (+9.1 vs field)；#8 好運年: race_shape 76.6 (+17.6 vs field), form_line 96.0 (+6.3 vs field)；#11 君達得: class_advantage 75.6 (+9.1 vs field), form_line 96.0 (+6.3 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: major_incident: #1 威武年代: 14 1 威武年代 (J451) 何澤堯表示，坐騎在入直路後受催策並顯著轉弱，但他未能就坐騎令人失望的表現提供任何解釋。賽後立即接受獸醫檢查，並無發現任何明顯異常之處。小組認為與近仗相比，「威武年代」今仗的表現令人失望。「威武年代」必須試閘及格，並且通過獸醫檢驗後，才可再次出賽。

## 2026-05-13 R4 — model Top-2 hits 0, Matrix 0

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 跑馬地, Turf, 1650m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #4 上浦福旺 | 1 | 12 / 0.026 | 12 / 0.026 |
| #10 滿洛城 | 2 | 3 / 0.099 | 3 / 0.099 |
| #11 獎星 | 3 | 5 / 0.092 | 5 / 0.092 |

Overrated Top-2 review: #3 睿智多寶 (actual 9, p=0.191)；#5 大千氣象 (actual 5, p=0.145).
Pre-race signal review: #4 上浦福旺: no ≥3-point above-field Matrix dimension；#10 滿洛城: race_shape 77.2 (+12.5 vs field), stability 66.3 (+8.2 vs field)；#11 獎星: class_advantage 72.3 (+4.2 vs field), horse_health 73.2 (+4.0 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: interference: #1 勁進駒: 12 1 勁進駒 (J384) 起步後不久發生碰撞。接近三百五十米處時在「滿洛城」與開始墮退的「翠湖烈風」之間未能望空之際大力勒避。被查詢時，潘頓表示，他獲指示讓坐騎上前及居於預期領放馬「睿智多寶」外側。他說，他催策坐騎上前及將坐騎置於「翠湖烈風」外側，其後等待「翠湖烈風」佔取「睿智多寶」之後有遮擋的位置，因為他察覺到策騎「翠湖烈風」的見習騎師黃寶妮望向她的

## 2026-05-13 R7 — model Top-2 hits 0, Matrix 0

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 跑馬地, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #11 驕陽雄心 | 1 | 6 / 0.067 | 6 / 0.067 |
| #3 縱橫天下 | 2 | 8 / 0.060 | 8 / 0.060 |
| #1 競駿非凡 | 3 | 10 / 0.047 | 10 / 0.047 |

Overrated Top-2 review: #6 銳目 (actual 12, p=0.147)；#12 勝在當下 (actual 4, p=0.144).
Pre-race signal review: #11 驕陽雄心: no ≥3-point above-field Matrix dimension；#3 縱橫天下: race_shape 71.8 (+9.9 vs field)；#1 競駿非凡: trainer_signal 75.0 (+3.2 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #3 縱橫天下 actual 2／odds 36 | major_incident: #6 銳目: 12 6 銳目 (L068) 接近六百米處時與「福進」互相觸碰，當時「福進」在搶口之際向外斜跑。潘頓表示，他於早段催策坐騎以嘗試佔取前列位置。他說，坐騎今仗展現的前速未如上仗，因而居於較賽前部署為後的位置。他說，坐騎經驗仍然相對較淺，中段沿途未能適應在其他馬匹之間競跑，其後在直路上墮退。賽後立即接受獸醫檢查，並無發現任何明顯異常之處。「銳目」上仗勝出，小組認

## 2026-05-13 R9 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 跑馬地, Turf, 1650m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #9 包裝福星 | 1 | 4 / 0.111 | 4 / 0.111 |
| #4 太陽勇士 | 2 | 2 / 0.127 | 2 / 0.127 |
| #10 一起美麗 | 3 | 8 / 0.081 | 8 / 0.081 |

Overrated Top-2 review: #8 銀亮奔騰 (actual 4, p=0.138).
Pre-race signal review: #9 包裝福星: race_shape 78.0 (+15.3 vs field), stability 65.3 (+4.4 vs field)；#4 太陽勇士: trainer_signal 83.7 (+10.8 vs field)；#10 一起美麗: stability 74.7 (+13.7 vs field), trainer_signal 77.2 (+4.3 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: interference: #1 勁速威龍: 8 1 勁速威龍 (H380) 自外檔出閘僅屬一般，於早段在馬群之後切入。末段開始以佳勢衝刺之際在「銀亮奔騰」與「非惟僥倖」之間未能望空，因而於最後五十米未能被力策。賽後立即接受獸醫檢查，並無發現任何明顯異常之處。

## 2026-05-17 R1 — model Top-2 hits 0, Matrix 0

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1800m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #6 齊歡最樂 | 1 | 5 / 0.095 | 5 / 0.095 |
| #10 捷足奔馳 | 2 | 6 / 0.064 | 6 / 0.064 |
| #7 香港精神 | 3 | 8 / 0.041 | 8 / 0.041 |

Overrated Top-2 review: #8 開心三多 (actual 6, p=0.146)；#9 幸運同行 (actual 8, p=0.142).
Pre-race signal review: #6 齊歡最樂: race_shape 71.0 (+11.6 vs field), trainer_signal 72.2 (+4.3 vs field)；#10 捷足奔馳: trainer_signal 71.7 (+3.8 vs field)；#7 香港精神: class_advantage 74.1 (+7.3 vs field), stability 59.2 (+4.0 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #7 香港精神 actual 3／odds 50

## 2026-05-17 R4 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #11 小魔怪 | 1 | 7 / 0.065 | 7 / 0.065 |
| #10 天天更好 | 2 | 1 / 0.186 | 1 / 0.186 |
| #8 你知我寶 | 3 | 4 / 0.101 | 4 / 0.101 |

Overrated Top-2 review: #1 禾道豐 (actual 4, p=0.168).
Pre-race signal review: #11 小魔怪: class_advantage 72.3 (+8.5 vs field), sectional 66.5 (+5.0 vs field)；#10 天天更好: stability 74.2 (+17.4 vs field), form_line 95.0 (+11.3 vs field)；#8 你知我寶: trainer_signal 78.2 (+7.1 vs field), race_shape 67.8 (+6.5 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: interference: #1 禾道豐: 4 1 禾道豐 (L264) 躍出時在「星光大道」與略為向外斜跑的「你知我寶」之間受擠迫之際失去平衡。四百五十米處至三百五十米處之間受困而未能望空。賽後須抽取樣本檢驗。

## 2026-05-17 R6 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #10 傑出雷霆 | 1 | 3 / 0.147 | 3 / 0.147 |
| #11 有備而戰 | 2 | 11 / 0.032 | 11 / 0.032 |
| #2 星月飛雲 | 3 | 2 / 0.151 | 2 / 0.151 |

Overrated Top-2 review: #3 健康快車 (actual 5, p=0.165).
Pre-race signal review: #10 傑出雷霆: stability 71.1 (+14.3 vs field), form_line 96.0 (+11.2 vs field)；#11 有備而戰: form_line 94.0 (+9.2 vs field)；#2 星月飛雲: form_line 96.0 (+11.2 vs field), trainer_signal 81.5 (+8.5 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #11 有備而戰 actual 2／odds 60

## 2026-05-17 R10 — model Top-2 hits 1, Matrix 1

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1400m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #10 臻至辰 | 1 | 8 / 0.066 | 8 / 0.066 |
| #8 超輕鬆 | 2 | 2 / 0.108 | 2 / 0.108 |
| #6 三甲之星 | 3 | 6 / 0.079 | 6 / 0.079 |

Overrated Top-2 review: #5 安泰 (actual 9, p=0.170).
Pre-race signal review: #10 臻至辰: form_line 96.0 (+10.8 vs field), stability 62.6 (+9.8 vs field)；#8 超輕鬆: form_line 96.0 (+10.8 vs field), stability 59.9 (+7.1 vs field)；#6 三甲之星: sectional 69.9 (+13.1 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: major_incident: #11 正本良心: 14 11 正本良心 (L382) 於起步點被發現口內有血，其後接受獸醫檢查，獸醫認為此駒適宜出賽。在閘內煩躁不安，導致右後腿一度擱在閘廂內，其後被牽出閘廂及再度接受獸醫檢查，獸醫認為此駒適宜出賽。大部分途程在沒有遮擋下走外疊。莫雷拉表示，坐騎於早段及中段沿途走勢良佳，但在直路上受催策時轉弱。賽後立即接受獸醫檢查，並無發現任何明顯異常之處。「正本良心」包尾大

## 2026-05-20 R5 — model Top-2 hits 1, Matrix 1

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 跑馬地, Turf, 1000m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #2 財將 | 1 | 7 / 0.081 | 7 / 0.081 |
| #7 鴻圖新星 | 2 | 2 / 0.140 | 2 / 0.140 |
| #5 紅錢到 | 3 | 10 / 0.042 | 10 / 0.042 |

Overrated Top-2 review: #4 美麗登場 (actual 7, p=0.154).
Pre-race signal review: #2 財將: stability 87.9 (+28.2 vs field), race_shape 64.2 (+3.9 vs field)；#7 鴻圖新星: trainer_signal 85.9 (+15.0 vs field), sectional 63.4 (+3.8 vs field)；#5 紅錢到: sectional 66.0 (+6.5 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #5 紅錢到 actual 3／odds 33

## 2026-05-20 R9 — model Top-2 hits 0, Matrix 0

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 跑馬地, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #8 維港智能 | 1 | 12 / 0.019 | 12 / 0.019 |
| #7 扶搖勢勁 | 2 | 5 / 0.096 | 5 / 0.096 |
| #1 天天同樂 | 3 | 6 / 0.073 | 6 / 0.073 |

Overrated Top-2 review: #9 俏眼光 (actual 12, p=0.175)；#4 信心星 (actual 6, p=0.140).
Pre-race signal review: #8 維港智能: no ≥3-point above-field Matrix dimension；#7 扶搖勢勁: stability 81.5 (+13.3 vs field), form_line 94.0 (+6.1 vs field)；#1 天天同樂: race_shape 66.8 (+4.8 vs field), sectional 70.0 (+3.6 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #8 維港智能 actual 1／odds 59 | major_incident: #9 俏眼光: 12 9 俏眼光 (L003) 田泰安表示，坐騎出閘僅屬一般，居後列競跑。他說，坐騎在直路上受催策時毫無反應，表現令人失望。練馬師蔡約翰表示，他認為此駒已屆歇暑休賽之時，將會安排此駒休息。賽後立即接受獸醫檢查，並無發現任何明顯異常之處。「俏眼光」上仗勝出，小組認為此駒今仗的表現令人失望。「俏眼光」必須試閘及格，並且通過獸醫檢驗後，才可再次出賽。

## 2026-05-24 R2 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1400m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #14 金快飛飛 | 1 | 3 / 0.099 | 3 / 0.099 |
| #1 包裝明將 | 2 | 6 / 0.084 | 6 / 0.084 |
| #2 嵐臣 | 3 | 2 / 0.105 | 2 / 0.105 |

Overrated Top-2 review: #10 隋我同來 (actual 10, p=0.145).
Pre-race signal review: #14 金快飛飛: stability 65.8 (+9.8 vs field), class_advantage 71.5 (+6.6 vs field)；#1 包裝明將: stability 68.4 (+12.4 vs field), class_advantage 71.6 (+6.7 vs field)；#2 嵐臣: stability 68.7 (+12.8 vs field), race_shape 70.5 (+9.3 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: interference: #11 華麗再贏: 5 11 華麗再贏 (L087) 在起步點重新裝上左前蹄的蹄鐵，其後接受獸醫檢查，獸醫認為此駒適宜出賽，賽事因而延遲開跑。起步後不久在「隋我同來」與外閃的「嵐臣」之間受擠迫。四百米處至一百五十米處之間受困而未能望空。

## 2026-05-24 R3 — model Top-2 hits 0, Matrix 0

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #1 錶之浩瀚 | 1 | 11 / 0.047 | 11 / 0.047 |
| #2 巧眼光 | 2 | 3 / 0.102 | 3 / 0.102 |
| #14 有你有我 | 3 | 5 / 0.086 | 5 / 0.086 |

Overrated Top-2 review: #4 老鼠斑 (actual 8, p=0.146)；#12 同喜 (actual 12, p=0.118).
Pre-race signal review: #1 錶之浩瀚: sectional 62.0 (+4.9 vs field), class_advantage 71.6 (+3.6 vs field)；#2 巧眼光: form_line 96.0 (+11.1 vs field), trainer_signal 80.5 (+10.3 vs field)；#14 有你有我: form_line 96.0 (+11.1 vs field), sectional 63.6 (+6.5 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #2 巧眼光 actual 2／odds 44 || #14 有你有我 actual 3／odds 41

## 2026-05-24 R4 — model Top-2 hits 1, Matrix 1

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #3 包裝天王 | 1 | 2 / 0.144 | 2 / 0.144 |
| #11 銀刺勇士 | 2 | 8 / 0.049 | 8 / 0.049 |
| #9 北極之錶 | 3 | 12 / 0.045 | 12 / 0.045 |

Overrated Top-2 review: #8 應龍飛影 (actual 11, p=0.167).
Pre-race signal review: #3 包裝天王: trainer_signal 84.7 (+14.0 vs field), stability 65.2 (+10.6 vs field)；#11 銀刺勇士: trainer_signal 84.8 (+14.1 vs field), class_advantage 70.8 (+5.0 vs field)；#9 北極之錶: race_shape 67.5 (+7.9 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #11 銀刺勇士 actual 2／odds 49 || #9 北極之錶 actual 3／odds 115

## 2026-05-24 R6 — model Top-2 hits 0, Matrix 0

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1400m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #5 仁仁有餘 | 1 | 3 / 0.113 | 3 / 0.113 |
| #8 馬上盈 | 2 | 6 / 0.072 | 6 / 0.072 |
| #9 共創歡欣 | 3 | 10 / 0.046 | 10 / 0.046 |

Overrated Top-2 review: #14 觀萬物 (actual 9, p=0.169)；#4 馬馳登 (actual 5, p=0.136).
Pre-race signal review: #5 仁仁有餘: trainer_signal 84.8 (+12.6 vs field), sectional 63.4 (+5.8 vs field)；#8 馬上盈: sectional 62.5 (+5.0 vs field), class_advantage 70.8 (+4.8 vs field)；#9 共創歡欣: trainer_signal 77.0 (+4.9 vs field), class_advantage 70.8 (+4.8 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: injury: #14 觀萬物: 9 14 觀萬物 (K101) 接近九百米處時收慢避開「方圓星」。潘頓表示，賽事早段及中段步速較標準時間為慢，不利坐騎發揮，坐騎因而在直路上難以追前。賽後立即接受獸醫檢查，發現此駒患有「喘鳴症」，而此駒過往也有此毛病報告。

## 2026-05-24 R7 — model Top-2 hits 0, Matrix 0

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1800m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #12 勁大威猛 | 1 | 7 / 0.082 | 7 / 0.082 |
| #13 勁好運 | 2 | 5 / 0.086 | 5 / 0.086 |
| #8 幸運派彩 | 3 | 13 / 0.033 | 13 / 0.033 |

Overrated Top-2 review: #3 平凡騎士 (actual 13, p=0.143)；#1 春風萬里 (actual 10, p=0.100).
Pre-race signal review: #12 勁大威猛: race_shape 70.1 (+9.7 vs field), form_line 96.0 (+6.1 vs field)；#13 勁好運: sectional 63.9 (+8.2 vs field), race_shape 67.7 (+7.3 vs field)；#8 幸運派彩: no ≥3-point above-field Matrix dimension.
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #13 勁好運 actual 2／odds 61 | major_incident: #2 友瑩光: 14 2 友瑩光 (K564) 起步後不久被「快路」碰撞後軀，因而失去平衡。潘頓表示，坐騎在直路上對催策毫無反應，他擔心坐騎有不妥，遂於接近三百米處時收慢坐騎。練馬師廖康銘表示，此駒於是賽前的表現令他滿意，他未能就此駒今仗的表現提供解釋。賽後立即接受獸醫檢查，並無發現任何明顯異常之處。包尾大敗而回，小組認為此駒的表現難以接受。「友瑩光」必須試閘及格，並且通過

## 2026-05-24 R8 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 2400m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #1 浪漫勇士 | 1 | 1 / 0.232 | 1 / 0.232 |
| #5 數字天文 | 2 | 4 / 0.109 | 4 / 0.109 |
| #2 大怪奇 | 3 | 9 / 0.056 | 9 / 0.056 |

Overrated Top-2 review: #9 浪漫戰神 (actual 4, p=0.150).
Pre-race signal review: #1 浪漫勇士: stability 85.5 (+16.6 vs field), trainer_signal 84.7 (+9.6 vs field)；#5 數字天文: form_line 96.0 (+9.3 vs field), sectional 67.6 (+3.6 vs field)；#2 大怪奇: race_shape 68.2 (+4.5 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #5 數字天文 actual 2／odds 40

## 2026-05-27 R1 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 跑馬地, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #9 本能 | 1 | 4 / 0.080 | 4 / 0.080 |
| #11 東方福寶 | 2 | 11 / 0.041 | 11 / 0.041 |
| #10 星之願 | 3 | 2 / 0.160 | 2 / 0.160 |

Overrated Top-2 review: #2 魅力星 (actual 10, p=0.221).
Pre-race signal review: #9 本能: race_shape 78.0 (+15.4 vs field), horse_health 69.8 (+3.1 vs field)；#11 東方福寶: horse_health 71.8 (+5.2 vs field), form_line 88.0 (+3.2 vs field)；#10 星之願: race_shape 76.0 (+13.4 vs field), trainer_signal 80.3 (+10.3 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: injury: #2 魅力星: 10 2 魅力星 (K052) 田泰安表示，坐騎在直路上衝刺僅屬一般，或未能適應「好至快地」的場地狀況。賽後立即接受獸醫檢查，發現此駒患有「喘鳴症」，而此駒過往也有此毛病報告。

## 2026-05-27 R2 — model Top-2 hits 0, Matrix 0

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 跑馬地, Turf, 2200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #7 捷足奔馳 | 1 | 5 / 0.108 | 5 / 0.108 |
| #8 幸運同行 | 2 | 4 / 0.117 | 4 / 0.117 |
| #9 美麗多盈 | 3 | 12 / 0.028 | 12 / 0.028 |

Overrated Top-2 review: #1 管之友 (actual 7, p=0.199)；#12 同寶寶 (actual 5, p=0.128).
Pre-race signal review: #7 捷足奔馳: stability 63.6 (+9.0 vs field), trainer_signal 71.7 (+5.2 vs field)；#8 幸運同行: trainer_signal 84.8 (+18.2 vs field), race_shape 66.0 (+3.5 vs field)；#9 美麗多盈: no ≥3-point above-field Matrix dimension.
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #9 美麗多盈 actual 3／odds 36

## 2026-05-27 R9 — model Top-2 hits 0, Matrix 0

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 跑馬地, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #1 小霸王 | 1 | 5 / 0.073 | 5 / 0.073 |
| #5 晶晶日上 | 2 | 7 / 0.071 | 7 / 0.071 |
| #12 椒椒醒 | 3 | 12 / 0.009 | 12 / 0.009 |

Overrated Top-2 review: #7 富心星 (actual 10, p=0.213)；#9 可靠大師 (actual 12, p=0.168).
Pre-race signal review: #1 小霸王: form_line 96.0 (+6.8 vs field), stability 63.8 (+5.3 vs field)；#5 晶晶日上: stability 66.5 (+8.0 vs field), form_line 96.0 (+6.8 vs field)；#12 椒椒醒: no ≥3-point above-field Matrix dimension.
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #12 椒椒醒 actual 3／odds 118 | major_incident: #7 富心星: 10 7 富心星 (K125) 莫雷拉表示，坐騎直路上在催策下毫無反應，走勢平平。賽後立即接受獸醫檢查，並無發現任何明顯異常之處。小組認為與近仗相比，「富心星」今仗的表現令人失望。「富心星」必須試閘及格，並且通過獸醫檢驗後，才可再次出賽。 || #9 可靠大師: 12 9 可靠大師 (K283) 接近三百米處時在墮退之際內閃，導致騎師潘頓須停止催策並修正坐騎。潘頓表示，坐騎中段在居「富心星」之後時過於搶口，不願穩定走勢。他說，坐騎因而在直路上未能以勁勢衝刺。賽後立即接受獸醫檢查，並無發現任何明顯異常之處。「可靠大師」上仗勝出，小組認為此駒今仗的表現令人失望。「可靠大師」必須試閘及格，並且通過獸醫檢驗後，才可再次出賽。

## 2026-06-03 R1 — model Top-2 hits 1, Matrix 1

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 跑馬地, Turf, 1650m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #3 富裕君子 | 1 | 1 / 0.268 | 1 / 0.268 |
| #12 不假外求 | 2 | 7 / 0.046 | 7 / 0.046 |
| #6 電訊驕陽 | 3 | 12 / 0.018 | 12 / 0.018 |

Overrated Top-2 review: #9 華美之威 (actual 5, p=0.162).
Pre-race signal review: #3 富裕君子: trainer_signal 87.0 (+20.1 vs field), race_shape 79.8 (+17.0 vs field)；#12 不假外求: horse_health 73.8 (+4.0 vs field)；#6 電訊驕陽: class_advantage 70.8 (+3.8 vs field), stability 56.6 (+3.2 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #12 不假外求 actual 2／odds 38

## 2026-06-03 R3 — model Top-2 hits 1, Matrix 1

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 跑馬地, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #7 博愛先鋒 | 1 | 2 / 0.135 | 2 / 0.135 |
| #12 有你有我 | 2 | 6 / 0.101 | 6 / 0.101 |
| #4 驕陽雄心 | 3 | 8 / 0.048 | 8 / 0.048 |

Overrated Top-2 review: #3 團長好 (actual 10, p=0.185).
Pre-race signal review: #7 博愛先鋒: stability 67.5 (+11.6 vs field), sectional 73.4 (+10.2 vs field)；#12 有你有我: trainer_signal 74.8 (+5.4 vs field), stability 60.8 (+4.9 vs field)；#4 驕陽雄心: stability 70.9 (+15.0 vs field), sectional 67.8 (+4.6 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: major_incident: #3 團長好: 10 3 團長好 (K515) 躍出時發生碰撞。莫雷拉未能就坐騎令人失望的表現提供任何解釋。練馬師方嘉柏告知小組，此駒自上仗後的表現令他滿意，他能提供的唯一解釋是賽事早段步速較標準時間略快，或不合此駒發揮。賽後立即接受獸醫檢查，發現此駒患有「喘鳴症」，而此駒過往也有此毛病報告。小組認為與近仗相比，「團長好」今仗的表現令人失望。「團長好」必須試閘及格，並且通過 | injury: #3 團長好: 10 3 團長好 (K515) 躍出時發生碰撞。莫雷拉未能就坐騎令人失望的表現提供任何解釋。練馬師方嘉柏告知小組，此駒自上仗後的表現令他滿意，他能提供的唯一解釋是賽事早段步速較標準時間略快，或不合此駒發揮。賽後立即接受獸醫檢查，發現此駒患有「喘鳴症」，而此駒過往也有此毛病報告。小組認為與近仗相比，「團長好」今仗的表現令人失望。「團長好」必須試閘及格，並且通過

## 2026-06-03 R4 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 跑馬地, Turf, 1650m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #5 先到先得 | 1 | 3 / 0.139 | 3 / 0.139 |
| #1 星願無限 | 2 | 11 / 0.029 | 11 / 0.029 |
| #9 獎星 | 3 | 2 / 0.181 | 2 / 0.181 |

Overrated Top-2 review: #10 時間寶 (actual 12, p=0.211).
Pre-race signal review: #5 先到先得: trainer_signal 84.8 (+14.1 vs field), stability 70.9 (+12.7 vs field)；#1 星願無限: race_shape 66.8 (+4.6 vs field)；#9 獎星: race_shape 78.8 (+16.6 vs field), form_line 96.0 (+7.2 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: major_incident: #10 時間寶: 12 10 時間寶 (H403) 潘頓表示，坐騎在領放下走勢暢順，但直路上對催策毫無反應及顯著轉弱。練馬師姚本輝告知小組，此駒自上仗於五月十三日出賽後的表現令他滿意，儘管此駒被發現心律不正常，但同時在領放下受追迫，不利發揮。賽後立即接受獸醫檢查，發現此駒心律不正常。「時間寶」必須試閘及格，並且通過獸醫檢驗後，才可再次出賽。賽後須抽取樣本檢驗。 | injury: #10 時間寶: 12 10 時間寶 (H403) 潘頓表示，坐騎在領放下走勢暢順，但直路上對催策毫無反應及顯著轉弱。練馬師姚本輝告知小組，此駒自上仗於五月十三日出賽後的表現令他滿意，儘管此駒被發現心律不正常，但同時在領放下受追迫，不利發揮。賽後立即接受獸醫檢查，發現此駒心律不正常。「時間寶」必須試閘及格，並且通過獸醫檢驗後，才可再次出賽。賽後須抽取樣本檢驗。

## 2026-06-03 R8 — model Top-2 hits 1, Matrix 1

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 跑馬地, Turf, 1800m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #6 銀亮奔騰 | 1 | 1 / 0.193 | 1 / 0.193 |
| #11 奔放 | 2 | 6 / 0.069 | 6 / 0.069 |
| #4 加州動員 | 3 | 11 / 0.027 | 11 / 0.027 |

Overrated Top-2 review: #7 一起美麗 (actual 6, p=0.164).
Pre-race signal review: #6 銀亮奔騰: sectional 68.4 (+12.0 vs field), race_shape 75.8 (+11.8 vs field)；#11 奔放: sectional 70.4 (+14.0 vs field), stability 78.8 (+13.8 vs field)；#4 加州動員: no ≥3-point above-field Matrix dimension.
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #4 加州動員 actual 3／odds 38

## 2026-06-07 R5 — model Top-2 hits 0, Matrix 0

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, AWT, 1800m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #14 飛躍星伴 | 1 | 4 / 0.090 | 4 / 0.090 |
| #1 開心宇宙 | 2 | 12 / 0.045 | 12 / 0.045 |
| #3 超加加 | 3 | 8 / 0.050 | 8 / 0.050 |

Overrated Top-2 review: #9 精明選擇 (actual 4, p=0.169)；#2 凱明神駒 (actual 13, p=0.162).
Pre-race signal review: #14 飛躍星伴: race_shape 71.0 (+11.1 vs field), sectional 63.6 (+7.1 vs field)；#1 開心宇宙: stability 63.9 (+5.4 vs field), class_advantage 67.8 (+3.2 vs field)；#3 超加加: stability 61.7 (+3.3 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #14 飛躍星伴 actual 1／odds 32

## 2026-06-07 R6 — model Top-2 hits 0, Matrix 0

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1600m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #7 部族高手 | 1 | 5 / 0.085 | 5 / 0.085 |
| #10 捷威 | 2 | 4 / 0.085 | 4 / 0.085 |
| #5 好運年 | 3 | 12 / 0.040 | 12 / 0.040 |

Overrated Top-2 review: #1 雙星報喜 (actual 11, p=0.132)；#6 金鑽精靈 (actual 6, p=0.118).
Pre-race signal review: #7 部族高手: race_shape 68.4 (+8.5 vs field)；#10 捷威: sectional 63.6 (+6.6 vs field), trainer_signal 72.8 (+4.7 vs field)；#5 好運年: sectional 60.8 (+3.9 vs field), stability 62.8 (+3.4 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: interference: #9 愛心波: 7 9 愛心波 (L006) 出閘僅屬一般。轉直路彎時受困而未能望空。最後一百米在靠近「金鑽精靈」時再度受困而未能望空。

## 2026-06-07 R11 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1400m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #7 超輕鬆 | 1 | 4 / 0.091 | 4 / 0.091 |
| #5 自動自覺 | 2 | 2 / 0.110 | 2 / 0.110 |
| #8 勁無限 | 3 | 5 / 0.091 | 5 / 0.091 |

Overrated Top-2 review: #3 一世美麗 (actual 7, p=0.162).
Pre-race signal review: #7 超輕鬆: stability 66.8 (+6.5 vs field), race_shape 65.8 (+6.0 vs field)；#5 自動自覺: stability 71.6 (+11.3 vs field), class_advantage 71.8 (+9.3 vs field)；#8 勁無限: trainer_signal 82.5 (+11.6 vs field), race_shape 66.7 (+6.8 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #8 勁無限 actual 3／odds 83

## 2026-06-13 R3 — model Top-2 hits 0, Matrix 0

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1400m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #12 賢者威楓 | 1 | 4 / 0.091 | 4 / 0.091 |
| #4 深心星 | 2 | 6 / 0.080 | 6 / 0.080 |
| #5 龍之悅 | 3 | 7 / 0.074 | 7 / 0.074 |

Overrated Top-2 review: #9 馬上盈 (actual 6, p=0.174)；#13 共創歡欣 (actual 9, p=0.114).
Pre-race signal review: #12 賢者威楓: stability 63.5 (+10.4 vs field), sectional 67.0 (+8.9 vs field)；#4 深心星: stability 67.5 (+14.4 vs field), form_line 96.0 (+10.4 vs field)；#5 龍之悅: race_shape 67.2 (+6.9 vs field), sectional 62.0 (+3.9 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: interference: #11 你知我寶: 8 11 你知我寶 (L132) 接近三百五十米處時移至「龍之悅」內側以繼續望空。趨近一百五十米處時在「大勇勝」與向外斜跑的「深心星」之間未能望空之際收慢。此駒因而未能被全力催策至终點。

## 2026-06-13 R4 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1800m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #3 年年友福 | 1 | 9 / 0.039 | 9 / 0.039 |
| #12 天蓬貓 | 2 | 3 / 0.143 | 3 / 0.143 |
| #2 安可 | 3 | 2 / 0.153 | 2 / 0.153 |

Overrated Top-2 review: #6 超開心 (actual 4, p=0.222).
Pre-race signal review: #3 年年友福: no ≥3-point above-field Matrix dimension；#12 天蓬貓: race_shape 72.1 (+11.8 vs field), stability 67.8 (+11.7 vs field)；#2 安可: trainer_signal 84.8 (+14.7 vs field), race_shape 70.2 (+9.8 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #3 年年友福 actual 1／odds 49 | interference: #6 超開心: 4 6 超開心 (K260) 四百五十米處至三百米處之間在「新力飆」之後受困而未能望空。

## 2026-06-13 R5 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, AWT, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #7 文明戰士 | 1 | 7 / 0.069 | 7 / 0.069 |
| #2 葳莉非凡 | 2 | 3 / 0.126 | 3 / 0.126 |
| #3 逍遙人生 | 3 | 2 / 0.133 | 2 / 0.133 |

Overrated Top-2 review: #5 顯勝高昇 (actual 11, p=0.137).
Pre-race signal review: #7 文明戰士: trainer_signal 75.8 (+6.1 vs field)；#2 葳莉非凡: stability 78.7 (+21.9 vs field), sectional 70.8 (+13.0 vs field)；#3 逍遙人生: form_line 96.0 (+11.7 vs field), race_shape 70.5 (+9.6 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: injury: #5 顯勝高昇: 11 5 顯勝高昇 (K409) 起步後不久向外斜跑，導致騎師須修正坐騎。接近五百米處時收慢避開「葳莉非凡」（奧爾民），當時「葳莉非凡」在尚未充分帶離下向內移入。小組告誡奧爾民須加倍小心。見習騎師黃寶妮表示，坐騎在此宗事件後搶口，因而於接近九百米處時推進至「葳莉非凡」內側，她其後須約束坐騎。她說，策騎指示是讓坐騎領放，但坐騎於早段未能展現足夠前速以做到這點，

## 2026-06-13 R9 — model Top-2 hits 0, Matrix 0

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, AWT, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #10 偵探傳奇 | 1 | 10 / 0.038 | 10 / 0.038 |
| #3 興馳千里 | 2 | 3 / 0.121 | 3 / 0.121 |
| #9 德心知遇 | 3 | 8 / 0.053 | 8 / 0.053 |

Overrated Top-2 review: #6 三軍勇將 (actual 6, p=0.190)；#2 熾烈神駒 (actual 4, p=0.127).
Pre-race signal review: #10 偵探傳奇: no ≥3-point above-field Matrix dimension；#3 興馳千里: race_shape 71.4 (+8.7 vs field), form_line 94.0 (+7.2 vs field)；#9 德心知遇: no ≥3-point above-field Matrix dimension.
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #9 德心知遇 actual 3／odds 30

## 2026-06-21 R6 — model Top-2 hits 1, Matrix 1

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1400m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #3 金快飛飛 | 1 | 2 / 0.121 | 2 / 0.121 |
| #12 飛躍成就 | 2 | 10 / 0.051 | 10 / 0.051 |
| #4 手機錶能 | 3 | 9 / 0.064 | 9 / 0.064 |

Overrated Top-2 review: #1 加州熱浪 (actual 8, p=0.146).
Pre-race signal review: #3 金快飛飛: stability 73.9 (+16.8 vs field), sectional 71.3 (+9.5 vs field)；#12 飛躍成就: class_advantage 72.3 (+6.9 vs field), stability 62.5 (+5.4 vs field)；#4 手機錶能: sectional 66.1 (+4.3 vs field), race_shape 63.8 (+3.7 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #4 手機錶能 actual 3／odds 36

## 2026-06-21 R7 — model Top-2 hits 0, Matrix 0

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1400m, Group 3.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #6 小鳥天堂 | 1 | 6 / 0.087 | 6 / 0.087 |
| #1 錶之銀河 | 2 | 4 / 0.093 | 4 / 0.093 |
| #7 幸運有您 | 3 | 10 / 0.057 | 10 / 0.057 |

Overrated Top-2 review: #2 精算暴雪 (actual 9, p=0.162)；#10 韋金主 (actual 4, p=0.140).
Pre-race signal review: #6 小鳥天堂: race_shape 69.7 (+5.9 vs field), class_advantage 74.6 (+3.7 vs field)；#1 錶之銀河: form_line 96.0 (+8.7 vs field), race_shape 69.9 (+6.1 vs field)；#7 幸運有您: form_line 95.0 (+7.7 vs field), horse_health 73.2 (+3.2 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #7 幸運有您 actual 3／odds 74 | interference: #2 精算暴雪: 9 2 精算暴雪 (H368) 被查詢時，艾道拿表示，坐騎自內檔出閘後能夠佔取較近仗略為靠前的位置。他說，坐騎於中段沿途跟隨「手機錶霸」，「小鳥天堂」則居於坐騎外側。他說，儘管他曾考慮讓坐騎自六百米處起向外移出，但他覺得他不能做到這點，因為「小鳥天堂」於該階段居坐騎稍前的位置及走勢良佳。他說，由於他不希望讓坐騎跟隨「好友心得」，他讓坐騎保持居於「手機錶霸」之

## 2026-06-21 R8 — model Top-2 hits 0, Matrix 0

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 2000m, Class 3.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #10 千禧龍 | 1 | 12 / 0.030 | 12 / 0.030 |
| #5 安帝 | 2 | 3 / 0.132 | 3 / 0.132 |
| #1 春風萬里 | 3 | 8 / 0.056 | 8 / 0.056 |

Overrated Top-2 review: #6 共享富裕 (actual 9, p=0.146)；#11 紫荊拼搏 (actual 12, p=0.136).
Pre-race signal review: #10 千禧龍: sectional 59.7 (+3.7 vs field)；#5 安帝: form_line 96.0 (+9.5 vs field), trainer_signal 80.5 (+9.1 vs field)；#1 春風萬里: trainer_signal 84.8 (+13.4 vs field), class_advantage 68.6 (+3.5 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #10 千禧龍 actual 1／odds 64 || #1 春風萬里 actual 3／odds 44

## 2026-06-21 R9 — model Top-2 hits 1, Matrix 1

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1800m, Group 3.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #5 美麗同享 | 1 | 1 / 0.138 | 1 / 0.138 |
| #3 光年魅力 | 2 | 7 / 0.086 | 7 / 0.086 |
| #11 浪漫戰神 | 3 | 10 / 0.069 | 10 / 0.069 |

Overrated Top-2 review: #7 銀亮奔騰 (actual 4, p=0.109).
Pre-race signal review: #5 美麗同享: form_line 93.0 (+10.4 vs field), race_shape 71.7 (+8.9 vs field)；#3 光年魅力: race_shape 67.8 (+5.0 vs field), stability 67.1 (+5.0 vs field)；#11 浪漫戰神: form_line 96.0 (+13.4 vs field), stability 67.7 (+5.6 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: interference: #7 銀亮奔騰: 4 7 銀亮奔騰 (K057) 自大外檔出閘後於早段在馬群之後切入。四百五十米處至三百五十米處之間受困而未能望空。末段在「美麗同享」與「嘉應傳承」之間緊迫競跑。

## 2026-06-21 R10 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1200m, Class 3.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #7 有備而戰 | 1 | 3 / 0.129 | 3 / 0.129 |
| #4 人和家興 | 2 | 8 / 0.043 | 8 / 0.043 |
| #13 包裝天王 | 3 | 2 / 0.138 | 2 / 0.138 |

Overrated Top-2 review: #1 跨境寶馬 (actual 4, p=0.152).
Pre-race signal review: #7 有備而戰: form_line 93.0 (+12.6 vs field), trainer_signal 80.3 (+10.1 vs field)；#4 人和家興: sectional 67.0 (+6.1 vs field), class_advantage 69.8 (+5.1 vs field)；#13 包裝天王: stability 73.1 (+16.5 vs field), sectional 76.0 (+15.1 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #4 人和家興 actual 2／odds 66

## 2026-06-21 R11 — model Top-2 hits 0, Matrix 0

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1400m, Class 3.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #14 閃電小子 | 1 | 7 / 0.059 | 7 / 0.059 |
| #9 金勝名駒 | 2 | 11 / 0.038 | 11 / 0.038 |
| #1 閃耀天河 | 3 | 5 / 0.079 | 5 / 0.079 |

Overrated Top-2 review: #3 冷娃 (actual 6, p=0.142)；#11 紅運光輝 (actual 10, p=0.139).
Pre-race signal review: #14 閃電小子: stability 71.3 (+12.0 vs field)；#9 金勝名駒: form_line 93.0 (+6.6 vs field), class_advantage 70.8 (+3.5 vs field)；#1 閃耀天河: race_shape 63.5 (+4.0 vs field), stability 62.7 (+3.4 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #9 金勝名駒 actual 2／odds 40

## 2026-06-27 R1 — model Top-2 hits 0, Matrix 0

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1200m, Class 5.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #10 綫路光驊 | 1 | 9 / 0.059 | 9 / 0.059 |
| #4 翠湖烈風 | 2 | 12 / 0.038 | 12 / 0.038 |
| #3 果然僥倖 | 3 | 10 / 0.056 | 10 / 0.056 |

Overrated Top-2 review: #2 英雄豪邁 (actual 8, p=0.118)；#1 金風萬里 (actual 13, p=0.109).
Pre-race signal review: #10 綫路光驊: sectional 68.4 (+9.5 vs field), horse_health 71.8 (+3.7 vs field)；#4 翠湖烈風: trainer_signal 73.8 (+6.0 vs field)；#3 果然僥倖: stability 64.8 (+9.9 vs field), class_advantage 71.6 (+3.6 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: major_incident: #1 金風萬里: 13 1 金風萬里 (K150) 出閘僅屬一般。田泰安表示，坐騎走勢欠順，中段沿途未能穩定走勢。他說，坐騎因而在直路上未能以勁勢衝刺。練馬師桂福特告知小組，此駒於是賽前的表現令他滿意，而他未能就此駒令人失望的表現提供任何解釋。賽後立即接受獸醫檢查，並無發現任何明顯異常之處。小組認為與上仗相比，「金風萬里」今仗的表現令人失望。「金風萬里」必須試閘及格，並且通過

## 2026-06-27 R10 — model Top-2 hits 1, Matrix 1

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1200m, Class 3.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #6 堅先生 | 1 | 1 / 0.145 | 1 / 0.145 |
| #11 香港仔 | 2 | 9 / 0.051 | 9 / 0.051 |
| #7 傑出雷霆 | 3 | 7 / 0.059 | 7 / 0.059 |

Overrated Top-2 review: #1 得道猴王 (actual 10, p=0.140).
Pre-race signal review: #6 堅先生: stability 78.3 (+24.8 vs field), sectional 70.8 (+14.6 vs field)；#11 香港仔: trainer_signal 79.3 (+8.0 vs field), class_advantage 72.3 (+5.0 vs field)；#7 傑出雷霆: stability 62.3 (+8.8 vs field), trainer_signal 79.5 (+8.2 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #11 香港仔 actual 2／odds 53 | interference: #1 得道猴王: 10 1 得道猴王 (J303) 出閘僅屬一般，其後在受向內斜跑的「電光高昇」擠迫之際收慢。四百米處至三百五十米處之間受困而未能望空。潘頓表示，坐騎在直路上對催策毫無反應，而他能提供的唯一解釋是坐騎增程角逐或更合發揮。賽後立即接受獸醫檢查，並無發現任何明顯異常之處。

## 2026-06-27 R11 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1400m, Class 3.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #5 金牌活力 | 1 | 6 / 0.085 | 6 / 0.085 |
| #2 友瑩仁 | 2 | 3 / 0.113 | 3 / 0.113 |
| #6 綫路英雄 | 3 | 2 / 0.142 | 2 / 0.142 |

Overrated Top-2 review: #7 做好自己 (actual 4, p=0.181).
Pre-race signal review: #5 金牌活力: race_shape 67.9 (+8.1 vs field), sectional 67.0 (+7.6 vs field)；#2 友瑩仁: stability 80.0 (+21.6 vs field), sectional 69.8 (+10.4 vs field)；#6 綫路英雄: stability 81.0 (+22.6 vs field), sectional 70.8 (+11.4 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #5 金牌活力 actual 1／odds 51 | interference: #7 做好自己: 4 7 做好自己 (J444) 躍出時發生碰撞。過了一百五十米處後移至「金牌活力」外側以嘗試望空。「金牌活力」其後向外斜跑，此駒於最後一百五十米在緊貼「金牌活力」的後蹄處於窘境之際嚴重受困而未能望空，因而向外斜跑，接近五十米處時在一段途程上與「正本巨星」互相觸碰。

## 2026-07-01 R1 — model Top-2 hits 0, Matrix 0

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1600m, Class 5.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #3 手到再來 | 1 | 8 / 0.061 | 8 / 0.061 |
| #10 東方魅影 | 2 | 4 / 0.095 | 4 / 0.095 |
| #7 志醒大將 | 3 | 10 / 0.050 | 10 / 0.050 |

Overrated Top-2 review: #11 勁爽 (actual 4, p=0.124)；#2 平海之星 (actual 12, p=0.105).
Pre-race signal review: #3 手到再來: race_shape 67.7 (+7.5 vs field), trainer_signal 72.2 (+3.5 vs field)；#10 東方魅影: trainer_signal 82.5 (+13.7 vs field), stability 62.7 (+7.4 vs field)；#7 志醒大將: trainer_signal 75.0 (+6.2 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: injury: #6 巴閉佬: 11 6 巴閉佬 (K323) 出閘僅屬一般，其後不久被向外斜跑的「東方魅影」碰撞。奧爾民表示，他獲指示嘗試讓坐騎在直路上移出外疊，但他未能做到這點。他說，坐騎於末段衝刺時在催策下保持同速，而他認為坐騎或已屆歇暑休賽之時。賽後立即接受獸醫檢查，並無發現任何明顯異常之處。<2/7/2026獸醫報告增補> 表現令人失望的「巴閉佬」於賽後曾由主任獸醫（賽事管制）檢

## 2026-07-01 R3 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1400m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #2 佛亮老撾 | 1 | 4 / 0.096 | 4 / 0.096 |
| #11 潮流勇駒 | 2 | 6 / 0.063 | 6 / 0.063 |
| #14 順善寶 | 3 | 1 / 0.216 | 1 / 0.216 |

Overrated Top-2 review: #1 威武年代 (actual 6, p=0.100).
Pre-race signal review: #2 佛亮老撾: form_line 96.0 (+12.6 vs field), race_shape 64.8 (+5.0 vs field)；#11 潮流勇駒: trainer_signal 72.8 (+4.8 vs field)；#14 順善寶: stability 81.0 (+29.3 vs field), class_advantage 75.6 (+11.3 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #11 潮流勇駒 actual 2／odds 89 | interference: #1 威武年代: 6 1 威武年代 (J451) 三百五十米處至二百五十米處之間受困而未能望空。

## 2026-07-01 R5 — model Top-2 hits 0, Matrix 0

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1400m, Class 2.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #9 嘉應奇兵 | 1 | 7 / 0.070 | 7 / 0.070 |
| #7 美麗星晨 | 2 | 10 / 0.027 | 10 / 0.027 |
| #8 至尊瑰寶 | 3 | 3 / 0.113 | 3 / 0.113 |

Overrated Top-2 review: #2 笑傲江湖 (actual 5, p=0.257)；#6 喜尊龍 (actual 9, p=0.154).
Pre-race signal review: #9 嘉應奇兵: stability 73.1 (+15.3 vs field), sectional 60.3 (+4.3 vs field)；#7 美麗星晨: horse_health 74.6 (+4.0 vs field)；#8 至尊瑰寶: race_shape 67.8 (+4.8 vs field), sectional 60.0 (+4.0 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: interference: #2 笑傲江湖: 5 2 笑傲江湖 (K168) 四百米處至三百五十米處之間在「威利金箭」之後受困而未能望空。

## 2026-07-04 R2 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1200m, Class 5.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #9 魅力知福 | 1 | 3 / 0.096 | 3 / 0.096 |
| #11 駿先生 | 2 | 7 / 0.048 | 7 / 0.048 |
| #5 朗日雪峰 | 3 | 1 / 0.320 | 1 / 0.320 |

Overrated Top-2 review: #10 紅旺繽紛 (actual 7, p=0.143).
Pre-race signal review: #9 魅力知福: trainer_signal 77.2 (+7.3 vs field), race_shape 66.5 (+5.2 vs field)；#11 駿先生: form_line 96.0 (+5.7 vs field), race_shape 66.8 (+5.6 vs field)；#5 朗日雪峰: stability 72.6 (+19.4 vs field), trainer_signal 87.0 (+17.0 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #11 駿先生 actual 2／odds 45

## 2026-07-04 R7 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #5 添開心 | 1 | 4 / 0.114 | 4 / 0.114 |
| #12 同喜 | 2 | 3 / 0.136 | 3 / 0.136 |
| #6 老鼠斑 | 3 | 2 / 0.186 | 2 / 0.186 |

Overrated Top-2 review: #4 開心孖寶 (actual 10, p=0.207).
Pre-race signal review: #5 添開心: form_line 96.0 (+13.3 vs field), race_shape 67.9 (+7.5 vs field)；#12 同喜: class_advantage 75.6 (+10.4 vs field), race_shape 69.6 (+9.2 vs field)；#6 老鼠斑: trainer_signal 82.5 (+13.6 vs field), stability 67.7 (+13.0 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: interference: #4 開心孖寶: 10 4 開心孖寶 (K475) 跑離二百米處時在被「日出東方」碰撞之際失去平衡，當時「日出東方」在勒避之際向內斜跑。趨近一百五十米處時在「日出東方」與「擅搏」之間受擠迫之際大力勒避。賽後立即接受獸醫檢查，並無發現任何明顯異常之處。

## 2026-07-04 R8 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1800m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #6 捷威 | 1 | 1 / 0.134 | 1 / 0.134 |
| #9 風起雲湧 | 2 | 5 / 0.092 | 5 / 0.092 |
| #3 創科群英 | 3 | 13 / 0.028 | 13 / 0.028 |

Overrated Top-2 review: #12 鴻圖大展 (actual 7, p=0.117).
Pre-race signal review: #6 捷威: stability 68.2 (+10.5 vs field), sectional 64.2 (+8.2 vs field)；#9 風起雲湧: stability 80.1 (+22.4 vs field), sectional 62.8 (+6.8 vs field)；#3 創科群英: no ≥3-point above-field Matrix dimension.
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #3 創科群英 actual 3／odds 50

## 2026-07-04 R9 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #3 利高八斗 | 1 | 2 / 0.190 | 2 / 0.190 |
| #6 龍文正道 | 2 | 6 / 0.059 | 6 / 0.059 |
| #1 鼓浪好友 | 3 | 5 / 0.070 | 5 / 0.070 |

Overrated Top-2 review: #5 應龍飛影 (actual 4, p=0.190).
Pre-race signal review: #3 利高八斗: stability 79.7 (+21.2 vs field), trainer_signal 78.2 (+9.3 vs field)；#6 龍文正道: stability 65.0 (+6.4 vs field), trainer_signal 72.8 (+3.8 vs field)；#1 鼓浪好友: form_line 96.0 (+12.4 vs field), stability 67.6 (+9.1 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #6 龍文正道 actual 2／odds 111

## 2026-07-08 R4 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 跑馬地, Turf, 1650m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #1 哥倫布 | 1 | 2 / 0.190 | 2 / 0.190 |
| #7 焦點 | 2 | 5 / 0.120 | 5 / 0.120 |
| #6 準希望 | 3 | 6 / 0.108 | 6 / 0.108 |

Overrated Top-2 review: #5 好運年 (actual 4, p=0.220).
Pre-race signal review: #1 哥倫布: trainer_signal 87.0 (+10.5 vs field), race_shape 81.0 (+8.5 vs field)；#7 焦點: stability 69.9 (+8.9 vs field), sectional 67.5 (+5.5 vs field)；#6 準希望: sectional 66.5 (+4.5 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: interference: #5 好運年: 4 5 好運年 (K443) 末段在「準希望」與「焦點」之間緊迫競跑時未能被全力催策，當時「焦點」在催策下向外斜跑。賽後須抽取樣本檢驗。

## 2026-07-08 R8 — model Top-2 hits 0, Matrix 0

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 跑馬地, Turf, 1800m, Class 2.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #9 極光之子 | 1 | 10 / 0.038 | 10 / 0.038 |
| #11 幸運派彩 | 2 | 7 / 0.068 | 7 / 0.068 |
| #10 川河耀駒 | 3 | 12 / 0.019 | 12 / 0.019 |

Overrated Top-2 review: #3 奔放 (actual 9, p=0.195)；#5 春風萬里 (actual 5, p=0.132).
Pre-race signal review: #9 極光之子: stability 69.5 (+8.6 vs field)；#11 幸運派彩: race_shape 73.0 (+10.8 vs field), horse_health 73.8 (+3.7 vs field)；#10 川河耀駒: horse_health 74.6 (+4.5 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: interference: #12 將義: 10 12 將義 (J446) 轉直路彎時在「友瑩光」之後受困而未能望空。接近二百米處時「幸運派彩」（巴度）向內斜跑，避開「極光之子」，導致「奔放」被帶向內跑壓向「一起美麗」。「一起美麗」因此向內斜跑，將「浪漫戰神」向內擠迫壓向此駒，當時此駒在「友瑩光」與「浪漫戰神」之間未能望空之際收慢。小組告誡巴度須加倍小心。賽後立即接受獸醫檢查，並無發現任何明顯異常之處

## 2026-07-08 R9 — model Top-2 hits 0, Matrix 0

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 跑馬地, Turf, 1200m, Class 3.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #11 撼天鐵翼 | 1 | 4 / 0.121 | 4 / 0.121 |
| #4 觀眾之力 | 2 | 3 / 0.124 | 3 / 0.124 |
| #3 嘉應勇將 | 3 | 9 / 0.041 | 9 / 0.041 |

Overrated Top-2 review: #1 志滿同行 (actual 7, p=0.210)；#7 皇者有利 (actual 8, p=0.146).
Pre-race signal review: #11 撼天鐵翼: race_shape 79.0 (+16.1 vs field), form_line 96.0 (+8.5 vs field)；#4 觀眾之力: trainer_signal 87.0 (+11.3 vs field), stability 74.4 (+9.9 vs field)；#3 嘉應勇將: no ≥3-point above-field Matrix dimension.
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #3 嘉應勇將 actual 3／odds 32 | interference: #7 皇者有利: 8 7 皇者有利 (J539) 起步後不久受擠迫。直路彎受困而未能望空。小組押後有關此駒於接近三百米處時勒避的原因之研訊至七月十二日星期日沙田賽事當日進行。賽後立即接受獸醫檢查，並無發現任何明顯異常之處。

## 2026-07-12 R4 — model Top-2 hits 1, Matrix 1

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1400m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #2 金滙千帥 | 1 | 1 / 0.157 | 1 / 0.157 |
| #12 金運齊來 | 2 | 9 / 0.058 | 9 / 0.058 |
| #1 哈羅威 | 3 | 6 / 0.067 | 6 / 0.067 |

Overrated Top-2 review: #5 文明福星 (actual 10, p=0.113).
Pre-race signal review: #2 金滙千帥: race_shape 72.0 (+12.1 vs field), trainer_signal 87.0 (+11.5 vs field)；#12 金運齊來: form_line 96.0 (+12.6 vs field), sectional 67.0 (+11.1 vs field)；#1 哈羅威: stability 65.4 (+13.0 vs field), class_advantage 63.0 (+3.2 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #12 金運齊來 actual 2／odds 68 | interference: #5 文明福星: 10 5 文明福星 (J315) 一百五十米處至五十米處之間在「鬥志波」之後受困而未能望空。賽後，獸醫應練馬師丁冠豪的要求替「文明福星」進行內窺鏡檢查。獸醫表示，是項檢查顯示此駒的氣管內有很多血。「文明福星」必須通過獸醫檢驗後，才可再次出賽。

## 2026-07-12 R6 — model Top-2 hits 0, Matrix 0

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #2 盈妍威楓 | 1 | 9 / 0.065 | 9 / 0.065 |
| #10 烈進駒 | 2 | 12 / 0.046 | 12 / 0.046 |
| #8 實力加 | 3 | 10 / 0.057 | 10 / 0.057 |

Overrated Top-2 review: #6 銀刺勇士 (actual 12, p=0.113)；#14 旭能精英 (actual 5, p=0.109).
Pre-race signal review: #2 盈妍威楓: form_line 96.0 (+7.5 vs field)；#10 烈進駒: trainer_signal 77.2 (+3.3 vs field)；#8 實力加: stability 64.7 (+11.5 vs field), class_advantage 68.8 (+8.2 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #10 烈進駒 actual 2／odds 97

## 2026-07-12 R7 — model Top-2 hits 1, Matrix 1

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1600m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #3 包裝戰仕 | 1 | 6 / 0.069 | 6 / 0.069 |
| #6 新力飆 | 2 | 14 / 0.030 | 14 / 0.030 |
| #5 超開心 | 3 | 2 / 0.111 | 2 / 0.111 |

Overrated Top-2 review: #10 天蓬貓 (actual 4, p=0.124).
Pre-race signal review: #3 包裝戰仕: stability 66.6 (+8.4 vs field), trainer_signal 82.5 (+8.1 vs field)；#6 新力飆: no ≥3-point above-field Matrix dimension；#5 超開心: stability 69.5 (+11.3 vs field), class_advantage 68.8 (+6.3 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #6 新力飆 actual 2／odds 93

## 2026-07-12 R11 — model Top-2 hits 0, Matrix 0

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1400m, Class 3.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #3 臻至辰 | 1 | 5 / 0.081 | 5 / 0.081 |
| #12 金快飛飛 | 2 | 6 / 0.072 | 6 / 0.072 |
| #4 泰坦 | 3 | 10 / 0.039 | 10 / 0.039 |

Overrated Top-2 review: #1 綠野飛馳 (actual 5, p=0.143)；#9 仁仁有餘 (actual 4, p=0.137).
Pre-race signal review: #3 臻至辰: form_line 96.0 (+11.6 vs field), race_shape 64.4 (+4.4 vs field)；#12 金快飛飛: stability 80.5 (+19.3 vs field), class_advantage 70.3 (+6.8 vs field)；#4 泰坦: sectional 65.0 (+6.2 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 48 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #4 泰坦 actual 3／odds 49

# Recurring diagnosis

Weak races reviewed: **125** (68 normal-result cohort; 57 outsider/incident/injury/abnormal flagged). Races where the challenger improved Top-2 hit count over Matrix: **0**.

| Pattern | Races |
|---|---:|
| contender captured in Top-5 tier but not Top 2 | 77 |
| competitive group absent from both Top-5 rankings | 48 |

Changes are eligible only when the same pattern improves multiple chronological folds. A single missed horse does not authorize a weight change.

---

# Best ML Challenger Comparison

Model reviewed: **Logistic Regression**.  All ranks below use pre-race features only; incidents and odds are diagnostic annotations, never training inputs.

## 2026-05-09 R2 — model Top-2 hits 0, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #1 北地烈馬 | 1 | 5 / 0.094 | 4 / 0.139 |
| #2 馬馳登 | 2 | 4 / 0.099 | 3 / 0.144 |
| #5 奇異歡星 | 3 | 3 / 0.139 | 2 / 0.157 |

Overrated Top-2 review: #7 川河石駒 (actual 5, p=0.207)；#8 烈進駒 (actual 7, p=0.182).
Pre-race signal review: #1 北地烈馬: race_shape 72.2 (+11.1 vs field), sectional 69.7 (+9.3 vs field)；#2 馬馳登: form_line 96.0 (+14.0 vs field), trainer_signal 79.3 (+9.8 vs field)；#5 奇異歡星: race_shape 74.8 (+13.7 vs field), form_line 94.0 (+12.0 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-05-09 R3 — model Top-2 hits 1, Matrix 1

Classification: **ML reordering degraded Matrix contender**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1400m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #12 肥仔精神 | 1 | 11 / 0.032 | 12 / 0.023 |
| #8 巴閉佬 | 2 | 6 / 0.089 | 3 / 0.118 |
| #13 添喜運 | 3 | 1 / 0.172 | 1 / 0.215 |

Overrated Top-2 review: #6 志醒大將 (actual 12, p=0.170).
Pre-race signal review: #12 肥仔精神: no ≥3-point above-field Matrix dimension；#8 巴閉佬: race_shape 78.6 (+18.0 vs field), sectional 65.5 (+5.8 vs field)；#13 添喜運: race_shape 82.0 (+21.4 vs field), stability 65.0 (+13.5 vs field).
Cause assessment: challenger reordering or race-specific residual.
Systematicity: this pattern occurs in 13 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-05-09 R8 — model Top-2 hits 1, Matrix 0

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #7 㩒住贏 | 1 | 7 / 0.072 | 8 / 0.045 |
| #11 富國兄弟 | 2 | 5 / 0.088 | 3 / 0.144 |
| #3 手機錶勁 | 3 | 1 / 0.177 | 4 / 0.116 |

Overrated Top-2 review: #10 辣得準 (actual 7, p=0.163).
Pre-race signal review: #7 㩒住贏: stability 64.9 (+4.2 vs field)；#11 富國兄弟: form_line 96.0 (+12.2 vs field), race_shape 75.0 (+11.9 vs field)；#3 手機錶勁: stability 83.5 (+22.7 vs field), trainer_signal 87.0 (+18.6 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-05-09 R9 — model Top-2 hits 0, Matrix 0

Classification: **ML reordering degraded Matrix contender**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1000m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #7 團結勇士 | 1 | 6 / 0.082 | 4 / 0.101 |
| #13 幸運糖 | 2 | 9 / 0.050 | 9 / 0.043 |
| #14 飛來閃耀 | 3 | 8 / 0.055 | 8 / 0.068 |

Overrated Top-2 review: #2 米奇 (actual 7, p=0.135)；#1 會長之寶 (actual 9, p=0.134).
Pre-race signal review: #7 團結勇士: race_shape 78.2 (+16.7 vs field), stability 65.6 (+6.2 vs field)；#13 幸運糖: form_line 96.0 (+9.1 vs field), trainer_signal 75.0 (+6.2 vs field)；#14 飛來閃耀: form_line 96.0 (+9.1 vs field), class_advantage 75.6 (+7.1 vs field).
Cause assessment: challenger reordering or race-specific residual.
Systematicity: this pattern occurs in 13 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-05-09 R11 — model Top-2 hits 0, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #4 錶之星河 | 1 | 3 / 0.146 | 2 / 0.169 |
| #2 翠紅 | 2 | 4 / 0.096 | 5 / 0.079 |
| #12 威利金箭 | 3 | 5 / 0.095 | 6 / 0.072 |

Overrated Top-2 review: #6 燈胆將軍 (actual 6, p=0.196)；#5 競駿輝煌 (actual 12, p=0.153).
Pre-race signal review: #4 錶之星河: race_shape 76.0 (+13.8 vs field), stability 74.4 (+11.4 vs field)；#2 翠紅: stability 72.7 (+9.7 vs field), trainer_signal 77.0 (+5.7 vs field)；#12 威利金箭: race_shape 72.6 (+10.4 vs field), trainer_signal 76.0 (+4.7 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-05-13 R1 — model Top-2 hits 1, Matrix 1

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **normal-result cohort**. Venue 跑馬地, Turf, 1650m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #1 焦點 | 1 | 2 / 0.137 | 1 / 0.184 |
| #3 駟跑得 | 2 | 10 / 0.048 | 10 / 0.052 |
| #12 華美之威 | 3 | 9 / 0.053 | 11 / 0.043 |

Overrated Top-2 review: #11 龍又生 (actual 10, p=0.215).
Pre-race signal review: #1 焦點: race_shape 78.8 (+16.2 vs field), stability 68.6 (+12.6 vs field)；#3 駟跑得: no ≥3-point above-field Matrix dimension；#12 華美之威: horse_health 73.2 (+4.5 vs field).
Cause assessment: available pre-race Matrix signals did not place enough contenders in the competitive tier.
Systematicity: this pattern occurs in 37 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-05-17 R2 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1000m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #14 拉合爾 | 1 | 3 / 0.127 | 1 / 0.133 |
| #10 致力之城 | 2 | 4 / 0.111 | 3 / 0.109 |
| #4 鄉村威龍 | 3 | 1 / 0.162 | 4 / 0.104 |

Overrated Top-2 review: #1 日出東方 (actual 10, p=0.127).
Pre-race signal review: #14 拉合爾: form_line 96.0 (+16.1 vs field), trainer_signal 80.3 (+10.5 vs field)；#10 致力之城: trainer_signal 77.0 (+7.3 vs field), race_shape 69.2 (+5.2 vs field)；#4 鄉村威龍: trainer_signal 84.8 (+15.0 vs field), stability 66.3 (+7.1 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-05-17 R3 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #3 快樂高球 | 1 | 9 / 0.054 | 8 / 0.079 |
| #11 東方寶寶 | 2 | 3 / 0.116 | 3 / 0.089 |
| #5 後無來者 | 3 | 1 / 0.184 | 2 / 0.120 |

Overrated Top-2 review: #4 首駿 (actual 5, p=0.153).
Pre-race signal review: #3 快樂高球: form_line 96.0 (+12.4 vs field)；#11 東方寶寶: trainer_signal 74.8 (+6.1 vs field)；#5 後無來者: trainer_signal 84.8 (+16.1 vs field), race_shape 68.8 (+7.0 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-05-17 R5 — model Top-2 hits 1, Matrix 2

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #7 巴閉精 | 1 | 2 / 0.171 | 2 / 0.152 |
| #3 利高八斗 | 2 | 3 / 0.152 | 1 / 0.152 |
| #2 鼓浪好友 | 3 | 11 / 0.035 | 8 / 0.061 |

Overrated Top-2 review: #6 舞林盛宴 (actual 4, p=0.196).
Pre-race signal review: #7 巴閉精: trainer_signal 84.8 (+14.1 vs field), stability 63.7 (+8.8 vs field)；#3 利高八斗: stability 76.3 (+21.5 vs field), sectional 68.8 (+10.4 vs field)；#2 鼓浪好友: form_line 96.0 (+12.8 vs field), class_advantage 71.6 (+8.6 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-05-17 R7 — model Top-2 hits 0, Matrix 0

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1400m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #1 自動自覺 | 1 | 5 / 0.087 | 6 / 0.070 |
| #4 實力加 | 2 | 6 / 0.054 | 5 / 0.078 |
| #3 八仟好運 | 3 | 3 / 0.125 | 4 / 0.097 |

Overrated Top-2 review: #2 哥倫布 (actual 5, p=0.229)；#12 瀧澤飛駒 (actual 4, p=0.132).
Pre-race signal review: #1 自動自覺: class_advantage 74.1 (+8.5 vs field), stability 62.4 (+8.2 vs field)；#4 實力加: stability 65.0 (+10.8 vs field), sectional 67.0 (+6.2 vs field)；#3 八仟好運: trainer_signal 78.3 (+10.3 vs field), stability 58.6 (+4.4 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-05-17 R8 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1800m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #14 夢照發 | 1 | 3 / 0.129 | 3 / 0.109 |
| #7 佰勝金龍 | 2 | 9 / 0.038 | 8 / 0.048 |
| #5 超開心 | 3 | 1 / 0.227 | 1 / 0.198 |

Overrated Top-2 review: #4 赤風驪 (actual 11, p=0.135).
Pre-race signal review: #14 夢照發: stability 71.2 (+16.2 vs field), class_advantage 75.6 (+10.0 vs field)；#7 佰勝金龍: stability 61.0 (+6.0 vs field), sectional 59.5 (+4.5 vs field)；#5 超開心: stability 73.2 (+18.2 vs field), trainer_signal 87.0 (+15.6 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-05-17 R9 — model Top-2 hits 0, Matrix 1

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1400m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #5 百勝威龍 | 1 | 8 / 0.049 | 8 / 0.053 |
| #13 飛躍成就 | 2 | 10 / 0.039 | 12 / 0.034 |
| #7 洪才 | 3 | 4 / 0.113 | 2 / 0.133 |

Overrated Top-2 review: #12 星光快驅 (actual 9, p=0.173)；#10 遨遊波士 (actual 8, p=0.118).
Pre-race signal review: #5 百勝威龍: form_line 96.0 (+7.2 vs field)；#13 飛躍成就: horse_health 72.2 (+4.2 vs field), class_advantage 69.2 (+3.1 vs field)；#7 洪才: stability 66.8 (+13.0 vs field), race_shape 73.1 (+12.5 vs field).
Cause assessment: available pre-race Matrix signals did not place enough contenders in the competitive tier.
Systematicity: this pattern occurs in 37 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-05-20 R3 — model Top-2 hits 1, Matrix 1

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **normal-result cohort**. Venue 跑馬地, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #2 星火燎原 | 1 | 9 / 0.050 | 8 / 0.063 |
| #8 星辰千帥 | 2 | 8 / 0.072 | 7 / 0.074 |
| #4 佐治傳奇 | 3 | 1 / 0.188 | 1 / 0.192 |

Overrated Top-2 review: #6 烈焰光芒 (actual 5, p=0.130).
Pre-race signal review: #2 星火燎原: race_shape 76.8 (+16.3 vs field)；#8 星辰千帥: form_line 96.0 (+9.1 vs field), stability 63.0 (+6.3 vs field)；#4 佐治傳奇: stability 73.7 (+17.0 vs field), race_shape 73.0 (+12.5 vs field).
Cause assessment: available pre-race Matrix signals did not place enough contenders in the competitive tier.
Systematicity: this pattern occurs in 37 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-05-20 R4 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 跑馬地, Turf, 1650m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #8 有情有義 | 1 | 1 / 0.286 | 1 / 0.248 |
| #10 北海盜 | 2 | 4 / 0.081 | 3 / 0.088 |
| #3 財富非凡 | 3 | 6 / 0.064 | 5 / 0.082 |

Overrated Top-2 review: #12 多利神駒 (actual 7, p=0.131).
Pre-race signal review: #8 有情有義: trainer_signal 87.0 (+17.1 vs field), race_shape 76.6 (+13.9 vs field)；#10 北海盜: race_shape 76.0 (+13.3 vs field), class_advantage 72.3 (+4.6 vs field)；#3 財富非凡: race_shape 75.0 (+12.3 vs field), form_line 96.0 (+11.9 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-05-20 R7 — model Top-2 hits 0, Matrix 0

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 跑馬地, Turf, 1650m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #11 紫辰之星 | 1 | 3 / 0.118 | 3 / 0.145 |
| #4 泰力 | 2 | 9 / 0.034 | 7 / 0.051 |
| #5 做好自己 | 3 | 5 / 0.083 | 5 / 0.077 |

Overrated Top-2 review: #1 滿心星 (actual 6, p=0.277)；#3 開心勇駒 (actual 9, p=0.167).
Pre-race signal review: #11 紫辰之星: race_shape 79.8 (+16.3 vs field), form_line 96.0 (+8.4 vs field)；#4 泰力: sectional 67.0 (+8.3 vs field)；#5 做好自己: stability 77.0 (+17.6 vs field), sectional 67.3 (+8.7 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-05-24 R1 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1600m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #1 威力非凡 | 1 | 4 / 0.102 | 1 / 0.115 |
| #14 勁爽 | 2 | 13 / 0.040 | 13 / 0.042 |
| #6 神駒馬靈 | 3 | 2 / 0.111 | 3 / 0.098 |

Overrated Top-2 review: #7 志醒大將 (actual 4, p=0.142).
Pre-race signal review: #1 威力非凡: race_shape 72.5 (+12.8 vs field), trainer_signal 75.8 (+6.3 vs field)；#14 勁爽: stability 61.9 (+5.4 vs field), horse_health 73.2 (+5.4 vs field)；#6 神駒馬靈: stability 71.4 (+14.9 vs field), sectional 66.2 (+6.3 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-05-24 R5 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1600m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #2 大回報 | 1 | 1 / 0.183 | 1 / 0.162 |
| #13 幸運威龍 | 2 | 5 / 0.071 | 4 / 0.083 |
| #4 逍遙騎士 | 3 | 4 / 0.090 | 3 / 0.091 |

Overrated Top-2 review: #7 旌採 (actual 4, p=0.115).
Pre-race signal review: #2 大回報: stability 80.9 (+24.3 vs field), class_advantage 71.6 (+6.8 vs field)；#13 幸運威龍: race_shape 68.8 (+7.9 vs field), form_line 96.0 (+6.4 vs field)；#4 逍遙騎士: stability 67.5 (+11.0 vs field), form_line 96.0 (+6.4 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-05-24 R10 — model Top-2 hits 1, Matrix 1

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #5 煌上 | 1 | 1 / 0.177 | 1 / 0.136 |
| #13 閃電小子 | 2 | 8 / 0.047 | 10 / 0.037 |
| #1 得道猴王 | 3 | 14 / 0.019 | 13 / 0.028 |

Overrated Top-2 review: #12 鈁糖武士 (actual 9, p=0.134).
Pre-race signal review: #5 煌上: stability 82.8 (+20.0 vs field), race_shape 69.2 (+9.1 vs field)；#13 閃電小子: no ≥3-point above-field Matrix dimension；#1 得道猴王: form_line 96.0 (+14.1 vs field).
Cause assessment: available pre-race Matrix signals did not place enough contenders in the competitive tier.
Systematicity: this pattern occurs in 37 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-05-24 R11 — model Top-2 hits 1, Matrix 2

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1400m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #6 超勁赤兔 | 1 | 3 / 0.116 | 3 / 0.124 |
| #4 凌登 | 2 | 1 / 0.196 | 1 / 0.212 |
| #5 一世美麗 | 3 | 4 / 0.112 | 2 / 0.136 |

Overrated Top-2 review: #7 櫻花酒杯 (actual 4, p=0.169).
Pre-race signal review: #6 超勁赤兔: race_shape 70.3 (+10.0 vs field), sectional 67.3 (+9.8 vs field)；#4 凌登: stability 78.9 (+19.4 vs field), form_line 96.0 (+13.8 vs field)；#5 一世美麗: form_line 96.0 (+13.8 vs field), stability 72.8 (+13.3 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-05-27 R4 — model Top-2 hits 0, Matrix 0

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **normal-result cohort**. Venue 跑馬地, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #5 朗日自強 | 1 | 3 / 0.110 | 3 / 0.123 |
| #11 天下寵兒 | 2 | 9 / 0.056 | 10 / 0.058 |
| #9 頑童 | 3 | 11 / 0.028 | 11 / 0.047 |

Overrated Top-2 review: #1 紅愛舍 (actual 9, p=0.205)；#2 贏得自然 (actual 10, p=0.118).
Pre-race signal review: #5 朗日自強: race_shape 79.0 (+15.4 vs field), sectional 65.8 (+6.8 vs field)；#11 天下寵兒: form_line 96.0 (+10.2 vs field), class_advantage 74.6 (+8.2 vs field)；#9 頑童: sectional 69.1 (+10.1 vs field).
Cause assessment: available pre-race Matrix signals did not place enough contenders in the competitive tier.
Systematicity: this pattern occurs in 37 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-05-27 R5 — model Top-2 hits 1, Matrix 1

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **normal-result cohort**. Venue 跑馬地, Turf, 1650m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #2 穿甲金鷹 | 1 | 1 / 0.292 | 1 / 0.258 |
| #6 智勇名駒 | 2 | 9 / 0.034 | 9 / 0.046 |
| #5 納百川 | 3 | 7 / 0.064 | 7 / 0.065 |

Overrated Top-2 review: #8 凡凡有餘 (actual 8, p=0.151).
Pre-race signal review: #2 穿甲金鷹: stability 74.7 (+14.7 vs field), race_shape 80.8 (+13.5 vs field)；#6 智勇名駒: form_line 96.0 (+5.2 vs field)；#5 納百川: race_shape 78.0 (+10.7 vs field).
Cause assessment: available pre-race Matrix signals did not place enough contenders in the competitive tier.
Systematicity: this pattern occurs in 37 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-05-27 R6 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 跑馬地, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #9 風采人生 | 1 | 1 / 0.211 | 1 / 0.258 |
| #8 花好月盈 | 2 | 4 / 0.138 | 4 / 0.128 |
| #7 牛精新星 | 3 | 5 / 0.060 | 8 / 0.042 |

Overrated Top-2 review: #5 環球英雄 (actual 6, p=0.210).
Pre-race signal review: #9 風采人生: race_shape 77.0 (+14.8 vs field), sectional 72.7 (+13.9 vs field)；#8 花好月盈: race_shape 74.0 (+11.8 vs field), stability 70.0 (+10.7 vs field)；#7 牛精新星: stability 62.5 (+3.2 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-05-27 R7 — model Top-2 hits 0, Matrix 0

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **normal-result cohort**. Venue 跑馬地, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #9 幸運愉快 | 1 | 4 / 0.115 | 6 / 0.089 |
| #12 精益大師 | 2 | 11 / 0.030 | 10 / 0.041 |
| #6 新力 | 3 | 8 / 0.069 | 7 / 0.085 |

Overrated Top-2 review: #1 泰泰精神 (actual 4, p=0.145)；#10 智勝攻略 (actual 10, p=0.120).
Pre-race signal review: #9 幸運愉快: trainer_signal 78.2 (+6.2 vs field), stability 60.9 (+3.3 vs field)；#12 精益大師: form_line 96.0 (+9.8 vs field)；#6 新力: race_shape 77.0 (+12.7 vs field).
Cause assessment: available pre-race Matrix signals did not place enough contenders in the competitive tier.
Systematicity: this pattern occurs in 37 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-05-27 R8 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 跑馬地, Turf, 1000m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #3 八駿巨昇 | 1 | 10 / 0.032 | 9 / 0.041 |
| #1 馬力 | 2 | 1 / 0.199 | 1 / 0.176 |
| #2 燭光晚餐 | 3 | 3 / 0.121 | 3 / 0.127 |

Overrated Top-2 review: #10 飛龍在天 (actual 7, p=0.167).
Pre-race signal review: #3 八駿巨昇: class_advantage 70.8 (+3.8 vs field)；#1 馬力: trainer_signal 87.0 (+17.2 vs field), form_line 96.0 (+10.1 vs field)；#2 燭光晚餐: race_shape 77.8 (+15.2 vs field), sectional 69.3 (+9.0 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-03 R2 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 跑馬地, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #4 首駿 | 1 | 2 / 0.098 | 3 / 0.094 |
| #3 金風萬里 | 2 | 3 / 0.089 | 2 / 0.114 |
| #12 快馬加鞭 | 3 | 5 / 0.071 | 6 / 0.067 |

Overrated Top-2 review: #2 喆喆友福 (actual 5, p=0.329).
Pre-race signal review: #4 首駿: race_shape 75.8 (+12.9 vs field), stability 64.6 (+9.9 vs field)；#3 金風萬里: form_line 96.0 (+12.8 vs field), sectional 69.1 (+7.8 vs field)；#12 快馬加鞭: class_advantage 73.3 (+5.1 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-03 R6 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 跑馬地, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #1 星運少爵 | 1 | 2 / 0.232 | 1 / 0.227 |
| #4 喵喵怪 | 2 | 8 / 0.033 | 8 / 0.034 |
| #5 銳目 | 3 | 4 / 0.111 | 4 / 0.125 |

Overrated Top-2 review: #7 獵寶勤 (actual 6, p=0.256).
Pre-race signal review: #1 星運少爵: stability 76.5 (+15.5 vs field), trainer_signal 87.0 (+14.2 vs field)；#4 喵喵怪: no ≥3-point above-field Matrix dimension；#5 銳目: race_shape 76.2 (+13.1 vs field), trainer_signal 82.5 (+9.8 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-07 R4 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1400m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #14 挺秀弘利 | 1 | 5 / 0.078 | 4 / 0.085 |
| #6 八仟好運 | 2 | 1 / 0.152 | 2 / 0.121 |
| #7 北極之錶 | 3 | 3 / 0.129 | 3 / 0.120 |

Overrated Top-2 review: #2 龍城強將 (actual 6, p=0.145).
Pre-race signal review: #14 挺秀弘利: sectional 65.5 (+6.0 vs field), trainer_signal 72.8 (+3.6 vs field)；#6 八仟好運: trainer_signal 78.3 (+9.1 vs field), stability 64.0 (+6.7 vs field)；#7 北極之錶: sectional 71.8 (+12.2 vs field), trainer_signal 80.3 (+11.1 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-07 R10 — model Top-2 hits 1, Matrix 0

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #8 喜慶寶 | 1 | 2 / 0.152 | 3 / 0.124 |
| #5 魔術控制 | 2 | 10 / 0.031 | 10 / 0.044 |
| #9 威利金箭 | 3 | 4 / 0.116 | 4 / 0.113 |

Overrated Top-2 review: #6 扶搖勢勁 (actual 5, p=0.156).
Pre-race signal review: #8 喜慶寶: stability 75.0 (+12.6 vs field), trainer_signal 80.5 (+9.1 vs field)；#5 魔術控制: no ≥3-point above-field Matrix dimension；#9 威利金箭: race_shape 72.0 (+10.5 vs field), class_advantage 71.8 (+3.9 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-10 R1 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 跑馬地, Turf, 1800m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #2 家樂寶駒 | 1 | 6 / 0.067 | 4 / 0.111 |
| #1 竣誠駒 | 2 | 3 / 0.126 | 3 / 0.124 |
| #10 龍又生 | 3 | 1 / 0.154 | 2 / 0.132 |

Overrated Top-2 review: #7 幸運同行 (actual 4, p=0.146).
Pre-race signal review: #2 家樂寶駒: race_shape 77.8 (+17.1 vs field), form_line 95.0 (+14.0 vs field)；#1 竣誠駒: race_shape 73.0 (+12.3 vs field), stability 56.8 (+4.1 vs field)；#10 龍又生: sectional 63.0 (+10.4 vs field), race_shape 63.8 (+3.1 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-10 R2 — model Top-2 hits 0, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 跑馬地, Turf, 1650m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #1 高高至高 | 1 | 4 / 0.098 | 4 / 0.106 |
| #7 準希望 | 2 | 3 / 0.173 | 2 / 0.191 |
| #6 得意佳作 | 3 | 6 / 0.059 | 8 / 0.057 |

Overrated Top-2 review: #5 大千氣象 (actual 5, p=0.249)；#11 多利神駒 (actual 10, p=0.175).
Pre-race signal review: #1 高高至高: trainer_signal 80.3 (+12.5 vs field), form_line 96.0 (+10.7 vs field)；#7 準希望: race_shape 74.6 (+12.9 vs field), sectional 65.5 (+9.0 vs field)；#6 得意佳作: sectional 63.6 (+7.1 vs field), class_advantage 70.8 (+3.1 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-10 R3 — model Top-2 hits 0, Matrix 0

Classification: **ML reordering degraded Matrix contender**. Predictability review: **normal-result cohort**. Venue 跑馬地, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #8 風火猴王 | 1 | 7 / 0.084 | 5 / 0.090 |
| #11 友得盈 | 2 | 9 / 0.074 | 8 / 0.067 |
| #5 勝多多 | 3 | 6 / 0.087 | 7 / 0.074 |

Overrated Top-2 review: #9 良駒好友 (actual 6, p=0.140)；#7 豪邁先登 (actual 8, p=0.122).
Pre-race signal review: #8 風火猴王: sectional 65.0 (+3.9 vs field)；#11 友得盈: class_advantage 72.3 (+6.5 vs field), horse_health 74.0 (+4.3 vs field)；#5 勝多多: trainer_signal 80.5 (+13.0 vs field), class_advantage 70.8 (+5.0 vs field).
Cause assessment: challenger reordering or race-specific residual.
Systematicity: this pattern occurs in 13 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-10 R4 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 跑馬地, Turf, 1000m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #3 鴻圖新星 | 1 | 1 / 0.218 | 1 / 0.216 |
| #5 美麗登場 | 2 | 3 / 0.128 | 4 / 0.114 |
| #8 天火同人 | 3 | 4 / 0.101 | 3 / 0.120 |

Overrated Top-2 review: #2 紅錢到 (actual 4, p=0.137).
Pre-race signal review: #3 鴻圖新星: race_shape 79.8 (+17.8 vs field), trainer_signal 80.5 (+9.4 vs field)；#5 美麗登場: trainer_signal 85.9 (+14.8 vs field)；#8 天火同人: race_shape 77.8 (+15.8 vs field), class_advantage 70.8 (+4.2 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-10 R5 — model Top-2 hits 1, Matrix 1

Classification: **ML reordering degraded Matrix contender**. Predictability review: **normal-result cohort**. Venue 跑馬地, Turf, 1650m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #12 爆竹 | 1 | 8 / 0.043 | 8 / 0.050 |
| #3 紅海勁 | 2 | 6 / 0.060 | 5 / 0.082 |
| #1 上浦福旺 | 3 | 2 / 0.185 | 2 / 0.195 |

Overrated Top-2 review: #5 有情有義 (actual 4, p=0.272).
Pre-race signal review: #12 爆竹: form_line 96.0 (+6.7 vs field), class_advantage 72.3 (+4.8 vs field)；#3 紅海勁: race_shape 75.0 (+11.7 vs field), form_line 95.0 (+5.7 vs field)；#1 上浦福旺: race_shape 81.0 (+17.7 vs field), stability 70.0 (+13.8 vs field).
Cause assessment: challenger reordering or race-specific residual.
Systematicity: this pattern occurs in 13 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-10 R6 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 跑馬地, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #8 烈焰光芒 | 1 | 3 / 0.137 | 3 / 0.135 |
| #4 日馳千里 | 2 | 6 / 0.068 | 4 / 0.095 |
| #3 風采人生 | 3 | 1 / 0.276 | 1 / 0.239 |

Overrated Top-2 review: #2 巴閉王 (actual 4, p=0.211).
Pre-race signal review: #8 烈焰光芒: trainer_signal 81.6 (+9.8 vs field), form_line 96.0 (+8.8 vs field)；#4 日馳千里: race_shape 78.2 (+16.6 vs field), form_line 96.0 (+8.8 vs field)；#3 風采人生: stability 74.7 (+16.6 vs field), trainer_signal 87.0 (+15.2 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-10 R7 — model Top-2 hits 0, Matrix 1

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **normal-result cohort**. Venue 跑馬地, Turf, 1800m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #5 極光之子 | 1 | 10 / 0.032 | 10 / 0.027 |
| #11 將義 | 2 | 3 / 0.153 | 2 / 0.142 |
| #2 川河耀駒 | 3 | 6 / 0.071 | 6 / 0.102 |

Overrated Top-2 review: #3 豐辰 (actual 4, p=0.217)；#10 大千雄心 (actual 7, p=0.158).
Pre-race signal review: #5 極光之子: trainer_signal 76.0 (+6.6 vs field)；#11 將義: race_shape 82.0 (+18.3 vs field), sectional 61.8 (+4.0 vs field)；#2 川河耀駒: race_shape 81.2 (+17.5 vs field), form_line 96.0 (+6.6 vs field).
Cause assessment: available pre-race Matrix signals did not place enough contenders in the competitive tier.
Systematicity: this pattern occurs in 37 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-10 R9 — model Top-2 hits 1, Matrix 2

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 跑馬地, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #11 觀眾之力 | 1 | 1 / 0.230 | 1 / 0.232 |
| #1 東來欣賞 | 2 | 3 / 0.153 | 2 / 0.174 |
| #4 馬達 | 3 | 5 / 0.077 | 5 / 0.075 |

Overrated Top-2 review: #6 勇霸龍 (actual 4, p=0.156).
Pre-race signal review: #11 觀眾之力: race_shape 80.0 (+17.3 vs field), trainer_signal 87.0 (+16.7 vs field)；#1 東來欣賞: race_shape 81.8 (+19.1 vs field), stability 77.6 (+16.2 vs field)；#4 馬達: sectional 72.4 (+11.9 vs field), stability 73.2 (+11.7 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-13 R2 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #8 鄉村樂韻 | 1 | 2 / 0.169 | 1 / 0.159 |
| #4 果然僥倖 | 2 | 8 / 0.039 | 7 / 0.052 |
| #12 朗日雪峰 | 3 | 5 / 0.106 | 6 / 0.093 |

Overrated Top-2 review: #3 機械騎士 (actual 8, p=0.185).
Pre-race signal review: #8 鄉村樂韻: sectional 68.0 (+11.9 vs field), trainer_signal 77.2 (+9.8 vs field)；#4 果然僥倖: class_advantage 74.1 (+6.3 vs field), horse_health 71.7 (+3.0 vs field)；#12 朗日雪峰: race_shape 70.8 (+7.9 vs field), class_advantage 72.3 (+4.5 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-13 R6 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1400m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #1 百勝威龍 | 1 | 5 / 0.081 | 6 / 0.090 |
| #11 華麗再贏 | 2 | 1 / 0.193 | 1 / 0.147 |
| #9 遨遊波士 | 3 | 4 / 0.105 | 4 / 0.099 |

Overrated Top-2 review: #3 卓越蒨鋒 (actual 8, p=0.138).
Pre-race signal review: #1 百勝威龍: stability 64.7 (+10.1 vs field), form_line 96.0 (+7.5 vs field)；#11 華麗再贏: trainer_signal 82.5 (+13.1 vs field), stability 65.9 (+11.4 vs field)；#9 遨遊波士: form_line 96.0 (+7.5 vs field), race_shape 65.9 (+5.8 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-13 R7 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #3 巴閉精 | 1 | 1 / 0.274 | 1 / 0.211 |
| #6 利高八斗 | 2 | 3 / 0.141 | 3 / 0.123 |
| #1 鼓浪好友 | 3 | 4 / 0.074 | 4 / 0.100 |

Overrated Top-2 review: #5 巧眼光 (actual 9, p=0.176).
Pre-race signal review: #3 巴閉精: trainer_signal 87.0 (+18.4 vs field), stability 78.0 (+15.6 vs field)；#6 利高八斗: stability 79.5 (+17.2 vs field), trainer_signal 73.9 (+5.4 vs field)；#1 鼓浪好友: form_line 96.0 (+13.4 vs field), race_shape 71.2 (+9.3 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-13 R8 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1600m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #2 太陽勇士 | 1 | 4 / 0.113 | 4 / 0.116 |
| #7 一起美麗 | 2 | 2 / 0.199 | 2 / 0.178 |
| #1 睿盛人生 | 3 | 5 / 0.074 | 5 / 0.083 |

Overrated Top-2 review: #3 包裝福星 (actual 6, p=0.252).
Pre-race signal review: #2 太陽勇士: race_shape 70.1 (+6.5 vs field)；#7 一起美麗: sectional 68.0 (+7.6 vs field), trainer_signal 78.3 (+6.2 vs field)；#1 睿盛人生: trainer_signal 80.5 (+8.4 vs field), race_shape 66.7 (+3.2 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-13 R11 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1400m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #12 櫻花酒杯 | 1 | 3 / 0.142 | 3 / 0.121 |
| #3 綠野飛馳 | 2 | 2 / 0.151 | 2 / 0.152 |
| #4 超勁赤兔 | 3 | 6 / 0.069 | 7 / 0.069 |

Overrated Top-2 review: #7 友瑩亮 (actual 5, p=0.175).
Pre-race signal review: #12 櫻花酒杯: stability 75.3 (+13.6 vs field), trainer_signal 78.3 (+7.4 vs field)；#3 綠野飛馳: trainer_signal 84.8 (+13.9 vs field), form_line 96.0 (+9.6 vs field)；#4 超勁赤兔: sectional 68.0 (+10.7 vs field), stability 71.6 (+9.9 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-21 R1 — model Top-2 hits 0, Matrix 1

Classification: **ML reordering degraded Matrix contender**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1000m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #5 極速神影 | 1 | 7 / 0.057 | 6 / 0.063 |
| #7 致力之城 | 2 | 3 / 0.152 | 1 / 0.139 |
| #9 紅海旺 | 3 | 11 / 0.043 | 5 / 0.066 |

Overrated Top-2 review: #2 盈智多寶 (actual 10, p=0.157)；#8 將傲 (actual 4, p=0.156).
Pre-race signal review: #5 極速神影: stability 69.4 (+12.3 vs field), horse_health 74.0 (+5.6 vs field)；#7 致力之城: trainer_signal 79.2 (+9.3 vs field), stability 66.4 (+9.2 vs field)；#9 紅海旺: form_line 94.0 (+19.4 vs field), race_shape 68.0 (+5.1 vs field).
Cause assessment: challenger reordering or race-specific residual.
Systematicity: this pattern occurs in 13 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-21 R3 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #1 包裝明將 | 1 | 3 / 0.110 | 2 / 0.111 |
| #5 祥勝鷹駒 | 2 | 2 / 0.114 | 4 / 0.076 |
| #8 彪形勇將 | 3 | 14 / 0.012 | 14 / 0.017 |

Overrated Top-2 review: #2 博愛先鋒 (actual 4, p=0.290).
Pre-race signal review: #1 包裝明將: stability 71.2 (+17.0 vs field), class_advantage 74.1 (+9.6 vs field)；#5 祥勝鷹駒: stability 61.0 (+6.8 vs field), trainer_signal 75.8 (+6.2 vs field)；#8 彪形勇將: no ≥3-point above-field Matrix dimension.
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-21 R4 — model Top-2 hits 1, Matrix 1

Classification: **ML reordering degraded Matrix contender**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #2 超和平 | 1 | 6 / 0.053 | 5 / 0.061 |
| #3 鋁神 | 2 | 1 / 0.249 | 1 / 0.201 |
| #11 馬鳳凰 | 3 | 12 / 0.034 | 10 / 0.050 |

Overrated Top-2 review: #7 熱氣球 (actual 10, p=0.214).
Pre-race signal review: #2 超和平: form_line 92.0 (+9.9 vs field), stability 59.8 (+5.3 vs field)；#3 鋁神: sectional 72.2 (+13.3 vs field), trainer_signal 80.3 (+12.1 vs field)；#11 馬鳳凰: class_advantage 70.8 (+8.7 vs field), horse_health 72.0 (+4.4 vs field).
Cause assessment: challenger reordering or race-specific residual.
Systematicity: this pattern occurs in 13 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-21 R5 — model Top-2 hits 1, Matrix 0

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1600m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #3 逍遙騎士 | 1 | 2 / 0.155 | 3 / 0.131 |
| #4 包裝戰仕 | 2 | 7 / 0.040 | 11 / 0.036 |
| #12 好運年 | 3 | 5 / 0.071 | 5 / 0.084 |

Overrated Top-2 review: #2 深心星 (actual 5, p=0.267).
Pre-race signal review: #3 逍遙騎士: stability 67.6 (+13.3 vs field), race_shape 71.9 (+12.0 vs field)；#4 包裝戰仕: trainer_signal 82.5 (+11.0 vs field)；#12 好運年: stability 64.5 (+10.2 vs field), form_line 96.0 (+6.2 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-27 R3 — model Top-2 hits 0, Matrix 0

Classification: **ML reordering degraded Matrix contender**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #2 正極 | 1 | 6 / 0.093 | 5 / 0.097 |
| #5 千杯敬典 | 2 | 8 / 0.054 | 7 / 0.068 |
| #8 合夥智能 | 3 | 7 / 0.067 | 9 / 0.047 |

Overrated Top-2 review: #10 小魔怪 (actual 7, p=0.171)；#11 嘉應光彩 (actual 5, p=0.126).
Pre-race signal review: #2 正極: trainer_signal 82.5 (+13.1 vs field), form_line 96.0 (+9.7 vs field)；#5 千杯敬典: form_line 96.0 (+9.7 vs field), class_advantage 72.3 (+5.2 vs field)；#8 合夥智能: stability 59.8 (+6.7 vs field).
Cause assessment: challenger reordering or race-specific residual.
Systematicity: this pattern occurs in 13 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-27 R4 — model Top-2 hits 1, Matrix 2

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 2000m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #7 佰勝金龍 | 1 | 3 / 0.091 | 2 / 0.095 |
| #14 禾道威 | 2 | 4 / 0.088 | 4 / 0.087 |
| #4 安可 | 3 | 1 / 0.266 | 1 / 0.204 |

Overrated Top-2 review: #6 風火恆雲 (actual 11, p=0.093).
Pre-race signal review: #7 佰勝金龍: stability 68.5 (+9.6 vs field), sectional 66.2 (+7.8 vs field)；#14 禾道威: race_shape 72.6 (+13.7 vs field), class_advantage 72.3 (+3.5 vs field)；#4 安可: trainer_signal 87.0 (+16.3 vs field), sectional 70.6 (+12.2 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-27 R5 — model Top-2 hits 0, Matrix 0

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, AWT, 1650m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #10 午夜快車 | 1 | 5 / 0.071 | 5 / 0.070 |
| #12 林寶精神 | 2 | 10 / 0.042 | 11 / 0.047 |
| #4 超加加 | 3 | 3 / 0.105 | 3 / 0.099 |

Overrated Top-2 review: #2 奮鬥心 (actual 5, p=0.192)；#5 精彩動力 (actual 6, p=0.143).
Pre-race signal review: #10 午夜快車: stability 58.5 (+3.9 vs field)；#12 林寶精神: horse_health 73.8 (+4.4 vs field), class_advantage 72.3 (+4.3 vs field)；#4 超加加: race_shape 72.6 (+12.7 vs field), stability 61.5 (+7.0 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-27 R6 — model Top-2 hits 0, Matrix 0

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #8 嘉應駿馬 | 1 | 3 / 0.097 | 3 / 0.085 |
| #4 老鼠斑 | 2 | 6 / 0.062 | 9 / 0.058 |
| #1 怡昌光輝 | 3 | 5 / 0.083 | 5 / 0.079 |

Overrated Top-2 review: #3 風采人生 (actual 10, p=0.241)；#10 快樂高球 (actual 5, p=0.113).
Pre-race signal review: #8 嘉應駿馬: trainer_signal 79.2 (+7.9 vs field), stability 60.8 (+4.1 vs field)；#4 老鼠斑: trainer_signal 80.5 (+9.1 vs field), sectional 64.4 (+3.5 vs field)；#1 怡昌光輝: race_shape 70.1 (+9.7 vs field), trainer_signal 78.2 (+6.9 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-27 R8 — model Top-2 hits 0, Matrix 0

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1000m, Class 1.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #4 顏色之皇 | 1 | 9 / 0.054 | 9 / 0.065 |
| #7 魔術控制 | 2 | 3 / 0.125 | 3 / 0.109 |
| #3 天天同樂 | 3 | 4 / 0.118 | 4 / 0.104 |

Overrated Top-2 review: #8 勇敢巨星 (actual 11, p=0.174)；#2 星際快車 (actual 5, p=0.162).
Pre-race signal review: #4 顏色之皇: class_advantage 75.1 (+3.7 vs field)；#7 魔術控制: stability 65.7 (+4.2 vs field), trainer_signal 72.8 (+4.1 vs field)；#3 天天同樂: stability 69.1 (+7.7 vs field), trainer_signal 74.5 (+5.8 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-06-27 R9 — model Top-2 hits 1, Matrix 1

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **normal-result cohort**. Venue 沙田, AWT, 1650m, Class 3.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #1 精英雄心 | 1 | 2 / 0.141 | 2 / 0.123 |
| #14 正義波 | 2 | 10 / 0.045 | 11 / 0.049 |
| #12 都靈福星 | 3 | 11 / 0.037 | 8 / 0.061 |

Overrated Top-2 review: #8 自動自覺 (actual 5, p=0.238).
Pre-race signal review: #1 精英雄心: race_shape 71.0 (+10.0 vs field), trainer_signal 78.2 (+8.0 vs field)；#14 正義波: no ≥3-point above-field Matrix dimension；#12 都靈福星: form_line 96.0 (+9.8 vs field), race_shape 67.0 (+6.0 vs field).
Cause assessment: available pre-race Matrix signals did not place enough contenders in the competitive tier.
Systematicity: this pattern occurs in 37 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-07-01 R4 — model Top-2 hits 0, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1000m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #2 拉合爾 | 1 | 3 / 0.127 | 2 / 0.156 |
| #3 凝聚美麗 | 2 | 8 / 0.049 | 5 / 0.073 |
| #7 赤兔再世 | 3 | 4 / 0.106 | 4 / 0.074 |

Overrated Top-2 review: #13 天天更好 (actual 10, p=0.209)；#4 升升雙息 (actual 8, p=0.139).
Pre-race signal review: #2 拉合爾: form_line 96.0 (+18.8 vs field), sectional 72.4 (+12.2 vs field)；#3 凝聚美麗: form_line 96.0 (+18.8 vs field), class_advantage 74.1 (+8.8 vs field)；#7 赤兔再世: trainer_signal 77.2 (+8.1 vs field), race_shape 69.6 (+6.7 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-07-01 R7 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1000m, Class 3.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #6 團結勇士 | 1 | 7 / 0.078 | 7 / 0.079 |
| #12 幸運糖 | 2 | 1 / 0.154 | 1 / 0.132 |
| #2 會長之寶 | 3 | 3 / 0.120 | 3 / 0.114 |

Overrated Top-2 review: #5 精彩福星 (actual 4, p=0.150).
Pre-race signal review: #6 團結勇士: stability 61.0 (+7.7 vs field), class_advantage 74.1 (+6.5 vs field)；#12 幸運糖: stability 72.6 (+19.3 vs field), sectional 69.8 (+7.9 vs field)；#2 會長之寶: stability 65.4 (+12.1 vs field), class_advantage 74.1 (+6.5 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-07-01 R8 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1400m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #3 嵐臣 | 1 | 2 / 0.137 | 2 / 0.132 |
| #4 美麗大獎 | 2 | 3 / 0.130 | 3 / 0.105 |
| #7 龍城強將 | 3 | 9 / 0.044 | 8 / 0.058 |

Overrated Top-2 review: #10 挺秀弘利 (actual 5, p=0.206).
Pre-race signal review: #3 嵐臣: stability 72.7 (+18.3 vs field), form_line 96.0 (+13.2 vs field)；#4 美麗大獎: race_shape 70.2 (+9.6 vs field), trainer_signal 78.3 (+9.0 vs field)；#7 龍城強將: class_advantage 74.1 (+9.4 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-07-01 R9 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1600m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #8 旌採 | 1 | 1 / 0.192 | 1 / 0.188 |
| #11 幸運威龍 | 2 | 8 / 0.055 | 8 / 0.061 |
| #12 君達得 | 3 | 3 / 0.117 | 4 / 0.103 |

Overrated Top-2 review: #13 富裕君子 (actual 8, p=0.155).
Pre-race signal review: #8 旌採: sectional 75.0 (+15.5 vs field), trainer_signal 80.5 (+9.7 vs field)；#11 幸運威龍: form_line 96.0 (+9.2 vs field), trainer_signal 76.7 (+5.9 vs field)；#12 君達得: race_shape 70.6 (+11.3 vs field), class_advantage 75.6 (+7.1 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-07-01 R10 — model Top-2 hits 1, Matrix 2

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1600m, Class 3.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #3 一生好彩 | 1 | 3 / 0.175 | 2 / 0.178 |
| #2 活力拍檔 | 2 | 1 / 0.240 | 1 / 0.187 |
| #13 北斗福星 | 3 | 10 / 0.024 | 10 / 0.033 |

Overrated Top-2 review: #6 細水長流 (actual 5, p=0.181).
Pre-race signal review: #3 一生好彩: race_shape 72.2 (+12.2 vs field), trainer_signal 80.3 (+10.5 vs field)；#2 活力拍檔: stability 74.0 (+17.4 vs field), sectional 70.3 (+10.9 vs field)；#13 北斗福星: no ≥3-point above-field Matrix dimension.
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-07-01 R11 — model Top-2 hits 1, Matrix 2

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1200m, Class 3.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #7 馬達 | 1 | 3 / 0.164 | 2 / 0.148 |
| #4 金金小子 | 2 | 7 / 0.056 | 7 / 0.073 |
| #3 㩒住贏 | 3 | 1 / 0.196 | 1 / 0.166 |

Overrated Top-2 review: #2 財將 (actual 12, p=0.170).
Pre-race signal review: #7 馬達: stability 73.5 (+10.8 vs field), sectional 69.1 (+8.6 vs field)；#4 金金小子: form_line 96.0 (+11.6 vs field), class_advantage 74.1 (+5.9 vs field)；#3 㩒住贏: stability 83.0 (+20.3 vs field), sectional 73.4 (+12.9 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-07-04 R4 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1200m, Class 2.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #4 扶搖勢勁 | 1 | 2 / 0.220 | 1 / 0.201 |
| #6 巴基之勝 | 2 | 5 / 0.079 | 5 / 0.104 |
| #3 競駿輝煌 | 3 | 4 / 0.130 | 4 / 0.157 |

Overrated Top-2 review: #5 興馳千里 (actual 6, p=0.243).
Pre-race signal review: #4 扶搖勢勁: stability 71.9 (+9.6 vs field), trainer_signal 78.2 (+5.3 vs field)；#6 巴基之勝: form_line 92.0 (+11.0 vs field), class_advantage 74.1 (+4.6 vs field)；#3 競駿輝煌: trainer_signal 87.0 (+14.0 vs field), form_line 84.0 (+3.0 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-07-04 R5 — model Top-2 hits 1, Matrix 2

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1400m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #11 三代至醒 | 1 | 11 / 0.033 | 10 / 0.041 |
| #4 卓越蒨鋒 | 2 | 1 / 0.170 | 1 / 0.163 |
| #13 飛躍成就 | 3 | 3 / 0.120 | 2 / 0.109 |

Overrated Top-2 review: #8 有情有義 (actual 12, p=0.152).
Pre-race signal review: #11 三代至醒: sectional 63.8 (+4.9 vs field), horse_health 72.0 (+3.6 vs field)；#4 卓越蒨鋒: form_line 96.0 (+10.3 vs field), trainer_signal 79.3 (+9.6 vs field)；#13 飛躍成就: stability 69.1 (+14.9 vs field), class_advantage 75.6 (+8.8 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-07-04 R6 — model Top-2 hits 1, Matrix 1

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **normal-result cohort**. Venue 沙田, AWT, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #7 致力之城 | 1 | 2 / 0.176 | 2 / 0.176 |
| #6 砂漿麒星 | 2 | 8 / 0.040 | 7 / 0.057 |
| #11 瑤瑤日上 | 3 | 9 / 0.039 | 8 / 0.052 |

Overrated Top-2 review: #1 葳莉非凡 (actual 11, p=0.246).
Pre-race signal review: #7 致力之城: sectional 69.8 (+10.4 vs field), stability 71.0 (+8.5 vs field)；#6 砂漿麒星: sectional 66.5 (+7.2 vs field), form_line 86.0 (+6.1 vs field)；#11 瑤瑤日上: race_shape 69.8 (+8.6 vs field), form_line 84.0 (+4.1 vs field).
Cause assessment: available pre-race Matrix signals did not place enough contenders in the competitive tier.
Systematicity: this pattern occurs in 37 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-07-04 R10 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1200m, Class 3.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #7 實力股 | 1 | 4 / 0.090 | 5 / 0.070 |
| #6 巴閉精 | 2 | 1 / 0.294 | 2 / 0.256 |
| #12 辣得準 | 3 | 3 / 0.102 | 3 / 0.102 |

Overrated Top-2 review: #1 精彩駿將 (actual 4, p=0.259).
Pre-race signal review: #7 實力股: race_shape 68.2 (+7.8 vs field), trainer_signal 76.2 (+5.9 vs field)；#6 巴閉精: stability 81.2 (+20.9 vs field), trainer_signal 87.0 (+16.6 vs field)；#12 辣得準: class_advantage 75.6 (+8.8 vs field), trainer_signal 78.3 (+7.9 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-07-08 R1 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 跑馬地, Turf, 1000m, Class 5.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #3 萬眾開心 | 1 | 1 / 0.169 | 1 / 0.196 |
| #1 鄉村樂韻 | 2 | 5 / 0.094 | 8 / 0.069 |
| #5 洛河 | 3 | 7 / 0.066 | 6 / 0.077 |

Overrated Top-2 review: #12 天火同德 (actual 8, p=0.146).
Pre-race signal review: #3 萬眾開心: race_shape 75.0 (+12.8 vs field), form_line 96.0 (+11.8 vs field)；#1 鄉村樂韻: stability 67.3 (+12.0 vs field), sectional 70.1 (+9.6 vs field)；#5 洛河: no ≥3-point above-field Matrix dimension.
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-07-08 R2 — model Top-2 hits 0, Matrix 0

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 跑馬地, Turf, 1650m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #1 暴風之子 | 1 | 4 / 0.092 | 5 / 0.096 |
| #6 贏玥 | 2 | 6 / 0.077 | 7 / 0.053 |
| #8 越駿聯歡 | 3 | 5 / 0.085 | 4 / 0.098 |

Overrated Top-2 review: #2 川河帥駒 (actual 9, p=0.224)；#4 領航天子 (actual 4, p=0.172).
Pre-race signal review: #1 暴風之子: sectional 65.5 (+6.9 vs field), stability 60.0 (+6.2 vs field)；#6 贏玥: stability 64.9 (+11.1 vs field), sectional 65.9 (+7.2 vs field)；#8 越駿聯歡: race_shape 71.0 (+9.0 vs field), sectional 66.1 (+7.5 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-07-08 R3 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 跑馬地, Turf, 1000m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #11 福進 | 1 | 2 / 0.145 | 3 / 0.145 |
| #4 美麗登場 | 2 | 4 / 0.139 | 4 / 0.110 |
| #8 天火同人 | 3 | 3 / 0.143 | 2 / 0.161 |

Overrated Top-2 review: #1 鴻圖新星 (actual 4, p=0.227).
Pre-race signal review: #11 福進: trainer_signal 84.8 (+11.7 vs field), sectional 64.4 (+8.5 vs field)；#4 美麗登場: stability 70.7 (+18.7 vs field), trainer_signal 87.0 (+13.9 vs field)；#8 天火同人: stability 64.7 (+12.6 vs field), sectional 67.7 (+11.9 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-07-08 R5 — model Top-2 hits 1, Matrix 1

Classification: **ML reordering degraded Matrix contender**. Predictability review: **normal-result cohort**. Venue 跑馬地, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #9 至合拍 | 1 | 1 / 0.157 | 1 / 0.165 |
| #2 路路勁 | 2 | 6 / 0.070 | 6 / 0.082 |
| #12 頑童 | 3 | 7 / 0.067 | 5 / 0.083 |

Overrated Top-2 review: #6 勝多多 (actual 5, p=0.137).
Pre-race signal review: #9 至合拍: race_shape 75.8 (+13.6 vs field), sectional 70.6 (+6.9 vs field)；#2 路路勁: form_line 96.0 (+11.2 vs field), race_shape 67.0 (+4.8 vs field)；#12 頑童: sectional 69.1 (+5.4 vs field), class_advantage 67.0 (+3.9 vs field).
Cause assessment: challenger reordering or race-specific residual.
Systematicity: this pattern occurs in 13 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-07-08 R7 — model Top-2 hits 0, Matrix 0

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 跑馬地, Turf, 1000m, Class 3.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #8 舞林寶典 | 1 | 9 / 0.041 | 10 / 0.040 |
| #1 燭光晚餐 | 2 | 5 / 0.100 | 4 / 0.092 |
| #3 品德寶寶 | 3 | 3 / 0.144 | 5 / 0.086 |

Overrated Top-2 review: #2 連連幸運 (actual 9, p=0.199)；#5 加州本事 (actual 5, p=0.167).
Pre-race signal review: #8 舞林寶典: trainer_signal 84.8 (+11.2 vs field), form_line 89.0 (+5.9 vs field)；#1 燭光晚餐: stability 70.4 (+11.4 vs field), race_shape 66.8 (+5.3 vs field)；#3 品德寶寶: stability 73.4 (+14.3 vs field), trainer_signal 87.0 (+13.4 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-07-12 R1 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1800m, Class 5.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #1 特別美麗 | 1 | 4 / 0.086 | 6 / 0.079 |
| #11 龍又生 | 2 | 2 / 0.127 | 2 / 0.107 |
| #2 光輝歲月 | 3 | 3 / 0.088 | 4 / 0.083 |

Overrated Top-2 review: #4 連連好運 (actual 5, p=0.255).
Pre-race signal review: #1 特別美麗: sectional 60.4 (+7.3 vs field), stability 59.4 (+6.8 vs field)；#11 龍又生: stability 65.0 (+12.4 vs field), class_advantage 70.3 (+8.2 vs field)；#2 光輝歲月: race_shape 68.0 (+7.4 vs field), stability 57.6 (+5.1 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-07-12 R3 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1400m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #6 手機錶能 | 1 | 2 / 0.174 | 2 / 0.159 |
| #9 嘉應駿昇 | 2 | 10 / 0.025 | 12 / 0.030 |
| #10 遨遊波士 | 3 | 3 / 0.131 | 3 / 0.139 |

Overrated Top-2 review: #13 勤德皆備 (actual 8, p=0.250).
Pre-race signal review: #6 手機錶能: sectional 70.0 (+14.0 vs field), stability 61.9 (+9.6 vs field)；#9 嘉應駿昇: form_line 96.0 (+11.1 vs field)；#10 遨遊波士: stability 64.4 (+12.0 vs field), form_line 96.0 (+11.1 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-07-12 R5 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #10 綠色鐵驥 | 1 | 11 / 0.029 | 11 / 0.034 |
| #12 快樂高球 | 2 | 2 / 0.143 | 2 / 0.134 |
| #1 渡月橋 | 3 | 3 / 0.138 | 4 / 0.117 |

Overrated Top-2 review: #3 嘉應駿馬 (actual 6, p=0.184).
Pre-race signal review: #10 綠色鐵驥: no ≥3-point above-field Matrix dimension；#12 快樂高球: stability 69.5 (+15.8 vs field), class_advantage 70.3 (+9.8 vs field)；#1 渡月橋: trainer_signal 87.2 (+14.6 vs field), form_line 96.0 (+9.9 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-07-12 R10 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **normal-result cohort**. Venue 沙田, Turf, 1600m, Class 3.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #13 名揚四海 | 1 | 7 / 0.066 | 6 / 0.077 |
| #4 一生好彩 | 2 | 1 / 0.138 | 2 / 0.117 |
| #12 大回報 | 3 | 5 / 0.109 | 3 / 0.096 |

Overrated Top-2 review: #7 超勁赤兔 (actual 7, p=0.133).
Pre-race signal review: #13 名揚四海: sectional 73.4 (+10.7 vs field)；#4 一生好彩: race_shape 72.2 (+11.5 vs field), sectional 66.6 (+4.0 vs field)；#12 大回報: stability 83.4 (+18.0 vs field), class_advantage 70.3 (+5.1 vs field).
Cause assessment: competitive tier was identified; remaining error is ranking/weight calibration.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

## 2026-05-09 R1 — model Top-2 hits 1, Matrix 0

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, unknownm, Unknown.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #5 鵲橋飛昇 | 1 | 10 / 0.048 | 8 / 0.067 |
| #2 銳行星 | 2 | 2 / 0.152 | 3 / 0.123 |
| #6 永福 | 3 | 6 / 0.077 | 7 / 0.072 |

Overrated Top-2 review: #1 全能勇士 (actual 5, p=0.186).
Pre-race signal review: #5 鵲橋飛昇: race_shape 75.0 (+9.5 vs field)；#2 銳行星: trainer_signal 84.8 (+11.7 vs field)；#6 永福: no ≥3-point above-field Matrix dimension.
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 37 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #5 鵲橋飛昇 actual 1／odds 49

## 2026-05-09 R4 — model Top-2 hits 1, Matrix 1

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1000m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #10 一舖掂晒 | 1 | 10 / 0.033 | 13 / 0.014 |
| #4 支付之父 | 2 | 2 / 0.157 | 2 / 0.134 |
| #11 致力之城 | 3 | 9 / 0.040 | 10 / 0.022 |

Overrated Top-2 review: #6 鴻圖新星 (actual 12, p=0.203).
Pre-race signal review: #10 一舖掂晒: no ≥3-point above-field Matrix dimension；#4 支付之父: stability 77.9 (+19.4 vs field), race_shape 74.2 (+14.8 vs field)；#11 致力之城: trainer_signal 77.0 (+6.4 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 37 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #10 一舖掂晒 actual 1／odds 70

## 2026-05-09 R5 — model Top-2 hits 0, Matrix 0

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #4 君子 | 1 | 12 / 0.022 | 12 / 0.026 |
| #6 老鼠斑 | 2 | 8 / 0.058 | 10 / 0.035 |
| #2 心雄雄 | 3 | 3 / 0.113 | 3 / 0.117 |

Overrated Top-2 review: #3 輝灑自如 (actual 9, p=0.204)；#9 星辰千帥 (actual 5, p=0.120).
Pre-race signal review: #4 君子: no ≥3-point above-field Matrix dimension；#6 老鼠斑: stability 61.2 (+8.4 vs field)；#2 心雄雄: race_shape 74.2 (+11.4 vs field), form_line 84.0 (+4.8 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 37 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #4 君子 actual 1／odds 158 | major_incident: #3 輝灑自如: 9 3 輝灑自如 (L281) 見習騎師袁幸堯表示，坐騎在閘內煩躁不安，儘管能夠領放，但在該位置下走勢欠佳。她又說，坐騎於直路上對催策毫無反應，表現令人失望。練馬師姚本輝表示，此駒於是賽前的表現令他滿意。他說，他認為此駒未能適應「好至黏地」的場地狀況，尤其是牠陣上走勢欠佳，數度將頭低俯。賽後立即接受獸醫檢查，內窺鏡檢查顯示此駒的氣管內有很多痰。「輝灑自如」上

## 2026-05-09 R6 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1400m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #6 龍傲綾羅 | 1 | 1 / 0.161 | 3 / 0.112 |
| #7 文明福星 | 2 | 5 / 0.087 | 1 / 0.133 |
| #3 將傲 | 3 | 10 / 0.040 | 10 / 0.042 |

Overrated Top-2 review: #11 有情有義 (actual 6, p=0.157).
Pre-race signal review: #6 龍傲綾羅: trainer_signal 87.0 (+17.3 vs field), stability 65.2 (+11.5 vs field)；#7 文明福星: race_shape 82.0 (+21.6 vs field), stability 64.7 (+11.0 vs field)；#3 將傲: race_shape 64.2 (+3.8 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: interference: #9 開心旺財: 8 9 開心旺財 (L045) 接近三百五十米處時向內斜跑，與「龍傲綾羅」互相觸碰。三百五十米處至二百五十米處之間在靠近「笑必勝」處於窘境之際受困而未能望空。

## 2026-05-09 R7 — model Top-2 hits 0, Matrix 0

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1600m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #13 金鑽精靈 | 1 | 5 / 0.070 | 10 / 0.051 |
| #8 好運年 | 2 | 12 / 0.037 | 8 / 0.066 |
| #11 君達得 | 3 | 13 / 0.034 | 12 / 0.031 |

Overrated Top-2 review: #1 威武年代 (actual 14, p=0.160)；#5 大千雄心 (actual 9, p=0.159).
Pre-race signal review: #13 金鑽精靈: stability 74.3 (+16.7 vs field), class_advantage 75.6 (+9.1 vs field)；#8 好運年: race_shape 76.6 (+17.6 vs field), form_line 96.0 (+6.3 vs field)；#11 君達得: class_advantage 75.6 (+9.1 vs field), form_line 96.0 (+6.3 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 37 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: major_incident: #1 威武年代: 14 1 威武年代 (J451) 何澤堯表示，坐騎在入直路後受催策並顯著轉弱，但他未能就坐騎令人失望的表現提供任何解釋。賽後立即接受獸醫檢查，並無發現任何明顯異常之處。小組認為與近仗相比，「威武年代」今仗的表現令人失望。「威武年代」必須試閘及格，並且通過獸醫檢驗後，才可再次出賽。

## 2026-05-13 R4 — model Top-2 hits 0, Matrix 0

Classification: **ML reordering degraded Matrix contender**. Predictability review: **abnormal/outsider flagged**. Venue 跑馬地, Turf, 1650m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #4 上浦福旺 | 1 | 11 / 0.031 | 12 / 0.026 |
| #10 滿洛城 | 2 | 5 / 0.102 | 3 / 0.099 |
| #11 獎星 | 3 | 6 / 0.089 | 5 / 0.092 |

Overrated Top-2 review: #5 大千氣象 (actual 5, p=0.185)；#1 勁進駒 (actual 12, p=0.142).
Pre-race signal review: #4 上浦福旺: no ≥3-point above-field Matrix dimension；#10 滿洛城: race_shape 77.2 (+12.5 vs field), stability 66.3 (+8.2 vs field)；#11 獎星: class_advantage 72.3 (+4.2 vs field), horse_health 73.2 (+4.0 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 13 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: interference: #1 勁進駒: 12 1 勁進駒 (J384) 起步後不久發生碰撞。接近三百五十米處時在「滿洛城」與開始墮退的「翠湖烈風」之間未能望空之際大力勒避。被查詢時，潘頓表示，他獲指示讓坐騎上前及居於預期領放馬「睿智多寶」外側。他說，他催策坐騎上前及將坐騎置於「翠湖烈風」外側，其後等待「翠湖烈風」佔取「睿智多寶」之後有遮擋的位置，因為他察覺到策騎「翠湖烈風」的見習騎師黃寶妮望向她的

## 2026-05-13 R7 — model Top-2 hits 0, Matrix 0

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 跑馬地, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #11 驕陽雄心 | 1 | 8 / 0.055 | 6 / 0.067 |
| #3 縱橫天下 | 2 | 10 / 0.037 | 8 / 0.060 |
| #1 競駿非凡 | 3 | 9 / 0.053 | 10 / 0.047 |

Overrated Top-2 review: #6 銳目 (actual 12, p=0.196)；#12 勝在當下 (actual 4, p=0.159).
Pre-race signal review: #11 驕陽雄心: no ≥3-point above-field Matrix dimension；#3 縱橫天下: race_shape 71.8 (+9.9 vs field)；#1 競駿非凡: trainer_signal 75.0 (+3.2 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 37 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #3 縱橫天下 actual 2／odds 36 | major_incident: #6 銳目: 12 6 銳目 (L068) 接近六百米處時與「福進」互相觸碰，當時「福進」在搶口之際向外斜跑。潘頓表示，他於早段催策坐騎以嘗試佔取前列位置。他說，坐騎今仗展現的前速未如上仗，因而居於較賽前部署為後的位置。他說，坐騎經驗仍然相對較淺，中段沿途未能適應在其他馬匹之間競跑，其後在直路上墮退。賽後立即接受獸醫檢查，並無發現任何明顯異常之處。「銳目」上仗勝出，小組認

## 2026-05-13 R8 — model Top-2 hits 1, Matrix 2

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 跑馬地, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #11 馬達 | 1 | 3 / 0.140 | 2 / 0.156 |
| #1 小霸王 | 2 | 9 / 0.048 | 6 / 0.074 |
| #2 志滿同行 | 3 | 2 / 0.173 | 1 / 0.199 |

Overrated Top-2 review: #10 棒棒糖 (actual 9, p=0.185).
Pre-race signal review: #11 馬達: race_shape 80.2 (+17.7 vs field), sectional 68.6 (+5.0 vs field)；#1 小霸王: race_shape 73.8 (+11.3 vs field), sectional 69.1 (+5.6 vs field)；#2 志滿同行: race_shape 79.8 (+17.3 vs field), stability 76.3 (+16.4 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: interference: #10 棒棒糖: 9 10 棒棒糖 (J503) 出閘僅屬一般。接近二百米處時在一段短途程上在墮退的「人和家興」之後受困而未能望空。莫雷拉未能就坐騎令人失望的表現提供任何解釋。賽後立即接受獸醫檢查，並無發現任何明顯異常之處。

## 2026-05-17 R1 — model Top-2 hits 0, Matrix 0

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1800m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #6 齊歡最樂 | 1 | 4 / 0.113 | 5 / 0.095 |
| #10 捷足奔馳 | 2 | 6 / 0.059 | 6 / 0.064 |
| #7 香港精神 | 3 | 9 / 0.036 | 8 / 0.041 |

Overrated Top-2 review: #8 開心三多 (actual 6, p=0.174)；#5 富裕君子 (actual 4, p=0.152).
Pre-race signal review: #6 齊歡最樂: race_shape 71.0 (+11.6 vs field), trainer_signal 72.2 (+4.3 vs field)；#10 捷足奔馳: trainer_signal 71.7 (+3.8 vs field)；#7 香港精神: class_advantage 74.1 (+7.3 vs field), stability 59.2 (+4.0 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 37 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #7 香港精神 actual 3／odds 50

## 2026-05-17 R4 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #11 小魔怪 | 1 | 7 / 0.053 | 7 / 0.065 |
| #10 天天更好 | 2 | 2 / 0.157 | 1 / 0.186 |
| #8 你知我寶 | 3 | 4 / 0.101 | 4 / 0.101 |

Overrated Top-2 review: #1 禾道豐 (actual 4, p=0.229).
Pre-race signal review: #11 小魔怪: class_advantage 72.3 (+8.5 vs field), sectional 66.5 (+5.0 vs field)；#10 天天更好: stability 74.2 (+17.4 vs field), form_line 95.0 (+11.3 vs field)；#8 你知我寶: trainer_signal 78.2 (+7.1 vs field), race_shape 67.8 (+6.5 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: interference: #1 禾道豐: 4 1 禾道豐 (L264) 躍出時在「星光大道」與略為向外斜跑的「你知我寶」之間受擠迫之際失去平衡。四百五十米處至三百五十米處之間受困而未能望空。賽後須抽取樣本檢驗。

## 2026-05-17 R6 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #10 傑出雷霆 | 1 | 2 / 0.140 | 3 / 0.147 |
| #11 有備而戰 | 2 | 12 / 0.017 | 11 / 0.032 |
| #2 星月飛雲 | 3 | 3 / 0.129 | 2 / 0.151 |

Overrated Top-2 review: #3 健康快車 (actual 5, p=0.155).
Pre-race signal review: #10 傑出雷霆: stability 71.1 (+14.3 vs field), form_line 96.0 (+11.2 vs field)；#11 有備而戰: form_line 94.0 (+9.2 vs field)；#2 星月飛雲: form_line 96.0 (+11.2 vs field), trainer_signal 81.5 (+8.5 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #11 有備而戰 actual 2／odds 60

## 2026-05-17 R10 — model Top-2 hits 0, Matrix 1

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1400m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #10 臻至辰 | 1 | 10 / 0.038 | 8 / 0.066 |
| #8 超輕鬆 | 2 | 4 / 0.078 | 2 / 0.108 |
| #6 三甲之星 | 3 | 7 / 0.055 | 6 / 0.079 |

Overrated Top-2 review: #5 安泰 (actual 9, p=0.243)；#11 正本良心 (actual 14, p=0.141).
Pre-race signal review: #10 臻至辰: form_line 96.0 (+10.8 vs field), stability 62.6 (+9.8 vs field)；#8 超輕鬆: form_line 96.0 (+10.8 vs field), stability 59.9 (+7.1 vs field)；#6 三甲之星: sectional 69.9 (+13.1 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 37 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: major_incident: #11 正本良心: 14 11 正本良心 (L382) 於起步點被發現口內有血，其後接受獸醫檢查，獸醫認為此駒適宜出賽。在閘內煩躁不安，導致右後腿一度擱在閘廂內，其後被牽出閘廂及再度接受獸醫檢查，獸醫認為此駒適宜出賽。大部分途程在沒有遮擋下走外疊。莫雷拉表示，坐騎於早段及中段沿途走勢良佳，但在直路上受催策時轉弱。賽後立即接受獸醫檢查，並無發現任何明顯異常之處。「正本良心」包尾大

## 2026-05-20 R5 — model Top-2 hits 1, Matrix 1

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 跑馬地, Turf, 1000m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #2 財將 | 1 | 6 / 0.087 | 7 / 0.081 |
| #7 鴻圖新星 | 2 | 2 / 0.154 | 2 / 0.140 |
| #5 紅錢到 | 3 | 10 / 0.046 | 10 / 0.042 |

Overrated Top-2 review: #4 美麗登場 (actual 7, p=0.184).
Pre-race signal review: #2 財將: stability 87.9 (+28.2 vs field), race_shape 64.2 (+3.9 vs field)；#7 鴻圖新星: trainer_signal 85.9 (+15.0 vs field), sectional 63.4 (+3.8 vs field)；#5 紅錢到: sectional 66.0 (+6.5 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 37 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #5 紅錢到 actual 3／odds 33

## 2026-05-20 R9 — model Top-2 hits 0, Matrix 0

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 跑馬地, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #8 維港智能 | 1 | 12 / 0.022 | 12 / 0.019 |
| #7 扶搖勢勁 | 2 | 3 / 0.081 | 5 / 0.096 |
| #1 天天同樂 | 3 | 9 / 0.060 | 6 / 0.073 |

Overrated Top-2 review: #9 俏眼光 (actual 12, p=0.214)；#4 信心星 (actual 6, p=0.160).
Pre-race signal review: #8 維港智能: no ≥3-point above-field Matrix dimension；#7 扶搖勢勁: stability 81.5 (+13.3 vs field), form_line 94.0 (+6.1 vs field)；#1 天天同樂: race_shape 66.8 (+4.8 vs field), sectional 70.0 (+3.6 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 37 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #8 維港智能 actual 1／odds 59 | major_incident: #9 俏眼光: 12 9 俏眼光 (L003) 田泰安表示，坐騎出閘僅屬一般，居後列競跑。他說，坐騎在直路上受催策時毫無反應，表現令人失望。練馬師蔡約翰表示，他認為此駒已屆歇暑休賽之時，將會安排此駒休息。賽後立即接受獸醫檢查，並無發現任何明顯異常之處。「俏眼光」上仗勝出，小組認為此駒今仗的表現令人失望。「俏眼光」必須試閘及格，並且通過獸醫檢驗後，才可再次出賽。

## 2026-05-24 R2 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1400m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #14 金快飛飛 | 1 | 4 / 0.113 | 3 / 0.099 |
| #1 包裝明將 | 2 | 6 / 0.084 | 6 / 0.084 |
| #2 嵐臣 | 3 | 2 / 0.116 | 2 / 0.105 |

Overrated Top-2 review: #8 幸福約定 (actual 4, p=0.132).
Pre-race signal review: #14 金快飛飛: stability 65.8 (+9.8 vs field), class_advantage 71.5 (+6.6 vs field)；#1 包裝明將: stability 68.4 (+12.4 vs field), class_advantage 71.6 (+6.7 vs field)；#2 嵐臣: stability 68.7 (+12.8 vs field), race_shape 70.5 (+9.3 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: interference: #11 華麗再贏: 5 11 華麗再贏 (L087) 在起步點重新裝上左前蹄的蹄鐵，其後接受獸醫檢查，獸醫認為此駒適宜出賽，賽事因而延遲開跑。起步後不久在「隋我同來」與外閃的「嵐臣」之間受擠迫。四百米處至一百五十米處之間受困而未能望空。

## 2026-05-24 R3 — model Top-2 hits 0, Matrix 0

Classification: **ML reordering degraded Matrix contender**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #1 錶之浩瀚 | 1 | 11 / 0.037 | 11 / 0.047 |
| #2 巧眼光 | 2 | 4 / 0.095 | 3 / 0.102 |
| #14 有你有我 | 3 | 6 / 0.056 | 5 / 0.086 |

Overrated Top-2 review: #4 老鼠斑 (actual 8, p=0.202)；#12 同喜 (actual 12, p=0.140).
Pre-race signal review: #1 錶之浩瀚: sectional 62.0 (+4.9 vs field), class_advantage 71.6 (+3.6 vs field)；#2 巧眼光: form_line 96.0 (+11.1 vs field), trainer_signal 80.5 (+10.3 vs field)；#14 有你有我: form_line 96.0 (+11.1 vs field), sectional 63.6 (+6.5 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 13 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #2 巧眼光 actual 2／odds 44 || #14 有你有我 actual 3／odds 41

## 2026-05-24 R4 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #3 包裝天王 | 1 | 1 / 0.172 | 2 / 0.144 |
| #11 銀刺勇士 | 2 | 4 / 0.077 | 8 / 0.049 |
| #9 北極之錶 | 3 | 14 / 0.035 | 12 / 0.045 |

Overrated Top-2 review: #8 應龍飛影 (actual 11, p=0.166).
Pre-race signal review: #3 包裝天王: trainer_signal 84.7 (+14.0 vs field), stability 65.2 (+10.6 vs field)；#11 銀刺勇士: trainer_signal 84.8 (+14.1 vs field), class_advantage 70.8 (+5.0 vs field)；#9 北極之錶: race_shape 67.5 (+7.9 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #11 銀刺勇士 actual 2／odds 49 || #9 北極之錶 actual 3／odds 115

## 2026-05-24 R6 — model Top-2 hits 0, Matrix 0

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1400m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #5 仁仁有餘 | 1 | 3 / 0.112 | 3 / 0.113 |
| #8 馬上盈 | 2 | 5 / 0.072 | 6 / 0.072 |
| #9 共創歡欣 | 3 | 8 / 0.061 | 10 / 0.046 |

Overrated Top-2 review: #14 觀萬物 (actual 9, p=0.165)；#4 馬馳登 (actual 5, p=0.129).
Pre-race signal review: #5 仁仁有餘: trainer_signal 84.8 (+12.6 vs field), sectional 63.4 (+5.8 vs field)；#8 馬上盈: sectional 62.5 (+5.0 vs field), class_advantage 70.8 (+4.8 vs field)；#9 共創歡欣: trainer_signal 77.0 (+4.9 vs field), class_advantage 70.8 (+4.8 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: injury: #14 觀萬物: 9 14 觀萬物 (K101) 接近九百米處時收慢避開「方圓星」。潘頓表示，賽事早段及中段步速較標準時間為慢，不利坐騎發揮，坐騎因而在直路上難以追前。賽後立即接受獸醫檢查，發現此駒患有「喘鳴症」，而此駒過往也有此毛病報告。

## 2026-05-24 R7 — model Top-2 hits 0, Matrix 0

Classification: **ML reordering degraded Matrix contender**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1800m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #12 勁大威猛 | 1 | 6 / 0.076 | 7 / 0.082 |
| #13 勁好運 | 2 | 7 / 0.074 | 5 / 0.086 |
| #8 幸運派彩 | 3 | 12 / 0.035 | 13 / 0.033 |

Overrated Top-2 review: #2 友瑩光 (actual 14, p=0.131)；#3 平凡騎士 (actual 13, p=0.130).
Pre-race signal review: #12 勁大威猛: race_shape 70.1 (+9.7 vs field), form_line 96.0 (+6.1 vs field)；#13 勁好運: sectional 63.9 (+8.2 vs field), race_shape 67.7 (+7.3 vs field)；#8 幸運派彩: no ≥3-point above-field Matrix dimension.
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 13 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #13 勁好運 actual 2／odds 61 | major_incident: #2 友瑩光: 14 2 友瑩光 (K564) 起步後不久被「快路」碰撞後軀，因而失去平衡。潘頓表示，坐騎在直路上對催策毫無反應，他擔心坐騎有不妥，遂於接近三百米處時收慢坐騎。練馬師廖康銘表示，此駒於是賽前的表現令他滿意，他未能就此駒今仗的表現提供解釋。賽後立即接受獸醫檢查，並無發現任何明顯異常之處。包尾大敗而回，小組認為此駒的表現難以接受。「友瑩光」必須試閘及格，並且通過

## 2026-05-24 R8 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 2400m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #1 浪漫勇士 | 1 | 1 / 0.297 | 1 / 0.232 |
| #5 數字天文 | 2 | 5 / 0.071 | 4 / 0.109 |
| #2 大怪奇 | 3 | 7 / 0.065 | 9 / 0.056 |

Overrated Top-2 review: #9 浪漫戰神 (actual 4, p=0.223).
Pre-race signal review: #1 浪漫勇士: stability 85.5 (+16.6 vs field), trainer_signal 84.7 (+9.6 vs field)；#5 數字天文: form_line 96.0 (+9.3 vs field), sectional 67.6 (+3.6 vs field)；#2 大怪奇: race_shape 68.2 (+4.5 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #5 數字天文 actual 2／odds 40

## 2026-05-27 R1 — model Top-2 hits 1, Matrix 1

Classification: **ML reordering degraded Matrix contender**. Predictability review: **abnormal/outsider flagged**. Venue 跑馬地, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #9 本能 | 1 | 7 / 0.050 | 4 / 0.080 |
| #11 東方福寶 | 2 | 10 / 0.037 | 11 / 0.041 |
| #10 星之願 | 3 | 2 / 0.162 | 2 / 0.160 |

Overrated Top-2 review: #2 魅力星 (actual 10, p=0.295).
Pre-race signal review: #9 本能: race_shape 78.0 (+15.4 vs field), horse_health 69.8 (+3.1 vs field)；#11 東方福寶: horse_health 71.8 (+5.2 vs field), form_line 88.0 (+3.2 vs field)；#10 星之願: race_shape 76.0 (+13.4 vs field), trainer_signal 80.3 (+10.3 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 13 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: injury: #2 魅力星: 10 2 魅力星 (K052) 田泰安表示，坐騎在直路上衝刺僅屬一般，或未能適應「好至快地」的場地狀況。賽後立即接受獸醫檢查，發現此駒患有「喘鳴症」，而此駒過往也有此毛病報告。

## 2026-05-27 R2 — model Top-2 hits 1, Matrix 0

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 跑馬地, Turf, 2200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #7 捷足奔馳 | 1 | 3 / 0.132 | 5 / 0.108 |
| #8 幸運同行 | 2 | 2 / 0.140 | 4 / 0.117 |
| #9 美麗多盈 | 3 | 12 / 0.030 | 12 / 0.028 |

Overrated Top-2 review: #1 管之友 (actual 7, p=0.190).
Pre-race signal review: #7 捷足奔馳: stability 63.6 (+9.0 vs field), trainer_signal 71.7 (+5.2 vs field)；#8 幸運同行: trainer_signal 84.8 (+18.2 vs field), race_shape 66.0 (+3.5 vs field)；#9 美麗多盈: no ≥3-point above-field Matrix dimension.
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #9 美麗多盈 actual 3／odds 36

## 2026-05-27 R9 — model Top-2 hits 0, Matrix 0

Classification: **ML reordering degraded Matrix contender**. Predictability review: **abnormal/outsider flagged**. Venue 跑馬地, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #1 小霸王 | 1 | 6 / 0.060 | 5 / 0.073 |
| #5 晶晶日上 | 2 | 7 / 0.055 | 7 / 0.071 |
| #12 椒椒醒 | 3 | 12 / 0.010 | 12 / 0.009 |

Overrated Top-2 review: #7 富心星 (actual 10, p=0.268)；#9 可靠大師 (actual 12, p=0.209).
Pre-race signal review: #1 小霸王: form_line 96.0 (+6.8 vs field), stability 63.8 (+5.3 vs field)；#5 晶晶日上: stability 66.5 (+8.0 vs field), form_line 96.0 (+6.8 vs field)；#12 椒椒醒: no ≥3-point above-field Matrix dimension.
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 13 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #12 椒椒醒 actual 3／odds 118 | major_incident: #7 富心星: 10 7 富心星 (K125) 莫雷拉表示，坐騎直路上在催策下毫無反應，走勢平平。賽後立即接受獸醫檢查，並無發現任何明顯異常之處。小組認為與近仗相比，「富心星」今仗的表現令人失望。「富心星」必須試閘及格，並且通過獸醫檢驗後，才可再次出賽。 || #9 可靠大師: 12 9 可靠大師 (K283) 接近三百米處時在墮退之際內閃，導致騎師潘頓須停止催策並修正坐騎。潘頓表示，坐騎中段在居「富心星」之後時過於搶口，不願穩定走勢。他說，坐騎因而在直路上未能以勁勢衝刺。賽後立即接受獸醫檢查，並無發現任何明顯異常之處。「可靠大師」上仗勝出，小組認為此駒今仗的表現令人失望。「可靠大師」必須試閘及格，並且通過獸醫檢驗後，才可再次出賽。

## 2026-06-03 R1 — model Top-2 hits 1, Matrix 1

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 跑馬地, Turf, 1650m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #3 富裕君子 | 1 | 1 / 0.351 | 1 / 0.268 |
| #12 不假外求 | 2 | 7 / 0.044 | 7 / 0.046 |
| #6 電訊驕陽 | 3 | 12 / 0.023 | 12 / 0.018 |

Overrated Top-2 review: #9 華美之威 (actual 5, p=0.176).
Pre-race signal review: #3 富裕君子: trainer_signal 87.0 (+20.1 vs field), race_shape 79.8 (+17.0 vs field)；#12 不假外求: horse_health 73.8 (+4.0 vs field)；#6 電訊驕陽: class_advantage 70.8 (+3.8 vs field), stability 56.6 (+3.2 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 37 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #12 不假外求 actual 2／odds 38

## 2026-06-03 R3 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 跑馬地, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #7 博愛先鋒 | 1 | 2 / 0.147 | 2 / 0.135 |
| #12 有你有我 | 2 | 4 / 0.122 | 6 / 0.101 |
| #4 驕陽雄心 | 3 | 7 / 0.066 | 8 / 0.048 |

Overrated Top-2 review: #3 團長好 (actual 10, p=0.192).
Pre-race signal review: #7 博愛先鋒: stability 67.5 (+11.6 vs field), sectional 73.4 (+10.2 vs field)；#12 有你有我: trainer_signal 74.8 (+5.4 vs field), stability 60.8 (+4.9 vs field)；#4 驕陽雄心: stability 70.9 (+15.0 vs field), sectional 67.8 (+4.6 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: major_incident: #3 團長好: 10 3 團長好 (K515) 躍出時發生碰撞。莫雷拉未能就坐騎令人失望的表現提供任何解釋。練馬師方嘉柏告知小組，此駒自上仗後的表現令他滿意，他能提供的唯一解釋是賽事早段步速較標準時間略快，或不合此駒發揮。賽後立即接受獸醫檢查，發現此駒患有「喘鳴症」，而此駒過往也有此毛病報告。小組認為與近仗相比，「團長好」今仗的表現令人失望。「團長好」必須試閘及格，並且通過 | injury: #3 團長好: 10 3 團長好 (K515) 躍出時發生碰撞。莫雷拉未能就坐騎令人失望的表現提供任何解釋。練馬師方嘉柏告知小組，此駒自上仗後的表現令他滿意，他能提供的唯一解釋是賽事早段步速較標準時間略快，或不合此駒發揮。賽後立即接受獸醫檢查，發現此駒患有「喘鳴症」，而此駒過往也有此毛病報告。小組認為與近仗相比，「團長好」今仗的表現令人失望。「團長好」必須試閘及格，並且通過

## 2026-06-03 R4 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 跑馬地, Turf, 1650m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #5 先到先得 | 1 | 2 / 0.181 | 3 / 0.139 |
| #1 星願無限 | 2 | 10 / 0.029 | 11 / 0.029 |
| #9 獎星 | 3 | 3 / 0.157 | 2 / 0.181 |

Overrated Top-2 review: #10 時間寶 (actual 12, p=0.256).
Pre-race signal review: #5 先到先得: trainer_signal 84.8 (+14.1 vs field), stability 70.9 (+12.7 vs field)；#1 星願無限: race_shape 66.8 (+4.6 vs field)；#9 獎星: race_shape 78.8 (+16.6 vs field), form_line 96.0 (+7.2 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: major_incident: #10 時間寶: 12 10 時間寶 (H403) 潘頓表示，坐騎在領放下走勢暢順，但直路上對催策毫無反應及顯著轉弱。練馬師姚本輝告知小組，此駒自上仗於五月十三日出賽後的表現令他滿意，儘管此駒被發現心律不正常，但同時在領放下受追迫，不利發揮。賽後立即接受獸醫檢查，發現此駒心律不正常。「時間寶」必須試閘及格，並且通過獸醫檢驗後，才可再次出賽。賽後須抽取樣本檢驗。 | injury: #10 時間寶: 12 10 時間寶 (H403) 潘頓表示，坐騎在領放下走勢暢順，但直路上對催策毫無反應及顯著轉弱。練馬師姚本輝告知小組，此駒自上仗於五月十三日出賽後的表現令他滿意，儘管此駒被發現心律不正常，但同時在領放下受追迫，不利發揮。賽後立即接受獸醫檢查，發現此駒心律不正常。「時間寶」必須試閘及格，並且通過獸醫檢驗後，才可再次出賽。賽後須抽取樣本檢驗。

## 2026-06-03 R8 — model Top-2 hits 0, Matrix 1

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 跑馬地, Turf, 1800m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #6 銀亮奔騰 | 1 | 3 / 0.158 | 1 / 0.193 |
| #11 奔放 | 2 | 7 / 0.059 | 6 / 0.069 |
| #4 加州動員 | 3 | 11 / 0.027 | 11 / 0.027 |

Overrated Top-2 review: #7 一起美麗 (actual 6, p=0.202)；#2 太陽勇士 (actual 7, p=0.185).
Pre-race signal review: #6 銀亮奔騰: sectional 68.4 (+12.0 vs field), race_shape 75.8 (+11.8 vs field)；#11 奔放: sectional 70.4 (+14.0 vs field), stability 78.8 (+13.8 vs field)；#4 加州動員: no ≥3-point above-field Matrix dimension.
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 37 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #4 加州動員 actual 3／odds 38

## 2026-06-07 R5 — model Top-2 hits 0, Matrix 0

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, AWT, 1800m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #14 飛躍星伴 | 1 | 5 / 0.074 | 4 / 0.090 |
| #1 開心宇宙 | 2 | 11 / 0.040 | 12 / 0.045 |
| #3 超加加 | 3 | 9 / 0.044 | 8 / 0.050 |

Overrated Top-2 review: #9 精明選擇 (actual 4, p=0.225)；#2 凱明神駒 (actual 13, p=0.177).
Pre-race signal review: #14 飛躍星伴: race_shape 71.0 (+11.1 vs field), sectional 63.6 (+7.1 vs field)；#1 開心宇宙: stability 63.9 (+5.4 vs field), class_advantage 67.8 (+3.2 vs field)；#3 超加加: stability 61.7 (+3.3 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 37 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #14 飛躍星伴 actual 1／odds 32

## 2026-06-07 R6 — model Top-2 hits 0, Matrix 0

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1600m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #7 部族高手 | 1 | 5 / 0.079 | 5 / 0.085 |
| #10 捷威 | 2 | 4 / 0.084 | 4 / 0.085 |
| #5 好運年 | 3 | 12 / 0.033 | 12 / 0.040 |

Overrated Top-2 review: #6 金鑽精靈 (actual 6, p=0.155)；#1 雙星報喜 (actual 11, p=0.129).
Pre-race signal review: #7 部族高手: race_shape 68.4 (+8.5 vs field)；#10 捷威: sectional 63.6 (+6.6 vs field), trainer_signal 72.8 (+4.7 vs field)；#5 好運年: sectional 60.8 (+3.9 vs field), stability 62.8 (+3.4 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: interference: #9 愛心波: 7 9 愛心波 (L006) 出閘僅屬一般。轉直路彎時受困而未能望空。最後一百米在靠近「金鑽精靈」時再度受困而未能望空。

## 2026-06-07 R11 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1400m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #7 超輕鬆 | 1 | 4 / 0.097 | 4 / 0.091 |
| #5 自動自覺 | 2 | 2 / 0.130 | 2 / 0.110 |
| #8 勁無限 | 3 | 5 / 0.085 | 5 / 0.091 |

Overrated Top-2 review: #3 一世美麗 (actual 7, p=0.191).
Pre-race signal review: #7 超輕鬆: stability 66.8 (+6.5 vs field), race_shape 65.8 (+6.0 vs field)；#5 自動自覺: stability 71.6 (+11.3 vs field), class_advantage 71.8 (+9.3 vs field)；#8 勁無限: trainer_signal 82.5 (+11.6 vs field), race_shape 66.7 (+6.8 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #8 勁無限 actual 3／odds 83

## 2026-06-13 R3 — model Top-2 hits 0, Matrix 0

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1400m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #12 賢者威楓 | 1 | 4 / 0.085 | 4 / 0.091 |
| #4 深心星 | 2 | 7 / 0.070 | 6 / 0.080 |
| #5 龍之悅 | 3 | 6 / 0.076 | 7 / 0.074 |

Overrated Top-2 review: #9 馬上盈 (actual 6, p=0.194)；#11 你知我寶 (actual 8, p=0.147).
Pre-race signal review: #12 賢者威楓: stability 63.5 (+10.4 vs field), sectional 67.0 (+8.9 vs field)；#4 深心星: stability 67.5 (+14.4 vs field), form_line 96.0 (+10.4 vs field)；#5 龍之悅: race_shape 67.2 (+6.9 vs field), sectional 62.0 (+3.9 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 37 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: interference: #11 你知我寶: 8 11 你知我寶 (L132) 接近三百五十米處時移至「龍之悅」內側以繼續望空。趨近一百五十米處時在「大勇勝」與向外斜跑的「深心星」之間未能望空之際收慢。此駒因而未能被全力催策至终點。

## 2026-06-13 R4 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1800m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #3 年年友福 | 1 | 9 / 0.028 | 9 / 0.039 |
| #12 天蓬貓 | 2 | 3 / 0.139 | 3 / 0.143 |
| #2 安可 | 3 | 2 / 0.179 | 2 / 0.153 |

Overrated Top-2 review: #6 超開心 (actual 4, p=0.273).
Pre-race signal review: #3 年年友福: no ≥3-point above-field Matrix dimension；#12 天蓬貓: race_shape 72.1 (+11.8 vs field), stability 67.8 (+11.7 vs field)；#2 安可: trainer_signal 84.8 (+14.7 vs field), race_shape 70.2 (+9.8 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #3 年年友福 actual 1／odds 49 | interference: #6 超開心: 4 6 超開心 (K260) 四百五十米處至三百米處之間在「新力飆」之後受困而未能望空。

## 2026-06-13 R5 — model Top-2 hits 0, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, AWT, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #7 文明戰士 | 1 | 7 / 0.081 | 7 / 0.069 |
| #2 葳莉非凡 | 2 | 4 / 0.114 | 3 / 0.126 |
| #3 逍遙人生 | 3 | 3 / 0.115 | 2 / 0.133 |

Overrated Top-2 review: #5 顯勝高昇 (actual 11, p=0.164)；#1 起舞奜奜 (actual 4, p=0.129).
Pre-race signal review: #7 文明戰士: trainer_signal 75.8 (+6.1 vs field)；#2 葳莉非凡: stability 78.7 (+21.9 vs field), sectional 70.8 (+13.0 vs field)；#3 逍遙人生: form_line 96.0 (+11.7 vs field), race_shape 70.5 (+9.6 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: injury: #5 顯勝高昇: 11 5 顯勝高昇 (K409) 起步後不久向外斜跑，導致騎師須修正坐騎。接近五百米處時收慢避開「葳莉非凡」（奧爾民），當時「葳莉非凡」在尚未充分帶離下向內移入。小組告誡奧爾民須加倍小心。見習騎師黃寶妮表示，坐騎在此宗事件後搶口，因而於接近九百米處時推進至「葳莉非凡」內側，她其後須約束坐騎。她說，策騎指示是讓坐騎領放，但坐騎於早段未能展現足夠前速以做到這點，

## 2026-06-13 R9 — model Top-2 hits 0, Matrix 0

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, AWT, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #10 偵探傳奇 | 1 | 10 / 0.028 | 10 / 0.038 |
| #3 興馳千里 | 2 | 3 / 0.121 | 3 / 0.121 |
| #9 德心知遇 | 3 | 8 / 0.045 | 8 / 0.053 |

Overrated Top-2 review: #6 三軍勇將 (actual 6, p=0.245)；#2 熾烈神駒 (actual 4, p=0.147).
Pre-race signal review: #10 偵探傳奇: no ≥3-point above-field Matrix dimension；#3 興馳千里: race_shape 71.4 (+8.7 vs field), form_line 94.0 (+7.2 vs field)；#9 德心知遇: no ≥3-point above-field Matrix dimension.
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 37 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #9 德心知遇 actual 3／odds 30

## 2026-06-21 R6 — model Top-2 hits 1, Matrix 1

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1400m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #3 金快飛飛 | 1 | 2 / 0.144 | 2 / 0.121 |
| #12 飛躍成就 | 2 | 10 / 0.038 | 10 / 0.051 |
| #4 手機錶能 | 3 | 8 / 0.058 | 9 / 0.064 |

Overrated Top-2 review: #1 加州熱浪 (actual 8, p=0.169).
Pre-race signal review: #3 金快飛飛: stability 73.9 (+16.8 vs field), sectional 71.3 (+9.5 vs field)；#12 飛躍成就: class_advantage 72.3 (+6.9 vs field), stability 62.5 (+5.4 vs field)；#4 手機錶能: sectional 66.1 (+4.3 vs field), race_shape 63.8 (+3.7 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 37 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #4 手機錶能 actual 3／odds 36

## 2026-06-21 R7 — model Top-2 hits 0, Matrix 0

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1400m, Group 3.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #6 小鳥天堂 | 1 | 5 / 0.080 | 6 / 0.087 |
| #1 錶之銀河 | 2 | 8 / 0.069 | 4 / 0.093 |
| #7 幸運有您 | 3 | 10 / 0.027 | 10 / 0.057 |

Overrated Top-2 review: #2 精算暴雪 (actual 9, p=0.195)；#10 韋金主 (actual 4, p=0.182).
Pre-race signal review: #6 小鳥天堂: race_shape 69.7 (+5.9 vs field), class_advantage 74.6 (+3.7 vs field)；#1 錶之銀河: form_line 96.0 (+8.7 vs field), race_shape 69.9 (+6.1 vs field)；#7 幸運有您: form_line 95.0 (+7.7 vs field), horse_health 73.2 (+3.2 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 37 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #7 幸運有您 actual 3／odds 74 | interference: #2 精算暴雪: 9 2 精算暴雪 (H368) 被查詢時，艾道拿表示，坐騎自內檔出閘後能夠佔取較近仗略為靠前的位置。他說，坐騎於中段沿途跟隨「手機錶霸」，「小鳥天堂」則居於坐騎外側。他說，儘管他曾考慮讓坐騎自六百米處起向外移出，但他覺得他不能做到這點，因為「小鳥天堂」於該階段居坐騎稍前的位置及走勢良佳。他說，由於他不希望讓坐騎跟隨「好友心得」，他讓坐騎保持居於「手機錶霸」之

## 2026-06-21 R8 — model Top-2 hits 0, Matrix 0

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 2000m, Class 3.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #10 千禧龍 | 1 | 12 / 0.023 | 12 / 0.030 |
| #5 安帝 | 2 | 3 / 0.134 | 3 / 0.132 |
| #1 春風萬里 | 3 | 7 / 0.061 | 8 / 0.056 |

Overrated Top-2 review: #6 共享富裕 (actual 9, p=0.174)；#11 紫荊拼搏 (actual 12, p=0.145).
Pre-race signal review: #10 千禧龍: sectional 59.7 (+3.7 vs field)；#5 安帝: form_line 96.0 (+9.5 vs field), trainer_signal 80.5 (+9.1 vs field)；#1 春風萬里: trainer_signal 84.8 (+13.4 vs field), class_advantage 68.6 (+3.5 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 37 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #10 千禧龍 actual 1／odds 64 || #1 春風萬里 actual 3／odds 44

## 2026-06-21 R9 — model Top-2 hits 1, Matrix 1

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1800m, Group 3.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #5 美麗同享 | 1 | 1 / 0.139 | 1 / 0.138 |
| #3 光年魅力 | 2 | 7 / 0.086 | 7 / 0.086 |
| #11 浪漫戰神 | 3 | 10 / 0.054 | 10 / 0.069 |

Overrated Top-2 review: #10 海上大軍 (actual 8, p=0.133).
Pre-race signal review: #5 美麗同享: form_line 93.0 (+10.4 vs field), race_shape 71.7 (+8.9 vs field)；#3 光年魅力: race_shape 67.8 (+5.0 vs field), stability 67.1 (+5.0 vs field)；#11 浪漫戰神: form_line 96.0 (+13.4 vs field), stability 67.7 (+5.6 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 37 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: interference: #7 銀亮奔騰: 4 7 銀亮奔騰 (K057) 自大外檔出閘後於早段在馬群之後切入。四百五十米處至三百五十米處之間受困而未能望空。末段在「美麗同享」與「嘉應傳承」之間緊迫競跑。

## 2026-06-21 R10 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1200m, Class 3.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #7 有備而戰 | 1 | 4 / 0.125 | 3 / 0.129 |
| #4 人和家興 | 2 | 10 / 0.034 | 8 / 0.043 |
| #13 包裝天王 | 3 | 2 / 0.154 | 2 / 0.138 |

Overrated Top-2 review: #6 正本唐心 (actual 6, p=0.165).
Pre-race signal review: #7 有備而戰: form_line 93.0 (+12.6 vs field), trainer_signal 80.3 (+10.1 vs field)；#4 人和家興: sectional 67.0 (+6.1 vs field), class_advantage 69.8 (+5.1 vs field)；#13 包裝天王: stability 73.1 (+16.5 vs field), sectional 76.0 (+15.1 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #4 人和家興 actual 2／odds 66

## 2026-06-21 R11 — model Top-2 hits 0, Matrix 0

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1400m, Class 3.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #14 閃電小子 | 1 | 6 / 0.062 | 7 / 0.059 |
| #9 金勝名駒 | 2 | 12 / 0.024 | 11 / 0.038 |
| #1 閃耀天河 | 3 | 5 / 0.084 | 5 / 0.079 |

Overrated Top-2 review: #11 紅運光輝 (actual 10, p=0.152)；#10 仁仁有餘 (actual 5, p=0.151).
Pre-race signal review: #14 閃電小子: stability 71.3 (+12.0 vs field)；#9 金勝名駒: form_line 93.0 (+6.6 vs field), class_advantage 70.8 (+3.5 vs field)；#1 閃耀天河: race_shape 63.5 (+4.0 vs field), stability 62.7 (+3.4 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 37 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #9 金勝名駒 actual 2／odds 40

## 2026-06-27 R1 — model Top-2 hits 0, Matrix 0

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1200m, Class 5.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #10 綫路光驊 | 1 | 10 / 0.044 | 9 / 0.059 |
| #4 翠湖烈風 | 2 | 11 / 0.041 | 12 / 0.038 |
| #3 果然僥倖 | 3 | 9 / 0.055 | 10 / 0.056 |

Overrated Top-2 review: #9 鑽得勝 (actual 9, p=0.135)；#2 英雄豪邁 (actual 8, p=0.127).
Pre-race signal review: #10 綫路光驊: sectional 68.4 (+9.5 vs field), horse_health 71.8 (+3.7 vs field)；#4 翠湖烈風: trainer_signal 73.8 (+6.0 vs field)；#3 果然僥倖: stability 64.8 (+9.9 vs field), class_advantage 71.6 (+3.6 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 37 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: major_incident: #1 金風萬里: 13 1 金風萬里 (K150) 出閘僅屬一般。田泰安表示，坐騎走勢欠順，中段沿途未能穩定走勢。他說，坐騎因而在直路上未能以勁勢衝刺。練馬師桂福特告知小組，此駒於是賽前的表現令他滿意，而他未能就此駒令人失望的表現提供任何解釋。賽後立即接受獸醫檢查，並無發現任何明顯異常之處。小組認為與上仗相比，「金風萬里」今仗的表現令人失望。「金風萬里」必須試閘及格，並且通過

## 2026-06-27 R10 — model Top-2 hits 1, Matrix 1

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1200m, Class 3.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #6 堅先生 | 1 | 1 / 0.184 | 1 / 0.145 |
| #11 香港仔 | 2 | 8 / 0.060 | 9 / 0.051 |
| #7 傑出雷霆 | 3 | 6 / 0.074 | 7 / 0.059 |

Overrated Top-2 review: #8 健康快車 (actual 9, p=0.136).
Pre-race signal review: #6 堅先生: stability 78.3 (+24.8 vs field), sectional 70.8 (+14.6 vs field)；#11 香港仔: trainer_signal 79.3 (+8.0 vs field), class_advantage 72.3 (+5.0 vs field)；#7 傑出雷霆: stability 62.3 (+8.8 vs field), trainer_signal 79.5 (+8.2 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 37 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #11 香港仔 actual 2／odds 53 | interference: #1 得道猴王: 10 1 得道猴王 (J303) 出閘僅屬一般，其後在受向內斜跑的「電光高昇」擠迫之際收慢。四百米處至三百五十米處之間受困而未能望空。潘頓表示，坐騎在直路上對催策毫無反應，而他能提供的唯一解釋是坐騎增程角逐或更合發揮。賽後立即接受獸醫檢查，並無發現任何明顯異常之處。

## 2026-06-27 R11 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1400m, Class 3.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #5 金牌活力 | 1 | 7 / 0.073 | 6 / 0.085 |
| #2 友瑩仁 | 2 | 3 / 0.124 | 3 / 0.113 |
| #6 綫路英雄 | 3 | 2 / 0.142 | 2 / 0.142 |

Overrated Top-2 review: #7 做好自己 (actual 4, p=0.217).
Pre-race signal review: #5 金牌活力: race_shape 67.9 (+8.1 vs field), sectional 67.0 (+7.6 vs field)；#2 友瑩仁: stability 80.0 (+21.6 vs field), sectional 69.8 (+10.4 vs field)；#6 綫路英雄: stability 81.0 (+22.6 vs field), sectional 70.8 (+11.4 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #5 金牌活力 actual 1／odds 51 | interference: #7 做好自己: 4 7 做好自己 (J444) 躍出時發生碰撞。過了一百五十米處後移至「金牌活力」外側以嘗試望空。「金牌活力」其後向外斜跑，此駒於最後一百五十米在緊貼「金牌活力」的後蹄處於窘境之際嚴重受困而未能望空，因而向外斜跑，接近五十米處時在一段途程上與「正本巨星」互相觸碰。

## 2026-07-01 R1 — model Top-2 hits 1, Matrix 0

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1600m, Class 5.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #3 手到再來 | 1 | 7 / 0.070 | 8 / 0.061 |
| #10 東方魅影 | 2 | 1 / 0.140 | 4 / 0.095 |
| #7 志醒大將 | 3 | 9 / 0.051 | 10 / 0.050 |

Overrated Top-2 review: #11 勁爽 (actual 4, p=0.138).
Pre-race signal review: #3 手到再來: race_shape 67.7 (+7.5 vs field), trainer_signal 72.2 (+3.5 vs field)；#10 東方魅影: trainer_signal 82.5 (+13.7 vs field), stability 62.7 (+7.4 vs field)；#7 志醒大將: trainer_signal 75.0 (+6.2 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 37 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: injury: #6 巴閉佬: 11 6 巴閉佬 (K323) 出閘僅屬一般，其後不久被向外斜跑的「東方魅影」碰撞。奧爾民表示，他獲指示嘗試讓坐騎在直路上移出外疊，但他未能做到這點。他說，坐騎於末段衝刺時在催策下保持同速，而他認為坐騎或已屆歇暑休賽之時。賽後立即接受獸醫檢查，並無發現任何明顯異常之處。<2/7/2026獸醫報告增補> 表現令人失望的「巴閉佬」於賽後曾由主任獸醫（賽事管制）檢

## 2026-07-01 R3 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1400m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #2 佛亮老撾 | 1 | 4 / 0.082 | 4 / 0.096 |
| #11 潮流勇駒 | 2 | 6 / 0.062 | 6 / 0.063 |
| #14 順善寶 | 3 | 1 / 0.257 | 1 / 0.216 |

Overrated Top-2 review: #1 威武年代 (actual 6, p=0.138).
Pre-race signal review: #2 佛亮老撾: form_line 96.0 (+12.6 vs field), race_shape 64.8 (+5.0 vs field)；#11 潮流勇駒: trainer_signal 72.8 (+4.8 vs field)；#14 順善寶: stability 81.0 (+29.3 vs field), class_advantage 75.6 (+11.3 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #11 潮流勇駒 actual 2／odds 89 | interference: #1 威武年代: 6 1 威武年代 (J451) 三百五十米處至二百五十米處之間受困而未能望空。

## 2026-07-01 R5 — model Top-2 hits 0, Matrix 0

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1400m, Class 2.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #9 嘉應奇兵 | 1 | 7 / 0.067 | 7 / 0.070 |
| #7 美麗星晨 | 2 | 10 / 0.019 | 10 / 0.027 |
| #8 至尊瑰寶 | 3 | 3 / 0.118 | 3 / 0.113 |

Overrated Top-2 review: #2 笑傲江湖 (actual 5, p=0.311)；#6 喜尊龍 (actual 9, p=0.132).
Pre-race signal review: #9 嘉應奇兵: stability 73.1 (+15.3 vs field), sectional 60.3 (+4.3 vs field)；#7 美麗星晨: horse_health 74.6 (+4.0 vs field)；#8 至尊瑰寶: race_shape 67.8 (+4.8 vs field), sectional 60.0 (+4.0 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 37 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: interference: #2 笑傲江湖: 5 2 笑傲江湖 (K168) 四百米處至三百五十米處之間在「威利金箭」之後受困而未能望空。

## 2026-07-04 R2 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1200m, Class 5.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #9 魅力知福 | 1 | 3 / 0.087 | 3 / 0.096 |
| #11 駿先生 | 2 | 7 / 0.040 | 7 / 0.048 |
| #5 朗日雪峰 | 3 | 1 / 0.412 | 1 / 0.320 |

Overrated Top-2 review: #10 紅旺繽紛 (actual 7, p=0.147).
Pre-race signal review: #9 魅力知福: trainer_signal 77.2 (+7.3 vs field), race_shape 66.5 (+5.2 vs field)；#11 駿先生: form_line 96.0 (+5.7 vs field), race_shape 66.8 (+5.6 vs field)；#5 朗日雪峰: stability 72.6 (+19.4 vs field), trainer_signal 87.0 (+17.0 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #11 駿先生 actual 2／odds 45

## 2026-07-04 R7 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #5 添開心 | 1 | 5 / 0.098 | 4 / 0.114 |
| #12 同喜 | 2 | 3 / 0.134 | 3 / 0.136 |
| #6 老鼠斑 | 3 | 1 / 0.243 | 2 / 0.186 |

Overrated Top-2 review: #4 開心孖寶 (actual 10, p=0.189).
Pre-race signal review: #5 添開心: form_line 96.0 (+13.3 vs field), race_shape 67.9 (+7.5 vs field)；#12 同喜: class_advantage 75.6 (+10.4 vs field), race_shape 69.6 (+9.2 vs field)；#6 老鼠斑: trainer_signal 82.5 (+13.6 vs field), stability 67.7 (+13.0 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: interference: #4 開心孖寶: 10 4 開心孖寶 (K475) 跑離二百米處時在被「日出東方」碰撞之際失去平衡，當時「日出東方」在勒避之際向內斜跑。趨近一百五十米處時在「日出東方」與「擅搏」之間受擠迫之際大力勒避。賽後立即接受獸醫檢查，並無發現任何明顯異常之處。

## 2026-07-04 R8 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1800m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #6 捷威 | 1 | 1 / 0.143 | 1 / 0.134 |
| #9 風起雲湧 | 2 | 4 / 0.109 | 5 / 0.092 |
| #3 創科群英 | 3 | 12 / 0.024 | 13 / 0.028 |

Overrated Top-2 review: #12 鴻圖大展 (actual 7, p=0.134).
Pre-race signal review: #6 捷威: stability 68.2 (+10.5 vs field), sectional 64.2 (+8.2 vs field)；#9 風起雲湧: stability 80.1 (+22.4 vs field), sectional 62.8 (+6.8 vs field)；#3 創科群英: no ≥3-point above-field Matrix dimension.
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #3 創科群英 actual 3／odds 50

## 2026-07-04 R9 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #3 利高八斗 | 1 | 1 / 0.235 | 2 / 0.190 |
| #6 龍文正道 | 2 | 4 / 0.079 | 6 / 0.059 |
| #1 鼓浪好友 | 3 | 5 / 0.063 | 5 / 0.070 |

Overrated Top-2 review: #5 應龍飛影 (actual 4, p=0.186).
Pre-race signal review: #3 利高八斗: stability 79.7 (+21.2 vs field), trainer_signal 78.2 (+9.3 vs field)；#6 龍文正道: stability 65.0 (+6.4 vs field), trainer_signal 72.8 (+3.8 vs field)；#1 鼓浪好友: form_line 96.0 (+12.4 vs field), stability 67.6 (+9.1 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #6 龍文正道 actual 2／odds 111

## 2026-07-08 R4 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 跑馬地, Turf, 1650m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #1 哥倫布 | 1 | 1 / 0.266 | 2 / 0.190 |
| #7 焦點 | 2 | 4 / 0.116 | 5 / 0.120 |
| #6 準希望 | 3 | 5 / 0.097 | 6 / 0.108 |

Overrated Top-2 review: #5 好運年 (actual 4, p=0.211).
Pre-race signal review: #1 哥倫布: trainer_signal 87.0 (+10.5 vs field), race_shape 81.0 (+8.5 vs field)；#7 焦點: stability 69.9 (+8.9 vs field), sectional 67.5 (+5.5 vs field)；#6 準希望: sectional 66.5 (+4.5 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: interference: #5 好運年: 4 5 好運年 (K443) 末段在「準希望」與「焦點」之間緊迫競跑時未能被全力催策，當時「焦點」在催策下向外斜跑。賽後須抽取樣本檢驗。

## 2026-07-08 R8 — model Top-2 hits 0, Matrix 0

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 跑馬地, Turf, 1800m, Class 2.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #9 極光之子 | 1 | 9 / 0.043 | 10 / 0.038 |
| #11 幸運派彩 | 2 | 7 / 0.055 | 7 / 0.068 |
| #10 川河耀駒 | 3 | 12 / 0.016 | 12 / 0.019 |

Overrated Top-2 review: #3 奔放 (actual 9, p=0.248)；#5 春風萬里 (actual 5, p=0.143).
Pre-race signal review: #9 極光之子: stability 69.5 (+8.6 vs field)；#11 幸運派彩: race_shape 73.0 (+10.8 vs field), horse_health 73.8 (+3.7 vs field)；#10 川河耀駒: horse_health 74.6 (+4.5 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 37 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: interference: #12 將義: 10 12 將義 (J446) 轉直路彎時在「友瑩光」之後受困而未能望空。接近二百米處時「幸運派彩」（巴度）向內斜跑，避開「極光之子」，導致「奔放」被帶向內跑壓向「一起美麗」。「一起美麗」因此向內斜跑，將「浪漫戰神」向內擠迫壓向此駒，當時此駒在「友瑩光」與「浪漫戰神」之間未能望空之際收慢。小組告誡巴度須加倍小心。賽後立即接受獸醫檢查，並無發現任何明顯異常之處

## 2026-07-08 R9 — model Top-2 hits 0, Matrix 0

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 跑馬地, Turf, 1200m, Class 3.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #11 撼天鐵翼 | 1 | 4 / 0.078 | 4 / 0.121 |
| #4 觀眾之力 | 2 | 3 / 0.171 | 3 / 0.124 |
| #3 嘉應勇將 | 3 | 9 / 0.030 | 9 / 0.041 |

Overrated Top-2 review: #1 志滿同行 (actual 7, p=0.224)；#7 皇者有利 (actual 8, p=0.189).
Pre-race signal review: #11 撼天鐵翼: race_shape 79.0 (+16.1 vs field), form_line 96.0 (+8.5 vs field)；#4 觀眾之力: trainer_signal 87.0 (+11.3 vs field), stability 74.4 (+9.9 vs field)；#3 嘉應勇將: no ≥3-point above-field Matrix dimension.
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #3 嘉應勇將 actual 3／odds 32 | interference: #7 皇者有利: 8 7 皇者有利 (J539) 起步後不久受擠迫。直路彎受困而未能望空。小組押後有關此駒於接近三百米處時勒避的原因之研訊至七月十二日星期日沙田賽事當日進行。賽後立即接受獸醫檢查，並無發現任何明顯異常之處。

## 2026-07-12 R4 — model Top-2 hits 1, Matrix 1

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1400m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #2 金滙千帥 | 1 | 1 / 0.201 | 1 / 0.157 |
| #12 金運齊來 | 2 | 11 / 0.034 | 9 / 0.058 |
| #1 哈羅威 | 3 | 6 / 0.083 | 6 / 0.067 |

Overrated Top-2 review: #5 文明福星 (actual 10, p=0.111).
Pre-race signal review: #2 金滙千帥: race_shape 72.0 (+12.1 vs field), trainer_signal 87.0 (+11.5 vs field)；#12 金運齊來: form_line 96.0 (+12.6 vs field), sectional 67.0 (+11.1 vs field)；#1 哈羅威: stability 65.4 (+13.0 vs field), class_advantage 63.0 (+3.2 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 37 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #12 金運齊來 actual 2／odds 68 | interference: #5 文明福星: 10 5 文明福星 (J315) 一百五十米處至五十米處之間在「鬥志波」之後受困而未能望空。賽後，獸醫應練馬師丁冠豪的要求替「文明福星」進行內窺鏡檢查。獸醫表示，是項檢查顯示此駒的氣管內有很多血。「文明福星」必須通過獸醫檢驗後，才可再次出賽。

## 2026-07-12 R6 — model Top-2 hits 0, Matrix 0

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1200m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #2 盈妍威楓 | 1 | 10 / 0.050 | 9 / 0.065 |
| #10 烈進駒 | 2 | 11 / 0.043 | 12 / 0.046 |
| #8 實力加 | 3 | 9 / 0.057 | 10 / 0.057 |

Overrated Top-2 review: #6 銀刺勇士 (actual 12, p=0.167)；#1 鋁神 (actual 6, p=0.153).
Pre-race signal review: #2 盈妍威楓: form_line 96.0 (+7.5 vs field)；#10 烈進駒: trainer_signal 77.2 (+3.3 vs field)；#8 實力加: stability 64.7 (+11.5 vs field), class_advantage 68.8 (+8.2 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 37 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #10 烈進駒 actual 2／odds 97

## 2026-07-12 R7 — model Top-2 hits 1, Matrix 1

Classification: **contender captured in Top-5 tier but not Top 2**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1600m, Class 4.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #3 包裝戰仕 | 1 | 3 / 0.101 | 6 / 0.069 |
| #6 新力飆 | 2 | 14 / 0.023 | 14 / 0.030 |
| #5 超開心 | 3 | 1 / 0.148 | 2 / 0.111 |

Overrated Top-2 review: #10 天蓬貓 (actual 4, p=0.120).
Pre-race signal review: #3 包裝戰仕: stability 66.6 (+8.4 vs field), trainer_signal 82.5 (+8.1 vs field)；#6 新力飆: no ≥3-point above-field Matrix dimension；#5 超開心: stability 69.5 (+11.3 vs field), class_advantage 68.8 (+6.3 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 77 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #6 新力飆 actual 2／odds 93

## 2026-07-12 R11 — model Top-2 hits 0, Matrix 0

Classification: **competitive group absent from both Top-5 rankings**. Predictability review: **abnormal/outsider flagged**. Venue 沙田, Turf, 1400m, Class 3.

| Horse | Actual | ML rank / p | Matrix rank / p |
|---|---:|---:|---:|
| #3 臻至辰 | 1 | 6 / 0.058 | 5 / 0.081 |
| #12 金快飛飛 | 2 | 5 / 0.076 | 6 / 0.072 |
| #4 泰坦 | 3 | 10 / 0.028 | 10 / 0.039 |

Overrated Top-2 review: #9 仁仁有餘 (actual 4, p=0.184)；#1 綠野飛馳 (actual 5, p=0.159).
Pre-race signal review: #3 臻至辰: form_line 96.0 (+11.6 vs field), race_shape 64.4 (+4.4 vs field)；#12 金快飛飛: stability 80.5 (+19.3 vs field), class_advantage 70.3 (+6.8 vs field)；#4 泰坦: sectional 65.0 (+6.2 vs field).
Cause assessment: abnormal/outsider/incident cohort; result annotation is diagnostic only.
Systematicity: this pattern occurs in 37 weak races; any change must still improve multiple chronological folds and external evidence.

Post-race diagnostic annotation: extreme_outsider: #4 泰坦 actual 3／odds 49

# Recurring diagnosis

Weak races reviewed: **127** (70 normal-result cohort; 57 outsider/incident/injury/abnormal flagged). Races where the challenger improved Top-2 hit count over Matrix: **6**.

| Pattern | Races |
|---|---:|
| contender captured in Top-5 tier but not Top 2 | 77 |
| competitive group absent from both Top-5 rankings | 37 |
| ML reordering degraded Matrix contender | 13 |

Changes are eligible only when the same pattern improves multiple chronological folds. A single missed horse does not authorize a weight change.
