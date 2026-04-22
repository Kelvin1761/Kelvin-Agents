/**
 * 旺財街機 — 騎師資料庫 (24 位)
 * 含 4 位退役傳奇 (僅限經典名駒專屬)
 */

export const JOCKEYS = [
  // 冠軍級
  { id: 'purton',    name: '潘頓',     nameEn: 'Z. Purton',     rating: 95, type: '冠軍級', skill: { name: '起步搶前', phase: 1, bonus: 0.20, desc: '領放型專家' }, pullUpMultiplier: 2.0 },
  { id: 'mcdonald',  name: '麥道朗',   nameEn: 'J. McDonald',   rating: 94, type: '客串級', skill: { name: '末段衝刺', phase: 4, bonus: 0.15, desc: '客串大師' }, pullUpMultiplier: 1.0 },
  // 大師級
  { id: 'bowman',    name: '布文',     nameEn: 'H. Bowman',     rating: 93, type: '大師級', skill: { name: '內欄發力', phase: 3, bonus: 0.15, desc: '走位高手' }, pullUpMultiplier: 1.0 },
  { id: 'atzeni',    name: '艾兆禮',   nameEn: 'A. Atzeni',     rating: 86, type: '大師級', skill: { name: '中距離專家', phase: 2, bonus: 0.12, desc: '中距離' }, pullUpMultiplier: 1.0 },
  { id: 'bentley',   name: '班德禮',   nameEn: 'H. Bentley',    rating: 85, type: '大師級', skill: { name: '均衡型', phase: 0, bonus: 0.0, desc: '穩定' }, pullUpMultiplier: 1.0 },
  { id: 'badel',     name: '巴度',     nameEn: 'A. Badel',      rating: 85, type: '大師級', skill: { name: '內欄優勢', phase: 3, bonus: 0.10, desc: '走位' }, pullUpMultiplier: 1.0 },
  // 精英級
  { id: 'ho_cy',     name: '何澤堯',   nameEn: 'C.Y. Ho',      rating: 88, type: '精英級', skill: { name: '冷門馬爆發', phase: 4, bonus: 0.15, desc: '華將一哥' }, pullUpMultiplier: 1.0 },
  { id: 'teetan',    name: '田泰安',   nameEn: 'K. Teetan',     rating: 85, type: '精英級', skill: { name: '長途耐力', phase: 2, bonus: 0.10, desc: '耐力' }, pullUpMultiplier: 1.0 },
  { id: 'avdulla',   name: '艾道拿',   nameEn: 'B. Avdulla',    rating: 84, type: '精英級', skill: { name: '大賽爆發', phase: 4, bonus: 0.15, desc: '大賽型' }, pullUpMultiplier: 1.0 },
  { id: 'mcmonagle', name: '麥文堅',   nameEn: 'D. McMonagle',  rating: 83, type: '客串級', skill: { name: '歐洲騎法', phase: 2, bonus: 0.10, desc: '歐式' }, pullUpMultiplier: 1.0 },
  { id: 'rispoli',   name: '李寶利',   nameEn: 'U. Rispoli',    rating: 82, type: '客串級', skill: { name: '跑馬地專家', phase: 0, bonus: 0.15, desc: 'HV專家' }, pullUpMultiplier: 1.0 },
  { id: 'doyle',     name: '杜苑欣',   nameEn: 'H. Doyle',      rating: 81, type: '客串級', skill: { name: '輕磅優勢', phase: 0, bonus: 0.10, desc: '輕磅' }, pullUpMultiplier: 1.0 },
  { id: 'leung',     name: '梁家俊',   nameEn: 'D. Leung',      rating: 80, type: '精英級', skill: { name: '穩定性', phase: 0, bonus: 0.12, desc: '穩定' }, pullUpMultiplier: 1.0 },
  { id: 'hamelin',   name: '賀銘年',   nameEn: 'A. Hamelin',    rating: 79, type: '精英級', skill: { name: '冷門殺手', phase: 4, bonus: 0.10, desc: '冷門' }, pullUpMultiplier: 1.0 },
  { id: 'ferraris',  name: '霍宏聲',   nameEn: 'L. Ferraris',   rating: 78, type: '精英級', skill: { name: '慢出快返', phase: 4, bonus: 0.10, desc: '後追' }, pullUpMultiplier: 1.0 },
  { id: 'chau',      name: '周俊樂',   nameEn: 'J. Chau',       rating: 77, type: '精英級', skill: { name: '跑馬地專家', phase: 0, bonus: 0.10, desc: 'HV' }, pullUpMultiplier: 1.0 },
  { id: 'poon',      name: '潘明輝',   nameEn: 'M. Poon',       rating: 77, type: '精英級', skill: { name: '短途爆發', phase: 4, bonus: 0.12, desc: '短途' }, pullUpMultiplier: 1.0 },
  { id: 'yeung',     name: '楊明綸',   nameEn: 'K. Yeung',      rating: 75, type: '精英級', skill: { name: '濕地適應', phase: 0, bonus: 0.15, desc: '濕地' }, pullUpMultiplier: 1.0 },
  { id: 'chadwick',  name: '蔡明紹',   nameEn: 'M. Chadwick',   rating: 73, type: '一般',   skill: { name: '彎位走位', phase: 3, bonus: 0.10, desc: '彎位' }, pullUpMultiplier: 1.0 },
  // 見習
  { id: 'chung',     name: '鍾易禮',   nameEn: 'A. Chung',      rating: 71, type: '見習', skill: { name: '見習爆發', phase: 4, bonus: 0.10, desc: '減3/5磅' }, apprenticeAllowance: 5, pullUpMultiplier: 1.0 },
  { id: 'wong_e',    name: '黃智弘',   nameEn: 'E. Wong',       rating: 70, type: '見習', skill: { name: '見習超爆', phase: 4, bonus: 0.15, desc: '減7/10磅' }, apprenticeAllowance: 7, pullUpMultiplier: 1.0 },
  { id: 'yuen',      name: '袁幸堯',   nameEn: 'H.Y. Yuen',     rating: 68, type: '見習', skill: { name: '見習爆發', phase: 4, bonus: 0.15, desc: '減10磅' }, apprenticeAllowance: 10, pullUpMultiplier: 1.0 },
  { id: 'wong_pn',   name: '黃寶妮',   nameEn: 'P.N. Wong',     rating: 68, type: '見習', skill: { name: '女見習加成', phase: 4, bonus: 0.12, desc: '減10磅' }, apprenticeAllowance: 10, pullUpMultiplier: 1.0 },
  // 傳奇 (僅限經典名駒)
  { id: 'moreira',   name: '莫雷拉',   nameEn: 'J. Moreira',    rating: 96, type: '傳奇級', skill: { name: '末段衝刺', phase: 4, bonus: 0.15, desc: '傳奇直路王' }, pullUpMultiplier: 1.0, legendOnly: true },
  { id: 'coetzee',   name: '高雅志',   nameEn: 'F. Coetzee',    rating: 95, type: '傳奇級', skill: { name: '沿途走位', phase: 2, bonus: 0.15, desc: '傳奇走位' }, pullUpMultiplier: 1.0, legendOnly: true },
  { id: 'fradd',     name: '霍達',     nameEn: 'R. Fradd',      rating: 94, type: '傳奇級', skill: { name: '短途爆發', phase: 4, bonus: 0.15, desc: '傳奇短途' }, pullUpMultiplier: 1.0, legendOnly: true },
  { id: 'prebble',   name: '柏寶',     nameEn: 'B. Prebble',    rating: 93, type: '傳奇級', skill: { name: '全面型', phase: 0, bonus: 0.15, desc: '傳奇全面' }, pullUpMultiplier: 1.0, legendOnly: true },
];

// Get active (non-legend) jockeys for race assignment
export function getActiveJockeys() {
  return JOCKEYS.filter(j => !j.legendOnly);
}

// Get jockey by ID
export function getJockeyById(id) {
  return JOCKEYS.find(j => j.id === id);
}
