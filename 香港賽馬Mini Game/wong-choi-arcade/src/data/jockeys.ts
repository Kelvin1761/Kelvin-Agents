export type JockeyClass = 'champion' | 'master' | 'elite' | 'guest' | 'apprentice' | 'legend';

export interface JockeyData {
    id: string;
    name: { zh: string; en: string };
    rating: number; // 68-96
    type: JockeyClass;
    allowance: number; // 減磅 0, 3, 5, 7, 10
    feature: string;
}

export const JOCKEYS: JockeyData[] = [
    { id: 'J01', name: { zh: '潘頓', en: 'Z. Purton' }, rating: 95, type: 'champion', allowance: 0, feature: 'lead_speed_20' },
    { id: 'J02', name: { zh: '麥道朗', en: 'J. McDonald' }, rating: 94, type: 'guest', allowance: 0, feature: 'final_sprint_15' },
    { id: 'J03', name: { zh: '布文', en: 'H. Bowman' }, rating: 93, type: 'master', allowance: 0, feature: 'inside_rail_15' },
    { id: 'J04', name: { zh: '何澤堯', en: 'C.Y. Ho' }, rating: 88, type: 'elite', allowance: 0, feature: 'underdog_burst_15' },
    { id: 'J05', name: { zh: '艾兆禮', en: 'A. Atzeni' }, rating: 86, type: 'master', allowance: 0, feature: 'mid_dist_12' },
    { id: 'J06', name: { zh: '班德禮', en: 'H. Bentley' }, rating: 85, type: 'master', allowance: 0, feature: 'consistent' },
    { id: 'J07', name: { zh: '田泰安', en: 'K. Teetan' }, rating: 85, type: 'elite', allowance: 0, feature: 'long_dist_10' },
    { id: 'J08', name: { zh: '巴度', en: 'A. Badel' }, rating: 85, type: 'master', allowance: 0, feature: 'inside_rail_10' },
    { id: 'J09', name: { zh: '艾道拿', en: 'B. Avdulla' }, rating: 84, type: 'elite', allowance: 0, feature: 'big_stage_15' },
    { id: 'J10', name: { zh: '麥文堅', en: 'D. McMonagle' }, rating: 83, type: 'guest', allowance: 0, feature: 'euro_style_10' },
    { id: 'J11', name: { zh: '李寶利', en: 'U. Rispoli' }, rating: 82, type: 'guest', allowance: 0, feature: 'happy_valley_15' },
    { id: 'J12', name: { zh: '杜苑欣', en: 'H. Doyle' }, rating: 81, type: 'guest', allowance: 0, feature: 'light_weight_10' },
    { id: 'J13', name: { zh: '梁家俊', en: 'D. Leung' }, rating: 80, type: 'elite', allowance: 0, feature: 'consistent_12' },
    { id: 'J14', name: { zh: '賀銘年', en: 'A. Hamelin' }, rating: 79, type: 'elite', allowance: 0, feature: 'underdog_10' },
    { id: 'J15', name: { zh: '霍宏聲', en: 'L. Ferraris' }, rating: 78, type: 'elite', allowance: 0, feature: 'slow_out_fast_return_10' },
    { id: 'J16', name: { zh: '周俊樂', en: 'J. Chau' }, rating: 77, type: 'elite', allowance: 3, feature: 'happy_valley_10' },
    { id: 'J17', name: { zh: '潘明輝', en: 'M. Poon' }, rating: 77, type: 'elite', allowance: 3, feature: 'sprint_12' },
    { id: 'J18', name: { zh: '楊明綸', en: 'K. Yeung' }, rating: 75, type: 'elite', allowance: 0, feature: 'wet_track_15' },
    { id: 'J19', name: { zh: '蔡明紹', en: 'M. Chadwick' }, rating: 73, type: 'elite', allowance: 0, feature: 'corner_10' },
    
    // 見習生
    { id: 'J20', name: { zh: '鍾易禮', en: 'A. Chung' }, rating: 71, type: 'apprentice', allowance: 5, feature: 'random_burst_15' },
    { id: 'J21', name: { zh: '黃智弘', en: 'E. Wong' }, rating: 70, type: 'apprentice', allowance: 7, feature: 'super_burst_25' },
    { id: 'J22', name: { zh: '袁幸堯', en: 'H.Y. Yuen' }, rating: 68, type: 'apprentice', allowance: 10, feature: 'burst_25' },
    { id: 'J23', name: { zh: '黃寶妮', en: 'P.N. Wong' }, rating: 68, type: 'apprentice', allowance: 10, feature: 'female_bonus' },

    // 傳奇殿堂 (退役神級)
    { id: 'JL1', name: { zh: '莫雷拉', en: 'J. Moreira' }, rating: 96, type: 'legend', allowance: 0, feature: 'final_sprint_15' },
    { id: 'JL2', name: { zh: '高雅志', en: 'F. Coetzee' }, rating: 95, type: 'legend', allowance: 0, feature: 'positioning_15' },
    { id: 'JL3', name: { zh: '霍達', en: 'R. Fradd' }, rating: 94, type: 'legend', allowance: 0, feature: 'sprint_15' },
    { id: 'JL4', name: { zh: '柏寶', en: 'B. Prebble' }, rating: 93, type: 'legend', allowance: 0, feature: 'all_round_15' },
];
