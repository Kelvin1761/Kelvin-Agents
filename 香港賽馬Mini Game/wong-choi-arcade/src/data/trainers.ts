export interface TrainerData {
    id: string;
    name: { zh: string; en: string };
    rating: number; // 70-95
    feature: string;
}

export const TRAINERS: TrainerData[] = [
    { id: 'T01', name: { zh: '方嘉柏', en: 'C. Fownes' }, rating: 92, feature: 'consistency_bonus_10' },
    { id: 'T02', name: { zh: '蔡約翰', en: 'J. Size' }, rating: 90, feature: 'stamina_bonus_8' },
    { id: 'T03', name: { zh: '韋達', en: 'D. Whyte' }, rating: 88, feature: 'all_round_5' },
    { id: 'T04', name: { zh: '姚本輝', en: 'P.F. Yiu' }, rating: 85, feature: 'debut_speed_12' },
    { id: 'T05', name: { zh: '告東尼', en: 'A.S. Cruz' }, rating: 84, feature: 'heavy_weight_8' },
    { id: 'T06', name: { zh: '呂健威', en: 'K.W. Lui' }, rating: 83, feature: 'long_distance_stamina_10' },
    { id: 'T07', name: { zh: '賀賢', en: 'D.J. Hall' }, rating: 82, feature: 'import_horse_7' },
    { id: 'T08', name: { zh: '大衛希斯', en: 'D.A. Hayes' }, rating: 81, feature: 'recovery_10' },
    { id: 'T09', name: { zh: '文家良', en: 'K.L. Man' }, rating: 80, feature: 'sprint_burst_10' },
    { id: 'T10', name: { zh: '容天鵬', en: 'T.P. Yung' }, rating: 79, feature: 'young_horse_10' },
    { id: 'T11', name: { zh: '丁冠豪', en: 'K.H. Ting' }, rating: 78, feature: 'underdog_burst_8' },
    { id: 'T12', name: { zh: '苗禮德', en: 'A.T. Millard' }, rating: 77, feature: 'barrier_trial_12' },
    { id: 'T13', name: { zh: '沈集成', en: 'C.S. Shum' }, rating: 76, feature: 'dirt_track_12' },
    { id: 'T14', name: { zh: '徐雨石', en: 'Y.S. Tsui' }, rating: 75, feature: 'happy_valley_8' },
    { id: 'T15', name: { zh: '霍利時', en: 'D.E. Ferraris' }, rating: 74, feature: 'consistency_bonus_10' },
];
