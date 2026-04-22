/**
 * 旺財街機 — 練馬師資料庫 (15 位)
 */

export const TRAINERS = [
  { id: 'fcp',  name: '方嘉柏',   nameEn: 'F. Lor',        rating: 92, skill: { name: '冠軍練馬師', stat: 'consistency', bonus: 0.10 } },
  { id: 'cyj',  name: '蔡約翰',   nameEn: 'J. Size',       rating: 90, skill: { name: '老牌練馬師', stat: 'stamina', bonus: 0.08 } },
  { id: 'wd',   name: '韋達',     nameEn: 'C. Fownes',     rating: 88, skill: { name: '國際級', stat: 'all', bonus: 0.05 } },
  { id: 'ybf',  name: '姚本輝',   nameEn: 'D. Whyte',      rating: 85, skill: { name: '首出馬專家', stat: 'baseSpeed', bonus: 0.12, condition: 'debut' } },
  { id: 'kdt',  name: '告東尼',   nameEn: 'A. Cruz',       rating: 84, skill: { name: '大賽馬培育', stat: 'baseSpeed', bonus: 0.08, condition: 'heavy_weight' } },
  { id: 'ljw',  name: '呂健威',   nameEn: 'K. Lui',        rating: 83, skill: { name: '長途馬訓練', stat: 'stamina', bonus: 0.10, condition: 'long_distance' } },
  { id: 'hx',   name: '賀賢',     nameEn: 'D. Hall',       rating: 82, skill: { name: '外戰馬專家', stat: 'baseSpeed', bonus: 0.07, condition: 'import' } },
  { id: 'dhs',  name: '大衛希斯', nameEn: 'D. Hayes',      rating: 81, skill: { name: '回勇馬專家', stat: 'baseSpeed', bonus: 0.10, condition: 'comeback' } },
  { id: 'wjl',  name: '文家良',   nameEn: 'R. Gibson',     rating: 80, skill: { name: '短途馬訓練', stat: 'burstPower', bonus: 0.10, condition: 'short_distance' } },
  { id: 'ytp',  name: '容天鵬',   nameEn: 'M. Chang',      rating: 79, skill: { name: '年輕馬培育', stat: 'baseSpeed', bonus: 0.10, condition: 'young_horse' } },
  { id: 'dkh',  name: '丁冠豪',   nameEn: 'P. Ting',       rating: 78, skill: { name: '冷門馬培育', stat: 'burstChance', bonus: 0.08 } },
  { id: 'mld',  name: '苗禮德',   nameEn: 'C. Shum',       rating: 77, skill: { name: '試閘最佳', stat: 'baseSpeed', bonus: 0.12, condition: 'barrier_trial' } },
  { id: 'sjc',  name: '沈集成',   nameEn: 'W. So',         rating: 76, skill: { name: '全天候跑道', stat: 'dirtPreference', bonus: 0.12 } },
  { id: 'xys',  name: '徐雨石',   nameEn: 'B. Yiu',        rating: 75, skill: { name: '跑馬地專家', stat: 'baseSpeed', bonus: 0.08, condition: 'happy_valley' } },
  { id: 'hls',  name: '霍利時',   nameEn: 'P. O\'Sullivan', rating: 74, skill: { name: '穩定發揮', stat: 'consistency', bonus: 0.10 } },
];

export function getTrainerById(id) {
  return TRAINERS.find(t => t.id === id);
}
